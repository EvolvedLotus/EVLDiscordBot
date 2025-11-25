"""
TASK CHANNEL MONITOR
Monitors task channel and ensures all active tasks are always displayed
Reposts tasks if they're deleted manually
"""

import discord
from discord.ext import tasks
import logging
from datetime import datetime, timezone
import asyncio

logger = logging.getLogger(__name__)


class TaskChannelMonitor:
    """Monitors task channel and maintains task messages"""
    
    def __init__(self, bot, data_manager, ad_claim_manager):
        self.bot = bot
        self.data_manager = data_manager
        self.ad_claim_manager = ad_claim_manager
        self.monitoring = False
        
    async def start_monitoring(self):
        """Start the task channel monitoring loop"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_task_channels.start()
            logger.info("✅ Task channel monitoring started")
    
    async def stop_monitoring(self):
        """Stop the task channel monitoring loop"""
        if self.monitoring:
            self.monitor_task_channels.cancel()
            self.monitoring = False
            logger.info("⏹️ Task channel monitoring stopped")
    
    @tasks.loop(minutes=5)  # Check every 5 minutes
    async def monitor_task_channels(self):
        """Check all guilds and ensure task messages are posted"""
        try:
            # Get all active guilds
            guilds_data = self.data_manager.admin_client.table('guilds').select('*').eq('is_active', True).execute()
            
            for guild_data in guilds_data.data:
                guild_id = guild_data['guild_id']
                task_channel_id = guild_data.get('task_channel_id')
                
                if not task_channel_id:
                    continue  # Skip if no task channel configured
                
                try:
                    await self.sync_guild_tasks(guild_id, task_channel_id)
                except Exception as e:
                    logger.error(f"Error syncing tasks for guild {guild_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in task channel monitor: {e}")
    
    @monitor_task_channels.before_loop
    async def before_monitor(self):
        """Wait for bot to be ready before starting monitor"""
        await self.bot.wait_until_ready()
    
    async def sync_guild_tasks(self, guild_id: str, task_channel_id: str):
        """Sync all tasks for a guild to the task channel"""
        try:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return
            
            channel = guild.get_channel(int(task_channel_id))
            if not channel:
                logger.warning(f"Task channel {task_channel_id} not found in guild {guild_id}")
                return
            
            # Get all active tasks (regular + global)
            regular_tasks = await self.get_active_tasks(guild_id)
            global_tasks = await self.get_global_tasks()
            
            all_tasks = regular_tasks + global_tasks
            
            for task in all_tasks:
                await self.ensure_task_posted(guild, channel, task)
                
        except Exception as e:
            logger.error(f"Error syncing guild tasks: {e}")
    
    async def get_active_tasks(self, guild_id: str):
        """Get all active regular tasks for a guild"""
        try:
            # Use file-based storage (same as task_manager)
            tasks_data = self.data_manager.load_guild_data(guild_id, 'tasks')
            if not tasks_data:
                return []
            
            tasks = tasks_data.get('tasks', {})
            active_tasks = []
            
            for task_id, task in tasks.items():
                # Skip non-active tasks
                if task.get('status') != 'active':
                    continue
                
                # Check if not expired
                if task.get('expires_at'):
                    expires_at = task['expires_at']
                    if isinstance(expires_at, str):
                        expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    
                    if expires_at <= datetime.now(timezone.utc):
                        continue  # Skip expired
                
                # Add task with ID
                active_tasks.append({
                    **task,
                    'task_id': task_id,
                    'is_global': False
                })
            
            return active_tasks
        except Exception as e:
            logger.error(f"Error getting active tasks: {e}")
            return []
    
    async def get_global_tasks(self):
        """Get all active global tasks"""
        try:
            result = self.data_manager.admin_client.table('global_tasks').select('*').eq('is_active', True).execute()
            
            tasks = []
            for task in result.data:
                # Convert global task format to regular task format
                tasks.append({
                    'task_id': task['task_key'],  # Use task_key as ID
                    'guild_id': 'global',
                    'name': task['title'],
                    'description': task['description'],
                    'reward': task['reward_amount'],
                    'status': 'active',
                    'is_global': True,
                    'is_repeatable': task.get('is_repeatable', False),
                    'cooldown_minutes': task.get('cooldown_minutes', 0),
                    'disclaimer': task.get('disclaimer'),
                    'task_key': task['task_key']
                })
            
            return tasks
        except Exception as e:
            logger.error(f"Error getting global tasks: {e}")
            return []
    
    async def ensure_task_posted(self, guild: discord.Guild, channel: discord.TextChannel, task: dict):
        """Ensure a task is posted in the channel, repost if deleted"""
        try:
            message_id = task.get('message_id')
            task_id = task.get('task_id')
            is_global = task.get('is_global', False)
            
            # Try to fetch existing message
            message_exists = False
            if message_id:
                try:
                    await channel.fetch_message(int(message_id))
                    message_exists = True
                except discord.NotFound:
                    message_exists = False
                except Exception as e:
                    logger.error(f"Error fetching message {message_id}: {e}")
            
            # If message doesn't exist, post it
            if not message_exists:
                logger.info(f"Reposting task {task_id} to channel {channel.id}")
                await self.post_task_message(guild, channel, task)
                
        except Exception as e:
            logger.error(f"Error ensuring task posted: {e}")
    
    async def post_task_message(self, guild: discord.Guild, channel: discord.TextChannel, task: dict):
        """Post a task message to the channel"""
        try:
            is_global = task.get('is_global', False)
            
            # Create embed
            embed = discord.Embed(
                title=f"{'🌍 ' if is_global else ''}📋 {task['name']}",
                description=task.get('description', 'No description provided'),
                color=discord.Color.purple() if is_global else discord.Color.blue()
            )
            
            embed.add_field(
                name="💰 Reward",
                value=f"{task['reward']} points",
                inline=True
            )
            
            if is_global:
                if task.get('is_repeatable'):
                    cooldown = task.get('cooldown_minutes', 0)
                    if cooldown > 0:
                        embed.add_field(
                            name="🔄 Repeatable",
                            value=f"Every {cooldown} minutes",
                            inline=True
                        )
                    else:
                        embed.add_field(
                            name="🔄 Repeatable",
                            value="Unlimited",
                            inline=True
                        )
                
                embed.add_field(
                    name="🌍 Availability",
                    value="All Servers",
                    inline=True
                )
                
                if task.get('disclaimer'):
                    embed.set_footer(text=task['disclaimer'])
            else:
                # Regular task - show expiration
                if task.get('expires_at'):
                    expires_at = datetime.fromisoformat(task['expires_at'].replace('Z', '+00:00'))
                    embed.add_field(
                        name="⏰ Expires",
                        value=f"<t:{int(expires_at.timestamp())}:R>",
                        inline=True
                    )
                
                if task.get('max_claims') and task['max_claims'] > 0:
                    current = task.get('current_claims', 0)
                    max_claims = task['max_claims']
                    embed.add_field(
                        name="👥 Claims",
                        value=f"{current}/{max_claims}",
                        inline=True
                    )
            
            # Create view with claim button
            from cogs.tasks import TaskClaimView
            view = TaskClaimView(task['task_id'])
            
            # Post message
            message = await channel.send(embed=embed, view=view)
            
            # Update database with message ID
            if is_global:
                # For global tasks, store message ID per guild
                await self.store_global_task_message(guild.id, task['task_key'], channel.id, message.id)
            else:
                # Update regular task in file-based storage
                try:
                    tasks_data = self.data_manager.load_guild_data(str(guild.id), 'tasks')
                    if tasks_data and 'tasks' in tasks_data:
                        task_id = task['task_id']
                        if task_id in tasks_data['tasks']:
                            tasks_data['tasks'][task_id]['message_id'] = str(message.id)
                            tasks_data['tasks'][task_id]['channel_id'] = str(channel.id)
                            self.data_manager.save_guild_data(str(guild.id), 'tasks', tasks_data)
                except Exception as e:
                    logger.error(f"Error saving task message ID to file storage: {e}")
            
            logger.info(f"✅ Posted task {task['task_id']} to channel {channel.id} (message {message.id})")
            
        except Exception as e:
            logger.error(f"Error posting task message: {e}")
    
    async def store_global_task_message(self, guild_id: int, task_key: str, channel_id: int, message_id: int):
        """Store global task message ID for a specific guild"""
        try:
            # Create or update global_task_messages table entry
            self.data_manager.admin_client.table('global_task_messages').upsert({
                'guild_id': str(guild_id),
                'task_key': task_key,
                'channel_id': str(channel_id),
                'message_id': str(message_id),
                'posted_at': datetime.now(timezone.utc).isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"Error storing global task message: {e}")
    
    async def on_task_channel_set(self, guild_id: str, channel_id: str):
        """Called when a task channel is set for a guild"""
        try:
            logger.info(f"Task channel set for guild {guild_id}: {channel_id}")
            # Immediately sync tasks to the new channel
            await self.sync_guild_tasks(guild_id, channel_id)
        except Exception as e:
            logger.error(f"Error handling task channel set: {e}")
    
    async def on_task_created(self, guild_id: str, task: dict):
        """Called when a new task is created"""
        try:
            # Get task channel
            guild_data = self.data_manager.admin_client.table('guilds').select('task_channel_id').eq('guild_id', guild_id).single().execute()
            
            if guild_data.data and guild_data.data.get('task_channel_id'):
                task_channel_id = guild_data.data['task_channel_id']
                guild = self.bot.get_guild(int(guild_id))
                
                if guild:
                    channel = guild.get_channel(int(task_channel_id))
                    if channel:
                        await self.post_task_message(guild, channel, task)
        except Exception as e:
            logger.error(f"Error handling task created: {e}")
    
    async def on_task_deleted(self, guild_id: str, task_id: str):
        """Called when a task is deleted"""
        try:
            # Get task data from file-based storage
            tasks_data = self.data_manager.load_guild_data(guild_id, 'tasks')
            if not tasks_data or 'tasks' not in tasks_data:
                return
            
            task = tasks_data['tasks'].get(task_id)
            if task and task.get('message_id'):
                message_id = task['message_id']
                channel_id = task.get('channel_id')
                
                if channel_id:
                    guild = self.bot.get_guild(int(guild_id))
                    if guild:
                        channel = guild.get_channel(int(channel_id))
                        if channel:
                            try:
                                message = await channel.fetch_message(int(message_id))
                                await message.delete()
                                logger.info(f"Deleted task message {message_id} from channel {channel_id}")
                            except discord.NotFound:
                                pass  # Already deleted
                            except Exception as e:
                                logger.error(f"Error deleting task message: {e}")
        except Exception as e:
            logger.error(f"Error handling task deleted: {e}")


async def setup(bot):
    """Setup function for the monitor"""
    # This will be initialized in bot.py
    pass
