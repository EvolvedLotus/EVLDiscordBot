"""
Production-ready Discord bot currency system with comprehensive security and features.
"""

import json
import os
import tempfile
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Dict, Any, Optional, List
from collections import defaultdict
import asyncio

# Handle platform-specific file locking
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

# Configuration
DATA_FILE = "data/user_data.json"
TRANSACTION_LOG = "data/transactions.json"
BACKUP_DIR = "backups"
ADMIN_LOG_CHANNEL_ID = None  # Set this to your admin log channel ID

# Global variables for rate limiting
command_cooldowns = defaultdict(dict)

# Setup logging
logger = logging.getLogger(__name__)

@contextmanager
def locked_json_file(filepath, mode='r'):
    """Thread-safe JSON file access with file locking"""
    with open(filepath, mode) as f:
        if HAS_FCNTL:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    yield f
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                # File locking not supported on this platform, proceed without locking
                yield f
        else:
            # On Windows, we don't have fcntl, so just yield the file
            yield f

def atomic_write_json(filepath, data):
    """Write JSON atomically to prevent corruption"""
    # Create temp file in same directory to ensure atomic rename works
    dir_path = os.path.dirname(filepath)
    os.makedirs(dir_path, exist_ok=True)

    temp_fd, temp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
    try:
        with os.fdopen(temp_fd, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, filepath)  # Atomic on POSIX, as close as we get on Windows
    except:
        # Clean up temp file if something went wrong
        try:
            os.unlink(temp_path)
        except:
            pass
        raise

def load_data() -> Dict[str, Any]:
    """Load data with error handling and validation"""
    if not os.path.exists(DATA_FILE):
        logger.info("Data file doesn't exist, initializing new structure")
        return initialize_data_structure()

    try:
        with locked_json_file(DATA_FILE, 'r') as f:
            data = json.load(f)

        # Validate data structure
        if not validate_data_structure(data):
            logger.warning("Data structure invalid, attempting repair")
            data = repair_data_structure(data)

        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Error loading data file: {e}")
        # Try to load from latest backup
        backup_data = load_latest_backup()
        if backup_data:
            logger.info("Loaded data from backup")
            return backup_data
        else:
            logger.error("Could not load data from backup, initializing new structure")
            return initialize_data_structure()

def save_data(data: Dict[str, Any], create_backup_flag: bool = True):
    """Save data atomically with validation"""
    # Validate before saving
    if not validate_data_structure(data):
        raise ValueError("Invalid data structure, refusing to save")

    # Create backup before saving (only if flag is set)
    if create_backup_flag:
        create_backup_internal()

    atomic_write_json(DATA_FILE, data)

def validate_data_structure(data: Dict[str, Any]) -> bool:
    """Validate the data structure"""
    required_keys = ['users', 'inventory', 'shop_items', 'metadata']

    if not all(key in data for key in required_keys):
        return False

    # Validate metadata
    metadata = data.get('metadata', {})
    if not isinstance(metadata, dict):
        return False

    # Validate users structure
    users = data.get('users', {})
    if not isinstance(users, dict):
        return False

    # Validate inventory structure
    inventory = data.get('inventory', {})
    if not isinstance(inventory, dict):
        return False

    # Validate shop_items structure
    shop_items = data.get('shop_items', {})
    if not isinstance(shop_items, dict):
        return False

    return True

def repair_data_structure(data: Dict[str, Any]) -> Dict[str, Any]:
    """Attempt to repair corrupted data structure"""
    logger.info("Attempting to repair data structure")

    # Start with a fresh structure
    repaired = initialize_data_structure()

    # Try to salvage what we can
    if 'users' in data and isinstance(data['users'], dict):
        repaired['users'] = data['users']

    if 'inventory' in data and isinstance(data['inventory'], dict):
        repaired['inventory'] = data['inventory']

    if 'shop_items' in data and isinstance(data['shop_items'], dict):
        repaired['shop_items'] = data['shop_items']

    # Update metadata
    repaired['metadata']['last_backup'] = datetime.now().isoformat()

    return repaired

