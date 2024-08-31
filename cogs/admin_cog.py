from __future__ import annotations

import asyncio
import logging
import re
import string
import time
import typing
from math import floor
from typing import TYPE_CHECKING, Callable

import discord
from discord import app_commands
from discord.ext import commands
from unidecode import unidecode

from locations_container import Location, LocationsContainer

if TYPE_CHECKING:
    from bot import MyBot


logger = logging.getLogger(__name__)


async def setup(bot: MyBot):
    while not isinstance(bot.get_cog("Message"), commands.Cog):
        await asyncio.sleep(1)
    await bot.add_cog(AdminCommands(bot))


def is_textchannel():
    def predicate(interaction: discord.Interaction) -> bool:
        return isinstance(interaction.channel, (discord.TextChannel))

    return app_commands.check(predicate)


async def get_channel(
    name: str, guild: discord.Guild, reason: None | str
) -> discord.TextChannel:
    channel_name = unidecode(name).lower()
    for p in string.punctuation:
        channel_name = channel_name.replace(p, "")
    channel_name = channel_name.replace(" ", "-")

    channel = discord.utils.get(guild.channels, name=channel_name)
    if channel is None:
        loc_channel: discord.TextChannel = await guild.create_text_channel(
            name=channel_name, reason=reason
        )
    elif isinstance(channel, discord.TextChannel):
        loc_channel = channel
    else:
        raise Exception("Expected text channel.")

    return loc_channel


class MembersTransformer(app_commands.Transformer):
    async def transform(
        self, interaction: discord.Interaction, value: str
    ) -> list[discord.Member]:
        ctx = await commands.Context.from_interaction(interaction)
        mentions = re.findall(r"@(\w+)", value)
        members = await asyncio.gather(
            *(commands.MemberConverter().convert(ctx, mention) for mention in mentions)
        )

        if not members:
            raise Exception

        return members


class LocationSelect(discord.ui.Select):
    def __init__(self, locations: list[str], coroutines):
        self.location_names = locations
        self.coroutines = coroutines
        options = [
            discord.SelectOption(label=location)
            for location in locations
            if isinstance(location, str)
        ]
        if len(locations) != len(options):
            raise Exception("Location name undefined.")
        super().__init__(placeholder="Choose a more specific location", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"You chose {self.values[0]}.", silent=True
        )
        await self.coroutines[self.location_names.index(self.values[0])]


class LocationView(discord.ui.View):
    def __init__(self, locations: list[str], coroutines):
        super().__init__()
        self.add_item(LocationSelect(locations, coroutines))


async def convert_to_possible_locations(
    ctx: commands.Context, initial: None | str
) -> list[Location]:
    locations: LocationsContainer = ctx.bot.locations

    if initial is None:
        possible_locations = [await locations.random_location()]
        await ctx.send(
            f"Random location chosen: {possible_locations[0].name}", silent=True
        )
    else:
        await ctx.defer()
        possible_locations = await locations.get_possible_locations(initial)
        if not possible_locations:
            raise commands.BadArgument(
                f'No location could be found with name "{initial}".'
            )

        try:
            possible_locations = [
                await locations.search_by_name(
                    initial, possible_locations=possible_locations
                )
            ]
        except KeyError:  # Multiple locations with the same name.
            pass

    return possible_locations


