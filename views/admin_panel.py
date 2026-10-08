from datetime import datetime, timezone

import discord

from database import (
    break_total,
    count_shifts,
    delete_shift,
    end_shift,
    get_open_break,
    get_open_shift,
    get_recent_shifts,
    modify_shift,
    now_ts,
    shift_on_duty,
    start_shift,
    toggle_break,
    total_time,
)
from shift_log import log_break, log_delete, log_end, log_modify, log_start
from shift_roles import set_shift_role
from utils import fmt


def build_admin_embed(target):
    now = now_ts()
    shift = get_open_shift(target.id)
    if not shift:
        status, color = "Off Duty", discord.Color.light_grey()
    elif get_open_break(shift[0]):
        status, color = "On Break", discord.Color.orange()
    else:
        status, color = "On Duty", discord.Color.green()

    embed = discord.Embed(title="Shift Admin", color=color)
    embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Total shift time", value=fmt(total_time(target.id, now)), inline=True)
    embed.add_field(name="Shifts logged", value=str(count_shifts(target.id)), inline=True)

    if shift:
        shift_id, start = shift
        breaks = break_total(shift_id, now)
        embed.add_field(name="Current shift", value=f"#{shift_id} · started <t:{start}:R>", inline=True)
        embed.add_field(name="Time on duty", value=fmt(now - start - breaks), inline=True)
        embed.add_field(name="Break time", value=fmt(breaks), inline=True)

    recent = get_recent_shifts(target.id, 5)
    if recent:
        lines = []
        for sid, start, end in recent:
            duration = fmt(shift_on_duty(sid, start, end, now))
            lines.append(f"`#{sid}` · <t:{start}:d> · {duration}" + (" · open" if end is None else ""))
        embed.add_field(name="Recent shifts", value="\n".join(lines), inline=False)

    embed.set_footer(text=f"Member ID: {target.id}")
    return embed


