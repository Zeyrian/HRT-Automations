import discord

import config


async def set_shift_role(member, state):
    """state: 'on_duty', 'on_break', or 'off'. Swaps the member's shift roles to match."""
    on_duty = member.guild.get_role(config.ON_DUTY_ROLE_ID)
    on_break = member.guild.get_role(config.ON_BREAK_ROLE_ID)

    wanted = {"on_duty": on_duty, "on_break": on_break}.get(state)
    to_add = [wanted] if wanted is not None else []
    to_remove = [
        r for r in (on_duty, on_break)
        if r is not None and (wanted is None or r.id != wanted.id)
    ]

    try:
        if to_remove:
            await member.remove_roles(*to_remove, reason="HRT shift status")
        if to_add:
            await member.add_roles(*to_add, reason="HRT shift status")
    except discord.Forbidden:
        print(
            "Can't change shift roles - give the bot Manage Roles and move its role "
            "above the on-duty and on-break roles."
        )
    except discord.HTTPException as e:
        print(f"Could not update shift roles: {e}")