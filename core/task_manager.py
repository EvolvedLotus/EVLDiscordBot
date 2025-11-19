# core/task_manager.py - Task lifecycle management with Supabase integration

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import discord

logger = logging.getLogger(__name__)

class TaskManager:
    """
    Centralized task management with Supabase integration.
    Handles task lifecycle, claiming, submission, expiry, and Discord synchronization.
    """

    def __init__(self, data_manager, transaction_manager):
        self.data_manager = data_manager
        self.transaction_manager = transaction_manager
        self.bot = None

    def set_bot(self, bot):
        """Set bot instance for Discord operations"""
        self.bot = bot

    def set_cache_manager(self, cache_manager):
        """Set cache manager instance"""
        self.cache_manager = cache_manager

    def set_sse_manager(self, sse_manager):
        """Set SSE manager instance"""
        self.sse_manager = sse_manager

    async def create_task(self, guild_id, name, description, reward, duration_hours, max_claims=None):
        """Create new task with atomic task_id generation"""

        # VALIDATION
        if reward <= 0:
            raise ValueError("Reward must be positive")
        if duration_hours <= 0:
            raise ValueError("Duration must be positive")

        async with self.data_manager.atomic_transaction() as conn:
            # ATOMIC INCREMENT of task_id (prevent race condition)
            result = await conn.fetchrow(
                """UPDATE task_settings
                   SET next_task_id = next_task_id + 1
                   WHERE guild_id = $1
                   RETURNING next_task_id""",
                guild_id
            )

            if not result:
                # Initialize task_settings if not exists
                await conn.execute(
                    """INSERT INTO task_settings (guild_id, next_task_id)
                       VALUES ($1, 1)
                       ON CONFLICT (guild_id) DO NOTHING""",
                    guild_id
                )
                task_id = 1
            else:
                task_id = result['next_task_id']

            # Calculate expiration
            expires_at = datetime.now(timezone.utc) + timedelta(hours=duration_hours)

            # Insert task
            await conn.execute(
                """INSERT INTO tasks (task_id, guild_id, name, description, reward,
                                      duration_hours, max_claims, current_claims, status, expires_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, 0, 'active', $8)""",
                task_id, guild_id, name, description, reward, duration_hours, max_claims, expires_at
            )

        return task_id

    async def claim_task(self, guild_id: int, user_id: int, task_id: int) -> Dict:
        """Claim task with PREVENT OVER-CLAIMING - atomic validation"""
        user_id = str(user_id)
        guild_id = str(guild_id)
        task_id = str(task_id)

        try:
            async with self.data_manager.atomic_transaction() as conn:
                # 1. LOCK TASK ROW FIRST
                task_data = await conn.fetchrow(
                    """SELECT task_id, name, reward, duration_hours, max_claims,
                              current_claims, status, expires_at
                       FROM tasks
                       WHERE task_id = $1 AND guild_id = $2
                       FOR UPDATE""",
                    task_id, guild_id
                )

                if not task_data:
                    return {'success': False, 'error': "Task not found."}

                # VALIDATION: Task must be active
                if task_data['status'] != 'active':
                    return {'success': False, 'error': "Task is not active."}

                # VALIDATION: Task not expired
                if task_data['expires_at'] < datetime.now(timezone.utc):
                    return {'success': False, 'error': "Task has expired."}

                # VALIDATION: Max claims not exceeded
                if task_data['max_claims'] and task_data['current_claims'] >= task_data['max_claims']:
                    return {'success': False, 'error': "Task is full."}

                # VALIDATION: User hasn't already claimed
                existing_claim = await conn.fetchrow(
                    """SELECT id FROM user_tasks
                       WHERE user_id = $1 AND guild_id = $2 AND task_id = $3""",
                    user_id, guild_id, task_id
                )

                if existing_claim:
                    return {'success': False, 'error': "You already claimed this task."}

                # Calculate deadline
                deadline = datetime.now(timezone.utc) + timedelta(hours=task_data['duration_hours'])

                # CREATE USER TASK
                await conn.execute(
                    """INSERT INTO user_tasks (user_id, guild_id, task_id, status, claimed_at, deadline)
                       VALUES ($1, $2, $3, 'in_progress', $4, $5)""",
                    user_id, guild_id, task_id, datetime.now(timezone.utc), deadline
                )

                # INCREMENT CURRENT_CLAIMS
                await conn.execute(
                    """UPDATE tasks SET current_claims = current_claims + 1
                       WHERE task_id = $1 AND guild_id = $2""",
                    task_id, guild_id
                )

            # Invalidate cache safely
            if self.cache_manager:
                self.cache_manager.invalidate(f"tasks:{guild_id}")
                self.cache_manager.invalidate(f"user_tasks:{guild_id}:{user_id}")

            # Emit SSE event safely
            if self.sse_manager:
                await self.sse_manager.broadcast_event(guild_id, {
                    'type': 'task_claimed',
                    'user_id': user_id,
                    'task_id': task_id
                })

            return {
                'success': True,
                'task': task_data,
                'deadline': deadline
            }

        except Exception as e:
            logger.exception(f"Claim task error: {e}")
            return {'success': False, 'error': "Failed to claim task."}

    async def submit_task(self, guild_id: int, user_id: int, task_id: int, proof: str) -> Dict:
        """Submit task with PREVENT LATE SUBMISSIONS - deadline validation"""
        user_id = str(user_id)
        guild_id = str(guild_id)
        task_id = str(task_id)

        try:
            async with self.data_manager.atomic_transaction() as conn:
                # Get user task with lock
                user_task = await conn.fetchrow(
                    """SELECT id, status, deadline, submitted_at
                       FROM user_tasks
                       WHERE user_id = $1 AND guild_id = $2 AND task_id = $3
                       FOR UPDATE""",
                    user_id, guild_id, task_id
                )

                if not user_task:
                    return {'success': False, 'error': "You haven't claimed this task."}

                # VALIDATION: Not already submitted
                if user_task['status'] != 'in_progress':
                    return {'success': False, 'error': f"Task already {user_task['status']}."}

                # VALIDATION: Deadline not passed
                now = datetime.now(timezone.utc)
                if now > user_task['deadline']:
                    # Auto-expire the task
                    await conn.execute(
                        """UPDATE user_tasks SET status = 'expired'
                           WHERE id = $1""",
                        user_task['id']
                    )
                    return {'success': False, 'error': "Deadline has passed. Cannot submit."}

                # UPDATE SUBMISSION
                await conn.execute(
                    """UPDATE user_tasks
                       SET status = 'submitted',
                           proof_content = $1,
                           submitted_at = $2,
                           proof_message_id = $3
                       WHERE id = $4""",
                    proof, now, None, user_task['id']  # proof_message_id can be updated later
                )

            # Invalidate cache
            self.cache_manager.invalidate(f"user_tasks:{guild_id}:{user_id}")

            # Emit SSE event
            await self.sse_manager.broadcast_event(guild_id, {
                'type': 'task_submitted',
                'user_id': user_id,
                'task_id': task_id
            })

            return {'success': True}

        except Exception as e:
            logger.exception(f"Task submit error: {e}")
            return {'success': False, 'error': "Failed to submit task."}

    async def approve_task(self, guild_id: int, user_id: int, task_id: int, approver_id: int) -> Dict:
        """Approve task with PREVENT DUPLICATE REWARDS - atomic validation"""
        user_id = str(user_id)
        guild_id = str(guild_id)
        task_id = str(task_id)
        approver_id = str(approver_id)

        try:
            async with self.data_manager.atomic_transaction() as conn:
                # Get user task with lock
                user_task = await conn.fetchrow(
                    """SELECT ut.id, ut.status, t.reward, t.name
                       FROM user_tasks ut
                       JOIN tasks t ON ut.task_id = t.task_id AND ut.guild_id = t.guild_id
                       WHERE ut.user_id = $1 AND ut.guild_id = $2 AND ut.task_id = $3
                       FOR UPDATE""",
                    user_id, guild_id, task_id
                )

                if not user_task:
                    return {'success': False, 'error': "User hasn't claimed this task."}

                # VALIDATION: Not already completed
                if user_task['status'] == 'accepted':
                    return {'success': False, 'error': "Task already completed."}

                # Get user balance
                user_data = await conn.fetchrow(
                    "SELECT balance FROM users WHERE user_id = $1 AND guild_id = $2 FOR UPDATE",
                    user_id, guild_id
                )

                if not user_data:
                    return {'success': False, 'error': "User not found."}

                old_balance = user_data['balance']
                new_balance = old_balance + user_task['reward']

                # Update task status
                await conn.execute(
                    """UPDATE user_tasks
                       SET status = 'accepted', completed_at = $1
                       WHERE id = $2""",
                    datetime.now(timezone.utc), user_task['id']
                )

                # Award reward
                await conn.execute(
                    "UPDATE users SET balance = $1 WHERE user_id = $2 AND guild_id = $3",
                    new_balance, user_id, guild_id
                )

                # Log transaction
                await self.transaction_manager.log_transaction(
                    user_id=user_id,
                    guild_id=guild_id,
                    amount=user_task['reward'],
                    transaction_type="task_reward",
                    balance_before=old_balance,
                    balance_after=new_balance,
                    description=f"Task completed: {user_task['name']}",
                    metadata={'task_id': task_id, 'approver_id': approver_id},
                    conn=conn
                )

                # Update task_settings counter
                await conn.execute(
                    """UPDATE task_settings
                       SET total_completed = total_completed + 1
                       WHERE guild_id = $1""",
                    guild_id
                )

            # Invalidate caches
            self.cache_manager.invalidate(f"balance:{guild_id}:{user_id}")
            self.cache_manager.invalidate(f"user_tasks:{guild_id}:{user_id}")

            # Emit SSE events
            await self.sse_manager.broadcast_event(guild_id, {
                'type': 'task_completed',
                'user_id': user_id,
                'task_id': task_id,
                'reward': user_task['reward']
            })

            return {
                'success': True,
                'reward_amount': user_task['reward'],
                'new_balance': new_balance
            }

        except Exception as e:
            logger.exception(f"Complete task error: {e}")
            return {'success': False, 'error': "Failed to complete task."}

    def reject_task(self, guild_id: int, user_id: int, task_id: str, reason: str = None) -> Dict:
        """
        Reject a submitted task.

        Args:
            guild_id: Guild ID
            user_id: User ID
            task_id: Task ID
            reason: Rejection reason

        Returns:
            Result dictionary
        """
        def reject_operation(tasks_data, currency_data):
            user_tasks = tasks_data.get('user_tasks', {}).get(str(user_id), {})
            user_task = user_tasks.get(task_id)

            if not user_task:
                return {'success': False, 'error': "Task not found for user."}

            if user_task['status'] != 'submitted':
                return {'success': False, 'error': f"Task is not submitted (Status: {user_task['status']})."}

            # Reset to in_progress so user can resubmit
            user_task['status'] = 'in_progress'
            user_task['notes'] = f"Rejected: {reason}" if reason else "Rejected for review"

            return {'success': True}

        try:
            result = self._atomic_task_operation(guild_id, reject_operation)
            return result
        except Exception as e:
            logger.error(f"Task rejection failed: {e}")
            return {'success': False, 'error': "Failed to reject task."}

    def expire_overdue_tasks(self, guild_id: int) -> int:
        """
        Expire tasks that have passed their deadline.

        Args:
            guild_id: Guild ID

        Returns:
            Number of tasks expired
        """
        try:
            tasks_data = self.data_manager.load_guild_data(guild_id, 'tasks')
            if not tasks_data:
                return 0

            expired_count = 0
            now = datetime.now(timezone.utc)

            # Check user tasks for expiry
            for user_id, user_tasks in tasks_data.get('user_tasks', {}).items():
                for task_id, user_task in user_tasks.items():
                    if user_task['status'] in ['in_progress', 'submitted']:
                        deadline = datetime.fromisoformat(user_task['deadline'])
                        if now > deadline:
                            user_task['status'] = 'expired'
                            expired_count += 1

            # Check task definitions for expiry
            for task_id, task in tasks_data.get('tasks', {}).items():
                if task['status'] == 'active':
                    expires_at = datetime.fromisoformat(task['expires_at'])
                    if now > expires_at:
                        task['status'] = 'expired'
                        tasks_data['settings']['total_expired'] = tasks_data.get('settings', {}).get('total_expired', 0) + 1

            if expired_count > 0:
                self.data_manager.save_guild_data(guild_id, 'tasks', tasks_data)

            return expired_count

        except Exception as e:
            logger.error(f"Error expiring overdue tasks in guild {guild_id}: {e}")
            return 0

    def get_user_tasks(self, guild_id: int, user_id: int, status_filter: str = None) -> List[Dict]:
        """
        Get tasks for a specific user.

        Args:
            guild_id: Guild ID
            user_id: User ID
            status_filter: Optional status filter

        Returns:
            List of user tasks
        """
        try:
            tasks_data = self.data_manager.load_guild_data(guild_id, 'tasks')
            if not tasks_data:
                return []

            user_tasks = tasks_data.get('user_tasks', {}).get(str(user_id), {})

            if status_filter:
                user_tasks = {k: v for k, v in user_tasks.items() if v['status'] == status_filter}

            # Add task details
            tasks = tasks_data.get('tasks', {})
            result = []
            for task_id, user_task in user_tasks.items():
                task = tasks.get(task_id)
                if task:
                    result.append({
                        'task_id': task_id,
                        'task': task,
                        'user_task': user_task
                    })

            return result

        except Exception as e:
            logger.error(f"Error getting user tasks for user {user_id} in guild {guild_id}: {e}")
            return []

    def get_available_tasks(self, guild_id: int, user_id: int = None, channel_id: str = None) -> List[Dict]:
        """
        Get available tasks for claiming.

        Args:
            guild_id: Guild ID
            user_id: Optional user ID to exclude already claimed tasks
            channel_id: Optional channel filter

        Returns:
            List of available tasks
        """
        try:
            tasks_data = self.data_manager.load_guild_data(guild_id, 'tasks')
            if not tasks_data:
                return []

            config = self.data_manager.load_guild_data(guild_id, 'config')
            global_tasks = config.get('global_tasks', False)

            tasks = []
            for task_id, task in tasks_data.get('tasks', {}).items():
                # Filter by status
                if task['status'] != 'active':
                    continue

                # Filter by channel unless global
                if not global_tasks and channel_id and task.get('channel_id') != channel_id:
                    continue

                # Check if user already claimed
                if user_id:
                    user_tasks = tasks_data.get('user_tasks', {}).get(str(user_id), {})
                    if task_id in user_tasks:
                        continue

                # Check max claims
                if task['max_claims'] != -1 and task['current_claims'] >= task['max_claims']:
                    continue

                # Check expiry
                if datetime.now(timezone.utc) > datetime.fromisoformat(task['expires_at']):
                    continue

                tasks.append(task)

            return tasks

        except Exception as e:
            logger.error(f"Error getting available tasks for guild {guild_id}: {e}")
            return []

    def _atomic_task_operation(self, guild_id: int, operation_func):
        """
        Execute atomic task operations with rollback capability.

        Args:
            guild_id: Guild ID
            operation_func: Function that takes (tasks_data, currency_data) and returns result

        Returns:
            Operation result
        """
        import os
        import tempfile
        import json

        logger = logging.getLogger(__name__)

        try:
            # Load current data
            tasks_data = self.data_manager.load_guild_data(guild_id, 'tasks')
            currency_data = self.data_manager.load_guild_data(guild_id, 'currency')

            # Execute operation
            result = operation_func(tasks_data, currency_data)

            if result['success']:
                # Save atomically
                updates = {'tasks': tasks_data}
                if result.get('currency_updated', False):
                    updates['currency'] = currency_data

                success = self.data_manager.atomic_transaction(guild_id, updates)
                if not success:
                    raise Exception("Failed to save atomic transaction")

            return result

        except Exception as e:
            logger.error(f"Atomic task operation failed: {e}")
            raise

    def get_task_statistics(self, guild_id: int) -> Dict:
        """
        Get task statistics for a guild.

        Args:
            guild_id: Guild ID

        Returns:
            Statistics dictionary
        """
        try:
            tasks_data = self.data_manager.load_guild_data(guild_id, 'tasks')
            if not tasks_data:
                return {}

            tasks = tasks_data.get('tasks', {})
            user_tasks = tasks_data.get('user_tasks', {})
            settings = tasks_data.get('settings', {})

            stats = {
                'total_tasks': len(tasks),
                'active_tasks': len([t for t in tasks.values() if t['status'] == 'active']),
                'completed_tasks': settings.get('total_completed', 0),
                'expired_tasks': settings.get('total_expired', 0),
                'total_user_tasks': sum(len(user_tasks) for user_tasks in user_tasks.values()),
                'pending_submissions': len([ut for user_tasks in user_tasks.values()
                                          for ut in user_tasks.values() if ut['status'] == 'submitted'])
            }

            return stats

        except Exception as e:
            logger.error(f"Error getting task statistics for guild {guild_id}: {e}")
            return {}
