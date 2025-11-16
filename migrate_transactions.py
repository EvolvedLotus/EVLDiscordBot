#!/usr/bin/env python3
"""
Migration script to add missing 'type' field to existing transactions
"""

import json
import os
from datetime import datetime

def migrate_transactions():
    """Add 'type' field to existing transactions that don't have it"""

    data_dir = 'data/guilds'

    if not os.path.exists(data_dir):
        print("No data directory found")
        return

    for guild_dir in os.listdir(data_dir):
        guild_path = os.path.join(data_dir, guild_dir)
        if not os.path.isdir(guild_path):
            continue

        transactions_file = os.path.join(guild_path, 'transactions.json')
        if not os.path.exists(transactions_file):
            continue

        print(f"Migrating transactions for guild {guild_dir}")

        try:
            with open(transactions_file, 'r', encoding='utf-8') as f:
                transactions = json.load(f)

            updated = False
            for txn in transactions:
                if 'type' not in txn:
                    # Infer type from description or other fields
                    description = txn.get('description', '').lower()
                    source = txn.get('source', '')

                    if 'daily' in description:
                        txn_type = 'daily'
                    elif 'task' in description or 'completed' in description:
                        txn_type = 'task'
                    elif 'purchase' in description or 'bought' in description:
                        txn_type = 'shop'
                    elif 'gave' in description or 'received' in description:
                        if 'gave' in description:
                            txn_type = 'transfer_send'
                        else:
                            txn_type = 'transfer_receive'
                    elif source == 'cms':
                        txn_type = 'admin_adjustment'
                    else:
                        txn_type = 'earn'  # Default

                    txn['type'] = txn_type
                    updated = True

            if updated:
                with open(transactions_file, 'w', encoding='utf-8') as f:
                    json.dump(transactions, f, indent=2, ensure_ascii=False)
                print(f"  Updated {len(transactions)} transactions")
            else:
                print("  No updates needed")

        except Exception as e:
            print(f"  Error migrating guild {guild_dir}: {e}")

if __name__ == '__main__':
    migrate_transactions()
    print("Migration complete!")
