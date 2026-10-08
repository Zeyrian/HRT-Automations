import discord
from discord import app_commands

import config


def has_role(member, role_id):
    return any(role.id == role_id for role in getattr(member, "roles", []))


def is_shift_admin(member):
    return has_role(member, config.SHIFT_ADMIN_ROLE_ID)


def is_shift_member(member):
    return has_role(member, config.SHIFT_ROLE_ID) or is_shift_admin(member)


def admin_only():
    """Decorator for shift admin commands."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_shift_admin(interaction.user):
            return True
        raise app_commands.CheckFailure("You need the shift admin role to use this command.")
    return app_commands.check(predicate)