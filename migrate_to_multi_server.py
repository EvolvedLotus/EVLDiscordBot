"""
Migration script to convert single-server data to multi-server structure
"""

import json
import os
from pathlib import Path
from core import data_manager

def migrate_old_data():
    """Migrate from old single-file structure to new multi-server structure"""

    print("🔄 Starting migration...")

    # Check if old data file exists
    if not os.path.exists("data/user_data.json"):
        print("❌ No old data file found (data/user_data.json)")
        print("ℹ️  Starting fresh - no migration needed!")
        return

    # Load old data
    with open("data/user_data.json", 'r') as f:
        old_data = json.load(f)

    print(f"📂 Found old data with {len(old_data.get('users', {}))} users")

    # Use the first guild ID from the bot's connected servers
    # In a real scenario, you'd want to choose which server to migrate to
    guild_id = 955306191219787790  # Cupid's Garden server
    print(f"\n🔄 Migrating data to Guild ID: {guild_id}")

    # Migrate currency data
    if 'balances' in old_data or 'inventories' in old_data:
        currency_data = data_manager.load_guild_data(guild_id, "currency")

        # Migrate user balances
        for user_id, balance in old_data.get('balances', {}).items():
            try:
                currency_data['users'][user_id] = {
                    "balance": balance,
                    "total_earned": balance,  # Estimate
                    "total_spent": 0,
                    "last_daily": None,
                    "created_at": "2025-01-01T00:00:00"
                }
            except Exception as e:
                print(f"⚠️  Skipping invalid user data for {user_id}: {e}")

        # Migrate inventory
        for user_id, items in old_data.get('inventories', {}).items():
            if user_id not in currency_data['users']:
                continue

            currency_data['inventory'][user_id] = {}

            if isinstance(items, dict):
                for item_id, quantity in items.items():
                    try:
                        if isinstance(quantity, int) and quantity > 0:
                            currency_data['inventory'][user_id][item_id] = {
                                "quantity": quantity,
                                "acquired_at": "2025-01-01T00:00:00"
                            }
                    except Exception as e:
                        print(f"⚠️  Skipping invalid inventory item {item_id}: {e}")

        # Update total currency
        total_currency = sum(user.get('balance', 0) for user in currency_data['users'].values())
        currency_data['metadata']['total_currency'] = total_currency

        data_manager.save_guild_data(guild_id, "currency", currency_data)
        print(f"✅ Migrated {len(currency_data['users'])} users and their inventories")

    # Migrate tasks data if exists
    if 'tasks' in old_data:
        tasks_data = data_manager.load_guild_data(guild_id, "tasks")
        tasks_data['tasks'] = old_data['tasks']
        data_manager.save_guild_data(guild_id, "tasks", tasks_data)
        print(f"✅ Migrated {len(old_data['tasks'])} tasks")

    # Create backup of old file
    backup_path = Path("backups/migration")
    backup_path.mkdir(parents=True, exist_ok=True)

    import shutil
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_path / f"old_user_data_{timestamp}.json"
    shutil.copy("data/user_data.json", backup_file)

    print(f"📦 Old data backed up to: {backup_file}")

    # Automatically delete old file after migration
    os.remove("data/user_data.json")
    print("🗑️  Old file deleted")

    print("\n✅ Migration complete!")
    print(f"   Data is now in: data/guilds/{guild_id}/")
    print("   You can now run the bot with the new multi-server architecture!")

if __name__ == "__main__":
    migrate_old_data()
