import threading
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Literal
from collections import defaultdict
import discord

logger = logging.getLogger(__name__)

class ShopManager:
    """Centralized shop and inventory management with thread-safe operations"""

    def __init__(self, data_manager, transaction_manager):
        self.data_manager = data_manager
        self.transaction_manager = transaction_manager

        # Thread locks for atomic operations
        self._stock_locks = defaultdict(threading.Lock)  # guild_id -> Lock
        self._purchase_locks = defaultdict(threading.Lock)  # (guild_id, user_id) -> Lock

        # Caching for performance
        self._shop_cache = {}  # cache_key -> {'items': dict, 'timestamp': float}
        self._inventory_cache = {}  # cache_key -> {'inventory': dict, 'timestamp': float}
        self._stats_cache = {}  # cache_key -> {'stats': dict, 'timestamp': float}
        self.CACHE_TTL = 300  # 5 minutes for shop items
        self.STATS_CACHE_TTL = 600  # 10 minutes for statistics

        # Purchase limits
        self.MAX_PURCHASE_QUANTITY = 100

        logger.info("ShopManager initialized")

    def _get_item_emoji(self, item: dict) -> str:
        """Get emoji from item, handling missing emoji field gracefully"""
        emoji = item.get('emoji')
        if emoji:
            return emoji

        # Try to extract emoji from name
        name = item.get('name', '')
        if name and any(ord(c) > 127 for c in name[:5]):  # Check for unicode emoji
            extracted = ''.join(c for c in name[:5] if ord(c) > 127)
            if extracted:
                return extracted

        return '🛍️'  # Default shopping bag emoji

    def get_shop_items(
        self,
        guild_id: int,
        category: str = None,
        active_only: bool = True,
        include_out_of_stock: bool = False
    ) -> dict:
        """
        Get shop items with filtering and caching.
        Returns: {item_id: item_data}
        """
        cache_key = f"{guild_id}_{category}_{active_only}_{include_out_of_stock}"

        # Check cache
        if cache_key in self._shop_cache:
            cached = self._shop_cache[cache_key]
            if time.time() - cached['timestamp'] < self.CACHE_TTL:
                return cached['items'].copy()

        # Load from data
        currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
        shop_items = currency_data.get('shop_items', {})

        # Apply filters
        filtered_items = {}
        for item_id, item in shop_items.items():
            # Category filter
            if category and item.get('category', 'general') != category:
                continue

            # Active filter
            if active_only and not item.get('is_active', True):
                continue

            # Stock filter
            stock = item.get('stock', -1)
            if not include_out_of_stock and stock == 0:
                continue

            filtered_items[item_id] = item.copy()

        # Sort by category, then price
        def sort_key(item):
            return (item.get('category', 'general'), item.get('price', 0))

        sorted_items = dict(sorted(filtered_items.items(), key=lambda x: sort_key(x[1])))

        # Cache result
        self._shop_cache[cache_key] = {
            'items': sorted_items.copy(),
            'timestamp': time.time()
        }

        return sorted_items

    def get_items(self, guild_id: int) -> List[Dict]:
        """
        Get all shop items as a list for the API.
        """
        items_dict = self.get_shop_items(guild_id, active_only=False, include_out_of_stock=True)
        items_list = []
        for item_id, item in items_dict.items():
            item['item_id'] = item_id  # Ensure ID is present
            items_list.append(item)
        
        # Sort by name
        items_list.sort(key=lambda x: x.get('name', ''))
        return items_list

    def get_item(self, guild_id: int, item_id: str) -> Optional[dict]:
        """Get single item details"""
        currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
        shop_items = currency_data.get('shop_items', {})
        return shop_items.get(item_id)

    def create_item(self, guild_id: int, data: dict) -> dict:
        """Wrapper for add_item to handle dictionary input from API"""
        item_id = data.get('item_id')
        if not item_id:
            # Generate ID from name or timestamp
            name = data.get('name', 'item')
            slug = "".join(c for c in name.lower() if c.isalnum() or c in ('-', '_')).strip()
            if not slug:
                slug = 'item'
            timestamp = int(time.time())
            item_id = f"{slug}_{timestamp}"

        # Safe conversions
        try:
            price = int(data.get('price') or 0)
        except (ValueError, TypeError):
            price = 0
            
        try:
            stock = int(data.get('stock') or -1)
        except (ValueError, TypeError):
            stock = -1

        return self.add_item(
            guild_id=guild_id,
            item_id=item_id,
            name=data.get('name'),
            description=data.get('description'),
            price=price,
            category=data.get('category', 'general'),
            stock=stock,
            emoji=data.get('emoji', '🛍️'),
            role_requirement=data.get('role_requirement'),
            metadata=data.get('metadata')
        )

    def add_item(
        self,
        guild_id: int,
        item_id: str,
        name: str,
        description: str,
        price: int,
        category: str = "general",
        stock: int = -1,
        emoji: str = "🛍️",
        role_requirement: str = None,
        metadata: dict = None
    ) -> dict:
        """
        Add new shop item with validation.
        Returns created item data.
        """
        # Validation
        if not item_id or not item_id.replace('_', '').replace('-', '').isalnum():
            raise ValueError("Invalid item_id: must contain only letters, numbers, underscores, and hyphens")

        if price < 0:
            raise ValueError("Price must be non-negative")

        if not name or not name.strip():
            raise ValueError("Name cannot be empty")

        if stock < -1:
            raise ValueError("Stock cannot be less than -1 (unlimited)")

        # Check for duplicate item_id
        currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
        shop_items = currency_data.setdefault('shop_items', {})

        if item_id in shop_items:
            raise ValueError(f"Item with ID '{item_id}' already exists")

        # Create item
        item_data = {
            'name': name.strip(),
            'description': description or '',
            'price': price,
            'category': category,
            'stock': stock,
            'emoji': emoji,
            'role_requirement': role_requirement,
            'is_active': True,
            'created_at': datetime.now().isoformat(),
            'metadata': metadata or {}
        }

        # For role items, store role_id and duration in metadata
        if category == 'role' and metadata:
            if 'role_id' in metadata and 'duration_minutes' in metadata:
                item_data['role_id'] = metadata['role_id']
                item_data['duration_minutes'] = metadata['duration_minutes']

        shop_items[item_id] = item_data

        # Save and trigger events
        success = self.data_manager.save_guild_data(guild_id, 'currency', currency_data)
        if not success:
            raise RuntimeError("Failed to save shop item")

        # Clear caches - both shop manager and data manager
        self._clear_shop_cache(guild_id)
        self.data_manager.invalidate_cache(guild_id, 'currency')

        # Trigger SSE update
        self._broadcast_event('shop_update', {
            'guild_id': guild_id,
            'action': 'item_added',
            'item_id': item_id,
            'item': item_data
        })

        logger.info(f"Added shop item '{item_id}' to guild {guild_id}")
        return item_data.copy()

    def update_item(
        self,
        guild_id: int,
        item_id: str,
        updates: dict
    ) -> dict:
        """Update existing item with validation"""
        currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
        shop_items = currency_data.get('shop_items', {})

        if item_id not in shop_items:
            raise ValueError(f"Item '{item_id}' not found")

        item = shop_items[item_id]

        # Validate updates
        allowed_fields = {
            'name', 'description', 'price', 'stock', 'category',
            'emoji', 'is_active', 'role_requirement'
        }

        for field, value in updates.items():
            if field not in allowed_fields:
                raise ValueError(f"Field '{field}' is not allowed for updates")

            if field == 'price' and (not isinstance(value, int) or value < 0):
                raise ValueError("Price must be a non-negative integer")

            if field == 'stock' and (not isinstance(value, int) or value < -1):
                raise ValueError("Stock must be an integer >= -1")

            if field == 'name' and (not value or not value.strip()):
                raise ValueError("Name cannot be empty")

            # Log price changes in metadata
            if field == 'price' and value != item.get('price'):
                price_history = item.setdefault('metadata', {}).setdefault('price_history', [])
                price_history.append({
                    'old_price': item.get('price'),
                    'new_price': value,
                    'timestamp': datetime.now().isoformat()
                })

            item[field] = value

        # Save and trigger events
        success = self.data_manager.save_guild_data(guild_id, 'currency', currency_data)
        if not success:
            raise RuntimeError("Failed to save item update")

        # Clear caches - both shop manager and data manager
        self._clear_shop_cache(guild_id)
        self.data_manager.invalidate_cache(guild_id, 'currency')

        # Trigger SSE update
        self._broadcast_event('shop_update', {
            'guild_id': guild_id,
            'action': 'item_updated',
            'item_id': item_id,
            'updates': updates
        })

        logger.info(f"Updated shop item '{item_id}' in guild {guild_id}")
        return item.copy()

    def delete_item(
        self,
        guild_id: int,
        item_id: str,
        archive: bool = True
    ) -> bool:
        """Delete shop item, optionally archiving it"""
        currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
        shop_items = currency_data.get('shop_items', {})

        if item_id not in shop_items:
            return False

        item = shop_items[item_id]

        if archive:
            # Move to archived items
            archived = currency_data.setdefault('archived_shop_items', {})
            item_copy = item.copy()
            item_copy['archived_at'] = datetime.now().isoformat()
            archived[item_id] = item_copy

        # Remove from active shop
        del shop_items[item_id]

        # Explicitly delete from database
        db_success = self.data_manager.delete_shop_item(guild_id, item_id)
        if not db_success:
            logger.error(f"Failed to delete shop item {item_id} from database")
            # We continue anyway to update cache and memory

        # Save other changes (like archive)
        success = self.data_manager.save_guild_data(guild_id, 'currency', currency_data)
        if not success:
            raise RuntimeError("Failed to save shop item deletion state")

        # Clear caches - both shop manager and data manager
        self._clear_shop_cache(guild_id)
        self.data_manager.invalidate_cache(guild_id, 'currency')

        # Trigger SSE update
        self._broadcast_event('shop_update', {
            'guild_id': guild_id,
            'action': 'item_deleted',
            'item_id': item_id,
            'archived': archive
        })

        logger.info(f"Deleted shop item '{item_id}' from guild {guild_id}")
        return True

    def purchase_item(
        self,
        guild_id: int,
        user_id: int,
        item_id: str,
        quantity: int = 1,
        interaction: discord.Interaction = None
    ) -> dict:
        """
        Process item purchase with full validation and atomic operations.
        Returns purchase result dict.
        """
        # Input validation
        if quantity < 1:
            return {'success': False, 'error': 'Quantity must be at least 1'}

        if quantity > self.MAX_PURCHASE_QUANTITY:
            return {'success': False, 'error': f'Maximum purchase quantity is {self.MAX_PURCHASE_QUANTITY}'}

        # Acquire purchase lock (prevents concurrent purchases by same user)
        lock_key = (guild_id, user_id)
        with self._purchase_locks[lock_key]:
            try:
                # Load current data
                currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
                shop_items = currency_data.get('shop_items', {})
                inventory = currency_data.setdefault('inventory', {})
                user_inventory = inventory.setdefault(str(user_id), {})
                users = currency_data.setdefault('users', {})
                user_data = users.setdefault(str(user_id), {'balance': 0})

                # Validate item exists and is active
                if item_id not in shop_items:
                    return {'success': False, 'error': 'Item not found'}

                item = shop_items[item_id]
                if not item.get('is_active', True):
                    return {'success': False, 'error': 'Item is not available for purchase'}

                # Check role requirements
                if item.get('role_requirement') and interaction:
                    if not self._check_role_requirement(interaction.guild, user_id, item['role_requirement']):
                        return {'success': False, 'error': f"You need the '{item['role_requirement']}' role to purchase this item"}

                # Check stock availability
                current_stock = item.get('stock', -1)
                if current_stock != -1 and current_stock < quantity:
                    return {'success': False, 'error': f'Insufficient stock. Available: {current_stock}'}

                # Calculate total cost
                total_cost = item['price'] * quantity

                # Check user balance
                current_balance = user_data['balance']
                if current_balance < total_cost:
                    return {'success': False, 'error': f'Insufficient balance. Need {total_cost}, have {current_balance}'}

                # ATOMIC UPDATE PHASE
                # 1. Log transaction via transaction manager (this updates balance atomically)
                transaction_result = self.transaction_manager.log_transaction(
                    guild_id=guild_id,
                    user_id=user_id,
                    amount=-total_cost,  # Negative for deduction
                    balance_before=current_balance,
                    balance_after=current_balance - total_cost,
                    transaction_type='shop',
                    description=f"Purchased {quantity}x {self._get_item_emoji(item)} {item['name']}",
                    metadata={
                        'item_id': item_id,
                        'quantity': quantity,
                        'item_name': item['name'],
                        'item_price': item['price']
                    }
                )

                if not transaction_result:
                    return {'success': False, 'error': 'Failed to process payment'}

                new_balance = current_balance - total_cost

                # 2. Update stock (if limited)
                if current_stock != -1:
                    with self._stock_locks[guild_id]:
                        item['stock'] = current_stock - quantity
                        # Log stock change
                        stock_history = item.setdefault('metadata', {}).setdefault('stock_history', [])
                        stock_history.append({
                            'change': -quantity,
                            'new_stock': item['stock'],
                            'timestamp': datetime.now().isoformat(),
                            'reason': 'purchase'
                        })

                # 3. Add to inventory
                current_quantity = user_inventory.get(item_id, 0)
                user_inventory[item_id] = current_quantity + quantity

                # 4. Update item metadata (sales count)
                sales_count = item.setdefault('metadata', {}).setdefault('sales_count', 0)
                item['metadata']['sales_count'] = sales_count + quantity

                # 5. Save all changes
                success = self.data_manager.save_guild_data(guild_id, 'currency', currency_data)
                if not success:
                    # This should not happen in normal operation, but rollback if it does
                    logger.error(f"Failed to save purchase data for user {user_id} in guild {guild_id}")
                    return {'success': False, 'error': 'Failed to save purchase data'}

                # Clear caches - both shop manager and data manager
                self._clear_shop_cache(guild_id)
                self._clear_inventory_cache(guild_id, user_id)
                self.data_manager.invalidate_cache(guild_id, 'currency')

                # Trigger SSE updates
                self._broadcast_event('shop_update', {
                    'guild_id': guild_id,
                    'action': 'item_purchased',
                    'item_id': item_id,
                    'quantity': quantity,
                    'user_id': user_id
                })

                self._broadcast_event('inventory_update', {
                    'guild_id': guild_id,
                    'user_id': user_id,
                    'action': 'item_added',
                    'item_id': item_id,
                    'quantity': quantity
                })

                # Try to sync Discord message (non-blocking)
                if self.data_manager.bot_instance:
                    try:
                        import asyncio
                        future = asyncio.run_coroutine_threadsafe(
                            self.sync_discord_message(guild_id, item_id, self.data_manager.bot_instance),
                            self.data_manager.bot_instance.loop
                        )
                        future.result(timeout=5)  # Wait up to 5 seconds
                    except Exception as e:
                        logger.warning(f"Failed to sync Discord message for {item_id}: {e}")

                return {
                    'success': True,
                    'item': item.copy(),
                    'quantity': quantity,
                    'total_cost': total_cost,
                    'new_balance': new_balance,
                    'inventory_total': user_inventory[item_id]
                }

            except Exception as e:
                logger.error(f"Purchase failed for user {user_id}, item {item_id}: {e}")
                return {'success': False, 'error': str(e)}

    def check_stock(self, guild_id: int, item_id: str) -> dict:
        """Check item stock status"""
        item = self.get_item(guild_id, item_id)
        if not item:
            return {'available': 0, 'unlimited': False, 'out_of_stock': True}

        stock = item.get('stock', -1)
        return {
            'available': stock if stock != -1 else float('inf'),
            'unlimited': stock == -1,
            'out_of_stock': stock == 0
        }

    def update_stock(
        self,
        guild_id: int,
        item_id: str,
        quantity: int,
        operation: Literal['set', 'add', 'subtract'] = 'set'
    ) -> dict:
        """Update item stock with thread safety"""
        with self._stock_locks[guild_id]:
            currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
            shop_items = currency_data.get('shop_items', {})

            if item_id not in shop_items:
                raise ValueError(f"Item '{item_id}' not found")

            item = shop_items[item_id]
            current_stock = item.get('stock', -1)

            if operation == 'set':
                new_stock = quantity
            elif operation == 'add':
                if current_stock == -1:
                    raise ValueError("Cannot add to unlimited stock")
                new_stock = current_stock + quantity
            elif operation == 'subtract':
                if current_stock == -1:
                    raise ValueError("Cannot subtract from unlimited stock")
                new_stock = max(0, current_stock - quantity)
            else:
                raise ValueError(f"Invalid operation: {operation}")

            # Validate
            if new_stock < -1:
                new_stock = -1

            item['stock'] = new_stock

            # Log stock change
            stock_history = item.setdefault('metadata', {}).setdefault('stock_history', [])
            stock_history.append({
                'change': new_stock - (current_stock if current_stock != -1 else 0),
                'new_stock': new_stock,
                'timestamp': datetime.now().isoformat(),
                'operation': operation,
                'reason': 'admin_update'
            })

            # Save
            success = self.data_manager.save_guild_data(guild_id, 'currency', currency_data)
            if not success:
                raise RuntimeError("Failed to update stock")

            # Clear caches - both shop manager and data manager
            self._clear_shop_cache(guild_id)
            self.data_manager.invalidate_cache(guild_id, 'currency')

            # Trigger SSE update
            self._broadcast_event('shop_update', {
                'guild_id': guild_id,
                'action': 'stock_updated',
                'item_id': item_id,
                'old_stock': current_stock,
                'new_stock': new_stock
            })

            # Sync Discord message
            if self.data_manager.bot_instance:
                try:
                    import asyncio
                    future = asyncio.run_coroutine_threadsafe(
                        self.sync_discord_message(guild_id, item_id, self.data_manager.bot_instance),
                        self.data_manager.bot_instance.loop
                    )
                    future.result(timeout=5)
                except Exception as e:
                    logger.warning(f"Failed to sync Discord message for {item_id}: {e}")

            return {
                'item_id': item_id,
                'old_stock': current_stock,
                'new_stock': new_stock,
                'operation': operation
            }

    def get_inventory(
        self,
        guild_id: int,
        user_id: int,
        include_item_details: bool = True
    ) -> dict:
        """Get user inventory with optional item details"""
        cache_key = f"{guild_id}_{user_id}_{include_item_details}"

        # Check cache
        if cache_key in self._inventory_cache:
            cached = self._inventory_cache[cache_key]
            if time.time() - cached['timestamp'] < self.CACHE_TTL:
                return cached['inventory'].copy()

        currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
        inventory = currency_data.get('inventory', {})
        user_inventory = inventory.get(str(user_id), {})

        # Filter out zero quantities (handle both dict format from DB and int format from memory operations)
        filtered_inventory = {}
        for k, v in user_inventory.items():
            if isinstance(v, dict):
                # Handle database format where v might be a dict with quantity
                quantity = v.get('quantity', 0)
            elif isinstance(v, int):
                # Handle in-memory format where v is directly the quantity
                quantity = v
            else:
                # Fallback to 0 for unknown formats
                quantity = 0

            if quantity > 0:
                filtered_inventory[k] = quantity

        if not include_item_details:
            result = filtered_inventory
        else:
            # Add item details
            shop_items = currency_data.get('shop_items', {})
            archived_items = currency_data.get('archived_shop_items', {})

            result = {}
            for item_id, quantity in filtered_inventory.items():
                item_details = shop_items.get(item_id) or archived_items.get(item_id)
                if item_details:
                    result[item_id] = {
                        'quantity': quantity,
                        'item': item_details.copy()
                    }

            # Sort by category, then name
            def sort_key(item_data):
                item = item_data[1]['item']
                return (item.get('category', 'general'), item.get('name', ''))

            result = dict(sorted(result.items(), key=sort_key))

        # Cache result
        self._inventory_cache[cache_key] = {
            'inventory': result.copy(),
            'timestamp': time.time()
        }

        return result

    def add_to_inventory(
        self,
        guild_id: int,
        user_id: int,
        item_id: str,
        quantity: int = 1
    ):
        """Add items to user inventory (internal use)"""
        currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
        inventory = currency_data.setdefault('inventory', {})
        user_inventory = inventory.setdefault(str(user_id), {})

        current_quantity = user_inventory.get(item_id, 0)
        user_inventory[item_id] = current_quantity + quantity

        # Track acquisition history
        shop_items = currency_data.get('shop_items', {})
        if item_id in shop_items:
            item = shop_items[item_id]
            history = item.setdefault('metadata', {}).setdefault('acquisition_history', [])
            history.append({
                'user_id': user_id,
                'quantity': quantity,
                'timestamp': datetime.now().isoformat()
            })

        success = self.data_manager.save_guild_data(guild_id, 'currency', currency_data)
        if success:
            self._clear_inventory_cache(guild_id, user_id)
            self.data_manager.invalidate_cache(guild_id, 'currency')
            self._broadcast_event('inventory_update', {
                'guild_id': guild_id,
                'user_id': user_id,
                'action': 'item_added',
                'item_id': item_id,
                'quantity': quantity
            })

    def remove_from_inventory(
        self,
        guild_id: int,
        user_id: int,
        item_id: str,
        quantity: int = 1
    ) -> bool:
        """Remove items from inventory"""
        currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
        inventory = currency_data.get('inventory', {})
        user_inventory = inventory.get(str(user_id), {})

        current_quantity = user_inventory.get(item_id, 0)
        if current_quantity < quantity:
            return False

        new_quantity = current_quantity - quantity
        if new_quantity <= 0:
            user_inventory.pop(item_id, None)
        else:
            user_inventory[item_id] = new_quantity

        success = self.data_manager.save_guild_data(guild_id, 'currency', currency_data)
        if success:
            self._clear_inventory_cache(guild_id, user_id)
            self.data_manager.invalidate_cache(guild_id, 'currency')
            self._broadcast_event('inventory_update', {
                'guild_id': guild_id,
                'user_id': user_id,
                'action': 'item_removed',
                'item_id': item_id,
                'quantity': quantity
            })

        return success

    async def redeem_item(
        self,
        guild_id: int,
        user_id: int,
        item_id: str,
        quantity: int = 1,
        interaction = None
    ) -> dict:
        """Redeem shop item from inventory"""
        # Check if item exists
        item = self.get_item(guild_id, item_id)
        if not item:
            return {'success': False, 'error': 'Item not found'}

        category = item.get('category', 'misc')
        if category not in ['role', 'misc', 'general', 'other']:
            return {'success': False, 'error': 'Item is not redeemable'}

        # Check inventory
        inventory = self.get_inventory(guild_id, user_id, include_item_details=False)
        current_quantity = inventory.get(item_id, 0)
        
        # Handle case where inventory might be a dict with 'quantity' key
        if isinstance(current_quantity, dict):
            current_quantity = current_quantity.get('quantity', 0)

        if current_quantity < quantity:
            return {'success': False, 'error': f'Insufficient quantity. Have {current_quantity}, need {quantity}'}

        # Handle different categories
        try:
            if category == 'role':
                result = await self._redeem_role_item(guild_id, user_id, item, quantity, interaction)
            elif category in ['misc', 'general', 'other']:
                result = await self._redeem_misc_item(guild_id, user_id, item, quantity, interaction)
            else:
                result = {'success': False, 'error': f'Unknown category: {category}'}

            if result['success']:
                # Remove from inventory only after successful redemption
                success = self.remove_from_inventory(guild_id, user_id, item_id, quantity)
                if not success:
                    # This should not happen, but handle rollback if possible
                    logger.error(f"Failed to remove item from inventory after successful redemption: user {user_id}, item {item_id}")
                    return {'success': False, 'error': 'Redemption succeeded but inventory update failed'}

                # Log redemption
                currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
                redemption_log = currency_data.setdefault('item_redemption_log', [])
                redemption_log.append({
                    'user_id': user_id,
                    'item_id': item_id,
                    'quantity': quantity,
                    'category': category,
                    'timestamp': datetime.now().isoformat()
                })
                self.data_manager.save_guild_data(guild_id, 'currency', currency_data)

                self._broadcast_event('item_redeemed', {
                    'guild_id': guild_id,
                    'user_id': user_id,
                    'item_id': item_id,
                    'quantity': quantity,
                    'category': category
                })

                return result

            return result

        except Exception as e:
            logger.error(f"Error redeeming item {item_id} for user {user_id}: {e}")
            return {'success': False, 'error': str(e)}

    async def _redeem_role_item(self, guild_id: int, user_id: int, item: dict, quantity: int, interaction) -> dict:
        """Redeem role item - assign role for duration"""
        if not interaction:
            return {'success': False, 'error': 'Interaction required for role assignment'}

        role_id = item.get('role_id')
        duration_minutes = item.get('duration_minutes', 60)

        if not role_id:
            return {'success': False, 'error': 'Role ID not configured for this item'}

        # Get the role
        role = interaction.guild.get_role(int(role_id))
        if not role:
            return {'success': False, 'error': 'Configured role not found in server'}

        # Check bot permissions
        if not interaction.guild.me.guild_permissions.manage_roles:
            return {'success': False, 'error': 'Bot lacks permission to manage roles'}

        # Check role hierarchy
        if interaction.guild.me.top_role.position <= role.position:
            return {'success': False, 'error': 'Bot cannot assign this role (role is too high)'}

        # Add role to user
        member = interaction.guild.get_member(user_id)
        if not member:
            return {'success': False, 'error': 'User not found in server'}

        try:
            await member.add_roles(role, reason=f"Item redemption: {item['name']}")
        except discord.Forbidden:
            return {'success': False, 'error': 'Bot cannot assign this role'}
        except Exception as e:
            return {'success': False, 'error': f'Failed to assign role: {str(e)}'}

        # Schedule role removal using scheduled_jobs table
        from datetime import timedelta
        execute_at = datetime.now() + timedelta(minutes=duration_minutes)

        job_data = {
            'user_id': user_id,
            'role_id': role_id,
            'item_name': item['name'],
            'reason': 'item_redemption_expiry'
        }

        try:
            # Insert scheduled job for role removal
            import uuid
            job_id = f"role_remove_{uuid.uuid4()}"
            scheduled_job = {
                'job_id': job_id,
                'guild_id': guild_id,
                'user_id': user_id,
                'job_type': 'remove_role',
                'execute_at': execute_at,
                'job_data': job_data,
                'is_executed': False
            }

            # Insert into scheduled_jobs table
            self.data_manager.supabase.table('scheduled_jobs').insert(scheduled_job).execute()

        except Exception as e:
            logger.warning(f"Failed to schedule role removal job: {e}")
            # Don't fail the redemption if job scheduling fails, just log it

        # Send log message
        config = self.data_manager.load_guild_data(guild_id, 'config')
        log_channel_id = config.get('log_channel_id')
        if log_channel_id:
            log_channel = interaction.guild.get_channel(int(log_channel_id))
            if log_channel and log_channel.permissions_for(interaction.guild.me).send_messages:
                try:
                    embed = discord.Embed(
                        title="🎭 Role Redeemed",
                        description=f"User **{member.display_name}** redeemed **{item['name']}**",
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="Role Assigned", value=role.mention, inline=True)
                    embed.add_field(name="Duration", value=f"{duration_minutes} minutes", inline=True)
                    embed.set_footer(text=f"User ID: {user_id}")
                    await log_channel.send(embed=embed)
                except Exception as e:
                    logger.warning(f"Failed to send role redemption log: {e}")

        return {
            'success': True,
            'effect': 'role_assigned',
            'role_name': role.name,
            'duration_minutes': duration_minutes
        }

    async def _redeem_misc_item(self, guild_id: int, user_id: int, item: dict, quantity: int, interaction) -> dict:
        """Redeem misc item - send log message with approval buttons"""
        if not interaction:
            return {'success': False, 'error': 'Interaction required for log message'}

        # Get user
        member = interaction.guild.get_member(user_id)
        username = member.display_name if member else f"User {user_id}"

        # Get log channel from config
        config = self.data_manager.load_guild_data(guild_id, 'config')
        log_channel_id = config.get('log_channel_id')

        if not log_channel_id:
            return {'success': False, 'error': 'Log channel not configured'}

        log_channel = interaction.guild.get_channel(int(log_channel_id))
        if not log_channel:
            return {'success': False, 'error': 'Log channel not found'}

        # Check permissions
        if not log_channel.permissions_for(interaction.guild.me).send_messages:
            return {'success': False, 'error': 'Bot cannot send messages to log channel'}

        try:
            embed = discord.Embed(
                title="🎁 Redemption Request",
                description=f"User **{username}** wants to redeem **{item['name']}**",
                color=discord.Color.gold(),
                timestamp=datetime.now()
            )
            embed.add_field(name="Item ID", value=f"`{item.get('item_id', 'unknown')}`", inline=True)
            embed.add_field(name="Category", value=item.get('category', 'Misc').title(), inline=True)
            embed.add_field(name="Quantity", value=quantity, inline=True)
            embed.add_field(name="Status", value="⏳ Pending Approval", inline=False)
            
            embed.set_footer(text=f"User ID: {user_id}")

            # Create view for approval
            view = RedemptionRequestView(self, guild_id, user_id, item, quantity)
            
            await log_channel.send(embed=embed, view=view)

        except Exception as e:
            logger.error(f"Failed to send redemption log: {e}")
            return {'success': False, 'error': f'Failed to send log message: {str(e)}'}

        return {
            'success': True,
            'effect': 'log_message_sent',
            'log_channel': log_channel.name
        }

    def get_shop_statistics(self, guild_id: int, period: str = 'all') -> dict:
        """Get comprehensive shop statistics"""
        cache_key = f"{guild_id}_{period}"

        # Check cache
        if cache_key in self._stats_cache:
            cached = self._stats_cache[cache_key]
            if time.time() - cached['timestamp'] < self.STATS_CACHE_TTL:
                return cached['stats'].copy()

        # Calculate statistics
        transactions = self.transaction_manager.get_transactions(guild_id, transaction_type='shop')['transactions']

        # Filter by period
        now = datetime.now()
        if period == 'day':
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'week':
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
        elif period == 'month':
            cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            cutoff = None

        if cutoff:
            transactions = [t for t in transactions if datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00')) >= cutoff]

        # Calculate stats
        stats = {
            'total_sales': len(transactions),
            'total_revenue': sum(abs(t['amount']) for t in transactions),
            'unique_buyers': len(set(t['user_id'] for t in transactions)),
            'popular_items': {},
            'category_breakdown': {},
            'stock_value': 0
        }

        # Item popularity and category breakdown
        currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
        shop_items = currency_data.get('shop_items', {})

        for item_id, item in shop_items.items():
            sales_count = item.get('metadata', {}).get('sales_count', 0)
            if sales_count > 0:
                revenue = sales_count * item['price']
                stats['popular_items'][item_id] = {
                    'name': item['name'],
                    'emoji': self._get_item_emoji(item),
                    'sales': sales_count,
                    'revenue': revenue
                }

            # Category breakdown
            category = item.get('category', 'general')
            if category not in stats['category_breakdown']:
                stats['category_breakdown'][category] = {'sales': 0, 'revenue': 0, 'items': 0}
            stats['category_breakdown'][category]['items'] += 1

            # Stock value
            stock = item.get('stock', -1)
            if stock > 0:
                stats['stock_value'] += stock * item['price']

        # Sort popular items
        stats['popular_items'] = dict(sorted(
            stats['popular_items'].items(),
            key=lambda x: x[1]['sales'],
            reverse=True
        )[:10])  # Top 10

        # Cache result
        self._stats_cache[cache_key] = {
            'stats': stats.copy(),
            'timestamp': time.time()
        }

        return stats

    async def sync_discord_message(
        self,
        guild_id: int,
        item_id: str,
        bot_instance
    ):
        """Create or update Discord embed for shop item"""
        try:
            config = self.data_manager.load_guild_data(guild_id, 'config')
            shop_channel_id = config.get('shop_channel_id')

            if not shop_channel_id:
                return

            guild = bot_instance.get_guild(guild_id)
            if not guild:
                return

            channel = guild.get_channel(int(shop_channel_id))
            if not channel:
                return

            item = self.get_item(guild_id, item_id)
            if not item:
                return

            # Create embed
            embed = discord.Embed(
                title=f"{self._get_item_emoji(item)} {item['name']}",
                description=item.get('description', 'No description'),
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Price",
                value=f"{item['price']} {config.get('currency_symbol', '💰')}",
                inline=True
            )

            stock = item.get('stock', -1)
            stock_text = "♾️ Unlimited" if stock == -1 else f"{stock} in stock"
            embed.add_field(name="Stock", value=stock_text, inline=True)

            embed.add_field(
                name="Category",
                value=item.get('category', 'general').title(),
                inline=True
            )

            if item.get('role_requirement'):
                embed.add_field(
                    name="Required Role",
                    value=f"@{item['role_requirement']}",
                    inline=True
                )

            embed.set_footer(text=f"Item ID: {item_id}")

            # Create view with purchase button
            view = ShopItemView(self, item_id)

            # Check if message exists
            message_id = item.get('message_id')
            if message_id:
                try:
                    message = await channel.fetch_message(int(message_id))
                    await message.edit(embed=embed, view=view)
                except discord.NotFound:
                    # Message deleted, create new one
                    message = await channel.send(embed=embed, view=view)
                    item['message_id'] = str(message.id)
                    item['channel_id'] = str(channel.id)
                    # Save updated message_id
                    currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
                    currency_data['shop_items'][item_id] = item
                    self.data_manager.save_guild_data(guild_id, 'currency', currency_data)
            else:
                # Create new message
                message = await channel.send(embed=embed, view=view)
                item['message_id'] = str(message.id)
                item['channel_id'] = str(channel.id)
                # Save message_id
                currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
                currency_data['shop_items'][item_id] = item
                self.data_manager.save_guild_data(guild_id, 'currency', currency_data)

        except Exception as e:
            logger.error(f"Failed to sync Discord message for item {item_id}: {e}")

    def export_inventory(
        self,
        guild_id: int,
        user_id: int = None,
        format: str = 'json'
    ) -> str:
        """Export inventory data"""
        import json
        import csv
        from io import StringIO

        if user_id:
            # Single user inventory
            inventory = self.get_inventory(guild_id, user_id, include_item_details=True)
            data = {
                'user_id': user_id,
                'exported_at': datetime.now().isoformat(),
                'inventory': inventory
            }
        else:
            # All users inventory
            currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
            all_inventory = currency_data.get('inventory', {})
            data = {
                'guild_id': guild_id,
                'exported_at': datetime.now().isoformat(),
                'inventories': all_inventory
            }

        if format == 'json':
            return json.dumps(data, indent=2, ensure_ascii=False)
        elif format == 'csv':
            output = StringIO()
            writer = csv.writer(output)

            if user_id:
                writer.writerow(['Item ID', 'Name', 'Emoji', 'Category', 'Quantity', 'Value'])
                for item_id, item_data in data['inventory'].items():
                    item = item_data['item']
                    writer.writerow([
                        item_id,
                        item['name'],
                        self._get_item_emoji(item),
                        item.get('category', 'general'),
                        item_data['quantity'],
                        item_data['quantity'] * item['price']
                    ])
            else:
                writer.writerow(['User ID', 'Item ID', 'Name', 'Emoji', 'Quantity'])
                for user_id, user_inv in data['inventories'].items():
                    for item_id, quantity in user_inv.items():
                        item = self.get_item(guild_id, item_id)
                        if item:
                            writer.writerow([
                                user_id,
                                item_id,
                                item['name'],
                                self._get_item_emoji(item),
                                quantity
                            ])

            return output.getvalue()
        else:
            return "Unsupported format"

    def validate_shop_integrity(self, guild_id: int) -> dict:
        """Validate shop data integrity"""
        issues = []
        fixes_available = []

        currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
        shop_items = currency_data.get('shop_items', {})
        inventory = currency_data.get('inventory', {})
        archived_items = currency_data.get('archived_shop_items', {})

        # Check for orphaned inventory items
        all_inventory_items = set()
        for user_inv in inventory.values():
            all_inventory_items.update(user_inv.keys())

        active_item_ids = set(shop_items.keys())
        archived_item_ids = set(archived_items.keys())

        orphaned_items = all_inventory_items - (active_item_ids | archived_item_ids)
        if orphaned_items:
            issues.append(f"Found {len(orphaned_items)} orphaned inventory items: {', '.join(orphaned_items)}")
            fixes_available.append("Move orphaned items to archived items")

        # Check for invalid stock values
        invalid_stock = []
        for item_id, item in shop_items.items():
            stock = item.get('stock', -1)
            if stock < -1:
                invalid_stock.append(item_id)

        if invalid_stock:
            issues.append(f"Found {len(invalid_stock)} items with invalid stock values: {', '.join(invalid_stock)}")
            fixes_available.append("Set invalid stock values to -1 (unlimited)")

        # Check for missing Discord messages
        config = self.data_manager.load_guild_data(guild_id, 'config')
        shop_channel_id = config.get('shop_channel_id')

        if shop_channel_id:
            missing_messages = []
            for item_id, item in shop_items.items():
                if item.get('is_active', True) and not item.get('message_id'):
                    missing_messages.append(item_id)

            if missing_messages:
                issues.append(f"Found {len(missing_messages)} active items without Discord messages: {', '.join(missing_messages)}")
                fixes_available.append("Create missing Discord messages")

        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'fixes_available': fixes_available
        }

    def _check_role_requirement(self, guild, user_id: int, role_name: str) -> bool:
        """Check if user has required role"""
        if not guild:
            return False

        member = guild.get_member(user_id)
        if not member:
            return False

        return any(role.name == role_name for role in member.roles)

    def _clear_shop_cache(self, guild_id: int = None):
        """Clear shop-related caches"""
        if guild_id:
            keys_to_remove = [k for k in self._shop_cache.keys() if k.startswith(str(guild_id))]
            for key in keys_to_remove:
                self._shop_cache.pop(key, None)
        else:
            self._shop_cache.clear()

    def _clear_inventory_cache(self, guild_id: int, user_id: int = None):
        """Clear inventory-related caches"""
        if user_id:
            keys_to_remove = [k for k in self._inventory_cache.keys()
                            if k.startswith(f"{guild_id}_{user_id}")]
            for key in keys_to_remove:
                self._inventory_cache.pop(key, None)
        else:
            keys_to_remove = [k for k in self._inventory_cache.keys()
                            if k.startswith(str(guild_id))]
            for key in keys_to_remove:
                self._inventory_cache.pop(key, None)

    def _validate_item_active(self, item):
        """Check item exists and is_active = true"""
        return item and item.get('is_active', True)

    def _check_stock_available(self, item, quantity):
        """Verify sufficient stock for purchase"""
        stock = item.get('stock', -1)
        if stock == -1:  # Unlimited
            return True
        return stock >= quantity

    def _calculate_total_cost(self, item, quantity):
        """Return price * quantity"""
        return item['price'] * quantity

    def _update_item_stock(self, guild_id, item_id, quantity_change):
        """Atomic stock update"""
        with self._stock_locks[guild_id]:
            currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
            shop_items = currency_data.get('shop_items', {})

            if item_id not in shop_items:
                raise ValueError(f"Item '{item_id}' not found")

            item = shop_items[item_id]
            current_stock = item.get('stock', -1)

            if current_stock == -1:
                raise ValueError("Cannot update stock for unlimited item")

            new_stock = current_stock + quantity_change
            if new_stock < 0:
                raise ValueError("Insufficient stock")

            item['stock'] = new_stock

            # Log stock change
            stock_history = item.setdefault('metadata', {}).setdefault('stock_history', [])
            stock_history.append({
                'change': quantity_change,
                'new_stock': new_stock,
                'timestamp': datetime.now().isoformat(),
                'reason': 'stock_update'
            })

            success = self.data_manager.save_guild_data(guild_id, 'currency', currency_data)
            if not success:
                raise RuntimeError("Failed to update stock")

            # Clear cache
            self._clear_shop_cache(guild_id)

            return new_stock

    def _broadcast_event(self, event_type: str, data: dict):
        """Broadcast event to listeners"""
        try:
            if hasattr(self.data_manager, 'broadcast_event'):
                self.data_manager.broadcast_event(event_type, data)
            else:
                # Fallback to notify_listeners if broadcast_event doesn't exist
                self.data_manager._notify_listeners(event_type, data)
        except Exception as e:
            logger.warning(f"Failed to broadcast event {event_type}: {e}")


