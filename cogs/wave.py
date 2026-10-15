import os

import discord
from discord import app_commands
from discord.ext import commands

import config
from checks import admin_only
from database import (
    backup_database,
    count_all_shifts,
    start_shift,
    toggle_break,
    wipe_all_shifts,
)
from leaderboard import build_wave_embeds


async def get_wave_channel(client):
    channel = client.get_channel(config.WAVE_CHANNEL_ID)
    if channel is None:
        try:
            channel = await client.fetch_channel(config.WAVE_CHANNEL_ID)
        except discord.HTTPException:
            return None
    return channel


@app_commands.guild_only()
class Wave(commands.GroupCog, group_name="wave", group_description="HRT wave commands"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(
        name="end",
        description="End the wave: post the results and reset all shifts (admins only)",
    )
    @admin_only()
    async def end(self, interaction: discord.Interaction):
        guild = interaction.guild
        channel = await get_wave_channel(interaction.client)
        quota_seconds = int((config.QUOTA_HOURS or 0) * 3600)
        if (
            channel is None
            or guild.get_role(config.LEADERBOARD_ROLE_ID) is None
            or quota_seconds <= 0
        ):
            await interaction.response.send_message(
                "Wave setup is incomplete. Check WAVE_CHANNEL_ID, LEADERBOARD_ROLE_ID and "
                "QUOTA_HOURS in config.py.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Every open shift is counted up to this moment.
        embeds = build_wave_embeds(
            guild, quota_seconds, note=f"Wave ended by {interaction.user.display_name}"
        )
        if embeds is None:
            await interaction.followup.send(
                "Couldn't build the results. Check LEADERBOARD_ROLE_ID in config.py. "
                "Nothing was changed.",
                ephemeral=True,
            )
            return

        try:
            backup_path = backup_database()
        except Exception as e:
            print(f"Backup failed: {e}")
            await interaction.followup.send(
                "Couldn't create a backup, so nothing was changed.", ephemeral=True
            )
            return

        try:
            for embed in embeds:
                await channel.send(embed=embed)
        except discord.HTTPException as e:
            print(f"Could not post the wave embeds: {e}")
            await interaction.followup.send(
                "Couldn't post everything in the wave channel. Check the bot's permissions "
                "there. Nothing was wiped, but some embeds may already have been posted.",
                ephemeral=True,
            )
            return

        total = count_all_shifts()
        on_shift = wipe_all_shifts()

        # Carry everyone who was on shift (or on break) over into a fresh shift.
        carried = 0
        for uid, on_break in on_shift:
            if guild.get_member(uid) is None:
                continue
            start_shift(uid)
            if on_break:
                toggle_break(uid)
            carried += 1

        await interaction.followup.send(
            f"Wave ended. Results posted in {channel.mention} and {total} shifts wiped. "
            f"{carried} member(s) who were on shift were carried over to a new shift. "
            f"Backup: `{os.path.basename(backup_path)}`",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Wave(bot))