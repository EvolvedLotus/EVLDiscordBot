import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
from collections import defaultdict

class TransactionManager:
    def __init__(self, data_manager, audit_manager=None, cache_manager=None):
        self.data_manager = data_manager
        self.audit_manager = audit_manager
        self.cache_manager = cache_manager
        self.indexes = {}  # guild_id -> indexes
        self.index_locks = {}  # guild_id -> threading.Lock
        self.cache = {}  # Simple cache for recent queries
        self.cache_lock = threading.Lock()

    def _load_transactions(self, guild_id: int) -> List[dict]:
        """Load transactions from Supabase via data_manager"""
        transactions_data = self.data_manager.load_guild_data(guild_id, 'transactions')
        if transactions_data and 'transactions' in transactions_data:
            return transactions_data['transactions']
        return []

    def _save_transactions(self, guild_id: int, transactions: List[dict]):
        """Save transactions to Supabase via data_manager"""
        transactions_data = {'transactions': transactions}
        self.data_manager.save_guild_data(guild_id, 'transactions', transactions_data)

    def _get_lock(self, guild_id: int) -> threading.Lock:
        if guild_id not in self.index_locks:
            self.index_locks[guild_id] = threading.Lock()
        return self.index_locks[guild_id]

    def _build_indexes(self, guild_id: int):
        with self._get_lock(guild_id):
            if guild_id in self.indexes:
                return  # Already built

            transactions = self._load_transactions(guild_id)
            indexes = {
                'by_user': defaultdict(list),
                'by_type': defaultdict(list),
                'by_timestamp': []  # List of (timestamp, txn_id) tuples
            }

            for txn in transactions:
                txn_id = txn['id']
                user_id = txn['user_id']
                txn_type = txn['type']
                timestamp = txn['timestamp']

                indexes['by_user'][user_id].append(txn_id)
                indexes['by_type'][txn_type].append(txn_id)
                indexes['by_timestamp'].append((timestamp, txn_id))

            # Sort timestamp index
            indexes['by_timestamp'].sort(key=lambda x: x[0], reverse=True)

            self.indexes[guild_id] = indexes

    def adjust_balance(self, guild_id: int, user_id: int, amount: int, reason: str = "Admin adjustment"):
        """
        Adjust user balance and log transaction.
        Used by admin API.
        """
        # Get current balance
        currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
        users = currency_data.get('users', {})
        user_data = users.get(str(user_id), {})
        current_balance = user_data.get('balance', 0)
        
        # Log transaction (which updates balance atomically via RPC)
        return self.log_transaction(
            guild_id=guild_id,
            user_id=user_id,
            amount=amount,
            balance_before=current_balance,
            balance_after=current_balance + amount,
            transaction_type='admin_adjustment',
            description=reason
        )

    def log_transaction(
        self,
        guild_id: int,
        user_id: int,
        amount: int,
        balance_before: int,
        balance_after: int,
        transaction_type: str,
        description: str,
        metadata: dict = None,
        idempotency_key: str = None
    ) -> dict:
        """Log transaction using the atomic database function defined in schema.sql"""
        import logging
        logger = logging.getLogger(__name__)

        # Validate balance
        if balance_after != balance_before + amount:
            raise ValueError("Balance validation failed: balance_after != balance_before + amount")

        # Generate transaction ID
        timestamp_ms = int(datetime.utcnow().timestamp() * 1000)
        short_uuid = str(uuid.uuid4())[:8]
        txn_id = f"txn_{guild_id}_{user_id}_{timestamp_ms}_{short_uuid}"

        transaction = {
            "id": txn_id,
            "user_id": str(user_id),
            "amount": amount,
            "balance_before": balance_before,
            "balance_after": balance_after,
            "type": transaction_type,
            "description": description,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "metadata": metadata or {}
        }

        if idempotency_key:
            transaction["metadata"]["idempotency_key"] = idempotency_key

        # Use the atomic database function from schema.sql
        try:
            result = self.data_manager.admin_client.rpc(
                'log_transaction_atomic',
                {
                    'p_guild_id': str(guild_id),
                    'p_user_id': str(user_id),
                    'p_amount': amount,
                    'p_balance_before': balance_before,
                    'p_balance_after': balance_after,
                    'p_transaction_type': transaction_type,
                    'p_description': description,
                    'p_transaction_id': txn_id,
                    'p_metadata': transaction["metadata"]
                }
            ).execute()

            if result.data:
                # Update transaction with database timestamp
                db_txn = result.data[0] if isinstance(result.data, list) else result.data
                transaction['timestamp'] = db_txn.get('timestamp', transaction['timestamp'])
                logger.info(f"Transaction {txn_id} logged successfully")
            else:
                raise Exception("Transaction logging returned no data")

        except Exception as e:
            logger.error(f"Database transaction logging failed: {e}")
            # In production, this should trigger an alert for manual reconciliation
            raise Exception(f"Critical: Transaction logging failed: {e}")

        # Broadcast SSE event (only if transaction was logged successfully)
        try:
            from core.sse_manager import sse_manager
            sse_manager.broadcast_event('transaction', {
                'guild_id': str(guild_id),
                'user_id': str(user_id),
                'transaction': transaction
            })
        except Exception as e:
            logger.warning(f"Failed to broadcast transaction event: {e}")

        # Invalidate cache
        with self.cache_lock:
            self.cache.clear()

        # Invalidate centralized cache
        if self.cache_manager:
            # Invalidate balance cache for this user
            self.cache_manager.invalidate(f"balance:{guild_id}:{user_id}")
            # Invalidate transaction caches
            self.cache_manager.invalidate_pattern(f"transactions:{guild_id}:{user_id}:*")

        return transaction

    def _find_transaction_by_idempotency(self, guild_id: int, idempotency_key: str) -> Optional[dict]:
        transactions = self._load_transactions(guild_id)
        for txn in transactions:
            if txn.get('metadata', {}).get('idempotency_key') == idempotency_key:
                return txn
        return None

    def _update_indexes(self, guild_id: int, transaction: dict):
        self._build_indexes(guild_id)  # Ensure indexes exist
        indexes = self.indexes[guild_id]

        txn_id = transaction['id']
        user_id = transaction['user_id']
        txn_type = transaction['type']
        timestamp = transaction['timestamp']

        indexes['by_user'][user_id].append(txn_id)
        indexes['by_type'][txn_type].append(txn_id)
        indexes['by_timestamp'].append((timestamp, txn_id))
        indexes['by_timestamp'].sort(key=lambda x: x[0], reverse=True)

    def get_transactions(
        self,
        guild_id: int,
        user_id: int = None,
        transaction_type: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 100,
        offset: int = 0,
        sort: str = 'desc'
    ) -> dict:
        self._build_indexes(guild_id)
        indexes = self.indexes[guild_id]

        # Get candidate transaction IDs
        if user_id:
            candidate_ids = set(indexes['by_user'].get(str(user_id), []))
        else:
            candidate_ids = set()
            for user_txns in indexes['by_user'].values():
                candidate_ids.update(user_txns)

        if transaction_type:
            type_ids = set(indexes['by_type'].get(transaction_type, []))
            candidate_ids = candidate_ids.intersection(type_ids)

        # Load full transactions
        all_transactions = {txn['id']: txn for txn in self._load_transactions(guild_id)}
        filtered_transactions = []

        for txn_id in candidate_ids:
            txn = all_transactions.get(txn_id)
            if not txn:
                continue

            # Date filtering
            txn_datetime = datetime.fromisoformat(txn['timestamp'].replace('Z', '+00:00'))
            if start_date and txn_datetime < start_date:
                continue
            if end_date and txn_datetime > end_date:
                continue

            filtered_transactions.append(txn)

        # Sort
        reverse = sort == 'desc'
        filtered_transactions.sort(key=lambda x: x['timestamp'], reverse=reverse)

        # Paginate
        total = len(filtered_transactions)
        paginated = filtered_transactions[offset:offset + limit]
        has_more = offset + limit < total

        return {
            'transactions': paginated,
            'total': total,
            'has_more': has_more
        }

    def get_user_statistics(
        self,
        guild_id: int,
        user_id: int,
        period: str = 'all'
    ) -> dict:
        transactions = self.get_transactions(guild_id, user_id=user_id)['transactions']

        # Filter by period
        now = datetime.utcnow()
        if period == 'day':
            start_date = now - timedelta(days=1)
        elif period == 'week':
            start_date = now - timedelta(weeks=1)
        elif period == 'month':
            start_date = now - timedelta(days=30)
        else:
            start_date = None

        if start_date:
            transactions = [t for t in transactions if datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00')) >= start_date]

        stats = {
            'total_earned': 0,
            'total_spent': 0,
            'total_transferred_sent': 0,
            'total_transferred_received': 0,
            'transaction_count': len(transactions),
            'transaction_count_by_type': defaultdict(int),
            'average_transaction_size': 0,
            'date_range': {
                'start': transactions[-1]['timestamp'] if transactions else None,
                'end': transactions[0]['timestamp'] if transactions else None
            }
        }

        total_amount = 0
        for txn in transactions:
            amount = txn['amount']
            total_amount += abs(amount)
            stats['transaction_count_by_type'][txn['type']] += 1

            if amount > 0:
                stats['total_earned'] += amount
            elif amount < 0:
                stats['total_spent'] += abs(amount)

            if txn['type'] == 'transfer_send':
                stats['total_transferred_sent'] += abs(amount)
            elif txn['type'] == 'transfer_receive':
                stats['total_transferred_received'] += amount

        stats['average_transaction_size'] = total_amount / len(transactions) if transactions else 0

        return stats

    def get_server_statistics(
        self,
        guild_id: int,
        period: str = 'all'
    ) -> dict:
        transactions = self.get_transactions(guild_id)['transactions']

        # Filter by period
        now = datetime.utcnow()
        if period == 'day':
            start_date = now - timedelta(days=1)
        elif period == 'week':
            start_date = now - timedelta(weeks=1)
        elif period == 'month':
            start_date = now - timedelta(days=30)
        else:
            start_date = None

        if start_date:
            transactions = [t for t in transactions if datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00')) >= start_date]

        stats = {
            'total_transactions': len(transactions),
            'total_currency_in_circulation': 0,  # This would need to be calculated from currency data
            'most_active_users': [],
            'transaction_volume_by_type': defaultdict(int)
        }

        user_activity = defaultdict(int)
        for txn in transactions:
            user_activity[txn['user_id']] += 1
            stats['transaction_volume_by_type'][txn['type']] += abs(txn['amount'])

        # Get top 10 most active users
        sorted_users = sorted(user_activity.items(), key=lambda x: x[1], reverse=True)[:10]
        stats['most_active_users'] = [{'user_id': uid, 'transaction_count': count} for uid, count in sorted_users]

        return stats

    def rebuild_indexes(self, guild_id: int):
        with self._get_lock(guild_id):
            if guild_id in self.indexes:
                del self.indexes[guild_id]
            self._build_indexes(guild_id)

    def validate_transaction_integrity(self, guild_id: int, user_id: int) -> dict:
        transactions = self.get_transactions(guild_id, user_id=user_id)['transactions']
        currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
        current_balance = currency_data.get('users', {}).get(str(user_id), {}).get('balance', 0)

        calculated_balance = 0
        for txn in sorted(transactions, key=lambda x: x['timestamp']):
            calculated_balance += txn['amount']

        expected_balance = calculated_balance
        discrepancy = current_balance - expected_balance

        return {
            'valid': discrepancy == 0,
            'expected_balance': expected_balance,
            'actual_balance': current_balance,
            'discrepancy': discrepancy
        }



    def cleanup_old_transactions(
        self,
        guild_id: int,
        days_to_keep: int = 90,
        archive: bool = False  # Archive disabled for Supabase-only setup
    ):
        """
        Clean up old transactions by removing them from Supabase.
        Archive functionality disabled since we're using Supabase-only storage.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        transactions = self._load_transactions(guild_id)

        recent_transactions = []

        for txn in transactions:
            txn_datetime = datetime.fromisoformat(txn['timestamp'].replace('Z', '+00:00'))
            if txn_datetime >= cutoff_date:
                recent_transactions.append(txn)
            # Old transactions are simply discarded (no file archiving)

        # Save recent transactions only
        self._save_transactions(guild_id, recent_transactions)

        # Rebuild indexes
        self.rebuild_indexes(guild_id)

        return len(transactions) - len(recent_transactions)  # Return number of transactions removed

    async def validate_transaction_integrity(self, guild_id=None):
        """Validate all transactions have correct balance calculations"""

        violations = []

        try:
            query = """
                SELECT transaction_id, user_id, guild_id, amount,
                       balance_before, balance_after
                FROM transactions
            """

            if guild_id:
                query += " WHERE guild_id = $1"
                transactions = await self.data_manager.fetch(query, guild_id)
            else:
                transactions = await self.data_manager.fetch(query)

            for tx in transactions:
                expected_balance = tx['balance_before'] + tx['amount']

                if tx['balance_after'] != expected_balance:
                    violations.append({
                        'transaction_id': tx['transaction_id'],
                        'user_id': tx['user_id'],
                        'guild_id': tx['guild_id'],
                        'expected': expected_balance,
                        'actual': tx['balance_after'],
                        'difference': tx['balance_after'] - expected_balance
                    })

                    # Log to audit
                    await self.audit_manager.log_event(
                        guild_id=tx['guild_id'],
                        event_type='transaction_integrity_violation',
                        details={
                            'transaction_id': tx['transaction_id'],
                            'user_id': tx['user_id'],
                            'expected_balance': expected_balance,
                            'actual_balance': tx['balance_after']
                        }
                    )

            if violations:
                logger.error(f"Found {len(violations)} transaction integrity violations")

            return violations

        except Exception as e:
            logger.exception(f"Transaction integrity validation error: {e}")
            return []
