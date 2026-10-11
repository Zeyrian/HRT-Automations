import discord

import config


async def set_leave_role(member, on_leave):
    """Adds (on_leave=True) or removes (on_leave=False) the on-leave role."""
    role = member.guild.get_role(config.ON_LEAVE_ROLE_ID)
    if role is None:
        return
    try:
        if on_leave:
            await member.add_roles(role, reason="HRT leave of absence")
        else:
            await member.remove_roles(role, reason="HRT leave of absence ended")
    except discord.Forbidden:
        print(
            "Can't change the on-leave role - give the bot Manage Roles and move its role "
            "above the on-leave role."
        )
    except discord.HTTPException as e:
        print(f"Could not update the on-leave role: {e}")