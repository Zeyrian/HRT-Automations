import discord

import config
from database import all_totals, now_ts
from utils import fmt


def build_leaderboard_embed(guild, title="Shift Leaderboard", note=None):
    """Returns the leaderboard embed, or None if the leaderboard role isn't found."""
    role = guild.get_role(config.LEADERBOARD_ROLE_ID)
    if role is None:
        return None

    totals = all_totals(now_ts())
    ranked = sorted(
        ((m, totals.get(m.id, 0)) for m in role.members if not m.bot),
        key=lambda pair: pair[1],
        reverse=True,
    )

    if not ranked:
        return discord.Embed(
            title=title,
            description="No members have the leaderboard role.",
            color=discord.Color.gold(),
        )

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

    embed = discord.Embed(title=title, description="\n".join(shown), color=discord.Color.gold())
    footer = f"Showing {len(shown)} of {len(lines)} members · breaks excluded"
    if note:
        footer += f" · {note}"
    embed.set_footer(text=footer)
    return embed