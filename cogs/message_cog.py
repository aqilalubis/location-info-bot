import asyncio
import logging
import random
from io import BytesIO
from typing import TYPE_CHECKING, Callable

import discord
from discord import app_commands
from discord.ext import commands

from locations_container import Location, LocationsContainer

if TYPE_CHECKING:
    from bot import MyBot

logger = logging.getLogger(__name__)


async def setup(bot: "MyBot"):
    while not isinstance(bot.get_cog("FormatSettings"), commands.Cog):
        await asyncio.sleep(1)
    await bot.add_cog(Message(bot))


async def send_chunks(
    channel: discord.TextChannel | discord.DMChannel, chunks: list[str | bytes]
):
    for chunk in chunks:
        if isinstance(chunk, bytes):
            await channel.send(file=discord.File(BytesIO(chunk), "location.png"))
        elif isinstance(chunk, str):
            await channel.send(chunk)
        await asyncio.sleep(0.5)


async def send_greetings(message: discord.Message, possible_locations: list[Location]):
    greetings = ["Hello there!", "Hey,", "Yo,", "Woah!"]
    if len(possible_locations) == 1:
        found_locations_str = (
            f"{random.choice(greetings)} I found a location in your message:  "
        )
    else:
        found_locations_str = (
            f"{random.choice(greetings)} I found some locations in your message: "
        )
    for i, location in enumerate(possible_locations):
        if location.name is None:
            raise Exception("Location name is not defined.")
        if i == len(possible_locations) - 1:
            found_locations_str += location.name + "."
        else:
            found_locations_str += location.name + "; "
    await message.reply(found_locations_str, mention_author=False)


class Message(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot: commands.Bot = bot
        self.locations: LocationsContainer = bot.locations
        if not isinstance(cog := bot.get_cog("FormatSettings"), commands.Cog):
            raise Exception
        self.format_cog: commands.Cog = cog
        self.reply_locations: dict[int, list[Location]] = {}
        self.current_messages: dict[int, asyncio.Task] = {}
        self.finding_locations: dict[int, bool] = {}

    async def cancel_message(self, channel: discord.TextChannel | discord.DMChannel):
        if isinstance(self.finding_locations.get(channel.id), bool):
            while self.finding_locations.get(channel.id):
                await asyncio.sleep(0.5)
        self.finding_locations[channel.id] = True

        if current_task := self.current_messages.get(channel.id):
            current_task.cancel()
            del self.current_messages[channel.id]
            await asyncio.sleep(0.5)
            await channel.send("== MESSAGE CANCELLED ==")
            await asyncio.sleep(0.5)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        if not isinstance(message.channel, (discord.DMChannel, discord.TextChannel)):
            raise NotImplementedError("Not DM or text channel.")

        await self.cancel_message(message.channel)

        possible_locations = await self.locations.get_possible_locations(
            message.content
        )

        # Send location info
        if not possible_locations:
            self.finding_locations[message.channel.id] = False
            return
        emoji = "👀"
        await message.add_reaction(emoji)

        try:
            await send_greetings(message, possible_locations)
            await self.send_location_info(message.channel, possible_locations)
        except Exception as e:
            logger.error(e)

    @app_commands.command(
        name="continue",
        description="Continue a previously sent message with the next location",
    )
    async def _continue(self, interaction: discord.Interaction) -> None:
        if not isinstance(
            interaction.channel, (discord.DMChannel, discord.TextChannel)
        ):
            raise NotImplementedError("Not DM or text channel.")
        if self.finding_locations.get(
            interaction.channel.id
        ) or self.current_messages.get(interaction.channel.id):
            await interaction.response.send_message("Continuing...")
        await self.cancel_message(interaction.channel)
        if not self.reply_locations.get(interaction.channel.id):
            if interaction.response.is_done():
                await interaction.followup.send("No locations to continue...")
            else:
                await interaction.response.send_message("No locations to continue...")
            self.finding_locations[interaction.channel.id] = False
            return

        await asyncio.sleep(
            0.5
        )  # Prevent !continue from triggering before on_message and cancelling

        reply_locations = self.reply_locations[interaction.channel.id]
        await self.send_location_info(
            interaction.channel,
            reply_locations,
            interaction=interaction,
        )

    async def send_location_info(
        self,
        channel: discord.DMChannel | discord.TextChannel,
        possible_locations: list[Location],
        interaction: None | discord.Interaction = None,
    ):
        if not possible_locations:
            raise Exception("Empty possible_locations.")
        if not isinstance(current_task := asyncio.current_task(), asyncio.Task):
            raise NotImplementedError("Current task is not defined.")
        self.current_messages[channel.id] = current_task
        self.reply_locations[channel.id] = possible_locations[1:]
        self.finding_locations[channel.id] = False

        location = possible_locations[0]
        if not isinstance(
            summary := getattr(self.format_cog, "is_summary"), Callable
        ) or not isinstance(
            markdown := getattr(self.format_cog, "is_markdown"), Callable
        ):
            raise Exception
        is_summary = summary(channel)
        is_markdown = markdown(channel)
        if len(possible_locations) > 1:
            continue_location = possible_locations[1].name
            if continue_location is None:
                raise Exception("Location's name was undefined.")
        else:
            continue_location = ""
        reply = await location.get_reply_chunks(
            is_summary, is_markdown, continue_location
        )

        if interaction is not None:
            if interaction.response.is_done():
                await interaction.followup.send(reply.pop(0))
            else:
                await interaction.response.send_message(reply.pop(0))
        await send_chunks(channel, reply)
        del self.current_messages[channel.id]
