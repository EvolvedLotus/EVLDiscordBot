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

    async def create_task(self, guild_id, name, description=None, reward=None, duration_hours=None, max_claims=None, is_global=False):
        """Create new task with atomic task_id generation"""

        # Handle dictionary input (from API)
        if isinstance(name, dict):
            data = name
            name = data.get('name')
            description = data.get('description')
            reward = int(data.get('reward', 0))
            duration_hours = int(data.get('duration_hours', 24))
            max_claims = int(data.get('max_claims')) if data.get('max_claims') else None
            is_global = data.get('is_global', False)

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

        task_id = int(task_id)
        
        # Create task in database
        task_data = {
            'task_id': task_id,
            'guild_id': str(guild_id),
            'name': name,
            'description': description or '',
            'reward': reward,
            'duration_hours': duration_hours,
            'max_claims': max_claims,
            'current_claims': 0,
            'status': 'active',
            'is_global': is_global,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'expires_at': expires_at.isoformat()
        }
        
        try:
            # Insert into Supabase
            result = self.data_manager.admin_client.table('tasks').insert(task_data).execute()
            
            logger.info(f"✅ Created task {task_id} in guild {guild_id} (Global: {is_global})")
            
            # Invalidate cache
            if hasattr(self, 'cache_manager') and self.cache_manager:
                self.cache_manager.invalidate(f"tasks:{guild_id}")
                if is_global:
                    self.cache_manager.invalidate("tasks:global")
            
            # Emit SSE event
            if hasattr(self, 'sse_manager') and self.sse_manager:
                await self.sse_manager.broadcast_event(guild_id, {
                    'type': 'task_created',
                    'task_id': task_id,
                    'task': task_data
                })
            
            return task_data
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            raise e

    async def delete_task(self, guild_id: int, task_id: int) -> Dict:
        """Delete task and associated user tasks"""
        guild_id = str(guild_id)
        task_id = int(task_id)  # Ensure it's an int

        try:
            # Verify task exists using Supabase
            task_check = self.data_manager.admin_client.table('tasks') \
                .select('task_id') \
                .eq('task_id', task_id) \
                .eq('guild_id', guild_id) \
                .execute()

            if not task_check.data or len(task_check.data) == 0:
                logger.warning(f"Task {task_id} not found in guild {guild_id}")
                return {'success': False, 'error': "Task not found."}

            # Delete associated user_tasks first
            self.data_manager.admin_client.table('user_tasks') \
                .delete() \
                .eq('task_id', task_id) \
                .eq('guild_id', guild_id) \
                .execute()

            # Delete the main task
            self.data_manager.admin_client.table('tasks') \
                .delete() \
                .eq('task_id', task_id) \
                .eq('guild_id', guild_id) \
                .execute()

            logger.info(f"✅ Deleted task {task_id} from guild {guild_id}")

            # Invalidate cache safely
            if hasattr(self, 'cache_manager') and self.cache_manager:
                self.cache_manager.invalidate(f"tasks:{guild_id}")
                self.cache_manager.invalidate(f"user_tasks:{guild_id}*")

            # Emit SSE event safely
            if hasattr(self, 'sse_manager') and self.sse_manager:
                await self.sse_manager.broadcast_event(guild_id, {
                    'type': 'task_deleted',
                    'task_id': task_id
                })

            return {'success': True}

        except Exception as e:
            logger.exception(f"Delete task error: {e}")
            return {'success': False, 'error': "Failed to delete task."}

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
        Get tasks for a specific user from Supabase.

        Args:
            guild_id: Guild ID
            user_id: User ID
            status_filter: Optional status filter

        Returns:
            List of user tasks
        """
        try:
            # Get user tasks from Supabase
            query = self.data_manager.supabase.table('user_tasks').select('*').eq('guild_id', str(guild_id)).eq('user_id', str(user_id))

            if status_filter:
                query = query.eq('status', status_filter)

            user_tasks_result = query.execute()

            if not user_tasks_result.data:
                return []

            # Get task details for each user task
            result = []
            for user_task_data in user_tasks_result.data:
                task_id = int(user_task_data['task_id'])

                # Get the task details
                task_result = self.data_manager.supabase.table('tasks').select('*').eq('guild_id', str(guild_id)).eq('task_id', str(task_id)).execute()

                if task_result.data:
                    task_data = task_result.data[0]
                    # Convert string dates to datetime objects
                    if isinstance(task_data['expires_at'], str):
                        task_data['expires_at'] = datetime.fromisoformat(task_data['expires_at'].replace('Z', '+00:00'))

                    result.append({
                        'task_id': str(task_id),
                        'task': task_data,
                        'user_task': user_task_data
                    })

            return result

        except Exception as e:
            logger.error(f"Error getting user tasks for user {user_id} in guild {guild_id}: {e}")
            return []

    def get_available_tasks(self, guild_id: int, user_id: int = None, channel_id: str = None) -> List[Dict]:
        """
        Get available tasks for claiming from data_manager.

        Args:
            guild_id: Guild ID
            user_id: Optional user ID to exclude already claimed tasks
            channel_id: Optional channel filter

        Returns:
            List of available tasks
        """
        try:
            # Get tasks from data_manager (same as /list_tasks does)
            tasks_data = self.data_manager.load_guild_data(guild_id, 'tasks')

            if not tasks_data:
                return []

            tasks = tasks_data.get('tasks', {})
            user_tasks = tasks_data.get('user_tasks', {})

            available_tasks = []
            data_modified = False

            for task_id, task in tasks.items():
                # Skip non-active tasks
                if task['status'] != 'active':
                    continue

                # Convert string dates to datetime objects for comparison
                expires_at = task['expires_at']
                if isinstance(expires_at, str):
                    expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))

                # Check expiry
                if datetime.now(timezone.utc) > expires_at:
                    # Auto-expire the task
                    task['status'] = 'expired'
                    data_modified = True
                    continue

                # Check max claims
                if task.get('max_claims', -1) != -1 and task.get('current_claims', 0) >= task['max_claims']:
                    continue

                # Check if user already claimed (for this user only)
                if user_id:
                    guild_user_tasks = user_tasks.get(str(user_id), {})
                    if str(task_id) in guild_user_tasks:
                        continue

                # Add task_id to the task dict for compatibility (don't modify original)
                task_copy = task.copy()
                task_copy['id'] = task_id  # For compatibility with existing code expecting 'id' field

                available_tasks.append(task_copy)

            # Save data only once if modified, after converting datetime back to string
            if data_modified:
                for task_id, task in tasks.items():
                    if isinstance(task.get('expires_at'), datetime):
                        task['expires_at'] = task['expires_at'].isoformat()
                self.data_manager.save_guild_data(guild_id, 'tasks', tasks_data)

            return available_tasks

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
            logger.error(f"Error getting task statistics for guild {guild_id}: {e}")
            return {}

    def get_tasks(self, guild_id: int) -> List[Dict]:
        """
        Get all tasks for a guild (Admin view), including global tasks.
        
        Args:
            guild_id: Guild ID
            
        Returns:
            List of task dictionaries (regular + global)
        """
        try:
            # Get tasks for this guild OR global tasks
            # Note: Supabase/PostgREST doesn't support OR across different columns easily in one query without raw SQL
            # So we'll fetch guild tasks and global tasks separately and merge
            
            # 1. Fetch Guild Tasks
            guild_tasks_result = self.data_manager.admin_client.table('tasks') \
                .select('*') \
                .eq('guild_id', str(guild_id)) \
                .execute()
            
            tasks_list = guild_tasks_result.data if guild_tasks_result.data else []
            
            # 2. Fetch Global Tasks (where is_global is true)
            # We exclude tasks that are already in the list (though they shouldn't be if guild_id matches)
            global_tasks_result = self.data_manager.admin_client.table('tasks') \
                .select('*') \
                .eq('is_global', True) \
                .neq('guild_id', str(guild_id)) \
                .execute()
                
            if global_tasks_result.data:
                tasks_list.extend(global_tasks_result.data)
            
            # Sort by creation date if available, or ID
            # Put global tasks at the top
            tasks_list.sort(key=lambda x: (not x.get('is_global', False), x.get('created_at', '')), reverse=True)
            
            return tasks_list
        except Exception as e:
            logger.error(f"Error getting tasks for guild {guild_id}: {e}")
            return []
