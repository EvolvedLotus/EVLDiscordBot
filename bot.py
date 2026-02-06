# In bot.py - Ensure proper initialization order

import asyncio
import logging
import threading
import sys
from datetime import datetime, timezone
import discord
from discord.ext import commands, tasks
import os
from aiohttp import web
import json

# Import components
from core.data_manager import DataManager
from core.transaction_manager import TransactionManager
from core.task_manager import TaskManager
from core.shop_manager import ShopManager
from core.cache_manager import CacheManager
from core.initializer import GuildInitializer
from config import config

# Setup logging first
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load environment variables (only for local development)
if os.getenv('ENVIRONMENT') != 'production':
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed in production

# Environment variable validation for Railway deployment
REQUIRED_ENV_VARS = {
    'DISCORD_TOKEN': 'Discord bot token',
    'SUPABASE_URL': 'Supabase project URL',
    'SUPABASE_ANON_KEY': 'Supabase anon key',
    'SUPABASE_SERVICE_ROLE_KEY': 'Supabase service role key',
    'JWT_SECRET_KEY': 'JWT secret for authentication',
    'PORT': 'Server port (Railway auto-assigns)',
}

missing = []
for var, description in REQUIRED_ENV_VARS.items():
    if not os.getenv(var):
        missing.append(f"{var} ({description})")

if missing:
    print("❌ MISSING REQUIRED ENVIRONMENT VARIABLES:")
    for m in missing:
        print(f"  - {m}")
    sys.exit(1)

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Initialize data manager (global instance)
data_manager = DataManager()

def create_bot():
    """Create and configure the Discord bot"""

    # Create bot with intents
    intents = discord.Intents.default()
    intents.members = True
    intents.guilds = True

    # Enable message_content intent if available (privileged intent in Discord API)
    if hasattr(intents, 'message_content'):
        intents.message_content = True
    else:
        logger.warning("message_content intent not available - some features may not work")

    bot = commands.Bot(
        command_prefix=commands.when_mentioned,
        intents=intents,
        help_command=None
    )

    # Add CommandTree for slash commands
    tree = bot.tree

    return bot, DISCORD_TOKEN

