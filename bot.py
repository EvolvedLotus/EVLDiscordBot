# In bot.py - Ensure proper initialization order

import asyncio
import logging
import threading
from datetime import datetime
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os

# Import components
from core.data_manager import DataManager
from core.initializer import GuildInitializer

# Setup logging first
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

if not DISCORD_TOKEN:
    logger.error("DISCORD_TOKEN not found in environment variables!")
    exit(1)

# Initialize data manager (global instance)
data_manager = DataManager()

def create_bot():
    """Create and configure the Discord bot"""

    # Dynamic prefix function
    async def get_prefix(bot, message):
        if not message.guild:
            return '!'

        config = data_manager.load_guild_data(message.guild.id, 'config')
        return config.get('prefix', '!')

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
        command_prefix=get_prefix,
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
        initializer = GuildInitializer(bot, data_manager)

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
            guild_id = str(member.guild.id)
            user_id = str(member.id)

            try:
                # Load currency data
                currency_data = data_manager.load_guild_data(guild_id, 'currency')

                # Check if user already exists
                if user_id not in currency_data.get('users', {}):
                    # Auto-create user entry
                    currency_data.setdefault('users', {})[user_id] = {
                        'balance': 0,
                        'total_earned': 0,
                        'total_spent': 0,
                        'created_at': datetime.now().isoformat(),
                        'is_active': True,
                        'username': member.name,
                        'display_name': member.display_name
                    }

                    # Save data
                    data_manager.save_guild_data(guild_id, 'currency', currency_data)

                    logger.info(f"Auto-created user data for {member.display_name} ({member.name}) in guild {guild_id}")

                    # Broadcast SSE event
                    from backend import sse_manager
                    sse_manager.broadcast_event('user_joined', {
                        'guild_id': guild_id,
                        'user_id': user_id,
                        'username': member.name,
                        'display_name': member.display_name
                    })

                    # Send welcome DM (optional - can be disabled in config)
                    config = data_manager.load_guild_data(guild_id, 'config')
                    if config.get('welcome_dm', False):
                        try:
                            embed = discord.Embed(
                                title="👋 Welcome to the server!",
                                description="You now have access to our currency system. Use `/balance` to check your balance!",
                                color=discord.Color.green()
                            )
                            await member.send(embed=embed)
                        except discord.Forbidden:
                            logger.debug(f"Could not send welcome DM to {member.name} - DMs disabled")

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
                        log_channel_id = config.get('log_channel')

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

        # Start bot (no Flask backend here - handled by start.py)
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
        initializer = GuildInitializer(bot, data_manager)

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
            guild_id = str(member.guild.id)
            user_id = str(member.id)

            try:
                # Load currency data
                currency_data = data_manager.load_guild_data(guild_id, 'currency')

                # Check if user already exists
                if user_id not in currency_data.get('users', {}):
                    # Auto-create user entry
                    currency_data.setdefault('users', {})[user_id] = {
                        'balance': 0,
                        'total_earned': 0,
                        'total_spent': 0,
                        'created_at': datetime.now().isoformat(),
                        'is_active': True,
                        'username': member.name,
                        'display_name': member.display_name
                    }

                    # Save data
                    data_manager.save_guild_data(guild_id, 'currency', currency_data)

                    logger.info(f"Auto-created user data for {member.display_name} ({member.name}) in guild {guild_id}")

                    # Broadcast SSE event
                    from backend import sse_manager
                    sse_manager.broadcast_event('user_joined', {
                        'guild_id': guild_id,
                        'user_id': user_id,
                        'username': member.name,
                        'display_name': member.display_name
                    })

                    # Send welcome DM (optional - can be disabled in config)
                    config = data_manager.load_guild_data(guild_id, 'config')
                    if config.get('welcome_dm', False):
                        try:
                            embed = discord.Embed(
                                title="👋 Welcome to the server!",
                                description="You now have access to our currency system. Use `/balance` to check your balance!",
                                color=discord.Color.green()
                            )
                            await member.send(embed=embed)
                        except discord.Forbidden:
                            logger.debug(f"Could not send welcome DM to {member.name} - DMs disabled")

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
