import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from bot import MyBot

logger = logging.getLogger(__name__)


class Owner(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    @app_commands.command()
    @commands.is_owner()
    async def reload(self, interaction: discord.Interaction):
        synced = await self.bot.tree.sync()
        logger.info(f"Synced {len(synced)} app command(s)")
        await interaction.response.send_message(
            f"Synced {len(synced)} app command(s)", silent=True
        )

    @app_commands.command()
    @commands.is_owner()
    async def shutdown(self, interaction: discord.Interaction):
        logger.info("Shutting down")
        await interaction.response.send_message("Shutting down", silent=True)
        await self.bot.close()


async def setup(bot: "MyBot"):
    await bot.add_cog(Owner(bot))
