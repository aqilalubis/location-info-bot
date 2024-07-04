from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from bot import MyBot


class FormatSettings(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.guild_settings = {}
        self.default_settings = {"is_summary": True, "is_markdown": True}

    def is_summary(self, channel: discord.TextChannel | discord.DMChannel) -> bool:
        if isinstance(channel, discord.TextChannel):
            guild_id = channel.guild.id
        else:
            guild_id = channel.id
        is_summary = self.guild_settings.get(guild_id, self.default_settings)[
            "is_summary"
        ]

        return is_summary

    def is_markdown(self, channel: discord.TextChannel | discord.DMChannel) -> bool:
        if isinstance(channel, discord.TextChannel):
            guild_id = channel.guild.id
        else:
            guild_id = channel.id
        is_markdown = self.guild_settings.get(guild_id, self.default_settings)[
            "is_markdown"
        ]

        return is_markdown

    @app_commands.command(
        description="Provide a True/False argument to set whether the message should be summarised.",
    )
    async def summary(
        self,
        interaction: discord.Interaction,
        argument: bool,
    ) -> None:
        if isinstance(interaction.channel, discord.TextChannel):
            guild_id = interaction.channel.guild.id
        elif isinstance(interaction.channel, discord.DMChannel):
            guild_id = interaction.channel.id
        else:
            raise NotImplementedError
        self.guild_settings[guild_id] = self.guild_settings.get(
            guild_id, self.default_settings
        )
        self.guild_settings[guild_id]["is_summary"] = argument
        if argument:
            await interaction.response.send_message('Content type is now "summary"')
        else:
            await interaction.response.send_message(
                'Content type is no longer "summary"'
            )

    @app_commands.command(
        description="Provide a True/False argument to set whether the message should be in markdown "
        "format.",
    )
    async def markdown(
        self,
        interaction: discord.Interaction,
        argument: bool,
    ) -> None:
        if isinstance(interaction.channel, discord.TextChannel):
            guild_id = interaction.channel.guild.id
        elif isinstance(interaction.channel, discord.DMChannel):
            guild_id = interaction.channel.id
        else:
            raise NotImplementedError
        self.guild_settings[guild_id] = self.guild_settings.get(
            guild_id, self.default_settings
        )
        self.guild_settings[guild_id]["is_markdown"] = argument
        await interaction.response.send_message(
            f"Markdown message formatting set to: {argument}"
        )


async def setup(bot: "MyBot"):
    await bot.add_cog(FormatSettings(bot))
