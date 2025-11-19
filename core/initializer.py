from datetime import datetime, timezone
import logging
import discord
from discord import Embed  # ADD THIS LINE
import asyncio

logger = logging.getLogger(__name__)

class GuildInitializer:
    def __init__(self, data_manager, bot):
        self.data_manager = data_manager
        self.bot = bot

    async def initialize_guild(self, guild: discord.Guild):
        """Initialize a guild with proper configuration"""
        logger.info(f"🔄 Initializing {guild.name}...")

        try:
            # Load existing config if it exists
            existing_config = self.data_manager.load_guild_data(guild.id, "config")

            # Create/update config with ALL required fields
            config = {
                'guild_id': str(guild.id),
                'server_name': guild.name,  # ✅ REQUIRED FIELD
                'owner_id': str(guild.owner_id),  # ✅ REQUIRED FIELD
                'member_count': guild.member_count if hasattr(guild, 'member_count') else 0,
                'icon_url': str(guild.icon.url) if guild.icon else None,
                'is_active': True,
                # Preserve existing settings if they exist
                'prefix': existing_config.get('prefix', '!') if existing_config else '!',
                'currency_name': existing_config.get('currency_name', 'coins') if existing_config else 'coins',
                'currency_symbol': existing_config.get('currency_symbol', '$') if existing_config else '$',
                'admin_roles': existing_config.get('admin_roles', []) if existing_config else [],
                'moderator_roles': existing_config.get('moderator_roles', []) if existing_config else [],
                'log_channel': existing_config.get('log_channel') if existing_config else None,
                'welcome_channel': existing_config.get('welcome_channel') if existing_config else None,
                'task_channel_id': existing_config.get('task_channel_id') if existing_config else None,
                'shop_channel_id': existing_config.get('shop_channel_id') if existing_config else None,
                'feature_currency': existing_config.get('feature_currency', True) if existing_config else True,
                'feature_tasks': existing_config.get('feature_tasks', True) if existing_config else True,
                'feature_shop': existing_config.get('feature_shop', True) if existing_config else True,
                'feature_announcements': existing_config.get('feature_announcements', True) if existing_config else True,
                'feature_moderation': existing_config.get('feature_moderation', True) if existing_config else True,
                'global_shop': existing_config.get('global_shop', False) if existing_config else False,
                'global_tasks': existing_config.get('global_tasks', False) if existing_config else False,
            }

            # Save the complete config
            success = self.data_manager.save_guild_data(guild.id, 'config', config)

            if not success:
                logger.error(f"  ❌ Failed to save config for {guild.name}")
                return False

            logger.info(f"  ✅ Config saved for {guild.name}")

            # Initialize subsystems
            await self._initialize_tasks(guild)
            await self._initialize_shop(guild)
            await self._initialize_embeds(guild)

            # Step 4: CREATE ALL USERS (NEW)
            await self._initialize_users(guild)

            # Sync last_sync timestamp via RPC
            self.data_manager.sync_guild_to_database(guild.id)

            logger.info(f"✅ {guild.name} initialization complete")
            return True

        except Exception as e:
            logger.error(f"❌ Error initializing {guild.name}: {e}", exc_info=True)
            return False

    async def _ensure_config(self, guild: discord.Guild):
        """Ensure guild configuration exists with valid settings"""
        try:
            guild_id = str(guild.id)

            # Check if guild exists in database using direct Supabase call
            existing = self.data_manager.admin_client.table('guilds').select('*').eq('guild_id', guild_id).execute()

            if existing.data:
                # Guild exists, just update basic info with direct Supabase update
                self.data_manager.admin_client.table('guilds').update({
                    'server_name': guild.name,
                    'member_count': guild.member_count,
                    'icon_url': str(guild.icon.url) if guild.icon else None,
                    'is_active': True,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }).eq('guild_id', guild_id).execute()
                print(f"  ✓ Updated config for {guild.name}")
            else:
                # Create new guild with all defaults using direct Supabase insert
                self.data_manager.admin_client.table('guilds').insert({
                    'guild_id': guild_id,
                    'server_name': guild.name,
                    'owner_id': str(guild.owner_id),
                    'member_count': guild.member_count,
                    'icon_url': str(guild.icon.url) if guild.icon else None,
                    'prefix': '!',
                    'currency_name': 'coins',
                    'currency_symbol': '$',
                    'feature_currency': True,
                    'feature_tasks': True,
                    'feature_shop': True,
                    'feature_announcements': True,
                    'feature_moderation': True,
                    'is_active': True,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }).execute()
                print(f"  ✓ Created new config for {guild.name}")

        except Exception as e:
            print(f"  ✗ Error ensuring config for {guild.name}: {e}")

    async def _initialize_tasks(self, guild: discord.Guild):
        """Initialize task system"""
        try:
            # Load existing tasks data
            tasks_data = self.data_manager.load_guild_data(guild.id, "tasks")

            # Ensure settings exist within tasks data
            settings = tasks_data.get('settings', {})
            if not settings.get('next_task_id'):
                settings = {
                    'allow_user_tasks': True,
                    'max_tasks_per_user': 10,
                    'auto_expire_enabled': True,
                    'require_proof': True,
                    'next_task_id': 1,
                    'total_completed': 0,
                    'total_expired': 0
                }

                # Save updated tasks data with settings
                tasks_data['settings'] = settings
                self.data_manager.save_guild_data(guild.id, "tasks", tasks_data)

            logger.info(f"  ✓ Tasks initialized for {guild.name}")
        except Exception as e:
            logger.error(f"  ❌ Failed to initialize tasks for {guild.name}: {e}")

    async def _initialize_shop(self, guild: discord.Guild):
        """Initialize shop system"""
        try:
            # Shop items are loaded on demand, just log
            logger.info(f"  ✓ Shop initialized for {guild.name}")
        except Exception as e:
            logger.error(f"  ❌ Failed to initialize shop for {guild.name}: {e}")

    async def _initialize_embeds(self, guild: discord.Guild):
        """Initialize embed system"""
        try:
            # Embeds are created on demand
            logger.info(f"  ✓ Embeds initialized for {guild.name}")
        except Exception as e:
            logger.error(f"  ❌ Failed to initialize embeds for {guild.name}: {e}")

    async def _initialize_users(self, guild: discord.Guild):
        """Create user records for all guild members"""
        try:
            logger.info(f"  🔄 Creating users for {guild.name}...")

            # Get all members (excluding bots)
            members = [m for m in guild.members if not m.bot]

            logger.info(f"  📊 Found {len(members)} human members")

            # Create users in batches to avoid rate limits
            batch_size = 50
            created_count = 0

            for i in range(0, len(members), batch_size):
                batch = members[i:i + batch_size]

                for member in batch:
                    try:
                        # Check if user exists
                        user_data = self.data_manager.load_user_data(guild.id, member.id)

                        if not user_data or user_data.get('balance') is None:
                            # Create new user with default balance
                            self.data_manager.ensure_user_exists(guild.id, member.id)
                            created_count += 1

                    except Exception as e:
                        logger.warning(f"  ⚠️  Failed to create user {member.id}: {e}")
                        continue

                # Small delay between batches
                if i + batch_size < len(members):
                    await asyncio.sleep(0.5)

            logger.info(f"  ✓ Created {created_count} new users for {guild.name}")

        except Exception as e:
            logger.error(f"  ❌ Failed to initialize users for {guild.name}: {e}")

    async def _validate_user_data(self, guild: discord.Guild):
        """Ensure all users in data still exist in guild"""
        currency_data = self.data_manager.load_guild_data(guild.id, "currency")
        users = currency_data.get("users", {})

        # Get current guild member IDs
        member_ids = {str(member.id) for member in guild.members}

        # Find users in data who left the guild
        orphaned_users = set(users.keys()) - member_ids

        if orphaned_users:
            print(f"  ℹ️ Found {len(orphaned_users)} users who left {guild.name}")
            # Don't delete - keep for if they rejoin
            # Just log for awareness

    async def _cleanup_orphaned_data(self, guild: discord.Guild):
        """Remove Discord messages for deleted data"""
        config = self.data_manager.load_guild_data(guild.id, "config")

        # Clean up task messages
        task_channel_id = config.get("task_channel_id")
        if task_channel_id:
            task_channel = guild.get_channel(int(task_channel_id))
            if task_channel:
                tasks_data = self.data_manager.load_guild_data(guild.id, "tasks")
                valid_message_ids = {
                    task.get("message_id")
                    for task in tasks_data.get("tasks", {}).values()
                    if task.get("message_id")
                }

                # Check messages in channel
                try:
                    async for message in task_channel.history(limit=100):
                        if message.author == self.bot.user:
                            if str(message.id) not in valid_message_ids:
                                await message.delete()
                                print(f"  🗑️ Deleted orphaned task message in {guild.name}")
                except discord.Forbidden:
                    pass  # No permission to read history

    def _create_task_embed(self, task_data: dict) -> Embed:
        """Create embed for task display"""
        embed = Embed(
            title=f"📋 {task_data['name']}",
            description=task_data.get('description', 'No description'),
            color=discord.Color.blue()
        )

        embed.add_field(name="Reward", value=f"💰 {task_data['reward']} coins", inline=True)

        duration = task_data.get('duration_hours', 24)
        embed.add_field(name="Time Limit", value=f"⏰ {duration} hours", inline=True)

        status = task_data.get('status', 'pending')
        status_emoji = {"pending": "🟡", "active": "🟢", "completed": "✅"}.get(status, "⚪")
        embed.add_field(name="Status", value=f"{status_emoji} {status.title()}", inline=True)

        embed.set_footer(text=f"Task ID: {task_data['id']} | Use /claim {task_data['id']} to start")

        return embed

    def _create_shop_item_embed(self, item_data: dict, config: dict) -> Embed:
        """Create embed for shop item display"""
        currency_symbol = config.get("currency_symbol", "🪙")

        embed = Embed(
            title=item_data['name'],
            description=item_data.get('description', 'No description'),
            color=discord.Color.green() if item_data.get('is_active', True) else discord.Color.grey()
        )

        embed.add_field(
            name="Price",
            value=f"{currency_symbol}{item_data['price']}",
            inline=True
        )

        stock = item_data.get('stock', -1)
        stock_text = "♾️ Unlimited" if stock == -1 else f"📦 {stock} available"
        embed.add_field(name="Stock", value=stock_text, inline=True)

        category = item_data.get('category', 'misc')
        embed.add_field(name="Category", value=f"🏷️ {category.title()}", inline=True)

        embed.set_footer(text="Use /buy <item_id> to purchase")

        return embed
