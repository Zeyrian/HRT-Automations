import discord
from discord import app_commands
from discord.ext import commands

import config
from checks import admin_only
from leaderboard import build_quota_embeds


class Activity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="activity",
        description="Show who has and hasn't met the shift quota (admins only)",
    )
    @app_commands.guild_only()
    @admin_only()
    async def activity(self, interaction: discord.Interaction):
        if not config.QUOTA_HOURS:
            await interaction.response.send_message(
                "The quota isn't set. Set QUOTA_HOURS in config.py.", ephemeral=True
            )
            return

        embeds = build_quota_embeds(interaction.guild, int(config.QUOTA_HOURS * 3600))
        if embeds is None:
            await interaction.response.send_message(
                "The leaderboard role isn't set up. Check LEADERBOARD_ROLE_ID in config.py.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(embed=embeds[0])
        await interaction.followup.send(embed=embeds[1])


async def setup(bot):
    await bot.add_cog(Activity(bot))