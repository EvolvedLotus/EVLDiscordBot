"""
Channel Lock Manager - Handles scheduled channel locking/unlocking (Premium Feature)

This manager provides:
- Schedule creation, update, and deletion
- Channel permission management (lock/unlock)
- Bot permission verification
- Timezone-aware scheduling
"""

import logging
from datetime import datetime, time as time_type
from typing import Dict, Any, List, Optional, Tuple
import pytz
import discord

logger = logging.getLogger(__name__)


class ChannelLockManager:
    """Manages scheduled channel lock/unlock functionality for premium guilds."""
    
    # Common timezones for display in UI
    COMMON_TIMEZONES = [
        'America/New_York',
        'America/Chicago', 
        'America/Denver',
        'America/Los_Angeles',
        'America/Toronto',
        'Europe/London',
        'Europe/Paris',
        'Europe/Berlin',
        'Asia/Tokyo',
        'Asia/Singapore',
        'Australia/Sydney',
        'Pacific/Auckland',
        'UTC'
    ]
    
    def __init__(self, data_manager):
        """Initialize the channel lock manager.
        
        Args:
            data_manager: The DataManager instance for database access
        """
        self.data_manager = data_manager
        self._bot_instance = None
        logger.info("✅ ChannelLockManager initialized")
    
    def set_bot_instance(self, bot):
        """Set the bot instance for Discord operations.
        
        Args:
            bot: The Discord bot instance
        """
        self._bot_instance = bot
        logger.info("✅ Bot instance set for ChannelLockManager")
    
    # ============== PREMIUM CHECK ==============
    
    def is_premium_guild(self, guild_id: str) -> bool:
        """Check if a guild has premium subscription.
        
        Args:
            guild_id: The Discord guild ID
            
        Returns:
            bool: True if guild has premium tier
        """
        try:
            config = self.data_manager.load_guild_data(guild_id, 'config')
            tier = config.get('subscription_tier', 'free')
            return tier == 'premium'
        except Exception as e:
            logger.error(f"Error checking premium status for guild {guild_id}: {e}")
            return False
    
    # ============== SCHEDULE CRUD ==============
    
    def get_schedules(self, guild_id: str) -> List[Dict[str, Any]]:
        """Get all channel lock schedules for a guild.
        
        Args:
            guild_id: The Discord guild ID
            
        Returns:
            List of schedule dictionaries
        """
        try:
            result = self.data_manager.admin_client.table('channel_schedules') \
                .select('*') \
                .eq('guild_id', str(guild_id)) \
                .order('created_at', desc=False) \
                .execute()
            
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error fetching schedules for guild {guild_id}: {e}")
            return []
    
    def get_schedule(self, guild_id: str, schedule_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific schedule by ID.
        
        Args:
            guild_id: The Discord guild ID
            schedule_id: The schedule UUID
            
        Returns:
            Schedule dict or None if not found
        """
        try:
            result = self.data_manager.admin_client.table('channel_schedules') \
                .select('*') \
                .eq('guild_id', str(guild_id)) \
                .eq('schedule_id', schedule_id) \
                .execute()
            
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error fetching schedule {schedule_id}: {e}")
            return None
    
    def create_schedule(self, guild_id: str, data: Dict[str, Any], created_by: str = None) -> Dict[str, Any]:
        """Create a new channel lock schedule.
        
        Args:
            guild_id: The Discord guild ID
            data: Schedule configuration:
                - channel_id: Discord channel ID
                - unlock_time: Time string (HH:MM or HH:MM:SS)
                - lock_time: Time string (HH:MM or HH:MM:SS)
                - timezone: IANA timezone string
                - active_days: List of weekday integers (0-6)
            created_by: User ID who created the schedule
            
        Returns:
            Created schedule dict or error dict
        """
        try:
            channel_id = str(data.get('channel_id'))
            
            # Check for existing schedule on this channel
            existing = self.data_manager.admin_client.table('channel_schedules') \
                .select('schedule_id') \
                .eq('guild_id', str(guild_id)) \
                .eq('channel_id', channel_id) \
                .execute()
            
            if existing.data:
                return {'error': 'A schedule already exists for this channel'}
            
            # Validate timezone
            timezone = data.get('timezone', 'America/New_York')
            if timezone not in pytz.all_timezones:
                return {'error': f'Invalid timezone: {timezone}'}
            
            # Parse times
            unlock_time = self._parse_time(data.get('unlock_time', '09:00'))
            lock_time = self._parse_time(data.get('lock_time', '21:00'))
            
            if not unlock_time or not lock_time:
                return {'error': 'Invalid time format. Use HH:MM or HH:MM:SS'}
            
            # Get channel name for display
            channel_name = data.get('channel_name', '')
            if not channel_name and self._bot_instance:
                guild = self._bot_instance.get_guild(int(guild_id))
                if guild:
                    channel = guild.get_channel(int(channel_id))
                    if channel:
                        channel_name = channel.name
            
            # Prepare active days
            active_days = data.get('active_days', [0, 1, 2, 3, 4, 5, 6])
            if isinstance(active_days, str):
                active_days = [int(d.strip()) for d in active_days.split(',')]
            
            # Insert schedule
            schedule_data = {
                'guild_id': str(guild_id),
                'channel_id': channel_id,
                'channel_name': channel_name,
                'unlock_time': unlock_time.strftime('%H:%M:%S'),
                'lock_time': lock_time.strftime('%H:%M:%S'),
                'timezone': timezone,
                'active_days': active_days,
                'is_enabled': data.get('is_enabled', True),
                'current_state': 'locked',
                'created_by': created_by
            }
            
            result = self.data_manager.admin_client.table('channel_schedules') \
                .insert(schedule_data) \
                .execute()
            
            if result.data:
                logger.info(f"Created channel schedule for {channel_name} in guild {guild_id}")
                return {'success': True, 'schedule': result.data[0]}
            
            return {'error': 'Failed to create schedule'}
            
        except Exception as e:
            logger.error(f"Error creating schedule: {e}")
            return {'error': str(e)}
    
    def update_schedule(self, guild_id: str, schedule_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing channel lock schedule.
        
        Args:
            guild_id: The Discord guild ID  
            schedule_id: The schedule UUID
            data: Fields to update
            
        Returns:
            Updated schedule dict or error dict
        """
        try:
            update_data = {}
            
            # Only include provided fields
            if 'unlock_time' in data:
                parsed = self._parse_time(data['unlock_time'])
                if parsed:
                    update_data['unlock_time'] = parsed.strftime('%H:%M:%S')
            
            if 'lock_time' in data:
                parsed = self._parse_time(data['lock_time'])
                if parsed:
                    update_data['lock_time'] = parsed.strftime('%H:%M:%S')
            
            if 'timezone' in data:
                if data['timezone'] in pytz.all_timezones:
                    update_data['timezone'] = data['timezone']
                else:
                    return {'error': f'Invalid timezone: {data["timezone"]}'}
            
            if 'active_days' in data:
                active_days = data['active_days']
                if isinstance(active_days, str):
                    active_days = [int(d.strip()) for d in active_days.split(',')]
                update_data['active_days'] = active_days
            
            if 'is_enabled' in data:
                update_data['is_enabled'] = bool(data['is_enabled'])
            
            if not update_data:
                return {'error': 'No valid fields to update'}
            
            result = self.data_manager.admin_client.table('channel_schedules') \
                .update(update_data) \
                .eq('guild_id', str(guild_id)) \
                .eq('schedule_id', schedule_id) \
                .execute()
            
            if result.data:
                logger.info(f"Updated schedule {schedule_id} in guild {guild_id}")
                return {'success': True, 'schedule': result.data[0]}
            
            return {'error': 'Schedule not found'}
            
        except Exception as e:
            logger.error(f"Error updating schedule {schedule_id}: {e}")
            return {'error': str(e)}
    
    def delete_schedule(self, guild_id: str, schedule_id: str) -> Dict[str, Any]:
        """Delete a channel lock schedule.
        
        Args:
            guild_id: The Discord guild ID
            schedule_id: The schedule UUID
            
        Returns:
            Success/error dict
        """
        try:
            # Get schedule to potentially unlock channel first
            schedule = self.get_schedule(guild_id, schedule_id)
            
            if schedule and schedule.get('current_state') == 'locked':
                # Unlock the channel before deleting
                logger.info(f"Unlocking channel before deleting schedule {schedule_id}")
                # This is async, so we can't await here - handled by caller
            
            result = self.data_manager.admin_client.table('channel_schedules') \
                .delete() \
                .eq('guild_id', str(guild_id)) \
                .eq('schedule_id', schedule_id) \
                .execute()
            
            logger.info(f"Deleted schedule {schedule_id} from guild {guild_id}")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error deleting schedule {schedule_id}: {e}")
            return {'error': str(e)}
    
    # ============== CHANNEL LOCK/UNLOCK ==============
    
    async def lock_channel(self, guild_id: str, channel_id: str, schedule_id: str = None) -> Dict[str, Any]:
        """Lock a channel by denying SEND_MESSAGES for @everyone.
        
        Args:
            guild_id: The Discord guild ID
            channel_id: The channel to lock
            schedule_id: Optional schedule ID to update state
            
        Returns:
            Success/error dict
        """
        if not self._bot_instance:
            return {'error': 'Bot instance not available'}
        
        try:
            guild = self._bot_instance.get_guild(int(guild_id))
            if not guild:
                return {'error': 'Guild not found'}
            
            channel = guild.get_channel(int(channel_id))
            if not channel:
                await self._mark_schedule_error(schedule_id, 'Channel not found or deleted')
                return {'error': 'Channel not found'}
            
            if not isinstance(channel, discord.TextChannel):
                return {'error': 'Channel is not a text channel'}
            
            # Check bot permissions
            bot_member = guild.me
            if not channel.permissions_for(bot_member).manage_channels:
                await self._mark_schedule_error(schedule_id, 'Bot lacks Manage Channels permission')
                return {'error': 'Bot lacks Manage Channels permission'}
            
            if not channel.permissions_for(bot_member).manage_roles:
                await self._mark_schedule_error(schedule_id, 'Bot lacks Manage Roles permission')
                return {'error': 'Bot lacks Manage Roles permission'}
            
            # Get @everyone role
            everyone_role = guild.default_role
            
            # Store original permissions before modifying
            original_overwrite = channel.overwrites_for(everyone_role)
            original_send = original_overwrite.send_messages
            
            # Set send_messages to False for @everyone
            await channel.set_permissions(
                everyone_role,
                send_messages=False,
                reason="Scheduled channel lock by EVL Bot"
            )
            
            # Update schedule state
            if schedule_id:
                await self._update_schedule_state(
                    schedule_id, 
                    'locked',
                    original_permissions={'everyone_send_messages': original_send}
                )
            
            logger.info(f"🔒 Locked channel #{channel.name} in guild {guild.name}")
            return {'success': True, 'state': 'locked'}
            
        except discord.Forbidden:
            error_msg = 'Insufficient permissions to modify channel'
            await self._mark_schedule_error(schedule_id, error_msg)
            return {'error': error_msg}
        except Exception as e:
            logger.error(f"Error locking channel: {e}")
            await self._mark_schedule_error(schedule_id, str(e))
            return {'error': str(e)}
    
    async def unlock_channel(self, guild_id: str, channel_id: str, schedule_id: str = None) -> Dict[str, Any]:
        """Unlock a channel by allowing SEND_MESSAGES for @everyone.
        
        Args:
            guild_id: The Discord guild ID
            channel_id: The channel to unlock
            schedule_id: Optional schedule ID to update state
            
        Returns:
            Success/error dict
        """
        if not self._bot_instance:
            return {'error': 'Bot instance not available'}
        
        try:
            guild = self._bot_instance.get_guild(int(guild_id))
            if not guild:
                return {'error': 'Guild not found'}
            
            channel = guild.get_channel(int(channel_id))
            if not channel:
                await self._mark_schedule_error(schedule_id, 'Channel not found or deleted')
                return {'error': 'Channel not found'}
            
            if not isinstance(channel, discord.TextChannel):
                return {'error': 'Channel is not a text channel'}
            
            # Check bot permissions
            bot_member = guild.me
            if not channel.permissions_for(bot_member).manage_channels:
                await self._mark_schedule_error(schedule_id, 'Bot lacks Manage Channels permission')
                return {'error': 'Bot lacks Manage Channels permission'}
            
            # Get @everyone role
            everyone_role = guild.default_role
            
            # Set send_messages to None (inherit from category/server) for @everyone
            # Using None instead of True to restore default behavior
            await channel.set_permissions(
                everyone_role,
                send_messages=None,  # Reset to inherit
                reason="Scheduled channel unlock by EVL Bot"
            )
            
            # Update schedule state
            if schedule_id:
                await self._update_schedule_state(schedule_id, 'unlocked')
            
            logger.info(f"🔓 Unlocked channel #{channel.name} in guild {guild.name}")
            return {'success': True, 'state': 'unlocked'}
            
        except discord.Forbidden:
            error_msg = 'Insufficient permissions to modify channel'
            await self._mark_schedule_error(schedule_id, error_msg)
            return {'error': error_msg}
        except Exception as e:
            logger.error(f"Error unlocking channel: {e}")
            await self._mark_schedule_error(schedule_id, str(e))
            return {'error': str(e)}
    
    # ============== SCHEDULE PROCESSING ==============
    
    def get_all_enabled_schedules(self) -> List[Dict[str, Any]]:
        """Get all enabled schedules across all premium guilds.
        
        Returns:
            List of enabled schedule dictionaries
        """
        try:
            result = self.data_manager.admin_client.table('channel_schedules') \
                .select('*') \
                .eq('is_enabled', True) \
                .execute()
            
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error fetching all enabled schedules: {e}")
            return []
    
    def should_be_unlocked(self, schedule: Dict[str, Any]) -> bool:
        """Check if a channel should currently be unlocked based on schedule.
        
        Args:
            schedule: Schedule dictionary
            
        Returns:
            True if channel should be unlocked, False if locked
        """
        try:
            tz = pytz.timezone(schedule.get('timezone', 'America/New_York'))
            now = datetime.now(tz)
            
            # Check if today is an active day
            weekday = now.weekday()  # Monday=0, Sunday=6
            # Convert to our format (Sunday=0, Saturday=6)
            weekday_sunday_start = (weekday + 1) % 7
            
            active_days = schedule.get('active_days', [0, 1, 2, 3, 4, 5, 6])
            if weekday_sunday_start not in active_days:
                return False  # Not an active day, stay locked
            
            # Parse schedule times
            unlock_time = self._parse_time(schedule.get('unlock_time', '09:00'))
            lock_time = self._parse_time(schedule.get('lock_time', '21:00'))
            
            if not unlock_time or not lock_time:
                return False
            
            current_time = now.time()
            
            # Handle overnight schedules (e.g., unlock at 22:00, lock at 06:00)
            if unlock_time > lock_time:
                # Overnight: unlocked if current >= unlock OR current < lock
                return current_time >= unlock_time or current_time < lock_time
            else:
                # Normal: unlocked if current is between unlock and lock
                return unlock_time <= current_time < lock_time
            
        except Exception as e:
            logger.error(f"Error checking schedule state: {e}")
            return False
    
    async def process_all_schedules(self) -> Dict[str, Any]:
        """Process all enabled schedules and lock/unlock channels as needed.
        
        This should be called periodically by a background task.
        
        Returns:
            Summary of actions taken
        """
        schedules = self.get_all_enabled_schedules()
        results = {
            'processed': 0,
            'locked': 0,
            'unlocked': 0,
            'errors': 0,
            'skipped': 0
        }
        
        for schedule in schedules:
            guild_id = schedule['guild_id']
            schedule_id = schedule['schedule_id']
            channel_id = schedule['channel_id']
            current_state = schedule.get('current_state', 'locked')
            
            try:
                # Skip non-premium guilds
                if not self.is_premium_guild(guild_id):
                    results['skipped'] += 1
                    continue
                
                should_unlock = self.should_be_unlocked(schedule)
                
                if should_unlock and current_state != 'unlocked':
                    # Should be unlocked but isn't
                    result = await self.unlock_channel(guild_id, channel_id, schedule_id)
                    if result.get('success'):
                        results['unlocked'] += 1
                    else:
                        results['errors'] += 1
                        
                elif not should_unlock and current_state != 'locked':
                    # Should be locked but isn't
                    result = await self.lock_channel(guild_id, channel_id, schedule_id)
                    if result.get('success'):
                        results['locked'] += 1
                    else:
                        results['errors'] += 1
                
                results['processed'] += 1
                
            except Exception as e:
                logger.error(f"Error processing schedule {schedule_id}: {e}")
                results['errors'] += 1
        
        if results['locked'] or results['unlocked']:
            logger.info(f"📅 Schedule processing: {results['locked']} locked, "
                       f"{results['unlocked']} unlocked, {results['errors']} errors")
        
        return results
    
    async def sync_schedules_on_startup(self) -> Dict[str, Any]:
        """Sync all channel states on bot startup.
        
        This ensures channel states match their schedules after a restart.
        
        Returns:
            Sync results summary
        """
        logger.info("🔄 Syncing channel lock schedules on startup...")
        return await self.process_all_schedules()
    
    # ============== BOT PERMISSION CHECK ==============
    
    async def check_channel_permissions(self, guild_id: str, channel_id: str) -> Dict[str, Any]:
        """Check if bot has required permissions on a channel.
        
        Args:
            guild_id: The Discord guild ID
            channel_id: The channel to check
            
        Returns:
            Dict with permission status and details
        """
        if not self._bot_instance:
            return {'has_permissions': False, 'error': 'Bot not connected'}
        
        try:
            guild = self._bot_instance.get_guild(int(guild_id))
            if not guild:
                return {'has_permissions': False, 'error': 'Guild not found'}
            
            channel = guild.get_channel(int(channel_id))
            if not channel:
                return {'has_permissions': False, 'error': 'Channel not found'}
            
            bot_perms = channel.permissions_for(guild.me)
            
            return {
                'has_permissions': bot_perms.manage_channels and bot_perms.manage_roles,
                'manage_channels': bot_perms.manage_channels,
                'manage_roles': bot_perms.manage_roles,
                'channel_name': channel.name,
                'channel_type': str(channel.type)
            }
            
        except Exception as e:
            return {'has_permissions': False, 'error': str(e)}
    
    # ============== HELPER METHODS ==============
    
    def _parse_time(self, time_str: str) -> Optional[time_type]:
        """Parse a time string into a time object.
        
        Args:
            time_str: Time string in HH:MM or HH:MM:SS format
            
        Returns:
            time object or None if invalid
        """
        if not time_str:
            return None
        
        try:
            # Handle both HH:MM and HH:MM:SS formats
            if len(time_str.split(':')) == 2:
                return datetime.strptime(time_str, '%H:%M').time()
            else:
                return datetime.strptime(time_str, '%H:%M:%S').time()
        except ValueError:
            return None
    
    async def _update_schedule_state(self, schedule_id: str, state: str, 
                                      original_permissions: Dict = None):
        """Update schedule state in database.
        
        Args:
            schedule_id: The schedule UUID
            state: New state ('locked', 'unlocked', 'error')
            original_permissions: Optional permissions snapshot
        """
        try:
            update_data = {
                'current_state': state,
                'last_state_change': datetime.now().isoformat(),
                'last_error': None
            }
            
            if original_permissions:
                update_data['original_permissions'] = original_permissions
            
            self.data_manager.admin_client.table('channel_schedules') \
                .update(update_data) \
                .eq('schedule_id', schedule_id) \
                .execute()
                
        except Exception as e:
            logger.error(f"Error updating schedule state: {e}")
    
    async def _mark_schedule_error(self, schedule_id: str, error_message: str):
        """Mark a schedule as having an error.
        
        Args:
            schedule_id: The schedule UUID
            error_message: Error description
        """
        if not schedule_id:
            return
        
        try:
            self.data_manager.admin_client.table('channel_schedules') \
                .update({
                    'current_state': 'error',
                    'last_error': error_message,
                    'last_state_change': datetime.now().isoformat()
                }) \
                .eq('schedule_id', schedule_id) \
                .execute()
                
        except Exception as e:
            logger.error(f"Error marking schedule error: {e}")
    
    def get_timezones(self) -> List[Dict[str, str]]:
        """Get list of common timezones for UI display.
        
        Returns:
            List of timezone dicts with id and display name
        """
        timezones = []
        for tz_name in self.COMMON_TIMEZONES:
            try:
                tz = pytz.timezone(tz_name)
                now = datetime.now(tz)
                offset = now.strftime('%z')
                # Format offset as +HH:MM
                offset_formatted = f"{offset[:3]}:{offset[3:]}"
                timezones.append({
                    'id': tz_name,
                    'name': f"{tz_name.replace('_', ' ')} ({offset_formatted})"
                })
            except Exception:
                timezones.append({
                    'id': tz_name,
                    'name': tz_name.replace('_', ' ')
                })
        
        return timezones
