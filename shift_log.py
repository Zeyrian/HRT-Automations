import discord

import config
from utils import fmt


def _embed(title, color, user, shift_id, by=None):
    embed = discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(name="Member", value=user.mention, inline=True)
    embed.add_field(name="Shift ID", value=f"#{shift_id}", inline=True)
    if by is not None:
        embed.set_footer(text=f"Action by {by.display_name}")
    return embed


async def _send(client, embed):
    channel = client.get_channel(config.LOG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await client.fetch_channel(config.LOG_CHANNEL_ID)
        except discord.HTTPException:
            print("Shift log channel not found - check LOG_CHANNEL_ID in config.py")
            return
    try:
        await channel.send(embed=embed)
    except discord.HTTPException as e:
        print(f"Could not post to the shift log channel: {e}")


async def log_start(client, user, shift_id, by=None):
    await _send(client, _embed("Shift Started", discord.Color.green(), user, shift_id, by))


async def log_break(client, user, shift_id, action, seconds, by=None):
    if action == "started":
        embed = _embed("Break Started", discord.Color.orange(), user, shift_id, by)
    else:
        embed = _embed("Break Ended", discord.Color.blue(), user, shift_id, by)
        embed.add_field(name="Break length", value=fmt(seconds), inline=True)
    await _send(client, embed)


async def log_end(client, user, shift_id, on_duty, breaks, by=None):
    embed = _embed("Shift Ended", discord.Color.red(), user, shift_id, by)
    embed.add_field(name="Time on duty", value=fmt(on_duty), inline=True)
    embed.add_field(name="Break time", value=fmt(breaks), inline=True)
    await _send(client, embed)


async def log_delete(client, user, shift_id, on_duty, by):
    embed = _embed("Shift Deleted", discord.Color.dark_red(), user, shift_id, by)
    embed.add_field(name="Time on duty (removed)", value=fmt(on_duty), inline=True)
    await _send(client, embed)


async def log_modify(client, user, shift_id, minutes, new_on_duty, by):
    embed = _embed("Shift Modified", discord.Color.purple(), user, shift_id, by)
    embed.add_field(name="Adjustment", value=f"{minutes:+d} min", inline=True)
    embed.add_field(name="New time on duty", value=fmt(new_on_duty), inline=True)
    await _send(client, embed)