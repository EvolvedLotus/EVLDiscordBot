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

    def create_task(self, guild_id: int, task_data: Dict) -> Dict:
        """
        Create a new task with validation.

        Args:
            guild_id: Guild ID
            task_data: Task data dictionary

        Returns:
            Created task data or error dict
        """
        try:
            # Validate required fields
            required_fields = ['name', 'description', 'reward', 'duration_hours']
            for field in required_fields:
                if field not in task_data:
                    return {'success': False, 'error': f'Missing required field: {field}'}

            # Validate data types and ranges
            try:
                reward = int(task_data['reward'])
                duration_hours = int(task_data['duration_hours'])
                if reward < 0 or duration_hours < 1:
                    raise ValueError("Invalid reward or duration values")
            except (ValueError, TypeError):
                return {'success': False, 'error': 'Invalid reward or duration format'}

            # Get next task ID
            tasks_data = self.data_manager.load_guild_data(guild_id, 'tasks')
            if not tasks_data:
                tasks_data = {'tasks': {}, 'user_tasks': {}, 'settings': {}}

            next_id = tasks_data.get('settings', {}).get('next_task_id', 1)
            task_id = str(next_id)

            # Calculate expiry
            created = datetime.now(timezone.utc)
            expires_at = created + timedelta(hours=duration_hours)

            # Prepare task data
            task = {
                'id': int(task_id),
                'name': str(task_data['name']).strip(),
                'description': str(task_data['description']).strip(),
                'reward': reward,
                'duration_hours': duration_hours,
                'status': 'active',
                'created_at': created.isoformat(),
                'expires_at': expires_at.isoformat(),
                'channel_id': str(task_data.get('channel_id', '')),
                'max_claims': int(task_data.get('max_claims', -1)),
                'current_claims': 0,
                'assigned_users': [],
                'category': str(task_data.get('category', 'General')),
                'role_name': task_data.get('role_name'),
                'message_id': None
            }

            # Save task
            if 'tasks' not in tasks_data:
                tasks_data['tasks'] = {}
            tasks_data['tasks'][task_id] = task

            # Update next task ID
            if 'settings' not in tasks_data:
                tasks_data['settings'] = {}
            tasks_data['settings']['next_task_id'] = next_id + 1

            success = self.data_manager.save_guild_data(guild_id, 'tasks', tasks_data)

            if success:
                logger.info(f"Task created: {task_id} in guild {guild_id}")
                return {'success': True, 'task': task}
            else:
                return {'success': False, 'error': 'Failed to save task'}

        except Exception as e:
            logger.error(f"Error creating task in guild {guild_id}: {e}")
            return {'success': False, 'error': str(e)}

    def claim_task(self, guild_id: int, user_id: int, task_id: str) -> Dict:
        """
        Claim a task for a user with atomic operations.

        Args:
            guild_id: Guild ID
            user_id: User ID
            task_id: Task ID

        Returns:
            Result dictionary
        """
        def claim_operation(tasks_data, currency_data):
            task = tasks_data.get('tasks', {}).get(task_id)

            if not task:
                return {'success': False, 'error': "Task not found."}

            # Validation checks
            if task['status'] != 'active':
                return {'success': False, 'error': f"This task is no longer active (Status: {task['status']})."}

            # Check expiry
            if datetime.now(timezone.utc) > datetime.fromisoformat(task['expires_at']):
                task['status'] = 'expired'
                tasks_data['settings']['total_expired'] = tasks_data.get('settings', {}).get('total_expired', 0) + 1
                return {'success': False, 'error': "This task has expired."}

            # Check max claims
            if task['max_claims'] != -1 and task['current_claims'] >= task['max_claims']:
                return {'success': False, 'error': "This task has reached maximum claims."}

            # Check if user already claimed
            user_tasks = tasks_data.get('user_tasks', {}).get(str(user_id), {})
            if task_id in user_tasks:
                status = user_tasks[task_id]['status']
                return {'success': False, 'error': f"You have already claimed this task (Status: {status})."}

            # Check user task limit
            settings = tasks_data.get('settings', {})
            max_per_user = settings.get('max_tasks_per_user', 10)
            active_count = sum(
                1 for t in user_tasks.values()
                if t['status'] in ['claimed', 'in_progress', 'submitted']
            )
            if active_count >= max_per_user:
                return {'success': False, 'error': f"You have reached the maximum of {max_per_user} active tasks."}

            # Claim task
            claimed_at = datetime.now(timezone.utc)
            deadline = claimed_at + timedelta(hours=task['duration_hours'])

            tasks_data.setdefault('user_tasks', {}).setdefault(str(user_id), {})[task_id] = {
                'claimed_at': claimed_at.isoformat(),
                'deadline': deadline.isoformat(),
                'status': 'in_progress',
                'proof_message_id': None,
                'proof_attachments': [],
                'proof_content': '',
                'submitted_at': None,
                'completed_at': None,
                'notes': ''
            }

            # Update task claims
            task['current_claims'] += 1
            task['assigned_users'].append(str(user_id))

            return {
                'success': True,
                'task': task,
                'deadline': deadline,
                'claimed_at': claimed_at
            }

        # Execute atomic operation
        try:
            result = self._atomic_task_operation(guild_id, claim_operation)
            return result
        except Exception as e:
            logger.error(f"Atomic task claim failed: {e}")
            return {'success': False, 'error': "An error occurred while claiming the task. Please try again."}

    def submit_task(self, guild_id: int, user_id: int, task_id: str, proof_data: Dict) -> Dict:
        """
        Submit a task for review.

        Args:
            guild_id: Guild ID
            user_id: User ID
            task_id: Task ID
            proof_data: Proof submission data

        Returns:
            Result dictionary
        """
        def submit_operation(tasks_data, currency_data):
            user_tasks = tasks_data.get('user_tasks', {}).get(str(user_id), {})
            user_task = user_tasks.get(task_id)

            if not user_task:
                return {'success': False, 'error': "You haven't claimed this task."}

            if user_task['status'] != 'in_progress':
                return {'success': False, 'error': f"Task is not in progress (Status: {user_task['status']})."}

            # Check deadline
            deadline = datetime.fromisoformat(user_task['deadline'])
            if datetime.now(timezone.utc) > deadline:
                user_task['status'] = 'expired'
                return {'success': False, 'error': "Task deadline has passed."}

            # Update submission
            user_task['status'] = 'submitted'
            user_task['submitted_at'] = datetime.now(timezone.utc).isoformat()
            user_task['proof_content'] = proof_data.get('content', '')
            user_task['proof_attachments'] = proof_data.get('attachments', [])
            user_task['proof_message_id'] = proof_data.get('message_id')

            return {'success': True, 'user_task': user_task}

        try:
            result = self._atomic_task_operation(guild_id, submit_operation)
            return result
        except Exception as e:
            logger.error(f"Task submission failed: {e}")
            return {'success': False, 'error': "Failed to submit task."}

    def approve_task(self, guild_id: int, user_id: int, task_id: str, approver_id: int) -> Dict:
        """
        Approve a submitted task and award reward.

        Args:
            guild_id: Guild ID
            user_id: User ID
            task_id: Task ID
            approver_id: Admin approving the task

        Returns:
            Result dictionary
        """
        def approve_operation(tasks_data, currency_data):
            user_tasks = tasks_data.get('user_tasks', {}).get(str(user_id), {})
            user_task = user_tasks.get(task_id)

            if not user_task:
                return {'success': False, 'error': "Task not found for user."}

            if user_task['status'] != 'submitted':
                return {'success': False, 'error': f"Task is not submitted (Status: {user_task['status']})."}

            task = tasks_data.get('tasks', {}).get(task_id)
            if not task:
                return {'success': False, 'error': "Task definition not found."}

            # Award reward
            reward_amount = task['reward']
            description = f"Task completion: {task['name']}"

            # Log transaction
            transaction_result = self.transaction_manager.log_transaction(
                guild_id=guild_id,
                user_id=user_id,
                amount=reward_amount,
                balance_before=0,  # Will be calculated by transaction manager
                balance_after=0,   # Will be calculated by transaction manager
                transaction_type='task',
                description=description,
                metadata={
                    'task_id': task_id,
                    'task_name': task['name'],
                    'approver_id': approver_id
                }
            )

            if not transaction_result:
                return {'success': False, 'error': "Failed to log transaction."}

            # Update task status
            user_task['status'] = 'accepted'
            user_task['completed_at'] = datetime.now(timezone.utc).isoformat()

            # Update task statistics
            tasks_data['settings']['total_completed'] = tasks_data.get('settings', {}).get('total_completed', 0) + 1

            return {
                'success': True,
                'reward_amount': reward_amount,
                'transaction_id': transaction_result
            }

        try:
            result = self._atomic_task_operation(guild_id, approve_operation)
            return result
        except Exception as e:
            logger.error(f"Task approval failed: {e}")
            return {'success': False, 'error': "Failed to approve task."}

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
