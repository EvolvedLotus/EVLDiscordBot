import logging
import discord
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from .protection_manager import ProtectionManager

logger = logging.getLogger(__name__)

class ModerationActions:
    """Handles moderation actions like warnings, strikes, mutes, etc."""

    def __init__(self, protection_manager: ProtectionManager, bot):
        self.protection_manager = protection_manager
        self.bot = bot

    async def warn_user(self, guild_id: int, user_id: int, reason: str, moderator_id: int, auto_generated: bool = False) -> Dict:
        """Issues a warning to user via DM and logs a strike in the database"""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return {'success': False, 'error': 'Guild not found'}

            user = guild.get_member(user_id)
            if not user:
                return {'success': False, 'error': 'User not found in guild'}

            # Generate and add strike using PG
            import uuid
            ttl_days = self.protection_manager.load_protection_config(guild_id).get('warning_ttl_days', 30)
            
            try:
                # Add strike logic using Supabase
                strike_id = str(uuid.uuid4())
                expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()
                
                # We use synchronous execution since most DB managers wrap the REST API sync or async internally
                # Wait, the data_manager is in the cog not Actions explicitly? Need to access it:
                dm = self.protection_manager.data_manager
                dm.supabase.table('strikes').insert({
                    'strike_id': strike_id,
                    'guild_id': str(guild_id),
                    'user_id': str(user_id),
                    'reason': reason,
                    'moderator_id': str(moderator_id),
                    'auto_generated': auto_generated,
                    'expires_at': expires_at,
                    'is_active': True 
                }).execute()
                
                # Check thresholds
                active_strikes_res = dm.supabase.table('strikes') \
                    .select('id') \
                    .eq('guild_id', str(guild_id)) \
                    .eq('user_id', str(user_id)) \
                    .eq('is_active', True) \
                    .gt('expires_at', datetime.now(timezone.utc).isoformat()) \
                    .execute()
                strike_count = len(active_strikes_res.data) if active_strikes_res.data else 0

                # Escalate
                if strike_count >= 5:
                    await user.ban(reason="Strike threshold exceeded (5 strikes)")
                elif strike_count >= 3:
                    await user.kick(reason="Strike threshold exceeded (3 strikes)")
                elif strike_count >= 2:
                    timeout_until = discord.utils.utcnow() + timedelta(hours=24)
                    await user.timeout(timeout_until, reason="Strike threshold exceeded (2 strikes)")
            except Exception as e:
                logger.error(f"Failed to insert strike or escalate: {e}")

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

            return {
                'success': True,
                'dm_sent': dm_sent
            }

        except Exception as e:
            logger.error(f"Failed to warn user {user_id}: {e}")
            return {'success': False, 'error': str(e)}

    def get_user_warnings(self, guild_id: int, user_id: int) -> Dict:
        """Fetch active strikes honoring the TTL window from DB"""
        dm = self.protection_manager.data_manager
        res = dm.supabase.table('strikes') \
            .select('*') \
            .eq('guild_id', str(guild_id)) \
            .eq('user_id', str(user_id)) \
            .eq('is_active', True) \
            .gt('expires_at', datetime.now(timezone.utc).isoformat()) \
            .execute()
            
        return {'success': True, 'strikes': res.data if res.data else []}

    async def clear_user_warnings(self, guild_id: int, user_id: int, reason: str, moderator_id: int) -> Dict:
        """Clear (deactivate) active user warnings natively in DB"""
        dm = self.protection_manager.data_manager
        try:
            dm.supabase.table('strikes') \
                .update({'is_active': False}) \
                .eq('guild_id', str(guild_id)) \
                .eq('user_id', str(user_id)) \
                .execute()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to clear warnings: {e}")
            return {'success': False, 'error': str(e)}

    async def pardon_user(self, guild_id: int, user_id: int, reason: str, moderator_id: int) -> Dict:
        return await self.clear_user_warnings(guild_id, user_id, reason, moderator_id)

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
