import discord

import config
from utils import fmt


def _embed(title, color, user, shift_id):
    embed = discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(name="Member", value=user.mention, inline=True)
    embed.add_field(name="Shift ID", value=f"#{shift_id}", inline=True)
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


async def log_start(client, user, shift_id):
    await _send(client, _embed("Shift Started", discord.Color.green(), user, shift_id))


async def log_break(client, user, shift_id, action, seconds):
    if action == "started":
        embed = _embed("Break Started", discord.Color.orange(), user, shift_id)
    else:
        embed = _embed("Break Ended", discord.Color.blue(), user, shift_id)
        embed.add_field(name="Break length", value=fmt(seconds), inline=True)
    await _send(client, embed)


async def log_end(client, user, shift_id, on_duty, breaks):
    embed = _embed("Shift Ended", discord.Color.red(), user, shift_id)
    embed.add_field(name="Time on duty", value=fmt(on_duty), inline=True)
    embed.add_field(name="Break time", value=fmt(breaks), inline=True)
    await _send(client, embed)