async def run_bot():
    """Async function to run the bot (called by start.py)"""
    try:
        logger.info("=" * 50)
        logger.info("EVL Discord Bot Starting...")
        logger.info("=" * 50)

        # Create bot instance
        bot, token = create_bot()

        # Import backend functions (delayed to avoid circular import)
        from backend import run_backend, set_bot_instance, set_data_manager

        # CRITICAL: Attach managers to bot BEFORE loading cogs
        logger.info("Initializing managers...")
        bot.data_manager = data_manager
        bot.cache_manager = CacheManager()
        bot.transaction_manager = TransactionManager(data_manager, cache_manager=bot.cache_manager)
        bot.task_manager = TaskManager(data_manager, bot.transaction_manager)
        bot.task_manager.set_cache_manager(bot.cache_manager)
        bot.shop_manager = ShopManager(data_manager, bot.transaction_manager)
        
        # Initialize ad claim manager
        try:
            from core.ad_claim_manager import AdClaimManager
            bot.ad_claim_manager = AdClaimManager(data_manager, bot.transaction_manager)
            logger.info("✓ Ad claim manager initialized")
        except Exception as e:
            logger.error(f"✗ Failed to initialize ad claim manager: {e}")
            bot.ad_claim_manager = None
        
        # Initialize channel lock manager (Premium Feature)
        try:
            from core.channel_lock_manager import ChannelLockManager
            bot.channel_lock_manager = ChannelLockManager(data_manager)
            bot.channel_lock_manager.set_bot_instance(bot)
            logger.info("✓ Channel lock manager initialized")
        except Exception as e:
            logger.error(f"✗ Failed to initialize channel lock manager: {e}")
            bot.channel_lock_manager = None
        
        # Initialize task channel monitor
        try:
            from core.task_channel_monitor import TaskChannelMonitor
            bot.task_channel_monitor = TaskChannelMonitor(bot, data_manager, bot.ad_claim_manager)
            logger.info("✓ Task channel monitor initialized")
        except Exception as e:
            logger.error(f"✗ Failed to initialize task channel monitor: {e}")
            bot.task_channel_monitor = None

        # Set global references for backend
        set_bot_instance(bot)
        set_data_manager(data_manager)

        # CRITICAL: Link bot instance to data manager for sync
        data_manager.set_bot_instance(bot)

        # Initialize SSE manager with event loop
        from core.sse_manager import sse_manager
        sse_manager.set_event_loop(asyncio.get_event_loop())
        sse_manager.start()

        # Load cogs AFTER managers are attached
        logger.info("Loading cogs...")
        try:
            await bot.load_extension('cogs.currency')
            logger.info("✓ Currency cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load currency cog: {e}")

        try:
            await bot.load_extension('cogs.admin')
            logger.info("✓ Admin cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load admin cog: {e}")

        try:
            await bot.load_extension('cogs.general')
            logger.info("✓ General cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load general cog: {e}")

        try:
            await bot.load_extension('cogs.announcements')
            logger.info("✓ Announcements cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load announcements cog: {e}")

        try:
            await bot.load_extension('cogs.tasks')
            logger.info("✓ Tasks cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load tasks cog: {e}")

        try:
            await bot.load_extension('cogs.bot_admin')
            logger.info("✓ Bot Admin cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load bot admin cog: {e}")

        try:
            await bot.load_extension('cogs.embeds')
            logger.info("✓ Embeds cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load embeds cog: {e}")



        try:
            await bot.load_extension('cogs.moderation')
            logger.info("✓ Moderation cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load moderation cog: {e}")

        try:
            await bot.load_extension('cogs.ad_claim')
            logger.info("✓ Ad Claim cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load ad claim cog: {e}")

        try:
            await bot.load_extension('cogs.server_boost')
            logger.info("✓ Server Boost cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load server boost cog: {e}")

        try:
            await bot.load_extension('cogs.vote')
            logger.info("✓ Vote cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load vote cog: {e}")

        try:
            await bot.load_extension('cogs.premium_sync')
            logger.info("✓ Premium Sync cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load premium sync cog: {e}")


        # Register persistent views BEFORE on_ready to handle button interactions after bot restarts
        logger.info("Registering persistent views...")
        try:
            from core.task_channel_monitor import GlobalTaskClaimView
            from cogs.tasks import TaskClaimView
            
            # Register GlobalTaskClaimView for ad claim tasks
            # Note: We'll pass ad_claim_manager when the view is recreated
            bot.add_view(GlobalTaskClaimView(task_key='ad_claim_task', ad_claim_manager=bot.ad_claim_manager))
            logger.info("✓ Registered GlobalTaskClaimView (ad claim)")
            
            # Register TaskClaimView for regular tasks
            # Note: task_id will be set when the view is recreated from the message
            bot.add_view(TaskClaimView(task_id=''))
            logger.info("✓ Registered TaskClaimView (regular tasks)")
        except Exception as e:
            logger.error(f"✗ Failed to register persistent views: {e}")

        for cog_name in ['Moderation']:
            cog = bot.get_cog(cog_name)
            if cog and hasattr(cog, 'set_managers'):
                try:
                    cog.set_managers(data_manager)
                    logger.info(f"✓ Set managers on {cog_name} cog")
                except Exception as e:
                    logger.error(f"✗ Failed to set managers on {cog_name} cog: {e}")

        # Set managers for Tasks cog specifically
        tasks_cog = bot.get_cog('Tasks')
        if tasks_cog and hasattr(tasks_cog, 'set_managers'):
            try:
                tasks_cog.set_managers(data_manager, bot.transaction_manager)
                logger.info("✓ Set managers on Tasks cog")
            except Exception as e:
                logger.error(f"✗ Failed to set managers on Tasks cog: {e}")
        
        # Set manager for AdClaim cog
        ad_claim_cog = bot.get_cog('AdClaim')
        if ad_claim_cog and hasattr(ad_claim_cog, 'set_ad_claim_manager'):
            try:
                ad_claim_cog.set_ad_claim_manager(bot.ad_claim_manager)
                logger.info("✓ Set ad_claim_manager on AdClaim cog")
            except Exception as e:
                logger.error(f"✗ Failed to set ad_claim_manager on AdClaim cog: {e}")

        # Create initializer
        initializer = GuildInitializer(data_manager, bot)

        # Register event handlers
        @bot.event
        async def on_ready():
            logger.info("=" * 60)
            logger.info(f"🤖 Bot logged in as {bot.user.name} (ID: {bot.user.id})")
            logger.info(f"📊 Connected to {len(bot.guilds)} guild(s)")
            logger.info("=" * 60)

            # Set bot status - load from database if configured
            custom_status_set = False
            for guild in bot.guilds:
                try:
                    # Query guild-specific bot status
                    guild_result = data_manager.supabase.table('guilds').select('bot_status_message, bot_status_type').eq('guild_id', str(guild.id)).execute()

                    if guild_result.data and len(guild_result.data) > 0:
                        guild_data = guild_result.data[0]
                        status_message = guild_data.get('bot_status_message')
                        status_type = guild_data.get('bot_status_type', 'watching')

                        if status_message:
                            # Use custom bot status
                            activity_type_map = {
                                'watching': discord.ActivityType.watching,
                                'playing': discord.ActivityType.playing,
                                'listening': discord.ActivityType.listening,
                                'streaming': discord.ActivityType.streaming
                            }

                            activity = discord.Activity(
                                type=activity_type_map.get(status_type, discord.ActivityType.watching),
                                name=status_message
                            )

                            await bot.change_presence(activity=activity)
                            logger.info(f"✓ Custom bot status loaded for guild {guild.name}: {status_type.title()} '{status_message}'")
                            custom_status_set = True
                            break  # Use first custom status found

                except Exception as e:
                    logger.warning(f"Failed to load custom bot status for guild {guild.id}: {e}")

            # Fallback to default status if no custom status found
            if not custom_status_set:
                await bot.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching,
                        name=f"{len(bot.guilds)} servers"
                    )
                )
                logger.info("✓ Using default bot status (watching server count)")

            # Sync slash commands first
            try:
                synced = await bot.tree.sync()
                logger.info(f"✓ Synced {len(synced)} slash commands")
            except Exception as e:
                logger.error(f"✗ Failed to sync slash commands: {e}")

            # === CONCURRENT GUILD INITIALIZATION ===
            # Initialize all guilds concurrently instead of sequentially
            async def init_guild_safe(guild):
                """Initialize a single guild with error handling"""
                try:
                    logger.info(f"🔄 Initializing {guild.name}...")
                    await initializer.initialize_guild(guild)
                    logger.info(f"✅ {guild.name} initialized")
                except Exception as e:
                    logger.error(f"❌ Failed to initialize {guild.name}: {e}")

            # Run all initializations concurrently
            await asyncio.gather(
                *[init_guild_safe(guild) for guild in bot.guilds],
                return_exceptions=True  # Don't let one failure stop others
            )

            logger.info("=" * 60)
            logger.info("✅ All guild initializations complete")
            logger.info("=" * 60)

            # === RUN INITIAL STARTUP SYNC ===
            logger.info("=" * 60)
            logger.info("🚀 RUNNING INITIAL STARTUP SYNC")
            logger.info("=" * 60)

            try:
                sync_result = data_manager.sync_all_guilds()
                if sync_result['success']:
                    logger.info(f"✅ Startup sync complete: {sync_result['synced_guilds']} guilds synced, "
                              f"{sync_result['new_guilds']} new, {sync_result['inactive_guilds']} marked inactive")
                else:
                    logger.error(f"❌ Startup sync failed: {sync_result.get('error', 'Unknown error')}")
            except Exception as e:
                logger.error(f"❌ Error during startup sync: {e}", exc_info=True)

            # Start task channel monitor
            if bot.task_channel_monitor:
                try:
                    await bot.task_channel_monitor.start_monitoring()
                    logger.info("✅ Task channel monitor started")
                except Exception as e:
                    logger.error(f"❌ Failed to start task channel monitor: {e}")

            # Sync channel lock schedules on startup (Premium Feature)
            if bot.channel_lock_manager:
                try:
                    sync_result = await bot.channel_lock_manager.sync_schedules_on_startup()
                    logger.info(f"✅ Channel lock schedules synced: {sync_result.get('locked', 0)} locked, "
                              f"{sync_result.get('unlocked', 0)} unlocked")
                    
                    # Start the background task for schedule processing
                    process_channel_lock_schedules.start()
                    logger.info("✅ Channel lock schedule processor started")
                except Exception as e:
                    logger.error(f"❌ Failed to sync channel lock schedules: {e}")

            logger.info("=" * 60)
            logger.info("🎉 BOT IS FULLY READY AND OPERATIONAL")
            logger.info("=" * 60)

        @bot.event
        async def on_guild_join(guild):
            logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")

            # Initialize new guild
            await initializer.initialize_guild(guild)

            # Update bot status
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{len(bot.guilds)} servers"
                )
            )

        @bot.event
        async def on_guild_remove(guild):
            logger.info(f"Removed from guild: {guild.name} (ID: {guild.id})")
            
            # Clean up all guild data from database
            try:
                guild_id = str(guild.id)
                
                # Delete from all tables
                tables_to_clean = [
                    'guilds',
                    'user_balances',
                    'transactions',
                    'shop_items',
                    'user_inventory',
                    'tasks',
                    'user_tasks',
                    'announcements',
                    'embeds',
                    'moderation_audit_logs',
                    'scheduled_jobs',
                    'ad_sessions',
                    'guild_roles',
                    'user_roles'
                ]
                
                for table in tables_to_clean:
                    try:
                        data_manager.admin_client.table(table).delete().eq('guild_id', guild_id).execute()
                        logger.info(f"Deleted {table} data for guild {guild_id}")
                    except Exception as table_error:
                        logger.warning(f"Failed to delete {table} data for guild {guild_id}: {table_error}")
                
                # Delete file-based data
                try:
                    import shutil
                    guild_data_path = f"data/guilds/{guild_id}"
                    if os.path.exists(guild_data_path):
                        shutil.rmtree(guild_data_path)
                        logger.info(f"Deleted file data for guild {guild_id}")
                except Exception as file_error:
                    logger.warning(f"Failed to delete file data for guild {guild_id}: {file_error}")
                
                logger.info(f"Successfully cleaned up all data for guild {guild.name} ({guild_id})")
                
            except Exception as e:
                logger.error(f"Error cleaning up guild data for {guild.id}: {e}")

            # Update bot status
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{len(bot.guilds)} servers"
                )
            )

        @bot.event
        async def on_member_join(member):
            """Handle user joining server - auto-create user data"""
            if member.bot:
                return

            try:
                # Create user record
                data_manager.ensure_user_exists(member.guild.id, member.id)
                logger.info(f"✅ Created user record for {member.name} in {member.guild.name}")

                # Send welcome message if configured
                config = data_manager.load_guild_data(member.guild.id, "config")
                welcome_channel_id = config.get("welcome_channel")

                if welcome_channel_id:
                    channel = member.guild.get_channel(int(welcome_channel_id))
                    if channel:
                        await channel.send(f"Welcome {member.mention}! 🎉")

            except Exception as e:
                logger.error(f"Error handling member join for {member.name}: {e}")

        @bot.event
        async def on_member_remove(member):
            """Handle user leaving server - mark as inactive"""
            guild_id = str(member.guild.id)
            user_id = str(member.id)

            try:
                # Load currency data
                currency_data = data_manager.load_guild_data(guild_id, 'currency')

                # Mark user as inactive if they exist
                if user_id in currency_data.get('users', {}):
                    user_data = currency_data['users'][user_id]
                    user_data['is_active'] = False
                    user_data['left_at'] = datetime.now().isoformat()

                    # Cancel any in-progress tasks
                    tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
                    user_tasks = tasks_data.get('user_tasks', {}).get(user_id, {})

                    cancelled_tasks = []
                    for task_id, task_info in user_tasks.items():
                        if task_info.get('status') in ['claimed', 'in_progress']:
                            task_info['status'] = 'cancelled'
                            task_info['cancelled_at'] = datetime.now().isoformat()
                            task_info['cancel_reason'] = 'user_left_server'
                            cancelled_tasks.append(task_id)

                    # Save both files atomically
                    data_manager.atomic_transaction(guild_id, {
                        'currency': currency_data,
                        'tasks': tasks_data
                    })

                    logger.info(f"Marked user {member.display_name} ({member.name}) as inactive in guild {guild_id}")
                    if cancelled_tasks:
                        logger.info(f"Cancelled {len(cancelled_tasks)} in-progress tasks for leaving user")

                    # Broadcast SSE event
                    from backend import sse_manager
                    sse_manager.broadcast_event('user_left', {
                        'guild_id': guild_id,
                        'user_id': user_id,
                        'username': member.name,
                        'display_name': member.display_name,
                        'cancelled_tasks': cancelled_tasks
                    })

            except Exception as e:
                logger.error(f"Error handling member remove for {member.name}: {e}")

        # ============= DISCORD SYNC EVENT HANDLERS =============

        @bot.event
        async def on_guild_role_create(role):
            """Sync new role to database"""
            try:
                data_manager.supabase.table('guild_roles').insert({
                    'guild_id': str(role.guild.id),
                    'role_id': str(role.id),
                    'role_name': role.name,
                    'role_color': str(role.color),
                    'role_position': role.position,
                    'is_managed': role.managed,
                    'permissions': role.permissions.value,
                    'last_synced': datetime.now(timezone.utc).isoformat()
                }).execute()

                # Broadcast update
                from backend import sse_manager
                sse_manager.broadcast_event('guild.role.created', {
                    'guild_id': str(role.guild.id),
                    'role_id': str(role.id),
                    'role_name': role.name
                })

                logger.info(f"Synced new role '{role.name}' to database for guild {role.guild.id}")
            except Exception as e:
                logger.error(f"Error syncing role create: {e}")


        @bot.event
        async def on_guild_role_delete(role):
            """Remove deleted role from database"""
            try:
                data_manager.supabase.table('guild_roles').delete().match({
                    'guild_id': str(role.guild.id),
                    'role_id': str(role.id)
                }).execute()

                # Broadcast update
                from backend import sse_manager
                sse_manager.broadcast_event('guild.role.deleted', {
                    'guild_id': str(role.guild.id),
                    'role_id': str(role.id)
                })

                logger.info(f"Removed deleted role '{role.name}' from database for guild {role.guild.id}")
            except Exception as e:
                logger.error(f"Error syncing role delete: {e}")


        @bot.event
        async def on_guild_role_update(before, after):
            """Sync role updates to database"""
            try:
                data_manager.supabase.table('guild_roles').update({
                    'role_name': after.name,
                    'role_color': str(after.color),
                    'role_position': after.position,
                    'permissions': after.permissions.value,
                    'last_synced': datetime.now(timezone.utc).isoformat()
                }).match({
                    'guild_id': str(after.guild.id),
                    'role_id': str(after.id)
                }).execute()

                # Broadcast update
                from backend import sse_manager
                sse_manager.broadcast_event('guild.role.updated', {
                    'guild_id': str(after.guild.id),
                    'role_id': str(after.id),
                    'role_name': after.name
                })

                logger.info(f"Synced role update for '{after.name}' in guild {after.guild.id}")
            except Exception as e:
                logger.error(f"Error syncing role update: {e}")


        @bot.event
        async def on_member_update(before, after):
            """Sync member role changes to database"""
            try:
                if before.roles != after.roles:
                    # Get added/removed roles
                    added_roles = set(after.roles) - set(before.roles)
                    removed_roles = set(before.roles) - set(after.roles)

                    guild_id = str(after.guild.id)
                    user_id = str(after.id)

                    # Add new roles to database
                    for role in added_roles:
                        if role.name != "@everyone":
                            data_manager.supabase.table('user_roles').upsert({
                                'guild_id': guild_id,
                                'user_id': user_id,
                                'role_id': str(role.id),
                                'assigned_at': datetime.now(timezone.utc).isoformat()
                            }, on_conflict='guild_id,user_id,role_id').execute()

                    # Remove old roles from database
                    for role in removed_roles:
                        if role.name != "@everyone":
                            data_manager.supabase.table('user_roles').delete().match({
                                'guild_id': guild_id,
                                'user_id': user_id,
                                'role_id': str(role.id)
                            }).execute()

                    # Broadcast update
                    from backend import sse_manager
                    sse_manager.broadcast_event('member.roles.updated', {
                        'guild_id': guild_id,
                        'user_id': user_id,
                        'added': [str(r.id) for r in added_roles if r.name != "@everyone"],
                        'removed': [str(r.id) for r in removed_roles if r.name != "@everyone"]
                    })

                    logger.info(f"Synced role changes for user {after.display_name} in guild {guild_id}")
            except Exception as e:
                logger.error(f"Error syncing member roles: {e}")


        @bot.event
        async def on_guild_channel_create(channel):
            """Broadcast channel creation for CMS refresh"""
            if isinstance(channel, discord.TextChannel):
                # Broadcast update
                from backend import sse_manager
                sse_manager.broadcast_event('guild.channel.created', {
                    'guild_id': str(channel.guild.id),
                    'channel_id': str(channel.id),
                    'channel_name': channel.name
                })

                logger.info(f"Channel '{channel.name}' created in guild {channel.guild.id}")


        @bot.event
        async def on_guild_channel_delete(channel):
            """Broadcast channel deletion for CMS refresh"""
            if isinstance(channel, discord.TextChannel):
                # Broadcast update
                from backend import sse_manager
                sse_manager.broadcast_event('guild.channel.deleted', {
                    'guild_id': str(channel.guild.id),
                    'channel_id': str(channel.id)
                })

                logger.info(f"Channel '{channel.name}' deleted in guild {channel.guild.id}")


        @bot.event
        async def on_guild_channel_update(before, after):
            """Broadcast channel updates for CMS refresh"""
            if isinstance(after, discord.TextChannel) and before.name != after.name:
                # Broadcast update
                from backend import sse_manager
                sse_manager.broadcast_event('guild.channel.updated', {
                    'guild_id': str(after.guild.id),
                    'channel_id': str(after.id),
                    'channel_name': after.name
                })

                logger.info(f"Channel '{before.name}' renamed to '{after.name}' in guild {after.guild.id}")

        # ============= CHANNEL LOCK SCHEDULE BACKGROUND TASK (Premium Feature) =============
        @tasks.loop(minutes=1)
        async def process_channel_lock_schedules():
            """
            Process channel lock/unlock schedules every minute.
            Checks each enabled schedule and locks/unlocks channels based on time windows.
            Premium feature only.
            """
            if not bot.channel_lock_manager:
                return
            
            try:
                result = await bot.channel_lock_manager.process_all_schedules()
                
                # Only log if there were any changes
                if result.get('locked', 0) > 0 or result.get('unlocked', 0) > 0:
                    logger.info(f"📅 Channel schedules: {result.get('locked', 0)} locked, "
                              f"{result.get('unlocked', 0)} unlocked, "
                              f"{result.get('errors', 0)} errors")
                              
            except Exception as e:
                logger.error(f"Error processing channel lock schedules: {e}")

        @process_channel_lock_schedules.before_loop
        async def before_process_channel_lock_schedules():
            await bot.wait_until_ready()
            logger.info("Channel lock schedule processor initialized")

        @process_channel_lock_schedules.error
        async def process_channel_lock_schedules_error(error):
            logger.exception(f"Channel lock schedule processor failed: {error}")

        @tasks.loop(minutes=10)
        async def sync_pending_discord_messages():
            """
            Retry creating Discord messages for items marked 'pending_sync'.
            Runs every 10 minutes.
            """
            logger.info("Running Discord message sync job...")

            for guild in bot.guilds:
                guild_id = str(guild.id)

                try:
                    # Sync task messages
                    tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
                    tasks = tasks_data.get('tasks', {})

                    for task_id, task in tasks.items():
                        if task.get('message_id'):
                            # Verify message still exists
                            try:
                                channel = guild.get_channel(int(task['channel_id']))
                                if channel:
                                    await channel.fetch_message(int(task['message_id']))
                                # Message exists, continue
                            except discord.NotFound:
                                # Message deleted, clear message_id
                                task['message_id'] = None
                                logger.warning(f"Cleared orphaned message_id for task {task_id} in guild {guild_id}")
                        else:
                            # No message_id, try to recreate if task is active
                            if task.get('status') == 'active':
                                try:
                                    # Import tasks cog to use its method
                                    tasks_cog = bot.get_cog('Tasks')
                                    if tasks_cog:
                                        message_id = await tasks_cog.post_task_to_discord(guild_id, task)
                                        if message_id:
                                            task['message_id'] = message_id
                                            logger.info(f"Recreated Discord message for task {task_id} in guild {guild_id}")
                                except Exception as e:
                                    logger.error(f"Failed to recreate task message for {task_id}: {e}")

                    # Save updated tasks data
                    if tasks_data.get('tasks') != tasks:
                        data_manager.save_guild_data(guild_id, 'tasks', tasks_data)

                    # Sync shop messages
                    currency_data = data_manager.load_guild_data(guild_id, 'currency')
                    shop_items = currency_data.get('shop_items', {})

                    for item_id, item in shop_items.items():
                        if item.get('message_id'):
                            # Verify message still exists
                            try:
                                config = data_manager.load_guild_data(guild_id, 'config')
                                shop_channel_id = config.get('shop_channel_id')
                                if shop_channel_id:
                                    channel = guild.get_channel(int(shop_channel_id))
                                    if channel:
                                        await channel.fetch_message(int(item['message_id']))
                                # Message exists, continue
                            except discord.NotFound:
                                # Message deleted, clear message_id
                                item['message_id'] = None
                                logger.warning(f"Cleared orphaned message_id for shop item {item_id} in guild {guild_id}")
                        else:
                            # No message_id, try to recreate if item is active
                            if item.get('is_active', True):
                                try:
                                    # Import shop manager to sync message
                                    from core.shop_manager import ShopManager
                                    from core.transaction_manager import TransactionManager
                                    tm = TransactionManager(data_manager)
                                    shop_manager = ShopManager(data_manager, tm)

                                    await shop_manager.sync_discord_message(guild_id, item_id, bot)
                                    logger.info(f"Recreated Discord message for shop item {item_id} in guild {guild_id}")
                                except Exception as e:
                                    logger.error(f"Failed to recreate shop message for {item_id}: {e}")

                    # Save updated currency data
                    if currency_data.get('shop_items') != shop_items:
                        data_manager.save_guild_data(guild_id, 'currency', currency_data)

                    # Sync announcement messages
                    announcements_data = data_manager.load_guild_data(guild_id, 'announcements')
                    if announcements_data:
                        announcements = announcements_data.get('announcements', {})

                        for ann_id, announcement in announcements.items():
                            if announcement.get('message_id'):
                                # Verify message still exists
                                try:
                                    channel = guild.get_channel(int(announcement['channel_id']))
                                    if channel:
                                        await channel.fetch_message(int(announcement['message_id']))
                                    # Message exists, continue
                                except discord.NotFound:
                                    # Message deleted, mark as orphaned
                                    announcement['status'] = 'orphaned'
                                    logger.warning(f"Marked announcement {ann_id} as orphaned in guild {guild_id}")

                        # Save updated announcements data
                        if announcements_data.get('announcements') != announcements:
                            data_manager.save_guild_data(guild_id, 'announcements', announcements_data)

                except Exception as e:
                    logger.error(f"Error during Discord sync for guild {guild_id}: {e}")

            logger.info("Discord message sync job completed")

        @sync_pending_discord_messages.before_loop
        async def before_sync_pending_discord_messages():
            await bot.wait_until_ready()
            logger.info("Discord message sync job initialized")

        # Start the sync job
        sync_pending_discord_messages.start()

        @sync_pending_discord_messages.error
        async def sync_pending_discord_messages_error(error):
            logger.exception(f"Discord message sync job failed: {error}")

        @tasks.loop(hours=1)
        async def cleanup_expired_cache():
            """Remove expired entries from data manager cache."""
            logger.info("Running cache cleanup job...")

            try:
                # Get cache statistics before cleanup
                cache_stats_before = data_manager.get_cache_stats()

                # Perform cache cleanup
                data_manager.cleanup_expired_cache()

                # Get cache statistics after cleanup
                cache_stats_after = data_manager.get_cache_stats()

                cleaned_entries = cache_stats_before.get('total_entries', 0) - cache_stats_after.get('total_entries', 0)

                logger.info(f"Cache cleanup completed. Removed {cleaned_entries} expired entries. "
                          f"Cache now has {cache_stats_after.get('total_entries', 0)} entries.")

            except Exception as e:
                logger.error(f"Error during cache cleanup: {e}")

        @cleanup_expired_cache.before_loop
        async def before_cleanup_expired_cache():
            await bot.wait_until_ready()
            logger.info("Cache cleanup job initialized")

        # Start the cache cleanup job
        cleanup_expired_cache.start()

        @cleanup_expired_cache.error
        async def cleanup_expired_cache_error(error):
            logger.exception(f"Cache cleanup job failed: {error}")

        @tasks.loop(hours=1)
        async def hourly_guild_sync():
            """Hourly sync of all guilds to ensure database consistency."""
            logger.info("Running hourly guild sync...")

            try:
                # Run the guild sync
                sync_result = data_manager.sync_all_guilds()

                if sync_result['success']:
                    logger.info(f"Guild sync completed: {sync_result['synced_guilds']} synced, "
                              f"{sync_result['new_guilds']} new, {sync_result['inactive_guilds']} marked inactive")

                    # Broadcast sync completion event
                    from backend import sse_manager
                    sse_manager.broadcast_event('guild_sync_completed', {
                        'synced_guilds': sync_result['synced_guilds'],
                        'new_guilds': sync_result['new_guilds'],
                        'inactive_guilds': sync_result['inactive_guilds'],
                        'total_guilds': sync_result['total_discord_guilds']
                    })
                else:
                    logger.error(f"Guild sync failed: {sync_result.get('error', 'Unknown error')}")

            except Exception as e:
                logger.error(f"Error during hourly guild sync: {e}")

        @hourly_guild_sync.before_loop
        async def before_hourly_guild_sync():
            await bot.wait_until_ready()
            logger.info("Hourly guild sync job initialized")

        # Start the hourly guild sync job
        hourly_guild_sync.start()

        @hourly_guild_sync.error
        async def hourly_guild_sync_error(error):
            logger.exception(f"Hourly guild sync job failed: {error}")

        @tasks.loop(hours=24)
        async def validate_transaction_integrity():
            """Daily check that balances match transaction history."""
            logger.info("Running transaction integrity validation...")

            integrity_issues = []

            for guild in bot.guilds:
                guild_id = str(guild.id)

                try:
                    # Create TransactionManager instance
                    from core.transaction_manager import TransactionManager
                    tm = TransactionManager(data_manager)

                    # Get all transactions for this guild
                    result = tm.get_transactions(guild_id, limit=10000)  # Get all transactions
                    transactions = result['transactions']

                    # Load currency data
                    currency_data = data_manager.load_guild_data(guild_id, 'currency')
                    users = currency_data.get('users', {})

                    # Check each user's balance against transaction history
                    for user_id, user_data in users.items():
                        if not user_data.get('is_active', True):
                            continue  # Skip inactive users

                        current_balance = user_data.get('balance', 0)

                        # Calculate balance from transactions
                        calculated_balance = 0
                        user_transactions = [t for t in transactions if t.get('user_id') == user_id]

                        for txn in user_transactions:
                            calculated_balance += txn.get('amount', 0)

                        # Check for discrepancy
                        if abs(current_balance - calculated_balance) > 0.01:  # Allow small floating point differences
                            integrity_issues.append({
                                'guild_id': guild_id,
                                'user_id': user_id,
                                'current_balance': current_balance,
                                'calculated_balance': calculated_balance,
                                'discrepancy': current_balance - calculated_balance,
                                'transaction_count': len(user_transactions)
                            })

                            logger.warning(f"Balance discrepancy for user {user_id} in guild {guild_id}: "
                                         f"current={current_balance}, calculated={calculated_balance}")

                except Exception as e:
                    logger.error(f"Error validating transactions for guild {guild_id}: {e}")

            if integrity_issues:
                logger.warning(f"Found {len(integrity_issues)} transaction integrity issues")

                # Send alert to log channel if configured
                for guild in bot.guilds:
                    try:
                        config = data_manager.load_guild_data(str(guild.id), 'config')
                        log_channel_id = config.get('log_channel_id')

                        if log_channel_id:
                            log_channel = guild.get_channel(int(log_channel_id))
                            if log_channel:
                                embed = discord.Embed(
                                    title="⚠️ Transaction Integrity Issues",
                                    description=f"Found {len(integrity_issues)} balance discrepancies during daily validation.",
                                    color=discord.Color.orange()
                                )

                                # Show summary (first 5 issues)
                                for i, issue in enumerate(integrity_issues[:5]):
                                    embed.add_field(
                                        name=f"User {issue['user_id'][:8]}...",
                                        value=f"Discrepancy: {issue['discrepancy']:+.2f}",
                                        inline=True
                                    )

                                if len(integrity_issues) > 5:
                                    embed.set_footer(text=f"And {len(integrity_issues) - 5} more issues...")

                                await log_channel.send(embed=embed)

                    except Exception as e:
                        logger.error(f"Error sending integrity alert to guild {guild.id}: {e}")
            else:
                logger.info("Transaction integrity validation completed - no issues found")

        @validate_transaction_integrity.before_loop
        async def before_validate_transaction_integrity():
            await bot.wait_until_ready()
            logger.info("Transaction integrity validation job initialized")

        # Start the integrity validation job
        validate_transaction_integrity.start()

        @validate_transaction_integrity.error
        async def validate_transaction_integrity_error(error):
            logger.exception(f"Transaction integrity validation job failed: {error}")

        @tasks.loop(hours=24)
        async def mark_inactive_users():
            """Mark users who left server as inactive."""
            logger.info("Running inactive user cleanup job...")

            total_marked_inactive = 0

            for guild in bot.guilds:
                guild_id = str(guild.id)

                try:
                    # Get config to check inactive user settings
                    config = data_manager.load_guild_data(guild_id, 'config')
                    days_threshold = config.get('inactive_user_days', 30)

                    # Load currency data
                    currency_data = data_manager.load_guild_data(guild_id, 'currency')
                    users = currency_data.get('users', {})

                    # Find users who are marked as active but not in the guild
                    marked_inactive = []

                    for user_id, user_data in users.items():
                        if not user_data.get('is_active', True):
                            continue  # Already inactive

                        # Check if user is still in guild
                        try:
                            member = guild.get_member(int(user_id))
                            if member is None:
                                # User not in guild, mark as inactive
                                user_data['is_active'] = False
                                user_data['left_at'] = datetime.now().isoformat()
                                marked_inactive.append(user_id)

                                # Cancel any in-progress tasks
                                tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
                                user_tasks = tasks_data.get('user_tasks', {}).get(user_id, {})

                                cancelled_tasks = []
                                for task_id, task_info in user_tasks.items():
                                    if task_info.get('status') in ['claimed', 'in_progress', 'submitted']:
                                        task_info['status'] = 'cancelled'
                                        task_info['cancelled_at'] = datetime.now().isoformat()
                                        task_info['cancel_reason'] = 'user_left_server'
                                        cancelled_tasks.append(task_id)

                                # Save tasks data if any were cancelled
                                if cancelled_tasks:
                                    data_manager.save_guild_data(guild_id, 'tasks', tasks_data)

                                total_marked_inactive += 1

                                logger.info(f"Marked user {user_id} as inactive in guild {guild_id} "
                                          f"(cancelled {len(cancelled_tasks)} tasks)")

                        except Exception as e:
                            logger.error(f"Error checking member {user_id} in guild {guild_id}: {e}")

                    # Save currency data if any users were marked inactive
                    if marked_inactive:
                        data_manager.save_guild_data(guild_id, 'currency', currency_data)

                        # Broadcast SSE event
                        from backend import sse_manager
                        sse_manager.broadcast_event('inactive_users_cleaned', {
                            'guild_id': guild_id,
                            'marked_inactive': len(marked_inactive),
                            'days_threshold': days_threshold
                        })

                except Exception as e:
                    logger.error(f"Error during inactive user cleanup for guild {guild_id}: {e}")

            logger.info(f"Inactive user cleanup completed. Marked {total_marked_inactive} users as inactive.")

        @mark_inactive_users.before_loop
        async def before_mark_inactive_users():
            await bot.wait_until_ready()
            logger.info("Inactive user cleanup job initialized")

        # Start the inactive user cleanup job
        mark_inactive_users.start()

        @tasks.loop(hours=6)
        async def create_data_backups():
            """Create timestamped backups of all guild data."""
            logger.info("Running data backup job...")

            import os
            from pathlib import Path

            backup_count = 0
            error_count = 0

            for guild in bot.guilds:
                guild_id = str(guild.id)

                try:
                    # Create backup directory
                    backup_dir = Path(f"data/guilds/{guild_id}/backups")
                    backup_dir.mkdir(parents=True, exist_ok=True)

                    # Get config for backup settings
                    config = data_manager.load_guild_data(guild_id, 'config')
                    max_backups = config.get('max_backup_files', 28)

                    # Files to backup
                    files_to_backup = [
                        ('currency', 'currency.json'),
                        ('tasks', 'tasks.json'),
                        ('config', 'config.json'),
                        ('transactions', 'transactions.json'),
                        ('announcements', 'announcements.json'),
                        ('embeds', 'embeds.json')
                    ]

                    # Create timestamp
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                    for data_type, filename in files_to_backup:
                        try:
                            # Load data
                            data = data_manager.load_guild_data(guild_id, data_type)
                            if data is None:
                                continue  # Skip if no data

                            # Create backup file
                            backup_file = backup_dir / f"{data_type}_{timestamp}.json"

                            # Write backup
                            import json
                            with open(backup_file, 'w') as f:
                                json.dump(data, f, indent=2)

                            backup_count += 1

                        except Exception as e:
                            logger.error(f"Error backing up {data_type} for guild {guild_id}: {e}")
                            error_count += 1

                    # Clean up old backups
                    try:
                        backup_files = {}
                        for file_path in backup_dir.glob("*.json"):
                            if "_" in file_path.name:
                                data_type = file_path.name.split("_")[0]
                                if data_type not in backup_files:
                                    backup_files[data_type] = []
                                backup_files[data_type].append(file_path)

                        # Sort by modification time (newest first) and keep only max_backups
                        for data_type, files in backup_files.items():
                            files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                            files_to_delete = files[max_backups:]

                            for old_file in files_to_delete:
                                old_file.unlink()
                                logger.debug(f"Deleted old backup: {old_file.name}")

                    except Exception as e:
                        logger.error(f"Error cleaning up old backups for guild {guild_id}: {e}")

                except Exception as e:
                    logger.error(f"Error during backup for guild {guild_id}: {e}")
                    error_count += 1

            logger.info(f"Data backup completed. Created {backup_count} backups with {error_count} errors.")

        @create_data_backups.before_loop
        async def before_create_data_backups():
            await bot.wait_until_ready()
            logger.info("Data backup job initialized")

        # Start the backup job
        create_data_backups.start()

        @create_data_backups.error
        async def create_data_backups_error(error):
            logger.exception(f"Data backup job failed: {error}")

        @tasks.loop(hours=24)
        async def check_inactive_users():
            """Mark users as inactive if they haven't had transactions within configured period"""
            try:
                logger.info("🔍 Starting daily inactive user check")

                for guild in bot.guilds:
                    try:
                        # Get guild's inactivity threshold from database
                        guild_config = data_manager.supabase.table('guilds').select('inactivity_days').eq('guild_id', str(guild.id)).execute()

                        if not guild_config.data:
                            continue

                        inactivity_days = guild_config.data[0].get('inactivity_days', 30)

                        # Calculate cutoff date
                        from datetime import datetime, timedelta
                        cutoff_date = datetime.utcnow() - timedelta(days=inactivity_days)

                        # Mark users as inactive via stored procedure (atomic operation)
                        result = data_manager.supabase.rpc(
                            'mark_inactive_users',
                            {
                                'p_guild_id': str(guild.id),
                                'p_cutoff_date': cutoff_date.isoformat()
                            }
                        ).execute()

                        marked_count = result.data if result.data else 0

                        if marked_count > 0:
                            logger.info(f"✓ Marked {marked_count} users as inactive in {guild.name}")

                    except Exception as e:
                        logger.error(f"❌ Failed to check inactive users for guild {guild.id}: {e}")
                        continue

                logger.info("✅ Daily inactive user check complete")

            except Exception as e:
                logger.error(f"❌ Inactive user check failed: {e}")

        @check_inactive_users.before_loop
        async def before_check_inactive_users():
            await bot.wait_until_ready()
            logger.info("Inactive user check job initialized")

        # Start the inactive user check job
        check_inactive_users.start()

        @check_inactive_users.error
        async def check_inactive_users_error(error):
            logger.exception(f"Inactive user check job failed: {error}")

        @tasks.loop(minutes=5)
        async def execute_scheduled_database_jobs():
            """Execute pending scheduled jobs from database (every 5 minutes)"""
            try:
                # Get the moderation scheduler
                moderation_cog = bot.get_cog('Moderation')
                if moderation_cog and hasattr(moderation_cog, 'scheduler'):
                    scheduler = moderation_cog.scheduler

                    # Execute database jobs
                    await scheduler.execute_database_jobs(data_manager, bot)

            except Exception as e:
                logger.error(f"Error executing scheduled database jobs: {e}")

        @execute_scheduled_database_jobs.before_loop
        async def before_execute_scheduled_database_jobs():
            await bot.wait_until_ready()
            logger.info("Scheduled database jobs executor initialized")

        # Start the scheduled database jobs executor
        execute_scheduled_database_jobs.start()

        @execute_scheduled_database_jobs.error
        async def execute_scheduled_database_jobs_error(error):
            logger.exception(f"Scheduled database jobs executor failed: {error}")

        @bot.event
        async def on_command_error(ctx, error):
            """Global error handler"""

            # Ignore command not found
            if isinstance(error, commands.CommandNotFound):
                return

            # Permission errors
            if isinstance(error, commands.MissingPermissions):
                await ctx.send("❌ You don't have permission to use this command!")
                return

            if isinstance(error, commands.BotMissingPermissions):
                await ctx.send("❌ I don't have the required permissions to execute this command!")
                return

            # Argument errors
            if isinstance(error, commands.MissingRequiredArgument):
                await ctx.send(f"❌ Missing required argument: `{error.param.name}`\nUse `!help {ctx.command}` for usage.")
                return

            if isinstance(error, commands.BadArgument):
                await ctx.send(f"❌ Invalid argument provided!\nUse `!help {ctx.command}` for usage.")
                return

            # Cooldown errors
            if isinstance(error, commands.CommandOnCooldown):
                await ctx.send(f"⏱️ This command is on cooldown. Try again in {error.retry_after:.1f} seconds.")
                return

            # Check failures
            if isinstance(error, commands.CheckFailure):
                await ctx.send("❌ You don't meet the requirements to use this command!")
                return

            # Log unexpected errors
            logger.error(f"Unexpected error in command {ctx.command}: {error}", exc_info=error)

            # Send error embed
            embed = discord.Embed(
                title="❌ An Error Occurred",
                description="An unexpected error occurred while executing this command.",
                color=discord.Color.red()
            )
            embed.add_field(name="Command", value=ctx.command.name if ctx.command else "Unknown")
            embed.add_field(name="Error Type", value=type(error).__name__)

            try:
                await ctx.send(embed=embed)
            except:
                await ctx.send("❌ An error occurred while executing this command.")

        # Start internal webhook server for Flask communication
        webhook_app = web.Application()
        webhook_runner = None

        async def handle_admin_message(request):
            """Handle admin message injection from Flask"""
            try:
                data = await request.json()
                guild_id = data.get('guild_id')
                channel_id = data.get('channel_id')
                message = data.get('message')
                embed_data = data.get('embed')

                if not all([guild_id, channel_id, message]):
                    return web.json_response({'error': 'Missing required fields'}, status=400)

                # Get the guild and channel
                guild = bot.get_guild(int(guild_id))
                if not guild:
                    return web.json_response({'error': 'Guild not found'}, status=404)

                channel = guild.get_channel(int(channel_id))
                if not channel:
                    return web.json_response({'error': 'Channel not found'}, status=404)

                # Send the message
                if embed_data:
                    embed = discord.Embed.from_dict(embed_data)
                    await channel.send(message, embed=embed)
                else:
                    await channel.send(message)

                logger.info(f"Admin message sent to guild {guild_id}, channel {channel_id}")
                return web.json_response({'success': True})

            except Exception as e:
                logger.error(f"Error handling admin message: {e}")
                return web.json_response({'error': str(e)}, status=500)

        async def handle_sse_signal(request):
            """Handle SSE signal from Flask backend"""
            try:
                data = await request.json()
                event_type = data.get('event_type')
                event_data = data.get('data', {})

                if not event_type:
                    return web.json_response({'error': 'Missing event_type'}, status=400)

                # Broadcast the event via SSE manager
                from core.sse_manager import sse_manager
                sse_manager.broadcast_event(event_type, event_data)

                logger.debug(f"SSE signal processed: {event_type}")
                return web.json_response({'success': True})

            except Exception as e:
                logger.error(f"Error handling SSE signal: {e}")
                return web.json_response({'error': str(e)}, status=500)

        # Add routes
        webhook_app.router.add_post('/admin_message', handle_admin_message)
        webhook_app.router.add_post('/sse_signal', handle_sse_signal)

        # Start webhook server for Railway internal networking
        # Railway assigns each service its own PORT, so we use a fixed internal port
        try:
            webhook_runner = web.AppRunner(webhook_app)
            await webhook_runner.setup()
            # Use 0.0.0.0 to bind to all interfaces for Railway internal networking
            site = web.TCPSite(webhook_runner, '0.0.0.0', config.bot_webhook_port)
            await site.start()
            logger.info(f"✅ Internal webhook server started on 0.0.0.0:{config.bot_webhook_port}")
        except Exception as e:
            logger.error(f"Failed to start webhook server: {e}")
            raise

        # Start bot
        logger.info("Connecting to Discord...")
        await bot.start(token)

    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
    except Exception as e:
        logger.error(f"Fatal error in run_bot: {e}", exc_info=True)
    finally:
        if 'bot' in locals():
            await bot.close()

