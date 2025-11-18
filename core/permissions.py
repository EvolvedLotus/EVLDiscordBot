"""
Permission checking utilities for the bot
"""

import discord
from discord.ext import commands
from . import data_manager

def is_admin(ctx) -> bool:
    """Check if user has admin permissions in this guild"""
    if not ctx.guild:
        return False

    # Check Discord admin permission
    if ctx.author.guild_permissions.administrator:
        return True

    # Check custom admin roles from config
    try:
        config = data_manager.load_guild_data(ctx.guild.id, "config")
        admin_roles = config.get("admin_roles", [])

        user_roles = [role.id for role in ctx.author.roles]
        return any(role_id in user_roles for role_id in admin_roles)
    except Exception:
        return False

def is_admin_interaction(interaction) -> bool:
    """Check if user has admin permissions in this guild (for interactions)"""
    if not interaction.guild:
        return False

    # Check Discord admin permission
    if interaction.user.guild_permissions.administrator:
        return True

    # Check custom admin roles from config
    try:
        config = data_manager.load_guild_data(interaction.guild.id, "config")
        admin_roles = config.get("admin_roles", [])

        user_roles = [role.id for role in interaction.user.roles]
        return any(role_id in user_roles for role_id in admin_roles)
    except Exception:
        return False

def is_moderator(ctx) -> bool:
    """Check if user has moderator permissions in this guild"""
    if not ctx.guild:
        return False

    # Admins are also moderators
    if is_admin(ctx):
        return True

    # Check Discord moderator permissions
    mod_permissions = [
        'kick_members', 'ban_members', 'manage_messages',
        'manage_channels', 'manage_roles'
    ]

    if any(getattr(ctx.author.guild_permissions, perm) for perm in mod_permissions):
        return True

    # Check custom moderator roles from config
    try:
        config = data_manager.load_guild_data(ctx.guild.id, "config")
        moderator_roles = config.get("moderator_roles", [])

        user_roles = [role.id for role in ctx.author.roles]
        return any(role_id in user_roles for role_id in moderator_roles)
    except Exception:
        return False

def is_moderator_interaction(interaction) -> bool:
    """Check if user has moderator permissions in this guild (for interactions)"""
    if not interaction.guild:
        return False

    # Admins are also moderators
    if is_admin_interaction(interaction):
        return True

    # Check Discord moderator permissions
    mod_permissions = [
        'kick_members', 'ban_members', 'manage_messages',
        'manage_channels', 'manage_roles'
    ]

    if any(getattr(interaction.user.guild_permissions, perm) for perm in mod_permissions):
        return True

    # Check custom moderator roles from config
    try:
        config = data_manager.load_guild_data(interaction.guild.id, "config")
        moderator_roles = config.get("moderator_roles", [])

        user_roles = [role.id for role in interaction.user.roles]
        return any(role_id in user_roles for role_id in moderator_roles)
    except Exception:
        return False

def has_feature_enabled(ctx, feature: str) -> bool:
    """Check if a feature is enabled for this guild"""
    if not ctx.guild:
        return True  # Enable all features in DMs

    try:
        config = data_manager.load_guild_data(ctx.guild.id, "config")
        features = config.get("features", {})
        return features.get(feature, True)  # Default to enabled
    except Exception:
        return True  # Default to enabled if error

def is_bot_owner(ctx) -> bool:
    """Check if user is the bot owner"""
    # This would need to be configured with the actual owner ID
    # For now, just check if they have administrator in any server
    return ctx.author.guild_permissions.administrator if ctx.guild else False

# Custom check decorators
def admin_only():
    """Decorator for admin-only commands"""
    def predicate(ctx):
        if not is_admin(ctx):
            raise commands.MissingPermissions(["administrator"])
        return True
    return commands.check(predicate)

def moderator_only():
    """Decorator for moderator-only commands"""
    def predicate(ctx):
        if not is_moderator(ctx):
            raise commands.MissingPermissions(["moderator"])
        return True
    return commands.check(predicate)

def feature_enabled(feature: str):
    """Decorator to check if feature is enabled"""
    def predicate(ctx):
        if not has_feature_enabled(ctx, feature):
            raise commands.CheckFailure(f"Feature '{feature}' is disabled in this server")
        return True
    return commands.check(predicate)

def guild_only():
    """Decorator to ensure command is used in a guild"""
    return commands.guild_only()

def bot_owner_only():
    """Decorator for bot owner only commands"""
    def predicate(ctx):
        if not is_bot_owner(ctx):
            raise commands.MissingPermissions(["bot_owner"])
        return True
    return commands.check(predicate)

# Interaction-based check decorators for slash commands
def admin_only_interaction():
    """Decorator for admin-only slash commands"""
    async def predicate(interaction):
        if not is_admin_interaction(interaction):
            await interaction.response.send_message("❌ You need administrator permissions to use this command!", ephemeral=True)
            return False
        return True
    return discord.app_commands.check(predicate)

def moderator_only_interaction():
    """Decorator for moderator-only slash commands"""
    async def predicate(interaction):
        if not is_moderator_interaction(interaction):
            await interaction.response.send_message("❌ You need moderator permissions to use this command!", ephemeral=True)
            return False
        return True
    return discord.app_commands.check(predicate)

def check_command_permissions(guild_id: str, user_id: str, user_roles: list, command_name: str) -> bool:
    """
    Check if user has permission to execute command based on CMS configuration

    Args:
        guild_id: Guild ID
        user_id: User ID
        user_roles: List of user's role IDs
        command_name: Command name to check

    Returns:
        True if user has permission, False otherwise
    """
    try:
        # Fetch command permissions from database
        result = data_manager.supabase.table('command_permissions').select('*').match({
            'guild_id': guild_id,
            'command_name': command_name
        }).execute()

        if not result.data:
            # No permissions configured, allow by default
            return True

        perms = result.data[0]

        # Check if command is disabled
        if not perms.get('is_enabled', True):
            return False

        # Check denied users first (highest priority)
        if user_id in perms.get('denied_users', []):
            return False

        # Check denied roles
        if any(role_id in perms.get('denied_roles', []) for role_id in user_roles):
            return False

        # Check allowed users
        if user_id in perms.get('allowed_users', []):
            return True

        # Check allowed roles
        if perms.get('allowed_roles') and any(role_id in perms.get('allowed_roles', []) for role_id in user_roles):
            return True

        # If allowed lists exist but user not in them, deny
        if perms.get('allowed_users') or perms.get('allowed_roles'):
            return False

        # Default allow if no restrictions
        return True

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error checking command permissions: {e}")
        return True  # Fail open for safety


# Add decorator for commands
def check_permissions():
    """Decorator to check command permissions from CMS"""
    async def predicate(ctx):
        guild_id = str(ctx.guild.id) if ctx.guild else None
        if not guild_id:
            return True

        user_id = str(ctx.author.id)
        user_roles = [str(r.id) for r in ctx.author.roles]
        command_name = ctx.command.name

        has_permission = check_command_permissions(guild_id, user_id, user_roles, command_name)

        if not has_permission:
            raise commands.CheckFailure(f"You don't have permission to use `{command_name}`")

        return True

    return commands.check(predicate)
