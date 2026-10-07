import discord
from discord import app_commands
from discord.ext import commands

from database import (
    break_total,
    count_shifts,
    get_active_shifts,
    get_open_break,
    get_open_shift,
    now_ts,
    total_time,
)
from utils import fmt
from views.shift_panel import ShiftView, build_embed


class Shifts(commands.GroupCog, group_name="shift", group_description="HRT shift commands"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="manage", description="Open your shift panel")
    async def manage(self, interaction: discord.Interaction):
        view = ShiftView(interaction.user)
        await interaction.response.send_message(embed=build_embed(interaction.user), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="active", description="See who is currently on shift")
    async def active(self, interaction: discord.Interaction):
        now = now_ts()
        rows = get_active_shifts()

        on_duty, on_break = [], []
        for shift_id, uid, start in rows:
            worked = now - start - break_total(shift_id, now)
            line = f"<@{uid}> ({fmt(worked)})"
            if get_open_break(shift_id):
                on_break.append(line)
            else:
                on_duty.append(line)

        if not rows:
            embed = discord.Embed(
                title="Active Shifts",
                description="Nobody is on shift right now.",
                color=discord.Color.light_grey(),
            )
        else:
            sections = []
            if on_duty:
                sections.append("**On Duty**\n" + "\n".join(on_duty))
            if on_break:
                sections.append("**On Break**\n" + "\n".join(on_break))
            embed = discord.Embed(
                title="Active Shifts",
                description="\n\n".join(sections),
                color=discord.Color.green(),
            )
            embed.set_footer(text=f"{len(rows)} on shift")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="time", description="Show total shift time")
    @app_commands.describe(member="Member to check (defaults to you)")
    async def shift_time(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        now = now_ts()

        open_shift = get_open_shift(target.id)
        if not open_shift:
            status, color = "Off Duty", discord.Color.light_grey()
        elif get_open_break(open_shift[0]):
            status, color = "On Break", discord.Color.orange()
        else:
            status, color = "On Duty", discord.Color.green()

        embed = discord.Embed(title="Shift Time", color=color)
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
        embed.add_field(name="Total time on duty", value=fmt(total_time(target.id, now)), inline=False)
        embed.add_field(name="Shifts logged", value=str(count_shifts(target.id)), inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        embed.set_footer(text="Break time is excluded")
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Shifts(bot))