import asyncio
import json
import logging.config
import os

import discord
from discord.ext import commands

from keep_alive import keep_alive
from locations_container import LocationsContainer
from locations_from_wiki import create_locations

logger = logging.getLogger(__name__)


class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.locations = LocationsContainer()

    async def setup_hook(self) -> None:
        self.locations = await create_locations()
        async with asyncio.TaskGroup() as tg:
            for cog_file in os.listdir("cogs"):
                if cog_file.endswith(".py"):
                    tg.create_task(self.load_extension(f"cogs.{cog_file[:-3]}"))

    async def load_extension(self, *args, **kwargs):
        await super().load_extension(*args, **kwargs)
        logger.info(f"Loaded {args[0]}.")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user}")


async def main():
    with open("logging_config.json", "rt") as f:
        log_config = json.load(f)
    logging.config.dictConfig(log_config)

    intents = discord.Intents.default()
    intents.message_content = True
    bot = MyBot(command_prefix="!", intents=intents)
    try:
        bot_token = os.environ["BOT_TOKEN"]
        await bot.start(bot_token)
    except KeyError:
        logger.info("BOT_TOKEN environment variable is not defined.")


if __name__ == "__main__":
    keep_alive()  # For 24/7 hosting capability
    my_bot = asyncio.run(main())
