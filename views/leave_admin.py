import discord

import config
from leave_db import end_early, get_active, get_pending, get_recent, grant
from views.leave_panel import notify_member


def build_leave_admin_embed(target):
    active = get_active(target.id)
    pending = get_pending(target.id)
    if active:
        status, color = "On Leave", discord.Color.green()
    elif pending:
        status, color = "Request Pending", discord.Color.orange()
    else:
        status, color = "No Active Leave", discord.Color.light_grey()

    embed = discord.Embed(title="Leave Admin", color=color)
    embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
    embed.add_field(name="Status", value=status, inline=True)
    if active:
        embed.add_field(name="Leave ID", value=f"#{active['id']}", inline=True)
        embed.add_field(name="Ends", value=f"<t:{active['end_ts']}:R>", inline=True)

    recent = get_recent(target.id, 5)
    if recent:
        lines = []
        for leave in recent:
            reason = leave["reason"]
            if len(reason) > 60:
                reason = reason[:57] + "..."
            lines.append(
                f"`#{leave['id']}` · {leave['status'].capitalize()} · {leave['days']}d · {reason}"
            )
        embed.add_field(name="Recent leaves", value="\n".join(lines), inline=False)

    embed.set_footer(text=f"Member ID: {target.id}")
    return embed


class GrantModal(discord.ui.Modal, title="Grant Leave"):
    days = discord.ui.TextInput(label="Duration (days)", placeholder="e.g. 7", max_length=3)
    reason = discord.ui.TextInput(
        label="Reason", style=discord.TextStyle.paragraph, max_length=500
    )

    def __init__(self, panel):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        target = self.panel.target
        try:
            days = int(self.days.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "Enter the duration as a whole number of days.", ephemeral=True
            )
            return
        if not 1 <= days <= config.MAX_LEAVE_DAYS:
            await interaction.response.send_message(
                f"Leave must be between 1 and {config.MAX_LEAVE_DAYS} days.", ephemeral=True
            )
            return
        reason = self.reason.value.strip()
        if not reason:
            await interaction.response.send_message("Please give a reason.", ephemeral=True)
            return
        if get_active(target.id) or get_pending(target.id):
            await interaction.response.send_message(
                "They already have an active leave or a pending request.", ephemeral=True
            )
            return

        leave_id = grant(target.id, days, reason, interaction.user.id)
        await self.panel.refresh(
            interaction, notice=f"Granted leave #{leave_id} for {days} day(s)."
        )
        await notify_member(
            target,
            f"An admin granted you a leave of absence ({days} day(s)) in {interaction.guild.name}.",
        )


class LeaveAdminView(discord.ui.View):
    def __init__(self, admin, target):
        super().__init__(timeout=300)
        self.admin = admin
        self.target = target
        self.interaction = None
        self.refresh_buttons()

    def refresh_buttons(self):
        active = get_active(self.target.id)
        pending = get_pending(self.target.id)
        self.grant_btn.disabled = bool(active or pending)
        self.end_btn.disabled = active is None

    async def refresh(self, interaction: discord.Interaction, notice=None):
        self.refresh_buttons()
        await interaction.response.edit_message(
            content=notice, embed=build_leave_admin_embed(self.target), view=self
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

    @discord.ui.button(label="Grant Leave", style=discord.ButtonStyle.success)
    async def grant_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GrantModal(self))

    @discord.ui.button(label="End Leave Early", style=discord.ButtonStyle.danger)
    async def end_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        leave_id = end_early(self.target.id)
        notice = f"Ended leave #{leave_id} early." if leave_id else "They have no active leave."
        await self.refresh(interaction, notice=notice)
        if leave_id:
            await notify_member(
                self.target,
                f"Your leave #{leave_id} in {interaction.guild.name} was ended early by an admin.",
            )