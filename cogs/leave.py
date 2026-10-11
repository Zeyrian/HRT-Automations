import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from checks import admin_only, is_shift_member
from leave_db import get_active, get_all_active
from leave_roles import set_leave_role
from views.leave_admin import LeaveAdminView, build_leave_admin_embed
from views.leave_panel import LeaveView, ReviewView, build_leave_embed


@app_commands.guild_only()
class Leave(commands.GroupCog, group_name="leave", group_description="HRT leave of absence commands"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    async def cog_load(self):
        # Keeps Approve/Deny buttons on old requests working after a restart.
        self.bot.add_view(ReviewView())
        self.expire_roles.start()

    async def cog_unload(self):
        self.expire_roles.cancel()

    @tasks.loop(minutes=1)
    async def expire_roles(self):
        """Removes the on-leave role from anyone whose leave has ended or expired."""
        for guild in self.bot.guilds:
            role = guild.get_role(config.ON_LEAVE_ROLE_ID)
            if role is None:
                continue
            for member in role.members:
                try:
                    if not get_active(member.id):
                        await set_leave_role(member, False)
                except Exception as e:
                    print(f"Leave role check failed for {member.id}: {e}")

    @expire_roles.before_loop
    async def before_expire_roles(self):
        await self.bot.wait_until_ready()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_shift_member(interaction.user):
            return True
        raise app_commands.CheckFailure("You need the shift role to use leave commands.")

    @app_commands.command(name="manage", description="Request a leave of absence")
    async def manage(self, interaction: discord.Interaction):
        view = LeaveView(interaction.user)
        await interaction.response.send_message(
            embed=build_leave_embed(interaction.user), view=view, ephemeral=True
        )
        view.interaction = interaction

    @app_commands.command(name="active", description="See who is currently on leave")
    async def active(self, interaction: discord.Interaction):
        rows = get_all_active()
        if not rows:
            embed = discord.Embed(
                title="Members on Leave",
                description="Nobody is on leave right now.",
                color=discord.Color.light_grey(),
            )
        else:
            lines = [
                f"<@{leave['user_id']}> — returns <t:{leave['end_ts']}:R> (<t:{leave['end_ts']}:d>)"
                for leave in rows
            ]
            embed = discord.Embed(
                title="Members on Leave",
                description="\n".join(lines),
                color=discord.Color.green(),
            )
            embed.set_footer(text=f"{len(rows)} on leave")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="admin", description="Manage a member's leave (admins only)")
    @app_commands.describe(member="Member to manage")
    @admin_only()
    async def admin(self, interaction: discord.Interaction, member: discord.Member):
        if member.bot:
            await interaction.response.send_message("Bots don't take leave.", ephemeral=True)
            return
        view = LeaveAdminView(interaction.user, member)
        await interaction.response.send_message(
            embed=build_leave_admin_embed(member), view=view, ephemeral=True
        )
        view.interaction = interaction


async def setup(bot):
    await bot.add_cog(Leave(bot))