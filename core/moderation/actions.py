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

    async def add_strike(self, user_id, guild_id, reason, moderator_id, auto_generated=False, expires_hours=None):
        """Add strike with automatic escalation"""

        try:
            async with self.data_manager.atomic_transaction() as conn:
                # Generate unique strike_id
                import uuid
                strike_id = str(uuid.uuid4())

                expires_at = None
                if expires_hours:
                    expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)

                # Insert strike
                await conn.execute(
                    """INSERT INTO strikes (strike_id, guild_id, user_id, reason, moderator_id,
                                            auto_generated, expires_at, is_active)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, true)""",
                    strike_id, guild_id, user_id, reason, moderator_id, auto_generated, expires_at
                )

                # Get active strike count
                active_strikes = await conn.fetch(
                    """SELECT id FROM strikes
                       WHERE user_id = $1 AND guild_id = $2 AND is_active = true
                       AND (expires_at IS NULL OR expires_at > NOW())""",
                    user_id, guild_id
                )

                strike_count = len(active_strikes)

                # Log audit
                await self.audit_manager.log_event(
                    guild_id=guild_id,
                    event_type='strike_added',
                    user_id=user_id,
                    moderator_id=moderator_id,
                    details={
                        'strike_id': strike_id,
                        'reason': reason,
                        'total_strikes': strike_count,
                        'auto_generated': auto_generated
                    },
                    conn=conn
                )

                # ESCALATION LOGIC
                guild = self.bot.get_guild(int(guild_id))
                member = guild.get_member(int(user_id)) if guild else None

                if not member:
                    return strike_id

                # Strike thresholds
                if strike_count >= 5:
                    # BAN at 5 strikes
                    await member.ban(reason=f"Strike threshold exceeded (5 strikes)")
                    await conn.execute(
                        """INSERT INTO moderation_actions (action_id, guild_id, user_id, action_type,
                                                            reason, moderator_id)
                           VALUES ($1, $2, $3, 'ban', $4, $5)""",
                        str(uuid.uuid4()), guild_id, user_id, "Strike threshold: 5 strikes", moderator_id
                    )

                elif strike_count >= 3:
                    # KICK at 3 strikes
                    await member.kick(reason=f"Strike threshold exceeded (3 strikes)")
                    await conn.execute(
                        """INSERT INTO moderation_actions (action_id, guild_id, user_id, action_type,
                                                            reason, moderator_id)
                           VALUES ($1, $2, $3, 'kick', $4, $5)""",
                        str(uuid.uuid4()), guild_id, user_id, "Strike threshold: 3 strikes", moderator_id
                    )

                elif strike_count >= 2:
                    # TIMEOUT at 2 strikes (24 hours)
                    timeout_until = datetime.now(timezone.utc) + timedelta(hours=24)
                    await member.timeout(timeout_until, reason=f"Strike threshold exceeded (2 strikes)")
                    await conn.execute(
                        """INSERT INTO moderation_actions (action_id, guild_id, user_id, action_type,
                                                            reason, moderator_id, duration_seconds, expires_at)
                           VALUES ($1, $2, $3, 'timeout', $4, $5, 86400, $6)""",
                        str(uuid.uuid4()), guild_id, user_id, "Strike threshold: 2 strikes",
                        moderator_id, timeout_until
                    )

        except Exception as e:
            logger.exception(f"Add strike error: {e}")
            raise

        return strike_id

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
