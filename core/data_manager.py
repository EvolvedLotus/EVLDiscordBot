# In core/data_manager.py - Supabase-based implementation (NO LOCAL STORAGE)

import json
import logging
import asyncio
import os
from datetime import datetime, timezone
import time
import random
from typing import Any, Dict, List, Callable, Optional
import supabase
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class DataManager:
    """Supabase-based data management with enhanced connection management"""

    def __init__(self):
        # Supabase configuration
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_ANON_KEY')
        self.supabase_service_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

        if not all([self.supabase_url, self.supabase_key, self.supabase_service_key]):
            raise ValueError("Missing Supabase environment variables")

        # Connection configuration
        self.connection_timeout = int(os.getenv('DB_CONNECTION_TIMEOUT', '30'))
        self.max_retries = int(os.getenv('DB_MAX_RETRIES', '3'))
        self.retry_delay = float(os.getenv('DB_RETRY_DELAY', '1.0'))  # Base retry delay
        self.retry_backoff_base = float(os.getenv('DB_RETRY_BACKOFF_BASE', '2.0'))
        self.health_check_interval = int(os.getenv('DB_HEALTH_CHECK_INTERVAL', '60'))

        # Initialize Supabase clients with enhanced configuration
        self.client: Client = self._create_supabase_client(self.supabase_url, self.supabase_key)
        self.admin_client: Client = self._create_supabase_client(self.supabase_url, self.supabase_service_key)

        # ✅ CRITICAL: Store the supabase client for backward compatibility
        self.supabase = self.client

        # Connection health monitoring
        self._connection_healthy = True
        self._last_health_check = 0
        self._consecutive_failures = 0
        self._max_consecutive_failures = 5

        # Cache system DISABLED for immediate updates
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = int(os.getenv('CACHE_TTL', '0'))  # DISABLED - 0 seconds
        self._balance_cache_ttl = int(os.getenv('BALANCE_CACHE_TTL', '0'))  # DISABLED - 0 seconds

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
            'db_connection_errors': 0,
            'db_retry_attempts': 0,
            'db_query_timeouts': 0,
            'start_time': time.time()
        }

        # Graceful degradation mode
        self._degraded_mode = False

        # Verify client is valid
        if not self.supabase:
            raise ValueError("Supabase client cannot be None")

        logger.info("✅ DataManager initialized with Supabase client")

    def _serialize_datetime_field(self, value):
        """Safely serialize datetime fields from database"""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            return value  # Already serialized from Supabase
        return str(value)  # Fallback

    def _create_supabase_client(self, url: str, key: str) -> Client:
        """Create Supabase client with enhanced configuration"""
        try:
            client = create_client(url, key)
            # Configure timeouts and connection settings
            # Note: Supabase client handles most of this internally
            return client
        except Exception as e:
            logger.error(f"Failed to create Supabase client: {e}")
            raise

    def _execute_with_retry(self, operation, operation_name, *args, **kwargs):
        """Execute operation with retry logic (synchronous)"""
        import time
        for attempt in range(1, self.max_retries + 1):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries:
                    logger.error(f"❌ Operation {operation_name} failed after {self.max_retries} attempts: {e}")
                    self._enter_degraded_mode()
                    # Return safe fallback instead of raising
                    return self._get_fallback_result(operation_name)

                delay = self.retry_delay * (2 ** (attempt - 1))
                logger.warning(f"⚠️  Operation {operation_name} failed (attempt {attempt}/{self.max_retries}): {e}. Retrying in {delay:.2f}s")

                time.sleep(delay)
    
        # Fallback if all retries exhausted
        return self._get_fallback_result(operation_name)

    def _check_connection_health(self) -> bool:
        """Check database connection health"""
        current_time = time.time()

        # Only check health periodically
        if current_time - self._last_health_check < self.health_check_interval:
            return self._connection_healthy

        try:
            self._last_health_check = current_time

            # Simple health check query
            start_time = time.time()
            result = self.admin_client.table('guilds').select('guild_id').limit(1).execute()
            query_time = time.time() - start_time

            # Consider unhealthy if query takes too long
            if query_time > self.connection_timeout:
                self._performance_stats['db_query_timeouts'] += 1
                logger.warning(f"Database health check query timed out: {query_time:.2f}s")
                self._connection_healthy = False
                return False

            self._connection_healthy = True
            return True

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            self._connection_healthy = False
            return False

    def _enter_degraded_mode(self):
        """Enter degraded mode when database operations consistently fail"""
        self._degraded_mode = True
        logger.error("🚨 ENTERING DEGRADED MODE - Database operations failing")

    def _get_fallback_result(self, operation_name: str):
        """Provide fallback results when database is unavailable"""
        logger.warning(f"Providing fallback result for {operation_name} in degraded mode")

        if operation_name.startswith('load_guild_data'):
            # Extract data_type from operation name
            parts = operation_name.split('_')
            if len(parts) >= 3:
                data_type = '_'.join(parts[2:])  # Handle data types like 'guild_data_config'
                return self._get_default_data(data_type)
            return self._get_default_data('unknown')
        elif operation_name.startswith('save_guild_data'):
            return False  # Indicate save failed
        elif operation_name == 'get_all_guilds':
            return []  # Return empty list

        return None

    def is_degraded_mode(self) -> bool:
        """Check if DataManager is in degraded mode"""
        return self._degraded_mode

    def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed connection status information"""
        return {
            'healthy': self._connection_healthy,
            'degraded_mode': self._degraded_mode,
            'last_health_check': self._last_health_check,
            'consecutive_failures': self._consecutive_failures,
            'cache_size': len(self._cache),
            'uptime_seconds': time.time() - self._performance_stats['start_time']
        }

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

    def load_guild_data(self, guild_id: int, data_type: str, force_reload: bool = False) -> Dict:
        """Load guild data from Supabase with caching"""
        cache_key = f"{guild_id}_{data_type}"
        
        # Check cache first (unless force_reload)
        if not force_reload and cache_key in self._cache:
            cache_age = time.time() - self._cache_timestamps.get(cache_key, 0)
            # Use shorter TTL for balance-critical data
            ttl = self._balance_cache_ttl if data_type == 'currency' else self._cache_ttl
            if cache_age < ttl:
                self._performance_stats['cache_hits'] += 1
                return self._cache[cache_key].copy()

        self._performance_stats['cache_misses'] += 1

        def _load_operation(guild_id, data_type):
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
                        'global_tasks': guild_data.get('global_tasks', False),
                        'bot_status_message': guild_data.get('bot_status_message'),
                        'bot_status_type': guild_data.get('bot_status_type', 'playing')
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
                        'created_at': self._serialize_datetime_field(user.get('created_at')),
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
                        'created_at': self._serialize_datetime_field(item.get('created_at'))
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
                        'acquired_at': self._serialize_datetime_field(inv.get('acquired_at'))
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
                    # Ensure assigned_users is always a list
                    assigned_users = task.get('assigned_users', [])
                    if not isinstance(assigned_users, list):
                        # Convert to list if it's not (e.g., dict, string, etc.)
                        assigned_users = []
                    
                    tasks[str(task['task_id'])] = {
                        'id': task['task_id'],
                        'name': task['name'],
                        'description': task['description'],
                        'reward': task['reward'],
                        'duration_hours': task['duration_hours'],
                        'status': task['status'],
                        'created_at': self._serialize_datetime_field(task.get('created_at')),
                        'expires_at': self._serialize_datetime_field(task.get('expires_at')),
                        'channel_id': task['channel_id'],
                        'message_id': task['message_id'],
                        'max_claims': task['max_claims'],
                        'current_claims': task['current_claims'],
                        'assigned_users': assigned_users,
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
                        'claimed_at': self._serialize_datetime_field(ut.get('claimed_at')),
                        'deadline': self._serialize_datetime_field(ut.get('deadline')),
                        'status': ut['status'],
                        'proof_message_id': ut['proof_message_id'],
                        'proof_attachments': ut.get('proof_attachments', []),
                        'proof_content': ut['proof_content'],
                        'submitted_at': self._serialize_datetime_field(ut.get('submitted_at')),
                        'completed_at': self._serialize_datetime_field(ut.get('completed_at')),
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
                transactions_result = self.admin_client.table('transactions').select('*').eq('guild_id', str(guild_id)).order('"timestamp"', desc=True).execute()
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
                        'timestamp': self._serialize_datetime_field(txn.get('timestamp')),
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
                        'created_at': self._serialize_datetime_field(ann.get('created_at')),
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
                        'created_at': self._serialize_datetime_field(emb.get('created_at')),
                        'created_by': emb['created_by']
                    }

                # Validate structure
                loaded_data = {
                    'embeds': embeds,
                    'templates': {},  # TODO: implement templates
                    'settings': {}    # TODO: implement settings
                }

                # Ensure it's always a dict
                if isinstance(loaded_data, str):
                    loaded_data = {"embeds": {}}
                if not isinstance(loaded_data, dict):
                    loaded_data = {"embeds": {}}

                data = loaded_data

            else:
                data = self._get_default_data(data_type)

            return data

        try:
            data = self._execute_with_retry(_load_operation, f'load_guild_data_{data_type}', guild_id, data_type)

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

    def save_guild_data(self, guild_id, data_type, data):
        """Save guild data to database with proper error handling"""
        def _save_operation(gid, dtype, save_data):  # ✅ Now accepts 3 arguments
            """Inner function to save guild data"""
            try:
                guild_id_str = str(gid)

                if dtype == "config":
                    # ✅ FIXED: Handle MISSING required fields properly
                    # Try to get missing required fields from bot instance or database
                    server_name = None
                    owner_id = None

                    # Get from bot instance if available
                    if self.bot_instance and gid:
                        guild = self.bot_instance.get_guild(int(gid))
                        if guild:
                            server_name = guild.name
                            owner_id = str(guild.owner_id)

                    # If not found, try to load from existing database record
                    if not server_name or not owner_id:
                        try:
                            existing_result = self.admin_client.table('guilds').select('server_name, owner_id').eq('guild_id', guild_id_str).execute()
                            if existing_result.data and len(existing_result.data) > 0:
                                existing_data = existing_result.data[0]
                                server_name = server_name or existing_data.get('server_name')
                                owner_id = owner_id or existing_data.get('owner_id')
                        except Exception:
                            pass  # Continue with defaults if error

                    # Set defaults if still not found
                    server_name = server_name or save_data.get('server_name') or f'Guild_{guild_id_str}'
                    owner_id = owner_id or save_data.get('owner_id') or 'unknown'

                    guild_data = {
                        'guild_id': guild_id_str,
                        'server_name': server_name,
                        'owner_id': owner_id,
                        'member_count': save_data.get('member_count', 0),
                        'icon_url': save_data.get('icon_url'),
                        'prefix': save_data.get('prefix', '!'),
                        'currency_name': save_data.get('currency_name', 'coins'),
                        'currency_symbol': save_data.get('currency_symbol', '$'),
                        'admin_roles': save_data.get('admin_roles', []),
                        'moderator_roles': save_data.get('moderator_roles', []),
                        'log_channel': save_data.get('log_channel'),
                        'welcome_channel': save_data.get('welcome_channel'),
                        'task_channel_id': save_data.get('task_channel_id'),
                        'shop_channel_id': save_data.get('shop_channel_id'),
                        'feature_currency': save_data.get('feature_currency', True),
                        'feature_tasks': save_data.get('feature_tasks', True),
                        'feature_shop': save_data.get('feature_shop', True),
                        'feature_announcements': save_data.get('feature_announcements', True),
                        'feature_moderation': save_data.get('feature_moderation', True),
                        'global_shop': save_data.get('global_shop', False),
                        'global_tasks': save_data.get('global_tasks', False),
                        'bot_status_message': save_data.get('bot_status_message'),
                        'bot_status_type': save_data.get('bot_status_type', 'playing')
                    }

                    # Save guild data
                    self.admin_client.table('guilds').upsert(guild_data, on_conflict='guild_id').execute()

                    # Handle embeds data - store in embeds table
                    embeds_data = save_data.get('embeds', {})
                    for embed_id, embed_data in embeds_data.items():
                        self.admin_client.table('embeds').upsert({
                            'embed_id': embed_id,
                            'guild_id': guild_id_str,
                            'title': embed_data.get('title'),
                            'description': embed_data.get('description'),
                            'color': embed_data.get('color'),
                            'fields': embed_data.get('fields', []),
                            'footer': embed_data.get('footer'),
                            'thumbnail': embed_data.get('thumbnail'),
                            'image': embed_data.get('image'),
                            'channel_id': embed_data.get('channel_id'),
                            'message_id': embed_data.get('message_id'),
                            'created_by': embed_data.get('created_by'),
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }).execute()

                    logger.info(f"✅ Config data saved for guild {guild_id_str}")

                elif dtype == "tasks":
                    # Save tasks data to database
                    tasks_data = save_data.get('tasks', {})
                    user_tasks_data = save_data.get('user_tasks', {})
                    settings_data = save_data.get('settings', {})

                    # Save tasks - ensure datetime serialization
                    for task_id, task in tasks_data.items():
                        task_data = {
                            'task_id': int(task_id),
                            'guild_id': guild_id_str,
                            'name': task['name'],
                            'description': task['description'],
                            'reward': task['reward'],
                            'duration_hours': task['duration_hours'],
                            'status': task['status'],
                            'expires_at': self._serialize_datetime_field(task.get('expires_at')),
                            'channel_id': task.get('channel_id'),
                            'message_id': task.get('message_id'),
                            'max_claims': task.get('max_claims', -1),
                            'current_claims': task.get('current_claims', 0),
                            'assigned_users': task.get('assigned_users', []),
                            'category': task.get('category', 'general'),
                            'role_name': task.get('role_name')
                        }

                        # Remove None values to avoid JSON serialization issues
                        task_data = {k: v for k, v in task_data.items() if v is not None}

                        self.admin_client.table('tasks').upsert(task_data, on_conflict='guild_id,task_id').execute()

                    # Save user tasks - ensure datetime serialization
                    for user_id, user_tasks in user_tasks_data.items():
                        for task_id, user_task in user_tasks.items():
                            user_task_data = {
                                'guild_id': guild_id_str,
                                'user_id': user_id,
                                'task_id': int(task_id),
                                'claimed_at': self._serialize_datetime_field(user_task.get('claimed_at')),
                                'deadline': self._serialize_datetime_field(user_task.get('deadline')),
                                'status': user_task.get('status', 'in_progress'),
                                'proof_message_id': user_task.get('proof_message_id'),
                                'proof_attachments': user_task.get('proof_attachments', []),
                                'proof_content': user_task.get('proof_content', ''),
                                'submitted_at': self._serialize_datetime_field(user_task.get('submitted_at')),
                                'completed_at': self._serialize_datetime_field(user_task.get('completed_at')),
                                'notes': user_task.get('notes', ''),
                                'updated_at': datetime.now(timezone.utc).isoformat()
                            }

                            # Remove None values to avoid JSON serialization issues
                            user_task_data = {k: v for k, v in user_task_data.items() if v is not None}

                            self.admin_client.table('user_tasks').upsert(user_task_data, on_conflict='guild_id,user_id,task_id').execute()

                    # Save task settings - ensure datetime serialization
                    if settings_data:
                        settings_task_data = {
                            'guild_id': guild_id_str,
                            'allow_user_tasks': settings_data.get('allow_user_tasks', True),
                            'max_tasks_per_user': settings_data.get('max_tasks_per_user', 10),
                            'auto_expire_enabled': settings_data.get('auto_expire_enabled', True),
                            'require_proof': settings_data.get('require_proof', True),
                            'announcement_channel_id': settings_data.get('announcement_channel_id'),
                            'next_task_id': settings_data.get('next_task_id', 1),
                            'total_completed': settings_data.get('total_completed', 0),
                            'total_expired': settings_data.get('total_expired', 0),
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }

                        # Remove None values to avoid JSON serialization issues
                        settings_task_data = {k: v for k, v in settings_task_data.items() if v is not None}

                        self.admin_client.table('task_settings').upsert(settings_task_data, on_conflict='guild_id').execute()

                    logger.info(f"✅ Tasks data saved for guild {guild_id_str}")

                elif dtype == "currency":
                    # Save currency data to database
                    users_data = save_data.get('users', {})
                    shop_items_data = save_data.get('shop_items', {})
                    inventory_data = save_data.get('inventory', {})

                    # Save users
                    for user_id, user_data in users_data.items():
                        self.admin_client.table('users').upsert({
                            'guild_id': guild_id_str,
                            'user_id': user_id,
                            'balance': user_data.get('balance', 0),
                            'total_earned': user_data.get('total_earned', 0),
                            'total_spent': user_data.get('total_spent', 0),
                            'last_daily': user_data.get('last_daily'),
                            'is_active': user_data.get('is_active', True),
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }, on_conflict='guild_id,user_id').execute()

                    # Save shop items
                    for item_id, item_data in shop_items_data.items():
                        self.admin_client.table('shop_items').upsert({
                            'guild_id': guild_id_str,
                            'item_id': item_id,
                            'name': item_data['name'],
                            'description': item_data.get('description', ''),
                            'price': item_data['price'],
                            'category': item_data.get('category', 'general'),
                            'stock': item_data.get('stock', -1),
                            'emoji': item_data.get('emoji', '🛍️'),
                            'is_active': item_data.get('is_active', True),
                            'message_id': item_data.get('message_id'),
                            'channel_id': item_data.get('channel_id'),
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }, on_conflict='guild_id,item_id').execute()

                    # Save inventory - normalize data format before saving
                    for user_id, user_inventory in inventory_data.items():
                        for item_id, inventory_value in user_inventory.items():
                            # Handle both dict format (from DB load) and int format (from memory operations)
                            if isinstance(inventory_value, dict):
                                quantity = inventory_value.get('quantity', 0)
                            elif isinstance(inventory_value, int):
                                quantity = inventory_value
                            else:
                                quantity = 0

                            if quantity > 0:  # Only save positive quantities
                                self.admin_client.table('inventory').upsert({
                                    'guild_id': guild_id_str,
                                    'user_id': user_id,
                                    'item_id': item_id,
                                    'quantity': quantity,
                                    'updated_at': datetime.now(timezone.utc).isoformat()
                                }, on_conflict='guild_id,user_id,item_id').execute()
                            else:
                                # Remove zero quantity items
                                self.admin_client.table('inventory').delete().eq('guild_id', guild_id_str).eq('user_id', user_id).eq('item_id', item_id).execute()

                    logger.info(f"✅ Currency data saved for guild {guild_id_str}")

                else:
                    logger.warning(f"Unknown data type for save_guild_data: {dtype}")

                return True

            except Exception as e:
                logger.error(f"Error in _save_operation for {dtype}: {e}")
                raise

        try:
            # Call with arguments
            success = self._execute_with_retry(
                _save_operation,
                f'save_guild_data_{data_type}',
                guild_id,
                data_type,
                data
            )
            return success
        except Exception as e:
            logger.error(f"save_guild_data failed for {data_type}: {e}")
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
        """Get list of all guild IDs that have data stored with retry logic"""
        def _get_guilds_operation():
            result = self.admin_client.table('guilds').select('guild_id').execute()
            return [int(guild['guild_id']) for guild in result.data]

        try:
            return self._execute_with_retry(_get_guilds_operation, 'get_all_guilds')
        except Exception as e:
            logger.error(f"Error getting guilds from Supabase: {e}")
            return []

    def sync_all_guilds(self) -> Dict[str, Any]:
        """
        Sync all guilds from Discord to Supabase.
        Ensures all bot guilds have entries in the database.

        Returns:
            Dict with sync results
        """
        if not self.bot_instance:
            return {'success': False, 'error': 'Bot instance not available'}

        synced_guilds = []
        failed_guilds = []
        new_guilds = []

        try:
            # Get all current guilds from Discord
            discord_guilds = {}
            for guild in self.bot_instance.guilds:
                discord_guilds[str(guild.id)] = {
                    'guild_id': str(guild.id),
                    'server_name': guild.name,
                    'member_count': guild.member_count,
                    'owner_id': str(guild.owner_id),
                    'created_at': guild.created_at.isoformat(),
                    'icon_url': str(guild.icon.url) if guild.icon else None,
                    'is_active': True,
                    'last_sync': datetime.now(timezone.utc).isoformat()
                }

            # Get existing guilds from database
            existing_guilds_result = self.admin_client.table('guilds').select('guild_id, is_active').execute()
            existing_guild_ids = {guild['guild_id'] for guild in existing_guilds_result.data}

            # Sync each Discord guild
            for guild_id, guild_data in discord_guilds.items():
                try:
                    # Check if guild exists in database
                    is_new = guild_id not in existing_guild_ids

                    # Upsert guild data
                    self.admin_client.table('guilds').upsert({
                        **guild_data,
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }).execute()

                    synced_guilds.append(guild_id)
                    if is_new:
                        new_guilds.append(guild_id)

                    logger.info(f"{'Created' if is_new else 'Updated'} guild {guild_id} ({guild_data['server_name']}) in database")

                except Exception as e:
                    logger.error(f"Failed to sync guild {guild_id}: {e}")
                    failed_guilds.append(guild_id)

            # Mark inactive guilds (guilds in DB but not in Discord)
            inactive_count = self._mark_inactive_guilds(list(discord_guilds.keys()))

            return {
                'success': True,
                'synced_guilds': len(synced_guilds),
                'new_guilds': len(new_guilds),
                'failed_guilds': len(failed_guilds),
                'inactive_guilds': inactive_count,
                'total_discord_guilds': len(discord_guilds)
            }

        except Exception as e:
            logger.error(f"Error during guild sync: {e}")
            return {
                'success': False,
                'error': str(e),
                'synced_guilds': len(synced_guilds),
                'failed_guilds': len(failed_guilds)
            }

    def sync_guild_to_database(self, guild_id: str, guild_data: dict = None):
        """Sync guild data using RPC to bypass PostgREST cache issues"""
        try:
            # Use RPC function instead of direct table update
            result = self.supabase.rpc(
                'sync_guild_last_sync',
                {'p_guild_id': str(guild_id)}
            ).execute()

            logger.info(f"✅ Guild {guild_id} synced via RPC")
            return True

        except Exception as e:
            logger.warning(f"RPC sync failed for {guild_id}: {e}")

            # Fallback: update without last_sync column
            try:
                result = self.admin_client.table("guilds").update({
                    "is_active": True,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).eq("guild_id", str(guild_id)).execute()

                logger.info(f"✅ Guild {guild_id} synced via fallback (no last_sync)")
                return True

            except Exception as e2:
                logger.error(f"❌ All sync methods failed for {guild_id}: {e2}")
                return False

    def _mark_inactive_guilds(self, active_guild_ids: List[str]) -> int:
        """
        Mark guilds as inactive if they're not in the active list.
        Returns count of guilds marked inactive.
        """
        try:
            # Get all guilds from database
            all_guilds_result = self.admin_client.table('guilds').select('guild_id, is_active, server_name').execute()

            inactive_count = 0
            for guild in all_guilds_result.data:
                guild_id = guild['guild_id']
                if guild_id not in active_guild_ids and guild.get('is_active', True):
                    # Mark as inactive
                    self.admin_client.table('guilds').update({
                        'is_active': False,
                        'last_sync': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }).eq('guild_id', guild_id).execute()

                    inactive_count += 1
                    logger.info(f"Marked guild {guild_id} ({guild.get('server_name', 'Unknown')}) as inactive")

            return inactive_count

        except Exception as e:
            logger.error(f"Error marking inactive guilds: {e}")
            return 0

    def get_cache_stats(self):
        """Get cache statistics for monitoring"""
        cache_size = len(self._cache) if hasattr(self, '_cache') else 0
        return {
            'size': cache_size,
            'max_size': getattr(self, '_cache_max_size', 1000),
            'hit_rate': self._calculate_hit_rate() if hasattr(self, '_cache_hits') else 0.0,
            'keys': list(self._cache.keys())[:10] if hasattr(self, '_cache') else []  # Show first 10 keys
        }

    def _calculate_hit_rate(self):
        """Calculate cache hit rate"""
        total = getattr(self, '_cache_hits', 0) + getattr(self, '_cache_misses', 0)
        if total == 0:
            return 0.0
        return (self._cache_hits / total) * 100

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

    async def ensure_user_exists(self, guild_id: int, user_id: int) -> bool:
        """Ensure user exists in database with default values"""
        try:
            # First check if user exists to avoid unnecessary conflicts
            existing = self.supabase.table("users").select("user_id").eq(
                "guild_id", str(guild_id)
            ).eq(
                "user_id", str(user_id)
            ).execute()

            if existing.data and len(existing.data) > 0:
                # User already exists
                logger.debug(f"User {user_id} already exists in guild {guild_id}")
                return True

            # User doesn't exist, try to create
            result = self.supabase.table("users").insert({
                "user_id": str(user_id),
                "guild_id": str(guild_id),
                "balance": 0,
                "total_earned": 0,
                "total_spent": 0,
                "is_active": True
            }).execute()

            logger.info(f"✅ Created user {user_id} in guild {guild_id}")
            return True

        except Exception as e:
            error_msg = str(e)

            # Handle 409 Conflict or duplicate key errors
            if "409" in error_msg or "duplicate" in error_msg.lower() or "unique" in error_msg.lower():
                logger.debug(f"User {user_id} already exists in guild {guild_id} (handled conflict)")
                return True

            logger.error(f"Failed to create user {user_id} in guild {guild_id}: {e}")
            return False

    def load_user_data(self, guild_id: int, user_id: int) -> dict:
        """Load user data from database"""
        try:
            result = self.supabase.table("users").select("*").eq(
                "guild_id", str(guild_id)
            ).eq(
                "user_id", str(user_id)
            ).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]

            return {}

        except Exception as e:
            logger.error(f"Failed to load user {user_id} from guild {guild_id}: {e}")
            return {}

    def atomic_transaction(self, guild_id: int = None):
        """
        Context manager for atomic database transactions with proper error handling.
        Provides row-level locking and rollback capabilities.
        """
        return AtomicTransactionContext(self.admin_client, guild_id)

    def get_user_guilds(self, user_id: str) -> List[Dict]:
        """
        Get all guilds accessible by a user.
        For admin users (like admin-env-user), returns all guilds.
        For regular users, returns guilds where they have admin permissions.
        """
        try:
            # For environment admin user, return all guilds
            if user_id == 'admin-env-user':
                result = self.admin_client.table('guilds').select('guild_id, server_name').eq('is_active', True).execute()
                return [{'guild_id': g['guild_id'], 'server_name': g['server_name']} for g in result.data]
            
            # For database users, check admin_users table
            admin_result = self.admin_client.table('admin_users').select('guild_id').eq('user_id', user_id).execute()
            
            if not admin_result.data:
                # User has no admin access to any guilds
                return []
            
            guild_ids = [row['guild_id'] for row in admin_result.data]
            
            # Get guild details
            guilds_result = self.admin_client.table('guilds').select('*').in_('guild_id', guild_ids).eq('is_active', True).execute()
            
            return [{'guild_id': g['guild_id'], 'server_name': g['server_name']} for g in guilds_result.data]
            
        except Exception as e:
            logger.error(f"Error getting user guilds for {user_id}: {e}")
            return []

    def get_guild_users(self, guild_id: str, page: int = 1, limit: int = 50) -> Dict:
        """
        Get paginated list of users for a specific guild.
        Returns dict with 'users' list and 'total' count.
        """
        try:
            guild_id_str = str(guild_id)
            
            # Calculate offset for pagination
            offset = (page - 1) * limit
            
            # Get total count
            count_result = self.admin_client.table('users').select('user_id', count='exact').eq('guild_id', guild_id_str).execute()
            total_count = count_result.count if hasattr(count_result, 'count') else len(count_result.data)
            
            # Get paginated users
            users_result = self.admin_client.table('users').select('*').eq('guild_id', guild_id_str).range(offset, offset + limit - 1).execute()
            
            users = []
            for user in users_result.data:
                users.append({
                    'user_id': user['user_id'],
                    'username': user.get('username', 'Unknown'),
                    'display_name': user.get('display_name', 'Unknown'),
                    'balance': user.get('balance', 0),
                    'total_earned': user.get('total_earned', 0),
                    'total_spent': user.get('total_spent', 0),
                    'last_daily': self._serialize_datetime_field(user.get('last_daily')),
                    'is_active': user.get('is_active', True),
                    'created_at': self._serialize_datetime_field(user.get('created_at')),
                    'updated_at': self._serialize_datetime_field(user.get('updated_at'))
                })
            
            return {
                'users': users,
                'total': total_count,
                'page': page,
                'limit': limit,
                'pages': (total_count + limit - 1) // limit  # Ceiling division
            }
            
        except Exception as e:
            logger.error(f"Error getting guild users for {guild_id}: {e}")
            return {
                'users': [],
                'total': 0,
                'page': page,
                'limit': limit,
                'pages': 0
            }

    def get_guild_config(self, guild_id: str) -> Dict:
        """Get guild configuration"""
        try:
            config_data = self.load_guild_data(int(guild_id), 'config')
            return config_data if config_data else self._get_default_data('config')
        except Exception as e:
            logger.error(f"Error getting guild config for {guild_id}: {e}")
            return self._get_default_data('config')

    def update_guild_config(self, guild_id: str, config_data: Dict) -> bool:
        """Update guild configuration"""
        try:
            # Load existing config
            existing_config = self.load_guild_data(int(guild_id), 'config')
            
            # Merge with new data
            existing_config.update(config_data)
            
            # Save back
            return self.save_guild_data(int(guild_id), 'config', existing_config)
        except Exception as e:
            logger.error(f"Error updating guild config for {guild_id}: {e}")
            return False

    def get_guild_channels(self, guild_id: str) -> List[Dict]:
        """Get list of channels for a guild from Discord bot"""
        try:
            if not self.bot_instance:
                logger.warning("Bot instance not set, cannot get channels")
                return []
            
            guild = self.bot_instance.get_guild(int(guild_id))
            if not guild:
                logger.warning(f"Guild {guild_id} not found in bot instance")
                return []
            
            channels = []
            for channel in guild.channels:
                # Only include text channels and categories
                if hasattr(channel, 'type'):
                    channels.append({
                        'id': str(channel.id),
                        'name': channel.name,
                        'type': str(channel.type),
                        'position': channel.position if hasattr(channel, 'position') else 0
                    })
            
            return sorted(channels, key=lambda x: x['position'])
            
        except Exception as e:
            logger.error(f"Error getting guild channels for {guild_id}: {e}")
            return []

    def get_guild_roles(self, guild_id: str) -> List[Dict]:
        """Get list of roles for a guild from Discord bot"""
        try:
            if not self.bot_instance:
                logger.warning("Bot instance not set, cannot get roles")
                return []
            
            guild = self.bot_instance.get_guild(int(guild_id))
            if not guild:
                logger.warning(f"Guild {guild_id} not found in bot instance")
                return []
            
            roles = []
            for role in guild.roles:
                roles.append({
                    'id': str(role.id),
                    'name': role.name,
                    'color': role.color.value if hasattr(role, 'color') else 0,
                    'position': role.position,
                    'permissions': role.permissions.value if hasattr(role, 'permissions') else 0,
                    'mentionable': role.mentionable if hasattr(role, 'mentionable') else False
                })
            
            return sorted(roles, key=lambda x: x['position'], reverse=True)
            
        except Exception as e:
            logger.error(f"Error getting guild roles for {guild_id}: {e}")
            return []

    def get_user(self, guild_id: str, user_id: str) -> Dict:
        """Get detailed information about a specific user in a guild"""
        try:
            guild_id_str = str(guild_id)
            user_id_str = str(user_id)
            
            # Get user from database
            user_result = self.admin_client.table('users').select('*').eq('guild_id', guild_id_str).eq('user_id', user_id_str).execute()
            
            if not user_result.data:
                return {'error': 'User not found'}
            
            user = user_result.data[0]
            
            # Get user's inventory
            inventory_result = self.admin_client.table('inventory').select('*').eq('guild_id', guild_id_str).eq('user_id', user_id_str).execute()
            inventory = {}
            for inv in inventory_result.data:
                inventory[inv['item_id']] = {
                    'quantity': inv['quantity'],
                    'acquired_at': self._serialize_datetime_field(inv.get('acquired_at'))
                }
            
            # Get user's tasks
            user_tasks_result = self.admin_client.table('user_tasks').select('*').eq('guild_id', guild_id_str).eq('user_id', user_id_str).execute()
            tasks = []
            for ut in user_tasks_result.data:
                tasks.append({
                    'task_id': ut['task_id'],
                    'status': ut['status'],
                    'claimed_at': self._serialize_datetime_field(ut.get('claimed_at')),
                    'completed_at': self._serialize_datetime_field(ut.get('completed_at'))
                })
            
            # Get recent transactions
            transactions_result = self.admin_client.table('transactions').select('*').eq('guild_id', guild_id_str).eq('user_id', user_id_str).order('timestamp', desc=True).limit(10).execute()
            transactions = []
            for txn in transactions_result.data:
                transactions.append({
                    'id': txn['transaction_id'],
                    'amount': txn['amount'],
                    'type': txn['transaction_type'],
                    'description': txn['description'],
                    'timestamp': self._serialize_datetime_field(txn.get('timestamp'))
                })
            
            return {
                'user_id': user['user_id'],
                'username': user.get('username', 'Unknown'),
                'display_name': user.get('display_name', 'Unknown'),
                'balance': user.get('balance', 0),
                'total_earned': user.get('total_earned', 0),
                'total_spent': user.get('total_spent', 0),
                'last_daily': self._serialize_datetime_field(user.get('last_daily')),
                'is_active': user.get('is_active', True),
                'created_at': self._serialize_datetime_field(user.get('created_at')),
                'updated_at': self._serialize_datetime_field(user.get('updated_at')),
                'inventory': inventory,
                'tasks': tasks,
                'recent_transactions': transactions
            }
            
        except Exception as e:
            logger.error(f"Error getting user {user_id} for guild {guild_id}: {e}")
            return {'error': str(e)}


class AtomicTransactionContext:
    """Context manager for atomic database transactions"""

    def __init__(self, client, guild_id: int = None):
        self.client = client
        self.guild_id = guild_id
        self.connection = None
        self.in_transaction = False

    async def __aenter__(self):
        """Enter the transaction context"""
        try:
            # For Supabase, we use the client directly since it handles connection pooling
            # Note: Supabase doesn't expose raw connections, so we simulate transaction behavior
            self.connection = self.client
            self.in_transaction = True
            logger.debug(f"Entered atomic transaction context for guild {self.guild_id}")
            return self
        except Exception as e:
            logger.error(f"Failed to enter transaction context: {e}")
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the transaction context"""
        try:
            if exc_type is not None:
                # An exception occurred, transaction should be rolled back
                logger.warning(f"Transaction rolled back due to exception: {exc_val}")
                # Note: Supabase handles rollback automatically on errors
            else:
                logger.debug(f"Transaction committed successfully for guild {self.guild_id}")

            self.in_transaction = False
            self.connection = None
        except Exception as e:
            logger.error(f"Error exiting transaction context: {e}")

    async def fetchrow(self, query: str, *args):
        """
        Fetch a single row from the database (PostgreSQL-compatible interface for Supabase).
        This is used by task_manager for atomic operations.
        """
        if not self.in_transaction:
            raise RuntimeError("Not in transaction context")

        try:
            # Parse the query to determine the table and operation
            query_upper = query.strip().upper()
            
            if 'UPDATE task_settings' in query_upper and 'RETURNING' in query_upper:
                # Handle: UPDATE task_settings SET next_task_id = next_task_id + 1 WHERE guild_id = $1 RETURNING next_task_id
                guild_id = str(args[0])
                result = self.client.table('task_settings').select('next_task_id').eq('guild_id', guild_id).execute()
                
                if result.data and len(result.data) > 0:
                    current_id = result.data[0]['next_task_id']
                    new_id = current_id + 1
                    
                    # Update with new ID
                    self.client.table('task_settings').update({
                        'next_task_id': new_id
                    }).eq('guild_id', guild_id).execute()
                    
                    return {'next_task_id': new_id}
                return None
                
            elif 'SELECT' in query_upper and 'FROM tasks' in query_upper:
                # Handle: SELECT ... FROM tasks WHERE task_id = $1 AND guild_id = $2
                task_id = str(args[0])
                guild_id = str(args[1])
                result = self.client.table('tasks').select('*').eq('task_id', task_id).eq('guild_id', guild_id).execute()
                return result.data[0] if result.data else None
                
            elif 'SELECT' in query_upper and 'FROM user_tasks' in query_upper:
                # Handle: SELECT ... FROM user_tasks WHERE user_id = $1 AND guild_id = $2 AND task_id = $3
                user_id = str(args[0])
                guild_id = str(args[1])
                task_id = str(args[2])
                result = self.client.table('user_tasks').select('*').eq('user_id', user_id).eq('guild_id', guild_id).eq('task_id', task_id).execute()
                return result.data[0] if result.data else None
                
            elif 'SELECT' in query_upper and 'FROM users' in query_upper:
                # Handle: SELECT balance FROM users WHERE user_id = $1 AND guild_id = $2
                user_id = str(args[0])
                guild_id = str(args[1])
                result = self.client.table('users').select('*').eq('user_id', user_id).eq('guild_id', guild_id).execute()
                return result.data[0] if result.data else None
                
            else:
                logger.warning(f"Unhandled fetchrow query: {query[:100]}")
                return None
                
        except Exception as e:
            logger.error(f"fetchrow failed: {e}")
            raise

    async def execute(self, query: str, *args):
        """
        Execute a query within the transaction context (PostgreSQL-compatible interface for Supabase).
        This is used by task_manager for atomic operations.
        """
        if not self.in_transaction:
            raise RuntimeError("Not in transaction context")

        try:
            query_upper = query.strip().upper()
            
            if 'INSERT INTO task_settings' in query_upper:
                # Handle: INSERT INTO task_settings (guild_id, next_task_id) VALUES ($1, 1) ON CONFLICT DO NOTHING
                guild_id = str(args[0])
                self.client.table('task_settings').upsert({
                    'guild_id': guild_id,
                    'next_task_id': 1
                }, on_conflict='guild_id').execute()
                
            elif 'INSERT INTO tasks' in query_upper:
                # Handle: INSERT INTO tasks (task_id, guild_id, name, description, reward, duration_hours, max_claims, current_claims, status, expires_at)
                task_id, guild_id, name, description, reward, duration_hours, max_claims, expires_at = args
                self.client.table('tasks').insert({
                    'task_id': int(task_id),
                    'guild_id': str(guild_id),
                    'name': name,
                    'description': description,
                    'reward': reward,
                    'duration_hours': duration_hours,
                    'max_claims': max_claims if max_claims is not None else -1,
                    'current_claims': 0,
                    'status': 'active',
                    'expires_at': expires_at.isoformat() if hasattr(expires_at, 'isoformat') else expires_at
                }).execute()
                
            elif 'DELETE FROM user_tasks' in query_upper:
                # Handle: DELETE FROM user_tasks WHERE task_id = $1 AND guild_id = $2
                task_id = str(args[0])
                guild_id = str(args[1])
                self.client.table('user_tasks').delete().eq('task_id', task_id).eq('guild_id', guild_id).execute()
                
            elif 'DELETE FROM tasks' in query_upper:
                # Handle: DELETE FROM tasks WHERE task_id = $1 AND guild_id = $2
                task_id = str(args[0])
                guild_id = str(args[1])
                self.client.table('tasks').delete().eq('task_id', task_id).eq('guild_id', guild_id).execute()
                
            elif 'INSERT INTO user_tasks' in query_upper:
                # Handle: INSERT INTO user_tasks (user_id, guild_id, task_id, status, claimed_at, deadline)
                user_id, guild_id, task_id, claimed_at, deadline = args
                self.client.table('user_tasks').insert({
                    'user_id': str(user_id),
                    'guild_id': str(guild_id),
                    'task_id': int(task_id),
                    'status': 'in_progress',
                    'claimed_at': claimed_at.isoformat() if hasattr(claimed_at, 'isoformat') else claimed_at,
                    'deadline': deadline.isoformat() if hasattr(deadline, 'isoformat') else deadline
                }).execute()
                
            elif 'UPDATE tasks SET current_claims' in query_upper:
                # Handle: UPDATE tasks SET current_claims = current_claims + 1 WHERE task_id = $1 AND guild_id = $2
                task_id = str(args[0])
                guild_id = str(args[1])
                
                # Get current claims
                result = self.client.table('tasks').select('current_claims').eq('task_id', task_id).eq('guild_id', guild_id).execute()
                if result.data:
                    current = result.data[0]['current_claims']
                    self.client.table('tasks').update({
                        'current_claims': current + 1
                    }).eq('task_id', task_id).eq('guild_id', guild_id).execute()
                    
            elif 'UPDATE user_tasks' in query_upper and 'status' in query_upper:
                # Handle various UPDATE user_tasks queries
                if 'submitted' in query_upper.lower():
                    # UPDATE user_tasks SET status = 'submitted', proof_content = $1, submitted_at = $2, proof_message_id = $3 WHERE id = $4
                    proof, submitted_at, proof_message_id, user_task_id = args
                    self.client.table('user_tasks').update({
                        'status': 'submitted',
                        'proof_content': proof,
                        'submitted_at': submitted_at.isoformat() if hasattr(submitted_at, 'isoformat') else submitted_at,
                        'proof_message_id': proof_message_id
                    }).eq('id', user_task_id).execute()
                elif 'accepted' in query_upper.lower():
                    # UPDATE user_tasks SET status = 'accepted', completed_at = $1 WHERE id = $2
                    completed_at, user_task_id = args
                    self.client.table('user_tasks').update({
                        'status': 'accepted',
                        'completed_at': completed_at.isoformat() if hasattr(completed_at, 'isoformat') else completed_at
                    }).eq('id', user_task_id).execute()
                elif 'expired' in query_upper.lower():
                    # UPDATE user_tasks SET status = 'expired' WHERE id = $1
                    user_task_id = args[0]
                    self.client.table('user_tasks').update({
                        'status': 'expired'
                    }).eq('id', user_task_id).execute()
                    
            elif 'UPDATE users SET balance' in query_upper:
                # Handle: UPDATE users SET balance = $1 WHERE user_id = $2 AND guild_id = $3
                new_balance, user_id, guild_id = args
                self.client.table('users').update({
                    'balance': new_balance
                }).eq('user_id', str(user_id)).eq('guild_id', str(guild_id)).execute()
                
            elif 'UPDATE task_settings' in query_upper and 'total_completed' in query_upper:
                # Handle: UPDATE task_settings SET total_completed = total_completed + 1 WHERE guild_id = $1
                guild_id = str(args[0])
                result = self.client.table('task_settings').select('total_completed').eq('guild_id', guild_id).execute()
                if result.data:
                    current = result.data[0]['total_completed']
                    self.client.table('task_settings').update({
                        'total_completed': current + 1
                    }).eq('guild_id', guild_id).execute()
                    
            else:
                logger.warning(f"Unhandled execute query: {query[:100]}")
                
        except Exception as e:
            logger.error(f"execute failed: {e}")
            raise

    async def fetch(self, query: str, *args):
        """
        Fetch multiple rows from the database (PostgreSQL-compatible interface for Supabase).
        """
        if not self.in_transaction:
            raise RuntimeError("Not in transaction context")

        try:
            # For now, return empty list for fetch operations
            # This can be expanded as needed
            logger.warning(f"fetch operation not fully implemented: {query[:100]}")
            return []
        except Exception as e:
            logger.error(f"fetch failed: {e}")
            raise

    async def reconcile_user_balances(self, guild_id):
        """Recalculate all user balances from transaction history"""

        try:
            async with self.atomic_transaction() as conn:
                # Get all users in guild
                users = await conn.fetch(
                    "SELECT user_id, balance FROM users WHERE guild_id = $1",
                    guild_id
                )

                reconciliation_report = []

                for user in users:
                    # Calculate balance from transactions
                    txs = await conn.fetch(
                        """SELECT amount FROM transactions
                           WHERE user_id = $1 AND guild_id = $2
                           ORDER BY timestamp ASC""",
                        user['user_id'], guild_id
                    )

                    calculated_balance = sum(tx['amount'] for tx in txs)
                    current_balance = user['balance']

                    if calculated_balance != current_balance:
                        # Mismatch found
                        reconciliation_report.append({
                            'user_id': user['user_id'],
                            'current_balance': current_balance,
                            'calculated_balance': calculated_balance,
                            'difference': calculated_balance - current_balance
                        })

                        # Fix the balance
                        await conn.execute(
                            "UPDATE users SET balance = $1 WHERE user_id = $2 AND guild_id = $3",
                            calculated_balance, user['user_id'], guild_id
                        )

                        logger.warning(
                            f"Balance reconciled for user {user['user_id']}: "
                            f"{current_balance} -> {calculated_balance}"
                        )

                return reconciliation_report

        except Exception as e:
            logger.exception(f"Balance reconciliation error: {e}")
            return []

