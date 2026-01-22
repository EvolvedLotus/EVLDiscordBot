from datetime import datetime, timezone
import logging
import discord
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
                'log_channel_id': existing_config.get('log_channel_id') if existing_config else None,
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
            # Tasks are now managed directly through Supabase by TaskManager
            # No need to initialize task data files anymore
            # Task settings are automatically created by TaskManager when needed

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
        """Create user records for all guild members (Optimized Bulk Operation)"""
        try:
            logger.info(f"  🔄 Creating users for {guild.name}...")

            # Get all members (excluding bots)
            members = [m for m in guild.members if not m.bot]
            member_ids = {str(m.id) for m in members}
            
            logger.info(f"  📊 Found {len(members)} human members")

            # 1. Fetch ALL existing users for this guild in one query
            # Note: Supabase default limit is usually 1000. If guild is huge, pagination needed.
            # For typical usage <1000 members, this is fine.
            existing_users_result = self.data_manager.admin_client.table('users').select('user_id').eq('guild_id', str(guild.id)).execute()
            existing_user_ids = {u['user_id'] for u in existing_users_result.data}

            # 2. Identify missing users
            missing_member_ids = member_ids - existing_user_ids
            
            if not missing_member_ids:
                logger.info(f"  ✓ All {len(members)} members already exist in database")
                return

            logger.info(f"  📝 Need to create {len(missing_member_ids)} new user records")

            # 3. Prepare bulk data
            new_users_data = []
            for member_id in missing_member_ids:
                new_users_data.append({
                    "user_id": member_id,
                    "guild_id": str(guild.id),
                    "balance": 0,
                    "total_earned": 0,
                    "total_spent": 0,
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })

            # 4. Bulk Insert in batches
            batch_size = 100
            created_count = 0
            
            for i in range(0, len(new_users_data), batch_size):
                batch = new_users_data[i:i + batch_size]
                try:
                    self.data_manager.admin_client.table('users').insert(batch).execute()
                    created_count += len(batch)
                    logger.info(f"  ✓ Batch insert: {created_count}/{len(new_users_data)} users")
                except Exception as e:
                    logger.error(f"  ❌ Batch insert failed: {e}")
                    # Fallback to individual insert if batch fails (unlikely)
                    for user_data in batch:
                        try:
                            self.data_manager.admin_client.table('users').insert(user_data).execute()
                        except:
                            pass

            logger.info(f"  ✅ Created {created_count} new users for {guild.name}")

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

