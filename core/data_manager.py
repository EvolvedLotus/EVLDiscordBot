# In core/data_manager.py - Complete implementation with listeners

import json
import logging
import asyncio
import os
from pathlib import Path
from datetime import datetime
import time
import shutil
from typing import Any, Dict, List, Callable, Optional

logger = logging.getLogger(__name__)

class DataManager:
    """Centralized data management with event notifications"""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (self.data_dir / "guilds").mkdir(exist_ok=True)
        (self.data_dir / "global").mkdir(exist_ok=True)
        (self.data_dir / "backups").mkdir(exist_ok=True)

        # Cache system
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = 300  # 5 minutes

        # Event listener system
        self._listeners: List[Callable] = []

        # Bot instance for Discord sync
        self.bot_instance = None

        # Anti-loop protection
        self._write_locks = {}  # Prevent concurrent writes
        self._operation_timestamps = {}  # Track operation timing
        self._rate_limits = {}  # Rate limiting per operation

        # Performance monitoring
        self._performance_stats = {
            'loads': 0,
            'saves': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'sync_operations': 0,
            'start_time': time.time()
        }

        logger.info(f"DataManager initialized with data_dir: {self.data_dir}")

    def set_bot_instance(self, bot):
        """Set bot instance for Discord updates"""
        self.bot_instance = bot
        logger.info("Bot instance linked to DataManager for Discord sync")

    def register_listener(self, callback: Callable):
        """Register a callback for data change events"""
        self._listeners.append(callback)
        logger.info(f"Registered listener: {callback.__name__}")

    def _notify_listeners(self, event_type: str, data: Dict):
        """Notify all registered listeners of data changes"""
        for listener in self._listeners:
            try:
                listener(event_type, data)
            except Exception as e:
                logger.error(f"Error in listener {listener.__name__}: {e}")

    def broadcast_event(self, event_type: str, data: Dict):
        """Broadcast event to all listeners (alias for _notify_listeners)"""
        self._notify_listeners(event_type, data)

    def load_guild_data(self, guild_id: int, data_type: str, force_reload: bool = False) -> Optional[Dict]:
        """Load guild-specific data with caching"""
        cache_key = f"{guild_id}:{data_type}"

        # Check cache
        if not force_reload and cache_key in self._cache:
            cache_age = time.time() - self._cache_timestamps.get(cache_key, 0)
            if cache_age < self._cache_ttl:
                self._performance_stats['cache_hits'] += 1
                return self._cache[cache_key].copy()

        self._performance_stats['cache_misses'] += 1

        # Load from file
        guild_dir = self.data_dir / "guilds" / str(guild_id)
        file_path = guild_dir / f"{data_type}.json"

        if not file_path.exists():
            default_data = self._get_default_data(data_type)
            return default_data

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Update cache
            self._cache[cache_key] = data.copy()
            self._cache_timestamps[cache_key] = time.time()

            return data

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {guild_id}/{data_type}: {e}")
            # Try to recover from backup
            backup_path = guild_dir / f"{data_type}.backup.json"
            if backup_path.exists():
                try:
                    with open(backup_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    logger.info(f"Recovered {data_type} from backup for guild {guild_id}")
                    return data
                except Exception as backup_e:
                    logger.error(f"Backup recovery failed for {guild_id}/{data_type}: {backup_e}")
            return self._get_default_data(data_type)
        except FileNotFoundError as e:
            logger.warning(f"Data file not found for {guild_id}/{data_type}, using defaults: {e}")
            return self._get_default_data(data_type)
        except PermissionError as e:
            logger.error(f"Permission denied reading {guild_id}/{data_type}: {e}")
            return self._get_default_data(data_type)
        except OSError as e:
            logger.error(f"OS error reading {guild_id}/{data_type}: {e}")
            return self._get_default_data(data_type)
        except Exception as e:
            logger.error(f"Unexpected error loading {data_type} for guild {guild_id}: {e}")
            return self._get_default_data(data_type)

    def load_global_data(self, data_type: str, force_reload: bool = False) -> Optional[Dict]:
        """Load global data with caching"""
        cache_key = f"global:{data_type}"

        # Check cache
        if not force_reload and cache_key in self._cache:
            cache_age = time.time() - self._cache_timestamps.get(cache_key, 0)
            if cache_age < self._cache_ttl:
                self._performance_stats['cache_hits'] += 1
                return self._cache[cache_key].copy()

        self._performance_stats['cache_misses'] += 1

        # Load from file
        global_dir = self.data_dir / "global"
        file_path = global_dir / f"{data_type}.json"

        if not file_path.exists():
            default_data = self._get_default_global_data(data_type)
            return default_data

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Update cache
            self._cache[cache_key] = data.copy()
            self._cache_timestamps[cache_key] = time.time()

            return data

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for global/{data_type}: {e}")
            # Try to recover from backup
            backup_path = global_dir / f"{data_type}.backup.json"
            if backup_path.exists():
                try:
                    with open(backup_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    logger.info(f"Recovered global {data_type} from backup")
                    return data
                except Exception as backup_e:
                    logger.error(f"Backup recovery failed for global/{data_type}: {backup_e}")
            return self._get_default_global_data(data_type)
        except Exception as e:
            logger.error(f"Unexpected error loading global {data_type}: {e}")
            return self._get_default_global_data(data_type)

    def save_global_data(self, data_type: str, data) -> bool:
        """Save global data with atomic write"""
        if not isinstance(data, dict):
            logger.error(f"Invalid parameters: data_type={data_type}, data_type={type(data)}")
            return False

        global_dir = self.data_dir / "global"
        global_dir.mkdir(parents=True, exist_ok=True)

        file_path = global_dir / f"{data_type}.json"

        try:
            # Create backup if file exists
            if file_path.exists():
                backup_path = global_dir / f"{data_type}.backup.json"
                shutil.copy2(file_path, backup_path)

            # Atomic write using temp file
            temp_path = global_dir / f"{data_type}.tmp"

            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Atomic rename
            temp_path.replace(file_path)

            # Update cache
            cache_key = f"global:{data_type}"
            self._cache[cache_key] = data.copy()
            self._cache_timestamps[cache_key] = time.time()

            logger.debug(f"Saved global {data_type}")
            return True

        except Exception as e:
            logger.error(f"Error saving global {data_type}: {e}")
            return False

    def _get_default_global_data(self, data_type: str) -> Dict:
        """Get default global data structure"""
        defaults = {
            'config': {
                'bot_status': {
                    'type': 'playing',
                    'message': f'{len(self.bot_instance.guilds) if self.bot_instance else 0} servers',
                    'presence': 'online',
                    'streaming_url': None
                },
                'maintenance_mode': False,
                'version': '2.0'
            },
            'stats': {
                'total_guilds': 0,
                'total_users': 0,
                'total_commands': 0,
                'uptime_seconds': 0
            }
        }

        return defaults.get(data_type, {})

    def save_guild_data(self, guild_id: int, data_type: str, data) -> bool:
        """Save guild data with atomic write and event notification"""
        # Allow lists for transactions data type (existing format)
        if data_type == "transactions":
            if not isinstance(data, (dict, list)):
                logger.error(f"Invalid parameters: guild_id={guild_id}, data_type={data_type}, data_type={type(data)}")
                return False
        elif not isinstance(data, dict):
            logger.error(f"Invalid parameters: guild_id={guild_id}, data_type={data_type}, data_type={type(data)}")
            return False

        guild_dir = self.data_dir / "guilds" / str(guild_id)
        guild_dir.mkdir(parents=True, exist_ok=True)

        file_path = guild_dir / f"{data_type}.json"

        try:
            # Create backup if file exists
            if file_path.exists():
                backup_path = guild_dir / f"{data_type}.backup.json"
                shutil.copy2(file_path, backup_path)

            # Atomic write using temp file
            temp_path = guild_dir / f"{data_type}.tmp"

            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Atomic rename
            temp_path.replace(file_path)

            # Update cache
            cache_key = f"{guild_id}:{data_type}"
            self._cache[cache_key] = data.copy()
            self._cache_timestamps[cache_key] = time.time()

            # Notify listeners
            try:
                self._notify_listeners('guild_update', {
                    'guild_id': str(guild_id),
                    'data_type': data_type,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"Error notifying listeners: {e}")

            # NEW: Trigger Discord sync for specific data types
            if self.bot_instance and data_type in ["tasks", "currency"]:
                asyncio.run_coroutine_threadsafe(
                    self._sync_discord_elements(guild_id, data_type, data),
                    self.bot_instance.loop
                )

            logger.debug(f"Saved {data_type} for guild {guild_id}")
            return True

        except json.JSONEncodeError as e:
            logger.error(f"JSON encoding error saving {data_type} for guild {guild_id}: {e}")
            # Try to notify admin about data corruption
            asyncio.run_coroutine_threadsafe(
                self.notify_admin_critical_error(guild_id, f"save_{data_type}", f"JSON encoding failed: {str(e)}"),
                self.bot_instance.loop if self.bot_instance else asyncio.get_event_loop()
            )
        except PermissionError as e:
            logger.error(f"Permission denied saving {data_type} for guild {guild_id}: {e}")
            # Try to notify admin about permission issues
            asyncio.run_coroutine_threadsafe(
                self.notify_admin_missing_permissions(guild_id, f"write_{data_type}_file"),
                self.bot_instance.loop if self.bot_instance else asyncio.get_event_loop()
            )
        except OSError as e:
            logger.error(f"File system error saving {data_type} for guild {guild_id}: {e}")
            # Check if it's disk space or other OS issue
            if hasattr(e, 'errno'):
                if e.errno == 28:  # No space left on device
                    logger.critical(f"Disk space exhausted while saving {data_type} for guild {guild_id}")
                    asyncio.run_coroutine_threadsafe(
                        self.notify_admin_critical_error(guild_id, f"save_{data_type}", "Disk space exhausted"),
                        self.bot_instance.loop if self.bot_instance else asyncio.get_event_loop()
                    )
        except TypeError as e:
            logger.error(f"Type error in data structure for {data_type} guild {guild_id}: {e}")
            # Data structure issue - try to validate
            if not self.validate_data_integrity(guild_id, data_type):
                asyncio.run_coroutine_threadsafe(
                    self.notify_admin_critical_error(guild_id, f"save_{data_type}", f"Data structure corrupted: {str(e)}"),
                    self.bot_instance.loop if self.bot_instance else asyncio.get_event_loop()
                )
        except Exception as e:
            logger.error(f"Unexpected error saving {data_type} for guild {guild_id}: {e}")
            # Try to notify admin about unexpected errors
            asyncio.run_coroutine_threadsafe(
                self.notify_admin_critical_error(guild_id, f"save_{data_type}", f"Unexpected error: {str(e)}"),
                self.bot_instance.loop if self.bot_instance else asyncio.get_event_loop()
            )

        # Try to restore from backup
        backup_path = guild_dir / f"{data_type}.backup.json"
        if backup_path.exists():
            try:
                shutil.copy(backup_path, file_path)
                logger.info(f"Restored {data_type} from backup for guild {guild_id}")
            except Exception as e:
                logger.error(f"Failed to restore backup for guild {guild_id}: {e}")

        return False

    def _get_default_data(self, data_type: str) -> Dict:
        """Get default data structure for a given type"""
        defaults = {
            'config': {
                'prefix': '!',
                'currency_name': 'coins',
                'currency_symbol': '🪙',
                'admin_roles': [],
                'moderator_roles': [],
                'log_channel': None,
                'welcome_channel': None,
                'features': {
                    'currency': True,
                    'tasks': True,
                    'moderation': True
                }
            },
            'currency': {
                'users': {},
                'inventory': {},
                'shop_items': {},
                'metadata': {
                    'version': '2.0',
                    'total_currency': 0
                }
            },
            'tasks': {
                'tasks': {},
                'user_tasks': {},
                'categories': [],
                'settings': {
                    'allow_user_tasks': True,
                    'max_tasks_per_user': 10
                }
            },
            'transactions': {
                'transactions': []
            },
            'embeds': {
                'embeds': {},
                'templates': {
                    'task_template': {
                        'color': '#3498db',
                        'footer_text': 'Task System',
                        'thumbnail_url': None
                    },
                    'announcement_template': {
                        'color': '#e74c3c',
                        'footer_text': 'Server Announcement'
                    }
                },
                'settings': {
                    'default_color': '#7289da',
                    'allow_user_embeds': False,
                    'max_embeds_per_channel': 50
                }
            }
        }

        return defaults.get(data_type, {})

    def invalidate_cache(self, guild_id: Optional[int] = None, data_type: Optional[str] = None):
        """Invalidate cache entries"""
        if guild_id and data_type:
            cache_key = f"{guild_id}:{data_type}"
            self._cache.pop(cache_key, None)
            self._cache_timestamps.pop(cache_key, None)
        elif guild_id:
            keys_to_remove = [k for k in self._cache if k.startswith(f"{guild_id}:")]
            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
        else:
            self._cache.clear()
            self._cache_timestamps.clear()

    async def _sync_discord_elements(self, guild_id: int, data_type: str, data: dict):
        """Sync Discord elements when data changes"""
        guild = self.bot_instance.get_guild(guild_id)
        if not guild:
            return

        config = self.load_guild_data(guild_id, "config")

        if data_type == "tasks":
            await self._sync_tasks(guild, data, config)
        elif data_type == "currency":
            await self._sync_shop(guild, data, config)

    async def _sync_tasks(self, guild, tasks_data: dict, config: dict):
        """Update task messages when data changes (batch optimized)"""
        task_channel_id = config.get("task_channel_id")
        if not task_channel_id:
            return

        task_channel = guild.get_channel(int(task_channel_id))
        if not task_channel:
            return

        tasks = tasks_data.get("tasks", {})

        # Batch fetch existing messages for performance
        message_cache = {}
        try:
            async for message in task_channel.history(limit=100):
                if message.author == self.bot_instance.user:
                    message_cache[str(message.id)] = message
        except discord.Forbidden:
            # No permission to read history, fall back to individual fetches
            pass

        needs_save = False

        for task_id, task_data in tasks.items():
            message_id = task_data.get("message_id")

            if message_id and message_id in message_cache:
                # Update existing message from cache
                message = message_cache[message_id]
                embed = self._create_task_embed(task_data)
                try:
                    await message.edit(embed=embed)
                except discord.Forbidden:
                    logger.warning(f"No permission to update task message in {guild.name}")
                continue

            if not message_id:
                continue  # Will be created by initializer

            # Fetch message individually if not in cache
            try:
                message = await task_channel.fetch_message(int(message_id))

                # Update embed
                embed = self._create_task_embed(task_data)
                await message.edit(embed=embed)

            except discord.NotFound:
                # Message deleted, create new one
                embed = self._create_task_embed(task_data)
                try:
                    message = await task_channel.send(embed=embed)

                    # Update message ID in data
                    task_data["message_id"] = str(message.id)
                    needs_save = True
                except discord.Forbidden:
                    logger.warning(f"No permission to create task message in {guild.name}")

            except discord.Forbidden:
                logger.warning(f"No permission to update task message in {guild.name}")

        if needs_save:
            self.save_guild_data(guild.id, "tasks", tasks_data)

    async def _sync_shop(self, guild, currency_data: dict, config: dict):
        """Update shop messages when data changes (batch optimized)"""
        shop_channel_id = config.get("shop_channel_id")
        if not shop_channel_id:
            return

        shop_channel = guild.get_channel(int(shop_channel_id))
        if not shop_channel:
            return

        shop_items = currency_data.get("shop_items", {})

        # Batch fetch existing messages for performance
        message_cache = {}
        try:
            async for message in shop_channel.history(limit=100):
                if message.author == self.bot_instance.user:
                    message_cache[str(message.id)] = message
        except discord.Forbidden:
            # No permission to read history, fall back to individual fetches
            pass

        needs_save = False

        for item_id, item_data in shop_items.items():
            message_id = item_data.get("message_id")

            if message_id and message_id in message_cache:
                # Update existing message from cache
                message = message_cache[message_id]
                embed = self._create_shop_item_embed(item_data, config)
                try:
                    await message.edit(embed=embed)
                except discord.Forbidden:
                    logger.warning(f"No permission to update shop message in {guild.name}")
                continue

            if not message_id:
                continue

            # Fetch message individually if not in cache
            try:
                message = await shop_channel.fetch_message(int(message_id))

                # Update embed
                embed = self._create_shop_item_embed(item_data, config)
                await message.edit(embed=embed)

            except discord.NotFound:
                # Message deleted, recreate if item is active
                if item_data.get("is_active", True):
                    embed = self._create_shop_item_embed(item_data, config)
                    try:
                        message = await shop_channel.send(embed=embed)

                        # Update message ID in data
                        item_data["message_id"] = str(message.id)
                        needs_save = True
                    except discord.Forbidden:
                        logger.warning(f"No permission to create shop message in {guild.name}")

            except discord.Forbidden:
                logger.warning(f"No permission to update shop message in {guild.name}")

        if needs_save:
            self.save_guild_data(guild.id, "currency", currency_data)

    def _create_task_embed(self, task_data: dict):
        """Helper to create task embed"""
        import discord
        embed = discord.Embed(
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

    def _create_shop_item_embed(self, item_data: dict, config: dict):
        """Helper to create shop item embed"""
        import discord
        currency_symbol = config.get("currency_symbol", "$")

        embed = discord.Embed(
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

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        uptime = time.time() - self._performance_stats['start_time']
        total_operations = self._performance_stats['loads'] + self._performance_stats['saves']

        stats = self._performance_stats.copy()
        stats.update({
            'uptime_seconds': uptime,
            'total_operations': total_operations,
            'cache_hit_rate': (
                self._performance_stats['cache_hits'] /
                (self._performance_stats['cache_hits'] + self._performance_stats['cache_misses'])
                if (self._performance_stats['cache_hits'] + self._performance_stats['cache_misses']) > 0
                else 0
            ),
            'operations_per_second': total_operations / uptime if uptime > 0 else 0,
            'cache_size': len(self._cache)
        })

        return stats

    def _get_write_lock(self, guild_id: int, data_type: str):
        """Get or create a write lock for specific data"""
        import threading
        key = f"{guild_id}_{data_type}"
        if key not in self._write_locks:
            self._write_locks[key] = threading.Lock()
        return self._write_locks[key]

    def _check_rate_limit(self, operation_key: str, limit_seconds: float = 1.0) -> bool:
        """Check if operation is rate limited"""
        now = time.time()
        last_op = self._operation_timestamps.get(operation_key, 0)

        if now - last_op < limit_seconds:
            return False  # Rate limited

        self._operation_timestamps[operation_key] = now
        return True

    def save_guild_data_with_locking(self, guild_id: int, data_type: str, data, skip_rate_limit: bool = False) -> bool:
        """Save guild data with rate limiting and locking"""
        operation_key = f"save_{guild_id}_{data_type}"

        # Rate limit check (1 second between saves by default)
        if not skip_rate_limit and not self._check_rate_limit(operation_key, 1.0):
            logger.warning(f"Rate limit hit for {operation_key}, skipping save")
            return False

        # Acquire write lock
        with self._get_write_lock(guild_id, data_type):
            return self.save_guild_data(guild_id, data_type, data)

    def get_embed_by_message_id(self, guild_id: int, message_id: str) -> Optional[dict]:
        """Get embed data by Discord message ID (cached)"""
        cache_key = f"embed_msg_{guild_id}_{message_id}"

        # Check cache
        if cache_key in self._cache:
            age = time.time() - self._cache_timestamps[cache_key]
            if age < self._cache_ttl:
                return self._cache[cache_key]

        # Load from file
        embeds_data = self.load_guild_data(guild_id, 'embeds')
        if not embeds_data:
            return None

        for embed_id, embed in embeds_data.get('embeds', {}).items():
            if embed.get('message_id') == message_id:
                # Cache result
                self._cache[cache_key] = embed
                self._cache_timestamps[cache_key] = time.time()
                return embed

        return None

    def reset_performance_stats(self):
        """Reset performance statistics"""
        self._performance_stats = {
            'loads': 0,
            'saves': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'sync_operations': 0,
            'start_time': time.time()
        }

    def atomic_transaction(self, guild_id: int, updates: Dict[str, Any]) -> bool:
        """
        Update multiple data files atomically with rollback capability
        updates = {
            'currency': {...},
            'tasks': {...},
            'transactions': [...]
        }
        """
        backups = {}
        try:
            # Create backups for all files being updated
            for file_type in updates.keys():
                backup_path = self._create_backup(guild_id, file_type)
                if backup_path:
                    backups[file_type] = backup_path

            # Apply all updates
            for file_type, data in updates.items():
                success = self.save_guild_data(guild_id, file_type, data)
                if not success:
                    raise Exception(f"Failed to save {file_type} data")

            # Commit - delete backups
            for backup in backups.values():
                try:
                    os.remove(backup)
                except OSError as e:
                    logger.warning(f"Failed to remove backup {backup}: {e}")

            logger.info(f"Atomic transaction completed for guild {guild_id}")
            return True

        except Exception as e:
            # Rollback - restore from backups
            logger.error(f"Atomic transaction failed for guild {guild_id}, rolling back: {e}")
            for file_type, backup in backups.items():
                try:
                    file_path = self._get_file_path(guild_id, file_type)
                    shutil.copy(backup, file_path)
                    logger.info(f"Restored {file_type} from backup for guild {guild_id}")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback {file_type} for guild {guild_id}: {rollback_error}")
            raise

    def _create_backup(self, guild_id: int, data_type: str) -> Optional[Path]:
        """Create a backup of existing data file"""
        file_path = self._get_file_path(guild_id, data_type)
        if file_path.exists():
            backup_path = file_path.with_suffix('.backup.json')
            try:
                shutil.copy2(file_path, backup_path)
                logger.debug(f"Created backup: {backup_path}")
                return backup_path
            except OSError as e:
                logger.error(f"Failed to create backup for {data_type}: {e}")
                return None
        return None

    def _get_file_path(self, guild_id: int, data_type: str) -> Path:
        """Get the file path for a guild data file"""
        guild_dir = self.data_dir / "guilds" / str(guild_id)
        return guild_dir / f"{data_type}.json"

    def validate_data_integrity(self, guild_id: int, data_type: str) -> bool:
        """Validate data structure matches expected schema"""
        try:
            data = self.load_guild_data(guild_id, data_type)

            if data_type == 'currency':
                assert 'users' in data, "Missing users dict"
                assert 'shop_items' in data, "Missing shop_items dict"
                assert 'inventory' in data, "Missing inventory dict"
                assert 'metadata' in data, "Missing metadata"

                # Validate each user entry
                for user_id, user_data in data['users'].items():
                    assert 'balance' in user_data, f"User {user_id} missing balance"
                    assert user_data['balance'] >= 0, f"User {user_id} has negative balance"
                    assert 'total_earned' in user_data
                    assert 'total_spent' in user_data

            elif data_type == 'tasks':
                assert 'tasks' in data, "Missing tasks dict"
                assert 'user_tasks' in data, "Missing user_tasks dict"

                # Validate task references
                for user_id, user_tasks in data['user_tasks'].items():
                    for task_id in user_tasks.keys():
                        assert str(task_id) in data['tasks'], f"Orphaned user_task reference: {task_id}"

            logger.info(f"Data integrity check passed for guild {guild_id}/{data_type}")
            return True

        except AssertionError as e:
            logger.error(f"Data integrity violation in guild {guild_id}/{data_type}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error during data integrity check for guild {guild_id}/{data_type}: {e}")
            return False

    async def notify_admin_missing_permissions(self, guild_id: int, operation: str):
        """Notify admin about missing permissions"""
        if not self.bot_instance:
            return

        guild = self.bot_instance.get_guild(guild_id)
        if not guild:
            return

        config = self.load_guild_data(guild_id, 'config')
        log_channel_id = config.get('log_channel')

        if log_channel_id:
            try:
                log_channel = guild.get_channel(int(log_channel_id))
                if log_channel:
                    embed = self._create_error_embed(
                        "Missing Permissions",
                        f"Bot lacks permissions to perform: {operation}",
                        discord.Color.orange()
                    )
                    await log_channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to send permission error notification: {e}")

    async def notify_admin_critical_error(self, guild_id: int, operation: str, error_msg: str):
        """Notify admin about critical errors"""
        if not self.bot_instance:
            return

        guild = self.bot_instance.get_guild(guild_id)
        if not guild:
            return

        config = self.load_guild_data(guild_id, 'config')
        log_channel_id = config.get('log_channel')

        if log_channel_id:
            try:
                log_channel = guild.get_channel(int(log_channel_id))
                if log_channel:
                    embed = self._create_error_embed(
                        "Critical Error",
                        f"Operation: {operation}\nError: {error_msg}",
                        discord.Color.red()
                    )
                    await log_channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to send critical error notification: {e}")

    def get_all_guilds(self) -> List[int]:
        """Get list of all guild IDs that have data stored"""
        guilds_dir = self.data_dir / "guilds"
        if not guilds_dir.exists():
            return []

        guild_ids = []
        try:
            for item in guilds_dir.iterdir():
                if item.is_dir():
                    try:
                        guild_id = int(item.name)
                        guild_ids.append(guild_id)
                    except ValueError:
                        # Skip non-numeric directory names
                        continue
        except OSError as e:
            logger.error(f"Error reading guilds directory: {e}")
            return []

        return guild_ids

    def _broadcast_data_change(self, guild_id, data_type, change_type, affected_ids):
        """
        Broadcast data change event to all listeners.
        change_type: 'create', 'update', 'delete'
        affected_ids: List of IDs that changed (user_ids, task_ids, item_ids)
        """
        try:
            event_data = {
                'guild_id': str(guild_id),
                'data_type': data_type,
                'change_type': change_type,
                'affected_ids': affected_ids or [],
                'timestamp': datetime.now().isoformat()
            }

            # Broadcast to all registered listeners
            self._notify_listeners(f'{data_type}_{change_type}', event_data)

            # Also broadcast generic data change event
            self._notify_listeners('data_changed', event_data)

            logger.debug(f"Broadcasted {data_type}_{change_type} event for guild {guild_id}")

        except Exception as e:
            logger.error(f"Error broadcasting data change event: {e}")

    def _create_error_embed(self, title: str, description: str, color):
        """Create error notification embed"""
        import discord
        embed = discord.Embed(
            title=f"⚠️ {title}",
            description=description,
            color=color,
            timestamp=datetime.now()
        )
        embed.set_footer(text="DataManager Error Notification")
        return embed

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        current_time = time.time()
        total_entries = len(self._cache)
        expired_entries = 0
        active_entries = 0

        for cache_key, timestamp in self._cache_timestamps.items():
            age = current_time - timestamp
            if age > self._cache_ttl:
                expired_entries += 1
            else:
                active_entries += 1

        return {
            'total_entries': total_entries,
            'active_entries': active_entries,
            'expired_entries': expired_entries,
            'cache_hit_rate': (
                self._performance_stats['cache_hits'] /
                max(1, self._performance_stats['cache_hits'] + self._performance_stats['cache_misses'])
            ),
            'uptime_seconds': current_time - self._performance_stats['start_time']
        }

    def cleanup_expired_cache(self) -> int:
        """Remove expired cache entries and return count of removed entries"""
        current_time = time.time()
        expired_keys = []

        # Find expired entries
        for cache_key, timestamp in self._cache_timestamps.items():
            age = current_time - timestamp
            if age > self._cache_ttl:
                expired_keys.append(cache_key)

        # Remove expired entries
        for cache_key in expired_keys:
            self._cache.pop(cache_key, None)
            self._cache_timestamps.pop(cache_key, None)

        logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
        return len(expired_keys)