class ModeSelect(discord.ui.Select):
    def __init__(self, mode):
        options = [
            discord.SelectOption(
                label="Delete Shift", value="delete",
                description="Permanently delete one of the member's shifts",
                default=mode == "delete",
            ),
            discord.SelectOption(
                label="Modify Shift", value="modify",
                description="Add or remove time on one of the member's shifts",
                default=mode == "modify",
            ),
            discord.SelectOption(
                label="General", value="general",
                description="Start, break or end the member's shift",
                default=mode == "general",
            ),
        ]
        super().__init__(placeholder="Choose an action", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.mode = self.values[0]
        view.selected_shift = None
        await view.refresh(interaction)


class ShiftSelect(discord.ui.Select):
    def __init__(self, target, selected):
        now = now_ts()
        options = []
        for sid, start, end in get_recent_shifts(target.id, 25):
            when = datetime.fromtimestamp(start, tz=timezone.utc).strftime("%d %b %Y %H:%M UTC")
            duration = fmt(shift_on_duty(sid, start, end, now))
            options.append(
                discord.SelectOption(
                    label=f"Shift #{sid}" + (" (open)" if end is None else ""),
                    value=str(sid),
                    description=f"{when} · {duration}",
                    default=selected == sid,
                )
            )
        disabled = not options
        if not options:
            options = [discord.SelectOption(label="No shifts found", value="none")]
        super().__init__(placeholder="Select a shift", options=options, disabled=disabled, row=1)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.selected_shift = int(self.values[0])
        await view.refresh(interaction)


class StartButton(discord.ui.Button):
    def __init__(self, disabled):
        super().__init__(label="Start Shift", style=discord.ButtonStyle.success, disabled=disabled, row=1)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        shift_id = start_shift(view.target.id)
        await view.refresh(interaction)
        if shift_id:
            await set_shift_role(view.target, "on_duty")
            await log_start(interaction.client, view.target, shift_id, by=view.admin)


class BreakButton(discord.ui.Button):
    def __init__(self, on_break, disabled):
        super().__init__(
            label="End Break" if on_break else "Take Break",
            style=discord.ButtonStyle.primary if on_break else discord.ButtonStyle.secondary,
            disabled=disabled,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        result = toggle_break(view.target.id)
        await view.refresh(interaction)
        if result:
            shift_id, action, seconds = result
            await set_shift_role(view.target, "on_break" if action == "started" else "on_duty")
            await log_break(interaction.client, view.target, shift_id, action, seconds, by=view.admin)


class EndButton(discord.ui.Button):
    def __init__(self, disabled):
        super().__init__(label="End Shift", style=discord.ButtonStyle.danger, disabled=disabled, row=1)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        result = end_shift(view.target.id)
        await view.refresh(interaction)
        if result:
            shift_id, on_duty, breaks = result
            await set_shift_role(view.target, "off")
            await log_end(interaction.client, view.target, shift_id, on_duty, breaks, by=view.admin)


class DeleteButton(discord.ui.Button):
    def __init__(self, selected):
        super().__init__(
            label=f"Delete Shift #{selected}" if selected else "Delete Shift",
            style=discord.ButtonStyle.danger,
            disabled=selected is None,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        shift_id = view.selected_shift
        on_duty = delete_shift(shift_id, view.target.id)
        view.selected_shift = None
        if on_duty is None:
            await view.refresh(interaction, notice="That shift no longer exists.")
            return
        await view.refresh(interaction, notice=f"Deleted shift #{shift_id}.")
        if get_open_shift(view.target.id) is None:
            await set_shift_role(view.target, "off")
        await log_delete(interaction.client, view.target, shift_id, on_duty, by=view.admin)


class AdjustModal(discord.ui.Modal, title="Adjust Shift Time"):
    minutes = discord.ui.TextInput(
        label="Minutes to add (negative to remove)",
        placeholder="e.g. 30 or -15",
        max_length=6,
    )

    def __init__(self, panel, shift_id):
        super().__init__()
        self.panel = panel
        self.shift_id = shift_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            minutes = int(self.minutes.value.strip())
        except ValueError:
            await interaction.response.send_message("Enter a whole number of minutes.", ephemeral=True)
            return
        if minutes == 0 or abs(minutes) > 1440:
            await interaction.response.send_message(
                "Enter a number between -1440 and 1440 (not 0).", ephemeral=True
            )
            return

        new_on_duty, error = modify_shift(self.shift_id, self.panel.target.id, minutes)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await self.panel.refresh(
            interaction, notice=f"Adjusted shift #{self.shift_id} by {minutes:+d} min."
        )
        await log_modify(
            interaction.client, self.panel.target, self.shift_id, minutes, new_on_duty, by=self.panel.admin
        )


class AdjustButton(discord.ui.Button):
    def __init__(self, selected):
        super().__init__(
            label="Adjust Time",
            style=discord.ButtonStyle.primary,
            disabled=selected is None,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        await interaction.response.send_modal(AdjustModal(view, view.selected_shift))


class AdminView(discord.ui.View):
    def __init__(self, admin, target):
        super().__init__(timeout=300)
        self.admin = admin
        self.target = target
        self.mode = None
        self.selected_shift = None
        self.interaction = None
        self.rebuild()

    def rebuild(self):
        self.clear_items()
        self.add_item(ModeSelect(self.mode))
        if self.mode == "general":
            shift = get_open_shift(self.target.id)
            on_break = bool(shift and get_open_break(shift[0]))
            self.add_item(StartButton(disabled=bool(shift)))
            self.add_item(BreakButton(on_break, disabled=not shift))
            self.add_item(EndButton(disabled=not shift))
        elif self.mode in ("delete", "modify"):
            self.add_item(ShiftSelect(self.target, self.selected_shift))
            if self.mode == "delete":
                self.add_item(DeleteButton(self.selected_shift))
            else:
                self.add_item(AdjustButton(self.selected_shift))

    async def refresh(self, interaction: discord.Interaction, notice=None):
        self.rebuild()
        await interaction.response.edit_message(
            content=notice, embed=build_admin_embed(self.target), view=self
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin.id:
            await interaction.response.send_message("This isn't your panel.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.interaction:
            try:
                await self.interaction.edit_original_response(view=None)
            except discord.HTTPException:
                pass