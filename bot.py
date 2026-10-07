import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

EXTENSIONS = [
    "cogs.general",
    "cogs.shifts",
]


class HRTBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.default(),
        )

    async def setup_hook(self):
        for ext in EXTENSIONS:
            await self.load_extension(ext)
        await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user}")


bot = HRTBot()
bot.run(os.getenv("DISCORD_TOKEN"))