async def main():
    """Main bot startup function (legacy - kept for backward compatibility)"""
    try:
        logger.info("=" * 50)
        logger.info("Discord Economy Bot Starting...")
        logger.info("=" * 50)

        # Create bot instance
        bot, token = create_bot()

        # Import backend functions (delayed to avoid circular import)
        from backend import run_backend, set_bot_instance, set_data_manager

        # Set global references for backend
        set_bot_instance(bot)
        set_data_manager(data_manager)

        # CRITICAL: Link bot instance to data manager for sync
        data_manager.set_bot_instance(bot)

        # Load cogs
        logger.info("Loading cogs...")
        try:
            await bot.load_extension('cogs.currency')
            logger.info("✓ Currency cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load currency cog: {e}")

        try:
            await bot.load_extension('cogs.admin')
            logger.info("✓ Admin cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load admin cog: {e}")

        try:
            await bot.load_extension('cogs.general')
            logger.info("✓ General cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load general cog: {e}")

        try:
            await bot.load_extension('cogs.announcements')
            logger.info("✓ Announcements cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load announcements cog: {e}")

        try:
            await bot.load_extension('cogs.tasks')
            logger.info("✓ Tasks cog loaded")
        except Exception as e:
            logger.error(f"✗ Failed to load tasks cog: {e}")

        # Create initializer
        initializer = GuildInitializer(data_manager, bot)

        # Register event handlers
        @bot.event
        async def on_ready():
            logger.info(f"Bot logged in as {bot.user.name} (ID: {bot.user.id})")
            logger.info(f"Connected to {len(bot.guilds)} guild(s)")

            # Set bot status
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{len(bot.guilds)} servers"
                )
            )

            # Sync slash commands first
            try:
                synced = await bot.tree.sync()
                logger.info(f"✓ Synced {len(synced)} slash commands")
            except Exception as e:
                logger.error(f"✗ Failed to sync slash commands: {e}")

            # Initialize all guilds
            print(f"🔄 Initializing {len(bot.guilds)} guilds...")
            for guild in bot.guilds:
                try:
                    await initializer.initialize_guild(guild)
                except Exception as e:
                    logger.error(f'❌ Failed to initialize {guild.name}: {e}')

            logger.info("=" * 50)
            logger.info("Bot is ready and online!")
            logger.info(f"Web Dashboard: http://127.0.0.1:3000")
            logger.info("=" * 50)

        @bot.event
        async def on_guild_join(guild):
            logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")

            # Initialize new guild
            await initializer.initialize_guild(guild)

            # Update bot status
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{len(bot.guilds)} servers"
                )
            )

        @bot.event
        async def on_guild_remove(guild):
            logger.info(f"Removed from guild: {guild.name} (ID: {guild.id})")

            # Update bot status
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{len(bot.guilds)} servers"
                )
            )

        @bot.event
        async def on_member_join(member):
            """Handle user joining server - auto-create user data"""
            if member.bot:
                return

            try:
                # Create user record
                data_manager.ensure_user_exists(member.guild.id, member.id)
                logger.info(f"✅ Created user record for {member.name} in {member.guild.name}")

                # Send welcome message if configured
                config = data_manager.load_guild_data(member.guild.id, "config")
                welcome_channel_id = config.get("welcome_channel")

                if welcome_channel_id:
                    channel = member.guild.get_channel(int(welcome_channel_id))
                    if channel:
                        await channel.send(f"Welcome {member.mention}! 🎉")

            except Exception as e:
                logger.error(f"Error handling member join for {member.name}: {e}")

        @bot.event
        async def on_member_remove(member):
            """Handle user leaving server - mark as inactive"""
            guild_id = str(member.guild.id)
            user_id = str(member.id)

            try:
                # Load currency data
                currency_data = data_manager.load_guild_data(guild_id, 'currency')

                # Mark user as inactive if they exist
                if user_id in currency_data.get('users', {}):
                    user_data = currency_data['users'][user_id]
                    user_data['is_active'] = False
                    user_data['left_at'] = datetime.now().isoformat()

                    # Cancel any in-progress tasks
                    tasks_data = data_manager.load_guild_data(guild_id, 'tasks')
                    user_tasks = tasks_data.get('user_tasks', {}).get(user_id, {})

                    cancelled_tasks = []
                    for task_id, task_info in user_tasks.items():
                        if task_info.get('status') in ['claimed', 'in_progress']:
                            task_info['status'] = 'cancelled'
                            task_info['cancelled_at'] = datetime.now().isoformat()
                            task_info['cancel_reason'] = 'user_left_server'
                            cancelled_tasks.append(task_id)

                    # Save both files atomically
                    data_manager.atomic_transaction(guild_id, {
                        'currency': currency_data,
                        'tasks': tasks_data
                    })

                    logger.info(f"Marked user {member.display_name} ({member.name}) as inactive in guild {guild_id}")
                    if cancelled_tasks:
                        logger.info(f"Cancelled {len(cancelled_tasks)} in-progress tasks for leaving user")

                    # Broadcast SSE event
                    from backend import sse_manager
                    sse_manager.broadcast_event('user_left', {
                        'guild_id': guild_id,
                        'user_id': user_id,
                        'username': member.name,
                        'display_name': member.display_name,
                        'cancelled_tasks': cancelled_tasks
                    })

            except Exception as e:
                logger.error(f"Error handling member remove for {member.name}: {e}")

        @bot.event
        async def on_command_error(ctx, error):
            """Global error handler"""

            # Ignore command not found
            if isinstance(error, commands.CommandNotFound):
                return

            # Permission errors
            if isinstance(error, commands.MissingPermissions):
                await ctx.send("❌ You don't have permission to use this command!")
                return

            if isinstance(error, commands.BotMissingPermissions):
                await ctx.send("❌ I don't have the required permissions to execute this command!")
                return

            # Argument errors
            if isinstance(error, commands.MissingRequiredArgument):
                await ctx.send(f"❌ Missing required argument: `{error.param.name}`\nUse `!help {ctx.command}` for usage.")
                return

            if isinstance(error, commands.BadArgument):
                await ctx.send(f"❌ Invalid argument provided!\nUse `!help {ctx.command}` for usage.")
                return

            # Cooldown errors
            if isinstance(error, commands.CommandOnCooldown):
                await ctx.send(f"⏱️ This command is on cooldown. Try again in {error.retry_after:.1f} seconds.")
                return

            # Check failures
            if isinstance(error, commands.CheckFailure):
                await ctx.send("❌ You don't meet the requirements to use this command!")
                return

            # Log unexpected errors
            logger.error(f"Unexpected error in command {ctx.command}: {error}", exc_info=error)

            # Send error embed
            embed = discord.Embed(
                title="❌ An Error Occurred",
                description="An unexpected error occurred while executing this command.",
                color=discord.Color.red()
            )
            embed.add_field(name="Command", value=ctx.command.name if ctx.command else "Unknown")
            embed.add_field(name="Error Type", value=type(error).__name__)

            try:
                await ctx.send(embed=embed)
            except:
                await ctx.send("❌ An error occurred while executing this command.")

        # Start Flask backend in separate thread
        logger.info("Starting web backend...")
        backend_thread = threading.Thread(target=run_backend, daemon=True)
        backend_thread.start()

        # Give backend time to start
        await asyncio.sleep(2)

        # Start bot
        logger.info("Connecting to Discord...")
        await bot.start(token)

    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
    finally:
        if bot:
            await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown complete")
