import os
import traceback

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

EXTENSIONS = [
    "cogs.general",
    "cogs.shifts",
]


async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        message = str(error) or "You can't use this command."
    else:
        traceback.print_exception(type(error), error, error.__traceback__)
        message = "Something went wrong. Check the bot logs."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


class HRTBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.tree.error(on_tree_error)

    async def setup_hook(self):
        for ext in EXTENSIONS:
            await self.load_extension(ext)
        await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user}")


bot = HRTBot()
bot.run(os.getenv("DISCORD_TOKEN"))