class RedemptionRequestView(discord.ui.View):
    """View for handling redemption requests in log channel"""

    def __init__(self, shop_manager, guild_id: int, user_id: int, item: dict, quantity: int):
        super().__init__(timeout=None)
        self.shop_manager = shop_manager
        self.guild_id = guild_id
        self.user_id = user_id
        self.item = item
        self.quantity = quantity

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Accept redemption request"""
        # Check permissions (only mods/admins)
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You do not have permission to accept this request.", ephemeral=True)
            return

        # Disable buttons
        for child in self.children:
            child.disabled = True
        
        # Update embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        
        # Update Status field
        for i, field in enumerate(embed.fields):
            if field.name == "Status":
                embed.set_field_at(i, name="Status", value=f"✅ Accepted by {interaction.user.mention}", inline=False)
                break
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Notify user
        try:
            user = await interaction.guild.fetch_member(self.user_id)
            if user:
                await user.send(f"✅ Your redemption request for **{self.quantity}x {self.item['name']}** has been accepted!")
        except Exception as e:
            logger.warning(f"Failed to DM user {self.user_id} about acceptance: {e}")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌")
    async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Deny redemption request and refund item"""
        # Check permissions
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You do not have permission to deny this request.", ephemeral=True)
            return

        # Refund item
        self.shop_manager.add_to_inventory(self.guild_id, self.user_id, self.item['item_id'], self.quantity)
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
            
        # Update embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        
        # Update Status field
        for i, field in enumerate(embed.fields):
            if field.name == "Status":
                embed.set_field_at(i, name="Status", value=f"❌ Denied by {interaction.user.mention} (Refunded)", inline=False)
                break
                
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Notify user
        try:
            user = await interaction.guild.fetch_member(self.user_id)
            if user:
                await user.send(f"❌ Your redemption request for **{self.quantity}x {self.item['name']}** has been denied and the items have been refunded.")
        except Exception as e:
            logger.warning(f"Failed to DM user {self.user_id} about denial: {e}")


class ShopItemView(discord.ui.View):
    """Persistent view for individual shop item messages"""

    def __init__(self, shop_manager, item_id: str):
        super().__init__(timeout=None)
        self.shop_manager = shop_manager
        self.item_id = item_id

        # Set custom_id for persistence
        self.purchase_button.custom_id = f"shop_buy_{item_id}"

    @discord.ui.button(
        label="Purchase",
        style=discord.ButtonStyle.success,
        emoji="🛒"
    )
    async def purchase_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        """Handle purchase button click"""
        # This will be handled by the bot's button interaction handler
        # For now, just acknowledge
        await interaction.response.defer()
