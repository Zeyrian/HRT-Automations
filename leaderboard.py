from datetime import datetime, timezone

import discord

import config
from database import all_totals, count_shifts, now_ts
from utils import fmt

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def is_exempt(member):
    """True if the member has any of the quota-exempt roles."""
    return any(role.id in config.QUOTA_EXEMPT_ROLE_IDS for role in member.roles)


def get_ranked(guild):
    """Returns [(member, seconds)] for members with the leaderboard role, most time first.
    Returns None if the leaderboard role isn't found."""
    role = guild.get_role(config.LEADERBOARD_ROLE_ID)
    if role is None:
        return None
    totals = all_totals(now_ts())
    return sorted(
        ((m, totals.get(m.id, 0)) for m in role.members if not m.bot),
        key=lambda pair: pair[1],
        reverse=True,
    )


def _list_embed(title, lines, color, empty_text, footer):
    if not lines:
        embed = discord.Embed(title=title, description=empty_text, color=color)
        embed.set_footer(text=footer)
        return embed

    shown, size = [], 0
    for line in lines:
        if size + len(line) + 1 > 3900:
            break
        shown.append(line)
        size += len(line) + 1

    embed = discord.Embed(title=title, description="\n".join(shown), color=color)
    if len(shown) < len(lines):
        footer += f" · showing {len(shown)} of {len(lines)}"
    embed.set_footer(text=footer)
    return embed


def _leaderboard_embed(ranked, title, note=None):
    lines = [
        f"{MEDALS.get(i, f'**{i}.**')} {member.mention} — {fmt(secs)}"
        + (" (Exempt)" if is_exempt(member) else "")
        for i, (member, secs) in enumerate(ranked, start=1)
    ]
    footer = f"{len(ranked)} members · breaks excluded"
    if note:
        footer += f" · {note}"
    return _list_embed(
        title, lines, discord.Color.gold(), "No members have the leaderboard role.", footer
    )


def build_leaderboard_embed(guild, title="Shift Leaderboard", note=None):
    """Returns the leaderboard embed, or None if the leaderboard role isn't found."""
    ranked = get_ranked(guild)
    if ranked is None:
        return None
    return _leaderboard_embed(ranked, title, note)


def _quota_embeds(ranked, quota_seconds):
    exempt = [(m, s) for m, s in ranked if is_exempt(m)]
    counted = [(m, s) for m, s in ranked if not is_exempt(m)]
    met = [(m, s) for m, s in counted if s >= quota_seconds]
    not_met = [(m, s) for m, s in counted if s < quota_seconds]
    quota_text = f"Quota: {fmt(quota_seconds)}"

    def lines(pairs):
        return [f"{member.mention} — {fmt(secs)}" for member, secs in pairs]

    return [
        _list_embed(
            "Quota Met", lines(met), discord.Color.green(),
            "Nobody met the quota.", f"{quota_text} · {len(met)} members",
        ),
        _list_embed(
            "Quota Not Met", lines(not_met), discord.Color.red(),
            "Everybody met the quota.", f"{quota_text} · {len(not_met)} members",
        ),
        _list_embed(
            "Quota Exempted", lines(exempt), discord.Color.blue(),
            "Nobody is exempt from the quota.", f"{len(exempt)} members",
        ),
    ]

def _total_embed(ranked):
    total = sum(secs for _, secs in ranked)
    embed = discord.Embed(
        title="Total HRT Shift Time",
        description=f"**{fmt(total)}**",
        color=discord.Color.purple(),
    )
    embed.set_footer(text=f"{len(ranked)} members · breaks excluded")
    return embed

def build_quota_embeds(guild, quota_seconds):
    """Returns [quota met, quota not met, quota exempted, total time] embeds,
    or None if the leaderboard role isn't found."""
    ranked = get_ranked(guild)
    if ranked is None:
        return None
    return _quota_embeds(ranked, quota_seconds) + [_total_embed(ranked)]


def build_wave_embeds(guild, quota_seconds, note=None):
    """Returns [leaderboard, quota met, quota not met, quota exempted], or None if the role isn't found."""
    ranked = get_ranked(guild)
    if ranked is None:
        return None
    return [_leaderboard_embed(ranked, "Shift Leaderboard", note)] + _quota_embeds(
        ranked, quota_seconds
    )


def build_raw_data(guild):
    """Returns the leaderboard as plain text for a .txt export, or None if the role isn't found."""
    ranked = get_ranked(guild)
    if ranked is None:
        return None

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "HRT Shift Leaderboard - Raw Shift Data",
        f"Generated: {generated}",
        f"Members: {len(ranked)}",
        "Breaks are excluded from all times.",
        "Time from shifts in progress is counted up to the moment this file was generated.",
        "",
    ]
    for i, (member, secs) in enumerate(ranked, start=1):
        exempt = " (Exempt)" if is_exempt(member) else ""
        lines.append(
            f"{i}. {member.display_name} (ID: {member.id}) | "
            f"Total: {fmt(secs)} ({int(secs)} seconds){exempt} | Shifts: {count_shifts(member.id)}"
        )
    return "\n".join(lines) + "\n"