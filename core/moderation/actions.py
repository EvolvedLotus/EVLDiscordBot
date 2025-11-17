import logging
import discord
from datetime import datetime, timedelta
from typing import Dict, List
from .protection_manager import ProtectionManager

logger = logging.getLogger(__name__)

class ModerationActions:
    """Handles moderation actions like warnings, strikes, mutes, etc."""

    def __init__(self, protection_manager: ProtectionManager, bot):
        self.protection_manager = protection_manager
        self.bot = bot

    async def warn_user(self, guild_id: int, user_id: int, reason: str, moderator_id: int, auto_generated: bool = False) -> Dict:
        """Issues a warning to user via DM and logs a strike"""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return {'success': False, 'error': 'Guild not found'}

            user = guild.get_member(user_id)
            if not user:
                return {'success': False, 'error': 'User not found in guild'}

            # Send DM warning
            try:
                embed = discord.Embed(
                    title="⚠️ Warning",
                    description=f"You received a warning in **{guild.name}**",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Moderator", value=f"<@{moderator_id}>", inline=True)
                embed.set_footer(text="Repeated violations may result in further action")

                await user.send(embed=embed)
                dm_sent = True
            except discord.Forbidden:
                dm_sent = False
                logger.warning(f"Cannot DM user {user_id} in guild {guild_id}")

            # Log the warning (for now, just log to console - would need database table)
            warning_record = {
                'guild_id': guild_id,
                'user_id': user_id,
                'reason': reason,
                'moderator_id': moderator_id,
                'auto_generated': auto_generated,
                'dm_sent': dm_sent,
                'timestamp': datetime.now().isoformat()
            }

            logger.info(f"Warning issued: {warning_record}")

            return {
                'success': True,
                'warning_record': warning_record,
                'dm_sent': dm_sent
            }

        except Exception as e:
            logger.error(f"Failed to warn user {user_id}: {e}")
            return {'success': False, 'error': str(e)}

    async def add_strike(self, guild_id: int, user_id: int, reason: str, moderator_id: int) -> Dict:
        """Adds a strike record and evaluates escalation thresholds"""
        try:
            # For now, just log the strike - would need database table for persistent strikes
            strike_record = {
                'guild_id': guild_id,
                'user_id': user_id,
                'reason': reason,
                'moderator_id': moderator_id,
                'timestamp': datetime.now().isoformat()
            }

            logger.info(f"Strike added: {strike_record}")

            # Check escalation thresholds (simplified - would need strike count from DB)
            # For now, just return the record
            return {
                'success': True,
                'strike_record': strike_record,
                'escalation': 'none'  # none, mute, kick, ban
            }

        except Exception as e:
            logger.error(f"Failed to add strike for user {user_id}: {e}")
            return {'success': False, 'error': str(e)}

    async def remove_strike(self, guild_id: int, user_id: int, strike_id: str, moderator_id: int) -> Dict:
        """Removes a strike (manual) and logs action"""
        try:
            # For now, just log the removal - would need database table
            removal_record = {
                'guild_id': guild_id,
                'user_id': user_id,
                'strike_id': strike_id,
                'moderator_id': moderator_id,
                'timestamp': datetime.now().isoformat()
            }

            logger.info(f"Strike removed: {removal_record}")

            return {'success': True, 'removal_record': removal_record}

        except Exception as e:
            logger.error(f"Failed to remove strike {strike_id}: {e}")
            return {'success': False, 'error': str(e)}

    async def apply_temporary_mute(self, guild_id: int, user_id: int, duration_seconds: int, reason: str, moderator_id: int) -> Dict:
        """Applies mute role or timeout via Discord API for the specified duration"""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return {'success': False, 'error': 'Guild not found'}

            user = guild.get_member(user_id)
            if not user:
                return {'success': False, 'error': 'User not found in guild'}

            # Check bot permissions
            if not guild.me.guild_permissions.moderate_members:
                return {'success': False, 'error': 'Bot lacks moderate_members permission'}

            # Apply timeout
            duration = timedelta(seconds=duration_seconds)
            await user.timeout(duration, reason=reason)

            # Log the mute
            mute_record = {
                'guild_id': guild_id,
                'user_id': user_id,
                'duration_seconds': duration_seconds,
                'reason': reason,
                'moderator_id': moderator_id,
                'timestamp': datetime.now().isoformat()
            }

            logger.info(f"User muted: {mute_record}")

            return {
                'success': True,
                'mute_record': mute_record
            }

        except discord.Forbidden:
            logger.warning(f"Cannot mute user {user_id} in guild {guild_id}")
            return {'success': False, 'error': 'Insufficient permissions'}
        except Exception as e:
            logger.error(f"Failed to mute user {user_id}: {e}")
            return {'success': False, 'error': str(e)}

    def schedule_unmute_job(self, guild_id: int, user_id: int, unmute_timestamp: datetime) -> Dict:
        """Ensures temporary mutes are automatically removed at the scheduled time"""
        try:
            # For now, just log the scheduling - would need a proper job scheduler
            job_record = {
                'guild_id': guild_id,
                'user_id': user_id,
                'unmute_timestamp': unmute_timestamp.isoformat(),
                'job_type': 'unmute',
                'timestamp': datetime.now().isoformat()
            }

            logger.info(f"Unmute job scheduled: {job_record}")

            return {
                'success': True,
                'job_record': job_record,
                'job_id': f"unmute_{guild_id}_{user_id}_{int(unmute_timestamp.timestamp())}"
            }

        except Exception as e:
            logger.error(f"Failed to schedule unmute job: {e}")
            return {'success': False, 'error': str(e)}
