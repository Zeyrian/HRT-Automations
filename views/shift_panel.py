import discord
from shift_roles import set_shift_role

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
from shift_log import log_break, log_end, log_start
from utils import fmt


def build_embed(user):
    now = now_ts()
    shift = get_open_shift(user.id)
    footer = user.display_name
    if not shift:
        embed = discord.Embed(
            title="HRT Shift Panel",
            description="You are **off duty**.",
            color=discord.Color.light_grey(),
        )
    else:
        shift_id, start = shift
        on_break = get_open_break(shift_id) is not None
        breaks = break_total(shift_id, now)
        embed = discord.Embed(
            title="HRT Shift Panel",
            description="You are **on break**." if on_break else "You are **on duty**.",
            color=discord.Color.orange() if on_break else discord.Color.green(),
        )
        embed.add_field(name="Started", value=f"<t:{start}:R>", inline=True)
        embed.add_field(name="Time on duty", value=fmt(now - start - breaks), inline=True)
        embed.add_field(name="Break time", value=fmt(breaks), inline=True)
        footer = f"{user.display_name} · Shift #{shift_id}"
    embed.add_field(name="Total shift time", value=fmt(total_time(user.id, now)), inline=False)
    embed.set_footer(text=footer)
    return embed


class ShiftView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user
        self.message = None
        self.refresh_buttons()

    def refresh_buttons(self):
        shift = get_open_shift(self.user.id)
        on_break = bool(shift and get_open_break(shift[0]))
        self.start_btn.disabled = bool(shift)
        self.break_btn.disabled = not shift
        self.break_btn.label = "End Break" if on_break else "Take Break"
        self.break_btn.style = (
            discord.ButtonStyle.primary if on_break else discord.ButtonStyle.secondary
        )
        self.end_btn.disabled = not shift

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This isn't your panel.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def update(self, interaction: discord.Interaction, embed=None):
        self.refresh_buttons()
        await interaction.response.edit_message(
            embed=embed or build_embed(self.user), view=self
        )

    @discord.ui.button(label="Start Shift", style=discord.ButtonStyle.success)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        shift_id = start_shift(self.user.id)
        await self.update(interaction)
        if shift_id:
            await set_shift_role(self.user, "on_duty")
            await log_start(interaction.client, self.user, shift_id)

    @discord.ui.button(label="Take Break", style=discord.ButtonStyle.secondary)
    async def break_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = toggle_break(self.user.id)
        await self.update(interaction)
        if result:
            shift_id, action, seconds = result
            await set_shift_role(self.user, "on_break" if action == "started" else "on_duty")
            await log_break(interaction.client, self.user, shift_id, action, seconds)

    @discord.ui.button(label="End Shift", style=discord.ButtonStyle.danger)
    async def end_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = end_shift(self.user.id)
        summary = None
        if result:
            shift_id, on_duty, breaks = result
            summary = discord.Embed(title="Shift ended", color=discord.Color.red())
            summary.add_field(name="Time on duty", value=fmt(on_duty), inline=True)
            summary.add_field(name="Break time", value=fmt(breaks), inline=True)
            summary.add_field(name="Shift ID", value=f"#{shift_id}", inline=True)
            summary.set_footer(text=self.user.display_name)
        await self.update(interaction, embed=summary)
        if result:
            await set_shift_role(self.user, "off")
            await log_end(interaction.client, self.user, shift_id, on_duty, breaks)