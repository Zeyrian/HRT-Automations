import os

import discord
from discord import app_commands
from discord.ext import commands

import config
from checks import admin_only
from database import backup_database, count_all_shifts, get_active_shifts, wipe_all_shifts
from leaderboard import build_wave_embeds
from shift_roles import set_shift_role


async def get_wave_channel(client):
    channel = client.get_channel(config.WAVE_CHANNEL_ID)
    if channel is None:
        try:
            channel = await client.fetch_channel(config.WAVE_CHANNEL_ID)
        except discord.HTTPException:
            return None
    return channel


class ConfirmView(discord.ui.View):
    def __init__(self, admin):
        super().__init__(timeout=60)
        self.admin = admin
        self.interaction = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin.id:
            await interaction.response.send_message("This isn't your confirmation.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.interaction:
            try:
                await self.interaction.edit_original_response(
                    content="Wave end timed out. Nothing was changed.", embed=None, view=None
                )
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Confirm Wave End", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Ending the wave...", embed=None, view=None)

        guild = interaction.guild
        channel = await get_wave_channel(interaction.client)
        quota_seconds = int((config.QUOTA_HOURS or 0) * 3600)
        embeds = (
            build_wave_embeds(
                guild, quota_seconds, note=f"Wave ended by {self.admin.display_name}"
            )
            if quota_seconds > 0
            else None
        )
        if channel is None or embeds is None:
            await interaction.edit_original_response(
                content=(
                    "Couldn't end the wave. Check WAVE_CHANNEL_ID, LEADERBOARD_ROLE_ID and "
                    "QUOTA_HOURS in config.py. Nothing was changed."
                )
            )
            return

        try:
            backup_path = backup_database()
        except Exception as e:
            print(f"Backup failed: {e}")
            await interaction.edit_original_response(
                content="Couldn't create a backup, so nothing was changed."
            )
            return

        try:
            for embed in embeds:
                await channel.send(embed=embed)
        except discord.HTTPException as e:
            print(f"Could not post the wave embeds: {e}")
            await interaction.edit_original_response(
                content=(
                    "Couldn't post everything in the wave channel. Check the bot's permissions "
                    "there. Nothing was wiped, but some embeds may already have been posted."
                )
            )
            return

        total = count_all_shifts()
        open_users = wipe_all_shifts()
        for uid in open_users:
            member = guild.get_member(uid)
            if member:
                await set_shift_role(member, "off")

        await interaction.edit_original_response(
            content=(
                f"Wave ended. The leaderboard and quota results were posted in {channel.mention} "
                f"and {total} shifts were wiped. Backup: `{os.path.basename(backup_path)}`"
            )
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content="Cancelled. Nothing was changed.", embed=None, view=None
        )


@app_commands.guild_only()
class Wave(commands.GroupCog, group_name="wave", group_description="HRT wave commands"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(
        name="end", description="Post the leaderboard and quota results, then reset all shifts (admins only)"
    )
    @admin_only()
    async def end(self, interaction: discord.Interaction):
        channel = await get_wave_channel(interaction.client)
        if (
            channel is None
            or interaction.guild.get_role(config.LEADERBOARD_ROLE_ID) is None
            or not config.QUOTA_HOURS
        ):
            await interaction.response.send_message(
                "Wave setup is incomplete. Check WAVE_CHANNEL_ID, LEADERBOARD_ROLE_ID and "
                "QUOTA_HOURS in config.py.",
                ephemeral=True,
            )
            return

        total = count_all_shifts()
        active = len(get_active_shifts())
        description = (
            f"This posts the leaderboard and quota results (quota: **{config.QUOTA_HOURS:g}** hours) "
            f"in {channel.mention} and permanently wipes **{total}** shifts.\n"
        )
        if active:
            description += (
                f"**{active}** member(s) are on shift right now. Their shifts will be ended "
                "and their duty roles removed.\n"
            )
        description += "\nA backup of the database is saved first."

        embed = discord.Embed(title="End the wave?", description=description, color=discord.Color.red())
        view = ConfirmView(interaction.user)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.interaction = interaction


async def setup(bot):
    await bot.add_cog(Wave(bot))