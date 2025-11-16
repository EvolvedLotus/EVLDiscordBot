# In core/data_manager.py - Supabase-based implementation (NO LOCAL STORAGE)

import json
import logging
import asyncio
import os
from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Callable, Optional
import supabase
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class DataManager:
    """Supabase-based data management with event notifications"""

    def __init__(self):
        # Supabase configuration
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_ANON_KEY')
        self.supabase_service_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

        if not all([self.supabase_url, self.supabase_key, self.supabase_service_key]):
            raise ValueError("Missing Supabase environment variables")

        # Initialize Supabase clients
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.admin_client: Client = create_client(self.supabase_url, self.supabase_service_key)

        # Cache system (in-memory only, no file storage)
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = 300  # 5 minutes

        # Event listener system
        self._listeners: List[Callable] = []

        # Bot instance for Discord sync
        self.bot_instance = None

        # Performance monitoring
        self._performance_stats = {
            'loads': 0,
            'saves': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'sync_operations': 0,
            'start_time': time.time()
        }

        logger.info("DataManager initialized with Supabase backend")

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
        """Load guild-specific data from Supabase"""
        cache_key = f"{guild_id}:{data_type}"

        # Check cache
        if not force_reload and cache_key in self._cache:
            cache_age = time.time() - self._cache_timestamps.get(cache_key, 0)
            if cache_age < self._cache_ttl:
                self._performance_stats['cache_hits'] += 1
                return self._cache[cache_key].copy()

        self._performance_stats['cache_misses'] += 1

        try:
            # Load from Supabase based on data_type
            if data_type == 'config':
                result = self.admin_client.table('guilds').select('*').eq('guild_id', str(guild_id)).execute()
                if result.data:
                    guild_data = result.data[0]
                    # Convert database format to expected format
                    data = {
                        'prefix': guild_data.get('prefix', '!'),
                        'currency_name': guild_data.get('currency_name', 'coins'),
                        'currency_symbol': guild_data.get('currency_symbol', '$'),
                        'admin_roles': guild_data.get('admin_roles', []),
                        'moderator_roles': guild_data.get('moderator_roles', []),
                        'log_channel': guild_data.get('log_channel'),
                        'welcome_channel': guild_data.get('welcome_channel'),
                        'task_channel_id': guild_data.get('task_channel_id'),
                        'shop_channel_id': guild_data.get('shop_channel_id'),
                        'features': {
                            'currency': guild_data.get('feature_currency', True),
                            'tasks': guild_data.get('feature_tasks', True),
                            'shop': guild_data.get('feature_shop', True),
                            'announcements': guild_data.get('feature_announcements', True),
                            'moderation': guild_data.get('feature_moderation', True)
                        },
                        'global_shop': guild_data.get('global_shop', False),
                        'global_tasks': guild_data.get('global_tasks', False)
                    }
                else:
                    # Guild not found, return defaults
                    data = self._get_default_data(data_type)

            elif data_type == 'currency':
                # Get users for this guild
                users_result = self.admin_client.table('users').select('*').eq('guild_id', str(guild_id)).execute()
                users = {}
                for user in users_result.data:
                    users[user['user_id']] = {
                        'balance': user['balance'],
                        'total_earned': user['total_earned'],
                        'total_spent': user['total_spent'],
                        'last_daily': user.get('last_daily'),
                        'is_active': user['is_active'],
                        'created_at': user['created_at'].isoformat() if user['created_at'] else None,
                        'username': user.get('username', 'Unknown'),
                        'display_name': user.get('display_name', 'Unknown')
                    }

                # Get shop items for this guild
                shop_result = self.admin_client.table('shop_items').select('*').eq('guild_id', str(guild_id)).execute()
                shop_items = {}
                for item in shop_result.data:
                    shop_items[item['item_id']] = {
                        'name': item['name'],
                        'description': item['description'],
                        'price': item['price'],
                        'category': item['category'],
                        'stock': item['stock'],
                        'emoji': item['emoji'],
                        'is_active': item['is_active'],
                        'message_id': item['message_id'],
                        'channel_id': item['channel_id'],
                        'created_at': item['created_at'].isoformat() if item['created_at'] else None
                    }

                # Get inventory for this guild
                inventory_result = self.admin_client.table('inventory').select('*').eq('guild_id', str(guild_id)).execute()
                inventory = {}
                for inv in inventory_result.data:
                    user_id = inv['user_id']
                    item_id = inv['item_id']
                    if user_id not in inventory:
                        inventory[user_id] = {}
                    inventory[user_id][item_id] = {
                        'quantity': inv['quantity'],
                        'acquired_at': inv['acquired_at'].isoformat() if inv['acquired_at'] else None
                    }

                data = {
                    'users': users,
                    'shop_items': shop_items,
                    'inventory': inventory,
                    'metadata': {
                        'version': '2.0',
                        'total_currency': sum(u.get('balance', 0) for u in users.values())
                    }
                }

            elif data_type == 'tasks':
                # Get tasks for this guild
                tasks_result = self.admin_client.table('tasks').select('*').eq('guild_id', str(guild_id)).execute()
                tasks = {}
                for task in tasks_result.data:
                    tasks[str(task['task_id'])] = {
                        'id': task['task_id'],
                        'name': task['name'],
                        'description': task['description'],
                        'reward': task['reward'],
                        'duration_hours': task['duration_hours'],
                        'status': task['status'],
                        'created_at': task['created_at'].isoformat() if task['created_at'] else None,
                        'expires_at': task['expires_at'].isoformat() if task['expires_at'] else None,
                        'channel_id': task['channel_id'],
                        'message_id': task['message_id'],
                        'max_claims': task['max_claims'],
                        'current_claims': task['current_claims'],
                        'assigned_users': task.get('assigned_users', []),
                        'category': task['category'],
                        'role_name': task['role_name']
                    }

                # Get user tasks for this guild
                user_tasks_result = self.admin_client.table('user_tasks').select('*').eq('guild_id', str(guild_id)).execute()
                user_tasks = {}
                for ut in user_tasks_result.data:
                    user_id = ut['user_id']
                    task_id = str(ut['task_id'])
                    if user_id not in user_tasks:
                        user_tasks[user_id] = {}
                    user_tasks[user_id][task_id] = {
                        'claimed_at': ut['claimed_at'].isoformat() if ut['claimed_at'] else None,
                        'deadline': ut['deadline'].isoformat() if ut['deadline'] else None,
                        'status': ut['status'],
                        'proof_message_id': ut['proof_message_id'],
                        'proof_attachments': ut.get('proof_attachments', []),
                        'proof_content': ut['proof_content'],
                        'submitted_at': ut['submitted_at'].isoformat() if ut['submitted_at'] else None,
                        'completed_at': ut['completed_at'].isoformat() if ut['completed_at'] else None,
                        'notes': ut['notes']
                    }

                # Get task settings
                settings_result = self.admin_client.table('task_settings').select('*').eq('guild_id', str(guild_id)).execute()
                settings = {}
                if settings_result.data:
                    s = settings_result.data[0]
                    settings = {
                        'allow_user_tasks': s['allow_user_tasks'],
                        'max_tasks_per_user': s['max_tasks_per_user'],
                        'auto_expire_enabled': s['auto_expire_enabled'],
                        'require_proof': s['require_proof'],
                        'announcement_channel_id': s['announcement_channel_id'],
                        'next_task_id': s['next_task_id'],
                        'total_completed': s['total_completed'],
                        'total_expired': s['total_expired']
                    }

                data = {
                    'tasks': tasks,
                    'user_tasks': user_tasks,
                    'settings': settings,
                    'categories': []  # TODO: implement categories
                }

            elif data_type == 'transactions':
                # Get transactions for this guild
                transactions_result = self.admin_client.table('transactions').select('*').eq('guild_id', str(guild_id)).order('timestamp', desc=True).execute()
                transactions = []
                for txn in transactions_result.data:
                    transactions.append({
                        'id': txn['transaction_id'],
                        'user_id': txn['user_id'],
                        'amount': txn['amount'],
                        'balance_before': txn['balance_before'],
                        'balance_after': txn['balance_after'],
                        'type': txn['transaction_type'],
                        'description': txn['description'],
                        'timestamp': txn['timestamp'].isoformat() if txn['timestamp'] else None,
                        'metadata': txn.get('metadata', {})
                    })

                data = {'transactions': transactions}

            elif data_type == 'announcements':
                # Get announcements for this guild
                announcements_result = self.admin_client.table('announcements').select('*').eq('guild_id', str(guild_id)).order('created_at', desc=True).execute()
                announcements = {}
                for ann in announcements_result.data:
                    announcements[ann['announcement_id']] = {
                        'id': ann['announcement_id'],
                        'title': ann['title'],
                        'content': ann['content'],
                        'embed_data': ann.get('embed_data'),
                        'channel_id': ann['channel_id'],
                        'message_id': ann['message_id'],
                        'is_pinned': ann['is_pinned'],
                        'created_at': ann['created_at'].isoformat() if ann['created_at'] else None,
                        'created_by': ann['created_by']
                    }

                data = {'announcements': announcements}

            elif data_type == 'embeds':
                # Get embeds for this guild
                embeds_result = self.admin_client.table('embeds').select('*').eq('guild_id', str(guild_id)).order('created_at', desc=True).execute()
                embeds = {}
                for emb in embeds_result.data:
                    embeds[emb['embed_id']] = {
                        'id': emb['embed_id'],
                        'title': emb['title'],
                        'description': emb['description'],
                        'color': emb['color'],
                        'fields': emb.get('fields', []),
                        'footer': emb.get('footer'),
                        'thumbnail': emb.get('thumbnail'),
                        'image': emb.get('image'),
                        'channel_id': emb['channel_id'],
                        'message_id': emb['message_id'],
                        'created_at': emb['created_at'].isoformat() if emb['created_at'] else None,
                        'created_by': emb['created_by']
                    }

                data = {
                    'embeds': embeds,
                    'templates': {},  # TODO: implement templates
                    'settings': {}    # TODO: implement settings
                }

            else:
                data = self._get_default_data(data_type)

            # Update cache
            self._cache[cache_key] = data.copy()
            self._cache_timestamps[cache_key] = time.time()

            return data

        except Exception as e:
            logger.error(f"Error loading {data_type} for guild {guild_id} from Supabase: {e}")
            return self._get_default_data(data_type)

    def load_global_data(self, data_type: str, force_reload: bool = False) -> Optional[Dict]:
        """Load global data - for now just return defaults since we don't have global tables yet"""
        return self._get_default_global_data(data_type)

    def save_global_data(self, data_type: str, data) -> bool:
        """Save global data - placeholder for future global settings"""
        # For now, just return success since we don't have global persistence
        return True

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
        """Save guild data to Supabase"""
        try:
            if data_type == 'config':
                # Ensure guild exists
                self.admin_client.table('guilds').upsert({
                    'guild_id': str(guild_id),
                    'prefix': data.get('prefix', '!'),
                    'currency_name': data.get('currency_name', 'coins'),
                    'currency_symbol': data.get('currency_symbol', '$'),
                    'admin_roles': data.get('admin_roles', []),
                    'moderator_roles': data.get('moderator_roles', []),
                    'log_channel': data.get('log_channel'),
                    'welcome_channel': data.get('welcome_channel'),
                    'task_channel_id': data.get('task_channel_id'),
                    'shop_channel_id': data.get('shop_channel_id'),
                    'feature_currency': data.get('features', {}).get('currency', True),
                    'feature_tasks': data.get('features', {}).get('tasks', True),
                    'feature_shop': data.get('features', {}).get('shop', True),
                    'feature_announcements': data.get('features', {}).get('announcements', True),
                    'feature_moderation': data.get('features', {}).get('moderation', True),
                    'global_shop': data.get('global_shop', False),
                    'global_tasks': data.get('global_tasks', False),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }).execute()

            elif data_type == 'currency':
                # Save users
                for user_id, user_data in data.get('users', {}).items():
                    self.admin_client.table('users').upsert({
                        'user_id': user_id,
                        'guild_id': str(guild_id),
                        'balance': user_data.get('balance', 0),
                        'total_earned': user_data.get('total_earned', 0),
                        'total_spent': user_data.get('total_spent', 0),
                        'last_daily': user_data.get('last_daily'),
                        'is_active': user_data.get('is_active', True),
                        'username': user_data.get('username', 'Unknown'),
                        'display_name': user_data.get('display_name', 'Unknown'),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }).execute()

                # Save shop items
                for item_id, item_data in data.get('shop_items', {}).items():
                    self.admin_client.table('shop_items').upsert({
                        'item_id': item_id,
                        'guild_id': str(guild_id),
                        'name': item_data['name'],
                        'description': item_data.get('description'),
                        'price': item_data['price'],
                        'category': item_data.get('category', 'general'),
                        'stock': item_data.get('stock', -1),
                        'emoji': item_data.get('emoji', '🛒'),
                        'is_active': item_data.get('is_active', True),
                        'message_id': item_data.get('message_id'),
                        'channel_id': item_data.get('channel_id'),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }).execute()

                # Save inventory
                for user_id, user_inventory in data.get('inventory', {}).items():
                    for item_id, inv_data in user_inventory.items():
                        self.admin_client.table('inventory').upsert({
                            'user_id': user_id,
                            'guild_id': str(guild_id),
                            'item_id': item_id,
                            'quantity': inv_data.get('quantity', 0),
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }).execute()

            elif data_type == 'tasks':
                # Save tasks
                for task_id, task_data in data.get('tasks', {}).items():
                    self.admin_client.table('tasks').upsert({
                        'task_id': int(task_id),
                        'guild_id': str(guild_id),
                        'name': task_data['name'],
                        'description': task_data.get('description', ''),
                        'reward': task_data['reward'],
                        'duration_hours': task_data['duration_hours'],
                        'status': task_data.get('status', 'active'),
                        'expires_at': task_data.get('expires_at'),
                        'channel_id': task_data.get('channel_id'),
                        'message_id': task_data.get('message_id'),
                        'max_claims': task_data.get('max_claims', -1),
                        'current_claims': task_data.get('current_claims', 0),
                        'assigned_users': task_data.get('assigned_users', []),
                        'category': task_data.get('category', 'General'),
                        'role_name': task_data.get('role_name')
                    }).execute()

                # Save user tasks
                for user_id, user_tasks in data.get('user_tasks', {}).items():
                    for task_id, ut_data in user_tasks.items():
                        self.admin_client.table('user_tasks').upsert({
                            'user_id': user_id,
                            'guild_id': str(guild_id),
                            'task_id': int(task_id),
                            'status': ut_data.get('status', 'in_progress'),
                            'proof_message_id': ut_data.get('proof_message_id'),
                            'proof_attachments': ut_data.get('proof_attachments', []),
                            'proof_content': ut_data.get('proof_content'),
                            'notes': ut_data.get('notes', ''),
                            'deadline': ut_data.get('deadline'),
                            'submitted_at': ut_data.get('submitted_at'),
                            'completed_at': ut_data.get('completed_at')
                        }).execute()

                # Save task settings
                settings = data.get('settings', {})
                if settings:
                    self.admin_client.table('task_settings').upsert({
                        'guild_id': str(guild_id),
                        'allow_user_tasks': settings.get('allow_user_tasks', True),
                        'max_tasks_per_user': settings.get('max_tasks_per_user', 10),
                        'auto_expire_enabled': settings.get('auto_expire_enabled', True),
                        'require_proof': settings.get('require_proof', True),
                        'announcement_channel_id': settings.get('announcement_channel_id'),
                        'next_task_id': settings.get('next_task_id', 1),
                        'total_completed': settings.get('total_completed', 0),
                        'total_expired': settings.get('total_expired', 0),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }).execute()

            elif data_type == 'transactions':
                # Transactions are handled separately via transaction_manager
                pass

            elif data_type == 'announcements':
                # Announcements are handled separately via announcement_manager
                pass

            elif data_type == 'embeds':
                # Embeds are handled separately via embed_builder
                pass

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

            # Trigger Discord sync for specific data types
            if self.bot_instance and data_type in ["tasks", "currency"]:
                asyncio.run_coroutine_threadsafe(
                    self._sync_discord_elements(guild_id, data_type, data),
                    self.bot_instance.loop
                )

            logger.debug(f"Saved {data_type} for guild {guild_id} to Supabase")
            return True

        except Exception as e:
            logger.error(f"Error saving {data_type} for guild {guild_id} to Supabase: {e}")
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
                'task_channel_id': None,
                'shop_channel_id': None,
                'features': {
                    'currency': True,
                    'tasks': True,
                    'shop': True,
                    'announcements': True,
                    'moderation': True
                },
                'global_shop': False,
                'global_tasks': False
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
                    'max_tasks_per_user': 10,
                    'auto_expire_enabled': True,
                    'require_proof': True,
                    'announcement_channel_id': None,
                    'next_task_id': 1,
                    'total_completed': 0,
                    'total_expired': 0
                }
            },
            'transactions': {'transactions': []},
            'announcements': {'announcements': {}},
            'embeds': {
                'embeds': {},
                'templates': {},
                'settings': {}
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
                    # Update in database
                    self.admin_client.table('tasks').update({
                        'message_id': str(message.id)
                    }).eq('guild_id', str(guild.id)).eq('task_id', int(task_id)).execute()
                except discord.Forbidden:
                    logger.warning(f"No permission to create task message in {guild.name}")

            except discord.Forbidden:
                logger.warning(f"No permission to update task message in {guild.name}")

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
                        # Update in database
                        self.admin_client.table('shop_items').update({
                            'message_id': str(message.id)
                        }).eq('guild_id', str(guild.id)).eq('item_id', item_id).execute()
                    except discord.Forbidden:
                        logger.warning(f"No permission to create shop message in {guild.name}")

            except discord.Forbidden:
                logger.warning(f"No permission to update shop message in {guild.name}")

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

    def get_all_guilds(self) -> List[int]:
        """Get list of all guild IDs that have data stored"""
        try:
            result = self.admin_client.table('guilds').select('guild_id').execute()
            return [int(guild['guild_id']) for guild in result.data]
        except Exception as e:
            logger.error(f"Error getting guilds from Supabase: {e}")
            return []

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
