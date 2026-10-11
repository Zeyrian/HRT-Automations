import re

import discord

import config
from checks import is_shift_admin
from leave_db import (
    approve,
    create_request,
    delete_leave,
    deny,
    get_active,
    get_leave,
    get_pending,
)

STATUS_COLORS = {
    "pending": discord.Color.orange(),
    "approved": discord.Color.green(),
    "denied": discord.Color.red(),
    "ended": discord.Color.light_grey(),
}


async def get_leave_channel(client):
    channel = client.get_channel(config.LEAVE_CHANNEL_ID)
    if channel is None:
        try:
            channel = await client.fetch_channel(config.LEAVE_CHANNEL_ID)
        except discord.HTTPException:
            return None
    return channel


async def notify_member(member, text):
    if member is None:
        return
    try:
        await member.send(text)
    except discord.HTTPException:
        pass  # their DMs are closed


def build_leave_embed(user):
    active = get_active(user.id)
    pending = get_pending(user.id)
    if active:
        embed = discord.Embed(
            title="Leave of Absence", description="You are **on leave**.", color=discord.Color.green()
        )
        embed.add_field(name="Leave ID", value=f"#{active['id']}", inline=True)
        embed.add_field(
            name="Ends", value=f"<t:{active['end_ts']}:F> (<t:{active['end_ts']}:R>)", inline=False
        )
    elif pending:
        embed = discord.Embed(
            title="Leave of Absence",
            description="Your request is **pending review**.",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Request", value=f"#{pending['id']} · {pending['days']} day(s)", inline=True)
        embed.add_field(name="Requested", value=f"<t:{pending['requested_ts']}:R>", inline=True)
    else:
        embed = discord.Embed(
            title="Leave of Absence",
            description="You have no active leave or pending request.",
            color=discord.Color.light_grey(),
        )
    embed.set_footer(text=user.display_name)
    return embed


def build_review_embed(leave, member):
    embed = discord.Embed(
        title=f"Leave Request #{leave['id']}",
        color=STATUS_COLORS[leave["status"]],
        timestamp=discord.utils.utcnow(),
    )
    if member is not None:
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
    embed.add_field(name="Member", value=f"<@{leave['user_id']}>", inline=True)
    embed.add_field(name="Duration", value=f"{leave['days']} day(s)", inline=True)
    embed.add_field(name="Status", value=leave["status"].capitalize(), inline=True)
    embed.add_field(name="Reason", value=leave["reason"], inline=False)
    if leave["start_ts"]:
        embed.add_field(
            name="Leave period",
            value=f"<t:{leave['start_ts']}:d> → <t:{leave['end_ts']}:d>",
            inline=True,
        )
    if leave["reviewer_id"]:
        embed.add_field(name="Reviewed by", value=f"<@{leave['reviewer_id']}>", inline=True)
    return embed


class ReviewView(discord.ui.View):
    """Approve/Deny buttons on a leave request. Persistent: survives bot restarts."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="leave:approve")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.review(interaction, approved=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="leave:deny")
    async def deny_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.review(interaction, approved=False)

    async def review(self, interaction: discord.Interaction, approved: bool):
        if not is_shift_admin(interaction.user):
            await interaction.response.send_message(
                "Only shift admins can review leave requests.", ephemeral=True
            )
            return

        title = interaction.message.embeds[0].title if interaction.message.embeds else ""
        match = re.search(r"#(\d+)", title or "")
        if not match:
            await interaction.response.send_message("Couldn't read the request ID.", ephemeral=True)
            return

        leave_id = int(match.group(1))
        if approved:
            leave = approve(leave_id, interaction.user.id)
        else:
            leave = deny(leave_id, interaction.user.id)
        if leave is None:
            await interaction.response.send_message(
                "That request was already handled or no longer exists.", ephemeral=True
            )
            return

        member = interaction.guild.get_member(leave["user_id"])
        await interaction.response.edit_message(embed=build_review_embed(leave, member), view=None)

        guild_name = interaction.guild.name
        if approved:
            await notify_member(
                member,
                f"Your leave request #{leave_id} in {guild_name} was approved. "
                f"You're on leave until <t:{leave['end_ts']}:F>.",
            )
        else:
            await notify_member(member, f"Your leave request #{leave_id} in {guild_name} was denied.")


class RequestModal(discord.ui.Modal, title="Request Leave"):
    days = discord.ui.TextInput(label="Duration (days)", placeholder="e.g. 7", max_length=3)
    reason = discord.ui.TextInput(
        label="Reason", style=discord.TextStyle.paragraph, max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
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

        user = interaction.user
        if get_pending(user.id) or get_active(user.id):
            await interaction.response.send_message(
                "You already have a pending request or an active leave.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        channel = await get_leave_channel(interaction.client)
        if channel is None:
            await interaction.followup.send(
                "Leave requests aren't set up yet. Check LEAVE_CHANNEL_ID in config.py.",
                ephemeral=True,
            )
            return

        leave_id = create_request(user.id, days, reason)
        leave = get_leave(leave_id)
        try:
            await channel.send(embed=build_review_embed(leave, user), view=ReviewView())
        except discord.HTTPException as e:
            print(f"Could not post the leave request: {e}")
            delete_leave(leave_id)
            await interaction.followup.send(
                "Couldn't send your request to the leave channel. Please tell an admin.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Your leave request #{leave_id} was sent for review.", ephemeral=True
        )


class LeaveView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user
        self.interaction = None
        self.request_btn.disabled = bool(get_pending(user.id) or get_active(user.id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This isn't your panel.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.interaction:
            try:
                await self.interaction.edit_original_response(view=None)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Request Leave", style=discord.ButtonStyle.primary)
    async def request_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RequestModal())