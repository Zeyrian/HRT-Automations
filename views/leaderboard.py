import io
from datetime import datetime, timezone

import discord

from checks import is_shift_admin
from leaderboard import build_raw_data


class LeaderboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.interaction = None

    async def on_timeout(self):
        if self.interaction:
            try:
                await self.interaction.edit_original_response(view=None)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Raw Shift Data", style=discord.ButtonStyle.secondary)
    async def raw_data(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_shift_admin(interaction.user):
            await interaction.response.send_message(
                "Only shift admins can download the raw shift data.", ephemeral=True
            )
            return

        text = build_raw_data(interaction.guild)
        if text is None:
            await interaction.response.send_message(
                "The leaderboard role isn't set up. Check LEADERBOARD_ROLE_ID in config.py.",
                ephemeral=True,
            )
            return

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        file = discord.File(io.BytesIO(text.encode("utf-8")), filename=f"shift-leaderboard-{stamp}.txt")
        await interaction.response.send_message(file=file)