def initialize_data_structure() -> Dict[str, Any]:
    """Initialize a new data structure"""
    return {
        "users": {},
        "inventory": {},
        "shop_items": {
            "cookie": {
                "name": "🍪 Cookie",
                "description": "A delicious cookie",
                "price": 100,
                "category": "consumable",
                "stock": -1,
                "is_active": True
            },
            "role_color": {
                "name": "🎨 Custom Role Color",
                "description": "Change your role color",
                "price": 500,
                "category": "cosmetic",
                "stock": -1,
                "is_active": True
            }
        },
        "metadata": {
            "version": "2.0",
            "last_backup": datetime.now().isoformat(),
            "total_currency_in_circulation": 0
        }
    }

def load_latest_backup() -> Optional[Dict[str, Any]]:
    """Load the most recent backup"""
    if not os.path.exists(BACKUP_DIR):
        return None

    backup_files = [f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_') and f.endswith('.json')]
    if not backup_files:
        return None

    # Sort by timestamp (newest first)
    backup_files.sort(reverse=True)
    latest_backup = os.path.join(BACKUP_DIR, backup_files[0])

    try:
        with open(latest_backup, 'r') as f:
            return json.load(f)
    except:
        return None

def create_backup_internal():
    """Create timestamped backup (internal function to avoid recursion)"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.json")

    try:
        # Load data directly without validation to avoid recursion
        with locked_json_file(DATA_FILE, 'r') as f:
            data = json.load(f)

        with open(backup_file, 'w') as f:
            json.dump(data, f, indent=2)

        # Keep only last 7 days of backups
        cleanup_old_backups()

        # Update metadata without creating another backup
        data['metadata']['last_backup'] = datetime.now().isoformat()
        atomic_write_json(DATA_FILE, data)

        logger.info(f"Backup created: {backup_file}")
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")

def create_backup():
    """Create timestamped backup (public function)"""
    create_backup_internal()

def cleanup_old_backups():
    """Remove backups older than 7 days"""
    if not os.path.exists(BACKUP_DIR):
        return

    cutoff_date = datetime.now() - timedelta(days=7)

    for filename in os.listdir(BACKUP_DIR):
        if not filename.startswith('backup_') or not filename.endswith('.json'):
            continue

        try:
            # Extract timestamp from filename
            timestamp_str = filename.replace('backup_', '').replace('.json', '')
            file_date = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

            if file_date < cutoff_date:
                os.remove(os.path.join(BACKUP_DIR, filename))
                logger.info(f"Removed old backup: {filename}")
        except:
            continue

# Input validation functions
def validate_amount(amount) -> int:
    """Validate monetary amounts"""
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        raise ValueError("Amount must be a valid integer")

    if amount < 0:
        raise ValueError("Amount cannot be negative")
    if amount > 1_000_000_000:  # 1 billion cap
        raise ValueError("Amount exceeds maximum limit")

    return amount

def validate_user_id(user_id: str) -> str:
    """Validate Discord user IDs"""
    if not user_id.isdigit() or len(user_id) < 17 or len(user_id) > 19:
        raise ValueError("Invalid user ID format")
    return user_id

def validate_item_id(item_id: str) -> str:
    """Validate item IDs"""
    if not item_id or not isinstance(item_id, str):
        raise ValueError("Invalid item ID")
    if len(item_id) > 50:  # Reasonable length limit
        raise ValueError("Item ID too long")
    return item_id

# Rate limiting
def check_cooldown(user_id: str, command: str, cooldown_seconds: int) -> bool:
    """Prevent command spam"""
    now = datetime.now()
    last_used = command_cooldowns[user_id].get(command)

    if last_used and (now - last_used).total_seconds() < cooldown_seconds:
        return False

    command_cooldowns[user_id][command] = now
    return True

# User management
def initialize_user(user_id: str):
    """Create new user with default values"""
    validate_user_id(user_id)

    data = load_data()
    if user_id in data['users']:
        return  # User already exists

    data['users'][user_id] = {
        "balance": 0,
        "total_earned": 0,
        "total_spent": 0,
        "last_daily": None,
        "created_at": datetime.now().isoformat(),
        "stats": {
            "purchases": 0,
            "trades_completed": 0,
            "daily_streak": 0
        }
    }
    data['inventory'][user_id] = {}
    save_data(data)

def get_balance(user_id: str) -> int:
    """Get user balance safely"""
    validate_user_id(user_id)

    data = load_data()
    return data['users'].get(user_id, {}).get('balance', 0)

def add_balance(user_id: str, amount: int, reason: str = "", skip_transaction: bool = False):
    """Add money to balance"""
    validate_user_id(user_id)
    amount = validate_amount(amount)

    data = load_data()
    if user_id not in data['users']:
        initialize_user(user_id)
        data = load_data()  # Reload after initialization

    old_balance = data['users'][user_id]['balance']
    new_balance = old_balance + amount

    data['users'][user_id]['balance'] = new_balance
    data['users'][user_id]['total_earned'] += amount

    # Update total currency in circulation
    data['metadata']['total_currency_in_circulation'] += amount

    save_data(data)

    if not skip_transaction:
        log_transaction(user_id, amount, old_balance, new_balance, reason)

def deduct_balance(user_id: str, amount: int, reason: str = "") -> bool:
    """Safely deduct balance with validation"""
    validate_user_id(user_id)
    amount = validate_amount(amount)

    if amount < 0:
        raise ValueError("Cannot deduct negative amount")

    data = load_data()
    if user_id not in data['users']:
        return False

    current_balance = data['users'][user_id]['balance']

    if current_balance < amount:
        return False  # Insufficient funds

    new_balance = current_balance - amount
    data['users'][user_id]['balance'] = new_balance
    data['users'][user_id]['total_spent'] += amount

    # Update total currency in circulation
    data['metadata']['total_currency_in_circulation'] -= amount

    save_data(data)

    log_transaction(user_id, -amount, current_balance, new_balance, reason)
    return True

# Transaction logging
def log_transaction(user_id: str, amount: int, balance_before: int,
                   balance_after: int, description: str, item_id: str = None):
    """Log transaction to file"""
    if not os.path.exists(TRANSACTION_LOG):
        transactions = []
    else:
        try:
            with locked_json_file(TRANSACTION_LOG, 'r') as f:
                transactions = json.load(f)
        except:
            transactions = []

    transaction = {
        "id": f"txn_{int(datetime.now().timestamp() * 1000)}",
        "user_id": user_id,
        "type": "earn" if amount > 0 else "spend",
        "amount": amount,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "item_id": item_id,
        "description": description,
        "timestamp": datetime.now().isoformat()
    }

    transactions.append(transaction)

    # Keep only last 10,000 transactions
    if len(transactions) > 10000:
        transactions = transactions[-10000:]

    try:
        atomic_write_json(TRANSACTION_LOG, transactions)
    except Exception as e:
        logger.error(f"Failed to log transaction: {e}")

# Inventory management
def add_to_inventory(user_id: str, item_id: str, quantity: int):
    """Add item to user inventory"""
    validate_user_id(user_id)
    validate_item_id(item_id)

    if quantity <= 0:
        raise ValueError("Quantity must be positive")

    data = load_data()
    if user_id not in data['inventory']:
        data['inventory'][user_id] = {}

    if item_id in data['inventory'][user_id]:
        data['inventory'][user_id][item_id]['quantity'] += quantity
    else:
        data['inventory'][user_id][item_id] = {
            "quantity": quantity,
            "acquired_at": datetime.now().isoformat()
        }

    save_data(data)

def remove_from_inventory(user_id: str, item_id: str, quantity: int) -> bool:
    """Remove item from user inventory"""
    validate_user_id(user_id)
    validate_item_id(item_id)

    if quantity <= 0:
        raise ValueError("Quantity must be positive")

    data = load_data()
    if user_id not in data['inventory'] or item_id not in data['inventory'][user_id]:
        return False

    current_quantity = data['inventory'][user_id][item_id]['quantity']
    if current_quantity < quantity:
        return False

    if current_quantity == quantity:
        del data['inventory'][user_id][item_id]
    else:
        data['inventory'][user_id][item_id]['quantity'] = current_quantity - quantity

    save_data(data)
    return True

def get_inventory(user_id: str) -> Dict[str, Any]:
    """Get user inventory"""
    validate_user_id(user_id)

    data = load_data()
    return data['inventory'].get(user_id, {})

def clear_inventory(user_id: str):
    """Clear all items from user inventory"""
    validate_user_id(user_id)

    data = load_data()
    if user_id in data['inventory']:
        data['inventory'][user_id] = {}
        save_data(data)

# Shop management
def get_shop_items(category: str = None) -> Dict[str, Any]:
    """Get shop items, optionally filtered by category"""
    data = load_data()
    items = data['shop_items']

    if category:
        items = {k: v for k, v in items.items() if v.get('category') == category}

    return items

def add_shop_item(item_id: str, name: str, price: int, description: str,
                 category: str = "misc", stock: int = -1):
    """Add item to shop"""
    validate_item_id(item_id)
    validate_amount(price)

    data = load_data()
    data['shop_items'][item_id] = {
        "name": name,
        "description": description,
        "price": price,
        "category": category,
        "stock": stock,
        "is_active": True
    }
    save_data(data)

def update_shop_item(item_id: str, **updates):
    """Update shop item"""
    validate_item_id(item_id)

    data = load_data()
    if item_id not in data['shop_items']:
        raise ValueError("Item not found")

    for key, value in updates.items():
        if key == 'price':
            value = validate_amount(value)
        data['shop_items'][item_id][key] = value

    save_data(data)

def remove_shop_item(item_id: str):
    """Remove item from shop"""
    validate_item_id(item_id)

    data = load_data()
    if item_id in data['shop_items']:
        del data['shop_items'][item_id]
        save_data(data)

# Leaderboard and statistics
def get_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    """Get top users by balance"""
    data = load_data()
    users = []

    for user_id, user_data in data['users'].items():
        users.append({
            'user_id': user_id,
            'balance': user_data.get('balance', 0),
            'total_earned': user_data.get('total_earned', 0),
            'total_spent': user_data.get('total_spent', 0)
        })

    # Sort by balance descending
    users.sort(key=lambda x: x['balance'], reverse=True)
    return users[:limit]

def get_user_stats(user_id: str) -> Dict[str, Any]:
    """Get detailed user statistics"""
    validate_user_id(user_id)

    data = load_data()
    user_data = data['users'].get(user_id, {})
    inventory = data['inventory'].get(user_id, {})

    return {
        'balance': user_data.get('balance', 0),
        'total_earned': user_data.get('total_earned', 0),
        'total_spent': user_data.get('total_spent', 0),
        'net_worth': user_data.get('total_earned', 0) - user_data.get('total_spent', 0),
        'last_daily': user_data.get('last_daily'),
        'created_at': user_data.get('created_at'),
        'stats': user_data.get('stats', {}),
        'inventory_count': sum(item.get('quantity', 0) for item in inventory.values())
    }

def get_economy_stats() -> Dict[str, Any]:
    """Get global economy statistics"""
    data = load_data()
    users = data['users']

    total_users = len(users)
    total_balance = sum(user.get('balance', 0) for user in users.values())
    total_earned = sum(user.get('total_earned', 0) for user in users.values())
    total_spent = sum(user.get('total_spent', 0) for user in users.values())

    return {
        'total_users': total_users,
        'total_currency_in_circulation': data['metadata'].get('total_currency_in_circulation', 0),
        'total_balance': total_balance,
        'total_earned': total_earned,
        'total_spent': total_spent,
        'average_balance': total_balance / total_users if total_users > 0 else 0
    }

# Migration function
def migrate_old_data():
    """Migrate from old JSON structure to new structure"""
    old_file = "data/user_data.json.backup"
    if not os.path.exists(old_file):
        # Create backup of current data
        import shutil
        shutil.copy2(DATA_FILE, old_file)

    try:
        with open(old_file, 'r') as f:
            old_data = json.load(f)
    except:
        logger.error("Could not load old data for migration")
        return

    # Initialize new structure
    new_data = initialize_data_structure()

    # Migrate balances
    if 'balances' in old_data:
        for user_id, balance in old_data['balances'].items():
            try:
                validate_user_id(user_id)
                balance = validate_amount(balance)

                new_data['users'][user_id] = {
                    "balance": balance,
                    "total_earned": balance,  # Estimate
                    "total_spent": 0,
                    "last_daily": None,
                    "created_at": datetime.now().isoformat(),
                    "stats": {
                        "purchases": 0,
                        "trades_completed": 0,
                        "daily_streak": 0
                    }
                }
                new_data['inventory'][user_id] = {}
            except:
                logger.warning(f"Skipping invalid user during migration: {user_id}")

    # Migrate inventories
    if 'inventories' in old_data:
        for user_id, items in old_data['inventories'].items():
            if user_id in new_data['users']:
                new_inventory = {}
                for item_id, quantity in items.items():
                    try:
                        validate_item_id(item_id)
                        if isinstance(quantity, int) and quantity > 0:
                            new_inventory[item_id] = {
                                "quantity": quantity,
                                "acquired_at": datetime.now().isoformat()
                            }
                    except:
                        logger.warning(f"Skipping invalid item during migration: {item_id}")
                new_data['inventory'][user_id] = new_inventory

    # Update metadata
    new_data['metadata']['total_currency_in_circulation'] = sum(
        user.get('balance', 0) for user in new_data['users'].values()
    )

    # Save migrated data
    save_data(new_data)
    logger.info("Migration completed successfully")

# Trading system
class TradeSession:
    """Manages a trade session between two users"""

    def __init__(self, user1_id: str, user2_id: str):
        validate_user_id(user1_id)
        validate_user_id(user2_id)

        if user1_id == user2_id:
            raise ValueError("Cannot trade with yourself")

        self.id = f"trade_{int(datetime.now().timestamp())}"
        self.user1_id = user1_id
        self.user2_id = user2_id
        self.user1_offer = {"money": 0, "items": {}}
        self.user2_offer = {"money": 0, "items": {}}
        self.user1_confirmed = False
        self.user2_confirmed = False
        self.created_at = datetime.now()
        self.expires_at = datetime.now() + timedelta(minutes=5)
        self.status = "active"  # active, completed, cancelled, expired

    def add_money(self, user_id: str, amount: int):
        """Add money to a user's offer"""
        amount = validate_amount(amount)

        if user_id == self.user1_id:
            self.user1_offer["money"] += amount
        elif user_id == self.user2_id:
            self.user2_offer["money"] += amount
        else:
            raise ValueError("User not in this trade")

        self.reset_confirmations()

    def add_item(self, user_id: str, item_id: str, quantity: int):
        """Add item to a user's offer"""
        validate_item_id(item_id)
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        # Check if user has the item
        inventory = get_inventory(user_id)
        if item_id not in inventory or inventory[item_id]['quantity'] < quantity:
            raise ValueError("Insufficient item quantity")

        if user_id == self.user1_id:
            if item_id in self.user1_offer["items"]:
                self.user1_offer["items"][item_id] += quantity
            else:
                self.user1_offer["items"][item_id] = quantity
        elif user_id == self.user2_id:
            if item_id in self.user2_offer["items"]:
                self.user2_offer["items"][item_id] += quantity
            else:
                self.user2_offer["items"][item_id] = quantity
        else:
            raise ValueError("User not in this trade")

        self.reset_confirmations()

    def remove_money(self, user_id: str, amount: int):
        """Remove money from a user's offer"""
        amount = validate_amount(amount)

        if user_id == self.user1_id:
            self.user1_offer["money"] = max(0, self.user1_offer["money"] - amount)
        elif user_id == self.user2_id:
            self.user2_offer["money"] = max(0, self.user2_offer["money"] - amount)
        else:
            raise ValueError("User not in this trade")

        self.reset_confirmations()

    def remove_item(self, user_id: str, item_id: str, quantity: int):
        """Remove item from a user's offer"""
        validate_item_id(item_id)
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        if user_id == self.user1_id:
            if item_id in self.user1_offer["items"]:
                self.user1_offer["items"][item_id] = max(0, self.user1_offer["items"][item_id] - quantity)
                if self.user1_offer["items"][item_id] == 0:
                    del self.user1_offer["items"][item_id]
        elif user_id == self.user2_id:
            if item_id in self.user2_offer["items"]:
                self.user2_offer["items"][item_id] = max(0, self.user2_offer["items"][item_id] - quantity)
                if self.user2_offer["items"][item_id] == 0:
                    del self.user2_offer["items"][item_id]
        else:
            raise ValueError("User not in this trade")

        self.reset_confirmations()

    def confirm(self, user_id: str):
        """Confirm trade for a user"""
        if user_id == self.user1_id:
            self.user1_confirmed = True
        elif user_id == self.user2_id:
            self.user2_confirmed = True
        else:
            raise ValueError("User not in this trade")

    def reset_confirmations(self):
        """Reset confirmations when offers change"""
        self.user1_confirmed = False
        self.user2_confirmed = False

    def is_expired(self) -> bool:
        """Check if trade has expired"""
        return datetime.now() > self.expires_at

    def can_execute(self) -> tuple[bool, str]:
        """Check if trade can be executed"""
        if self.status != "active":
            return False, "Trade is not active"

        if self.is_expired():
            self.status = "expired"
            return False, "Trade has expired"

        if not (self.user1_confirmed and self.user2_confirmed):
            return False, "Both users must confirm the trade"

        # Check if users have sufficient funds
        user1_balance = get_balance(self.user1_id)
        user2_balance = get_balance(self.user2_id)

        if user1_balance < self.user1_offer["money"]:
            return False, f"{self.user1_id} has insufficient funds"
        if user2_balance < self.user2_offer["money"]:
            return False, f"{self.user2_id} has insufficient funds"

        # Check if users have sufficient items
        user1_inventory = get_inventory(self.user1_id)
        user2_inventory = get_inventory(self.user2_id)

        for item_id, quantity in self.user1_offer["items"].items():
            if item_id not in user1_inventory or user1_inventory[item_id]['quantity'] < quantity:
                return False, f"{self.user1_id} has insufficient {item_id}"

        for item_id, quantity in self.user2_offer["items"].items():
            if item_id not in user2_inventory or user2_inventory[item_id]['quantity'] < quantity:
                return False, f"{self.user2_id} has insufficient {item_id}"

        return True, "Trade can be executed"

    def execute(self) -> tuple[bool, str]:
        """Execute the trade atomically"""
        can_execute, reason = self.can_execute()
        if not can_execute:
            return False, reason

        try:
            # Execute money transfer
            if self.user1_offer["money"] > 0:
                deduct_balance(self.user1_id, self.user1_offer["money"], f"Trade with {self.user2_id}")
            if self.user2_offer["money"] > 0:
                deduct_balance(self.user2_id, self.user2_offer["money"], f"Trade with {self.user1_id}")

            if self.user1_offer["money"] > 0:
                add_balance(self.user2_id, self.user1_offer["money"], f"Trade from {self.user1_id}", skip_transaction=True)
            if self.user2_offer["money"] > 0:
                add_balance(self.user1_id, self.user2_offer["money"], f"Trade from {self.user2_id}", skip_transaction=True)

            # Execute item transfer
            for item_id, quantity in self.user1_offer["items"].items():
                remove_from_inventory(self.user1_id, item_id, quantity)
                add_to_inventory(self.user2_id, item_id, quantity)

            for item_id, quantity in self.user2_offer["items"].items():
                remove_from_inventory(self.user2_id, item_id, quantity)
                add_to_inventory(self.user1_id, item_id, quantity)

            # Update user stats
            data = load_data()
            if self.user1_id in data['users']:
                data['users'][self.user1_id]['stats']['trades_completed'] = data['users'][self.user1_id]['stats'].get('trades_completed', 0) + 1
            if self.user2_id in data['users']:
                data['users'][self.user2_id]['stats']['trades_completed'] = data['users'][self.user2_id]['stats'].get('trades_completed', 0) + 1
            save_data(data)

            self.status = "completed"
            return True, "Trade completed successfully"

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            return False, f"Trade execution failed: {str(e)}"

    def cancel(self, reason: str = "Cancelled by user"):
        """Cancel the trade"""
        self.status = "cancelled"
        logger.info(f"Trade {self.id} cancelled: {reason}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert trade to dictionary for serialization"""
        return {
            "id": self.id,
            "user1_id": self.user1_id,
            "user2_id": self.user2_id,
            "user1_offer": self.user1_offer,
            "user2_offer": self.user2_offer,
            "user1_confirmed": self.user1_confirmed,
            "user2_confirmed": self.user2_confirmed,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "status": self.status
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TradeSession':
        """Create trade from dictionary"""
        trade = cls(data['user1_id'], data['user2_id'])
        trade.id = data['id']
        trade.user1_offer = data['user1_offer']
        trade.user2_offer = data['user2_offer']
        trade.user1_confirmed = data['user1_confirmed']
        trade.user2_confirmed = data['user2_confirmed']
        trade.created_at = datetime.fromisoformat(data['created_at'])
        trade.expires_at = datetime.fromisoformat(data['expires_at'])
        trade.status = data['status']
        return trade

# Global trade sessions storage
active_trades = {}

def create_trade(user1_id: str, user2_id: str) -> TradeSession:
    """Create a new trade session"""
    # Check if either user is already in a trade
    for trade in active_trades.values():
        if trade.status == "active" and (user1_id in [trade.user1_id, trade.user2_id] or
                                        user2_id in [trade.user1_id, trade.user2_id]):
            raise ValueError("One or both users are already in an active trade")

    trade = TradeSession(user1_id, user2_id)
    active_trades[trade.id] = trade
    return trade

def get_trade(trade_id: str) -> Optional[TradeSession]:
    """Get a trade session by ID"""
    return active_trades.get(trade_id)

def get_user_trade(user_id: str) -> Optional[TradeSession]:
    """Get the active trade for a user"""
    for trade in active_trades.values():
        if trade.status == "active" and user_id in [trade.user1_id, trade.user2_id]:
            return trade
    return None

def cleanup_expired_trades():
    """Clean up expired trades"""
    expired_trades = []
    for trade_id, trade in active_trades.items():
        if trade.is_expired() and trade.status == "active":
            trade.status = "expired"
            expired_trades.append(trade_id)

    for trade_id in expired_trades:
        del active_trades[trade_id]

    if expired_trades:
        logger.info(f"Cleaned up {len(expired_trades)} expired trades")

# Admin functions
def get_transaction_history(user_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Get transaction history"""
    if not os.path.exists(TRANSACTION_LOG):
        return []

    try:
        with locked_json_file(TRANSACTION_LOG, 'r') as f:
            transactions = json.load(f)
    except:
        return []

    # Filter by user if specified
    if user_id:
        validate_user_id(user_id)
        transactions = [t for t in transactions if t['user_id'] == user_id]

    # Sort by timestamp descending and limit
    transactions.sort(key=lambda x: x['timestamp'], reverse=True)
    return transactions[:limit]

def get_admin_stats() -> Dict[str, Any]:
    """Get administrative statistics"""
    data = load_data()

    stats = {
        'total_users': len(data['users']),
        'total_currency': data['metadata'].get('total_currency_in_circulation', 0),
        'active_trades': len([t for t in active_trades.values() if t.status == 'active']),
        'total_shop_items': len(data['shop_items']),
        'data_file_size': os.path.getsize(DATA_FILE) if os.path.exists(DATA_FILE) else 0,
        'backup_count': len([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')]) if os.path.exists(BACKUP_DIR) else 0,
        'last_backup': data['metadata'].get('last_backup')
    }

    # Transaction stats
    if os.path.exists(TRANSACTION_LOG):
        try:
            with locked_json_file(TRANSACTION_LOG, 'r') as f:
                transactions = json.load(f)
            stats['total_transactions'] = len(transactions)
            stats['recent_transactions'] = len([t for t in transactions if
                                               (datetime.now() - datetime.fromisoformat(t['timestamp'])).days < 1])
        except:
            stats['total_transactions'] = 0
            stats['recent_transactions'] = 0
    else:
        stats['total_transactions'] = 0
        stats['recent_transactions'] = 0

    return stats

# Initialize on import
if __name__ != "__main__":
    # Ensure data structure exists
    try:
        data = load_data()
        logger.info("Currency system initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize currency system: {e}")
