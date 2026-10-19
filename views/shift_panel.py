import discord

import config
from database import (
    break_total,
    end_shift,
    get_open_break,
    get_open_shift,
    now_ts,
    start_shift,
    toggle_break,
    total_time,
)
from leaderboard import is_exempt
from shift_log import log_break, log_end, log_start
from shift_roles import set_shift_role
from utils import fmt_short

NO_PINGS = discord.AllowedMentions.none()


class ShiftView(discord.ui.LayoutView):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user
        self.interaction = None
        self.build()

    def requirement_text(self, total):
        if not config.QUOTA_HOURS:
            return None
        if is_exempt(self.user):
            return "Exempt"
        if total >= int(config.QUOTA_HOURS * 3600):
            return "Requirement met"
        return "Requirement not met"

    def build(self, disabled=False):
        self.clear_items()
        now = now_ts()
        shift = get_open_shift(self.user.id)
        on_break = bool(shift and get_open_break(shift[0]))

        if not shift:
            status, current = "Off Duty", "None"
        else:
            shift_id, start = shift
            status = "On Break" if on_break else "On Duty"
            current = fmt_short(now - start - break_total(shift_id, now))

        total = total_time(self.user.id, now)
        lines = [
            f"**Status:** {status}",
            f"**Current Shift:** {current}",
            f"**Total This Wave:** {fmt_short(total)}",
        ]
        requirement = self.requirement_text(total)
        if requirement:
            lines.append(f"**Requirement:** {requirement}")

        start_btn = discord.ui.Button(
            label="Start Shift",
            style=discord.ButtonStyle.success,
            disabled=disabled or bool(shift),
        )
        start_btn.callback = self.on_start

        break_btn = discord.ui.Button(
            label="End Break" if on_break else "Break",
            style=discord.ButtonStyle.primary if on_break else discord.ButtonStyle.secondary,
            disabled=disabled or not shift,
        )
        break_btn.callback = self.on_break

        end_btn = discord.ui.Button(
            label="End Shift",
            style=discord.ButtonStyle.danger,
            disabled=disabled or not shift,
        )
        end_btn.callback = self.on_end

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "# HRT | Shift Management\n"
                    f"{self.user.mention}\n\n"
                    "Manage your current HRT shift using the buttons below."
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay("\n".join(lines)),
                discord.ui.Separator(),
                discord.ui.ActionRow(start_btn, break_btn, end_btn),
            )
        )

    async def refresh(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self, allowed_mentions=NO_PINGS)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This isn't your panel.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        self.build(disabled=True)
        if self.interaction:
            try:
                await self.interaction.edit_original_response(view=self)
            except discord.HTTPException:
                pass

    async def on_start(self, interaction: discord.Interaction):
        shift_id = start_shift(self.user.id)
        await self.refresh(interaction)
        if shift_id:
            await set_shift_role(self.user, "on_duty")
            await log_start(interaction.client, self.user, shift_id)

    async def on_break(self, interaction: discord.Interaction):
        result = toggle_break(self.user.id)
        await self.refresh(interaction)
        if result:
            shift_id, action, seconds = result
            await set_shift_role(self.user, "on_break" if action == "started" else "on_duty")
            await log_break(interaction.client, self.user, shift_id, action, seconds)

    async def on_end(self, interaction: discord.Interaction):
        result = end_shift(self.user.id)
        await self.refresh(interaction)
        if result:
            shift_id, on_duty, breaks = result
            await set_shift_role(self.user, "off")
            await log_end(interaction.client, self.user, shift_id, on_duty, breaks)