class AdminCommands(commands.Cog):
    def __init__(self, bot: MyBot):
        self.bot: MyBot = bot
        if not isinstance(cog := bot.get_cog("Message"), commands.Cog):
            raise Exception
        self.message_cog: commands.Cog = cog
        self.deported: dict[int, list[dict]] = {}
        self.deporting: dict[int, bool] = {}
        self.queue_count: dict[int, int] = {}
        self.queue_at: dict[int, int] = {}

    async def queueing(self, guild_id: int):
        if self.deporting.get(guild_id):
            queue_number = self.queue_count.get(guild_id, 0)
            self.queue_count[guild_id] = queue_number + 1
            self.queue_at[guild_id] = self.queue_at.get(guild_id, 0)
            while self.deporting[guild_id] or queue_number != self.queue_at[guild_id]:
                await asyncio.sleep(1)
            self.queue_at[guild_id] += 1
            if self.queue_at[guild_id] == self.queue_count[guild_id]:
                del self.queue_at[guild_id]
                del self.queue_count[guild_id]

    async def timed(self, ctx, members, start_time, total_time):
        while time.time() - start_time < total_time:
            await asyncio.sleep(0.5)
        await ctx.send("Timed deport has expired:", silent=True)
        await asyncio.gather(self.import_members(ctx, members))

    async def deport_members(
        self,
        ctx: commands.Context,
        members: list[discord.Member],
        location: Location,
        seconds: None | int = None,
        reason: None | str = None,
    ):
        if location.name is None:
            raise Exception("Location has no name.")

        for member in members[:]:
            if ctx.guild is None:
                raise Exception
            if any(
                member.name == deport_dict["member"]
                for deport_dict in self.deported.get(ctx.guild.id, [])
            ):
                await ctx.send(f"{member} is already deported.", silent=True)
                members.remove(member)
        if not members:
            return

        await self.queueing(ctx.guild.id)

        self.deporting[ctx.guild.id] = True

        try:
            loc_channel = await get_channel(location.name, ctx.guild, reason)
        except Exception:
            await ctx.send(
                "Existing channel of the location already exists that is not a text channel.",
                silent=True,
            )

        # Create location role
        role_name = f"Citizen of {location.name}"
        loc_role = discord.utils.get(ctx.guild.roles, name=role_name)
        if loc_role is None:
            loc_role = await ctx.guild.create_role(
                name=role_name, permissions=discord.Permissions.general(), reason=reason
            )

        for channel in ctx.guild.channels:
            if channel != loc_channel:
                await channel.set_permissions(
                    loc_role, send_messages=False, reason=reason
                )

        start = time.time()
        for member in members:
            prev_roles = [role for role in member.roles if role.name != "@everyone"]
            if ctx.guild is None:
                raise Exception
            self.deported[ctx.guild.id] = self.deported.get(ctx.guild.id, [])
            self.deported[ctx.guild.id].append(
                {
                    "member": member.name,
                    "channel": loc_channel.id,
                    "role": loc_role.id,
                    "prev_roles": prev_roles,
                    "location": location.name,
                    "time": start,
                }
            )

            for role in prev_roles:
                await member.remove_roles(role, reason=reason)
            await member.add_roles(loc_role, reason=reason)

        deported_message = ""
        if seconds:
            deported_message += f"For {seconds} seconds: "
        deported_message += f"{member.name} deported to {location.name}."
        if reason:
            deported_message = deported_message[:-1] + f" for reason: {reason}."
        await ctx.send(deported_message, silent=True)
        if loc_channel != ctx.channel:
            await loc_channel.send(deported_message, silent=True)

        if isinstance(seconds, int):
            await ctx.defer()

        self.deporting[ctx.guild.id] = False
        async with asyncio.TaskGroup() as tg:
            if not isinstance(
                send_location_info := getattr(self.message_cog, "send_location_info"),
                Callable,
            ):
                raise Exception
            tg.create_task(send_location_info(loc_channel, [location]))
            if isinstance(seconds, int):
                tg.create_task(self.timed(ctx, members, start, seconds))

    @app_commands.command()
    @is_textchannel()
    @commands.has_permissions(administrator=True)
    async def deport(
        self,
        interaction: discord.Interaction,
        members: typing.Annotated[
            list[discord.Member], app_commands.Transform[list, MembersTransformer]
        ],
        location: typing.Optional[str],
        seconds: typing.Optional[int],
        reason: typing.Optional[str],
    ):
        ctx = await commands.Context.from_interaction(interaction)
        possible_locations = await convert_to_possible_locations(ctx, location)

        if isinstance(seconds, int) and seconds <= 0:
            await ctx.send("Please input a positive number of seconds", silent=True)
            raise commands.BadArgument

        if len(possible_locations) > 1:
            location_names = [
                location.name
                for location in possible_locations
                if location.name is not None
            ]
            if len(location_names) != len(possible_locations):
                raise Exception("Location's name is undefined.")
            coroutines = [
                self.deport_members(ctx, members, location, seconds, reason)
                for location in possible_locations
            ]
            await interaction.followup.send(
                "Multiple locations by the same name were found, choose a more specific location.",
                view=LocationView(location_names, coroutines),
                silent=True,
            )
            return

        await self.deport_members(ctx, members, possible_locations[0], seconds, reason)

    @deport.error
    async def deport_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        ctx = await commands.Context.from_interaction(interaction)
        if isinstance(error, app_commands.TransformerError):
            error_message = (
                str(error).split()[0].title()
                + " "
                + " ".join(str(error).split()[1:]).lower()
                + "."
            )
            logger.info(error_message)
            await ctx.send(error_message)
        if isinstance(error, app_commands.CheckFailure):
            await ctx.send("Deport can only be called in a text channel.", silent=True)

    async def import_members(
        self, ctx: commands.Context, members: list[discord.Member]
    ):
        await ctx.defer()
        await self.queueing(ctx.guild.id)
        self.deporting[ctx.guild.id] = True
        for member in members:
            for deport_dict in self.deported.get(ctx.guild.id, []):
                if member.name == deport_dict["member"]:
                    break
            else:
                await ctx.send(f"{member} has not been deported.", silent=True)
                return
            total_time = floor(time.time() - deport_dict["time"])
            self.deported[ctx.guild.id].remove(deport_dict)

            loc_channel = discord.utils.get(
                ctx.guild.channels, id=deport_dict["channel"]
            )
            if loc_channel and not any(
                d["channel"] == deport_dict["channel"]
                for d in self.deported[ctx.guild.id]
            ):
                if not isinstance(
                    cancel_message := getattr(self.message_cog, "cancel_message"),
                    Callable,
                ):
                    raise Exception
                await cancel_message(loc_channel)
                await loc_channel.delete()

            loc_role: discord.Role = discord.utils.get(
                ctx.guild.roles, id=deport_dict["role"]
            )
            if loc_role:
                await member.remove_roles(loc_role)
                if not any(
                    d["role"] == deport_dict["role"]
                    for d in self.deported[ctx.guild.id]
                ):
                    await loc_role.delete()

            for role in deport_dict["prev_roles"]:
                if role in ctx.guild.roles:
                    await member.add_roles(role)

            await ctx.send(
                f'{member.name} has been imported from {deport_dict["location"]} after '
                f"{total_time} seconds.",
                silent=True,
            )
        self.deporting[ctx.guild.id] = False

    @app_commands.command(name="import")
    @is_textchannel()
    @commands.has_permissions(administrator=True)
    async def _import(
        self,
        interaction: discord.Interaction,
        members: typing.Annotated[
            list[discord.Member], app_commands.Transform[list, MembersTransformer]
        ],
    ):
        ctx = await commands.Context.from_interaction(interaction)
        await self.import_members(ctx, members)

    @_import.error
    async def import_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        ctx = await commands.Context.from_interaction(interaction)
        if isinstance(error, app_commands.TransformerError):
            error_message = (
                str(error).split()[0].title()
                + " "
                + " ".join(str(error).split()[1:]).lower()
                + "."
            )
            logger.info(error_message)
            await ctx.send(error_message, silent=True)
        if isinstance(error, app_commands.CheckFailure):
            await ctx.send("Import can only be called in a text channel.", silent=True)
