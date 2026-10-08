import discord
from discord import app_commands
from discord.ext import commands

import config
from checks import admin_only, is_shift_member
from database import (
    all_totals,
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
from views.admin_panel import AdminView, build_admin_embed


@app_commands.guild_only()
class Shifts(commands.GroupCog, group_name="shift", group_description="HRT shift commands"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_shift_member(interaction.user):
            return True
        raise app_commands.CheckFailure("You need the shift role to use shift commands.")

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

    @app_commands.command(name="leaderboard", description="Shift time leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(config.LEADERBOARD_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                "The leaderboard role isn't set up. Check LEADERBOARD_ROLE_ID in config.py.",
                ephemeral=True,
            )
            return

        totals = all_totals(now_ts())
        ranked = sorted(
            ((m, totals.get(m.id, 0)) for m in role.members if not m.bot),
            key=lambda pair: pair[1],
            reverse=True,
        )

        if not ranked:
            embed = discord.Embed(
                title="Shift Leaderboard",
                description="No members have the leaderboard role.",
                color=discord.Color.gold(),
            )
            await interaction.response.send_message(embed=embed)
            return

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = [
            f"{medals.get(i, f'**{i}.**')} {member.mention} — {fmt(secs)}"
            for i, (member, secs) in enumerate(ranked, start=1)
        ]

        shown, size = [], 0
        for line in lines:
            if size + len(line) + 1 > 3900:
                break
            shown.append(line)
            size += len(line) + 1

        embed = discord.Embed(
            title="Shift Leaderboard",
            description="\n".join(shown),
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"Showing {len(shown)} of {len(lines)} members · breaks excluded")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="admin", description="Manage a member's shift (admins only)")
    @app_commands.describe(member="Member to manage")
    @admin_only()
    async def admin(self, interaction: discord.Interaction, member: discord.Member):
        if member.bot:
            await interaction.response.send_message("Bots don't have shifts.", ephemeral=True)
            return
        view = AdminView(interaction.user, member)
        await interaction.response.send_message(
            embed=build_admin_embed(member), view=view, ephemeral=True
        )
        view.interaction = interaction

async def setup(bot):
    await bot.add_cog(Shifts(bot))