import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Callable
import discord

logger = logging.getLogger(__name__)

class ModerationScheduler:
    """Handles scheduling of moderation-related jobs like unmute timers"""

    def __init__(self, bot):
        self.bot = bot
        self._scheduled_jobs = {}  # job_id -> job_info
        self._running = False

    def schedule_unmute_job(self, guild_id: int, user_id: int, unmute_timestamp: datetime) -> str:
        """Schedules an unmute job for a user"""
        job_id = f"unmute_{guild_id}_{user_id}_{int(unmute_timestamp.timestamp())}"

        job_info = {
            'job_id': job_id,
            'guild_id': guild_id,
            'user_id': user_id,
            'unmute_timestamp': unmute_timestamp,
            'job_type': 'unmute',
            'created_at': datetime.now()
        }

        self._scheduled_jobs[job_id] = job_info

        # Schedule the actual task
        delay = (unmute_timestamp - datetime.now()).total_seconds()
        if delay > 0:
            asyncio.create_task(self._schedule_unmute_task(job_id, delay))

        logger.info(f"Unmute job scheduled: {job_info}")
        return job_id

    async def _schedule_unmute_task(self, job_id: str, delay: float):
        """Schedules the actual unmute task with delay"""
        try:
            await asyncio.sleep(delay)

            # Check if job still exists (might have been cancelled)
            if job_id not in self._scheduled_jobs:
                return

            job_info = self._scheduled_jobs[job_id]
            await self._execute_unmute_job(job_info)

            # Remove completed job
            del self._scheduled_jobs[job_id]

        except Exception as e:
            logger.error(f"Failed to execute unmute job {job_id}: {e}")

    async def _execute_unmute_job(self, job_info: Dict):
        """Executes the unmute job"""
        try:
            guild_id = job_info['guild_id']
            user_id = job_info['user_id']

            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.warning(f"Guild {guild_id} not found for unmute job")
                return

            user = guild.get_member(user_id)
            if not user:
                logger.warning(f"User {user_id} not found in guild {guild_id} for unmute job")
                return

            # Check if user is still timed out
            if user.is_timed_out():
                # Remove timeout
                await user.timeout(None, reason="Automatic unmute - timeout expired")
                logger.info(f"Automatically unmuted user {user_id} in guild {guild_id}")
            else:
                logger.debug(f"User {user_id} in guild {guild_id} is no longer timed out")

        except Exception as e:
            logger.error(f"Failed to execute unmute for user {job_info['user_id']}: {e}")

    def cancel_job(self, job_id: str) -> bool:
        """Cancels a scheduled job"""
        if job_id in self._scheduled_jobs:
            del self._scheduled_jobs[job_id]
            logger.info(f"Job cancelled: {job_id}")
            return True
        return False

    def get_scheduled_jobs(self) -> List[Dict]:
        """Returns list of all scheduled jobs"""
        return list(self._scheduled_jobs.values())

    def get_job_info(self, job_id: str) -> Dict:
        """Returns information about a specific job"""
        return self._scheduled_jobs.get(job_id)

    async def cleanup_expired_jobs(self):
        """Removes jobs that have already executed"""
        current_time = datetime.now()
        expired_jobs = []

        for job_id, job_info in self._scheduled_jobs.items():
            if job_info['unmute_timestamp'] < current_time:
                expired_jobs.append(job_id)

        for job_id in expired_jobs:
            del self._scheduled_jobs[job_id]
            logger.debug(f"Cleaned up expired job: {job_id}")

        if expired_jobs:
            logger.info(f"Cleaned up {len(expired_jobs)} expired moderation jobs")

    async def execute_scheduled_jobs(self):
        """Execute all pending scheduled jobs"""

        try:
            now = datetime.now()

            # Get pending jobs with lock (simulated - in real implementation would use database)
            pending_jobs = []
            for job_id, job_info in self._scheduled_jobs.items():
                if job_info['unmute_timestamp'] <= now:
                    pending_jobs.append(job_info)

            for job in pending_jobs:
                try:
                    # Execute job based on type
                    if job['job_type'] == 'unmute':
                        await self._execute_unmute(job)
                    elif job['job_type'] == 'unban':
                        await self._execute_unban(job)
                    elif job['job_type'] == 'expire_strike':
                        await self._execute_expire_strike(job)

                    # Remove completed job
                    del self._scheduled_jobs[job['job_id']]

                    logger.info(f"Executed scheduled job: {job['job_id']} ({job['job_type']})")

                except Exception as e:
                    logger.exception(f"Failed to execute job {job['job_id']}: {e}")
                    # Don't remove failed jobs so they can be retried

        except Exception as e:
            logger.exception(f"Scheduled jobs execution error: {e}")

    async def _execute_unmute(self, job):
        """Execute unmute job"""
        guild = self.bot.get_guild(job['guild_id'])
        if not guild:
            return

        member = guild.get_member(job['user_id'])
        if not member:
            return

        # Remove timeout
        await member.timeout(None, reason="Scheduled unmute")

        # Update moderation_actions (would need database integration)
        logger.info(f"Executed unmute for user {job['user_id']} in guild {job['guild_id']}")

    async def _execute_unban(self, job):
        """Execute unban job"""
        guild = self.bot.get_guild(job['guild_id'])
        if not guild:
            return

        try:
            user = await self.bot.fetch_user(job['user_id'])
            await guild.unban(user, reason="Scheduled unban")
            logger.info(f"Executed unban for user {job['user_id']} in guild {job['guild_id']}")
        except discord.NotFound:
            logger.warning(f"User {job['user_id']} not found for unban in guild {job['guild_id']}")

    async def _execute_expire_strike(self, job):
        """Execute strike expiration job"""
        # Mark strike as expired (would need database integration)
        logger.info(f"Executed strike expiration for strike {job.get('strike_id', 'unknown')}")

    async def execute_database_jobs(self, data_manager, bot):
        """Execute pending scheduled jobs from database"""
        try:
            now = datetime.now()

            # Get pending jobs from database
            pending_jobs_result = data_manager.supabase.table('scheduled_jobs').select('*').eq('is_executed', False).lte('execute_at', now.isoformat()).execute()

            if not pending_jobs_result.data:
                return  # No pending jobs

            pending_jobs = pending_jobs_result.data

            for job in pending_jobs:
                try:
                    job_id = job['job_id']

                    # Execute job based on type
                    if job['job_type'] == 'unmute':
                        await self._execute_database_unmute(job, bot)
                    elif job['job_type'] == 'unban':
                        await self._execute_database_unban(job, bot)
                    elif job['job_type'] == 'remove_role':
                        await self._execute_remove_role(job, bot)
                    else:
                        logger.warning(f"Unknown job type: {job['job_type']} for job {job_id}")
                        continue

                    # Mark job as executed
                    data_manager.supabase.table('scheduled_jobs').update({
                        'is_executed': True,
                        'executed_at': now.isoformat()
                    }).eq('job_id', job_id).execute()

                    logger.info(f"Executed database scheduled job: {job_id} ({job['job_type']})")

                except Exception as e:
                    logger.exception(f"Failed to execute database job {job['job_id']}: {e}")
                    # Don't mark failed jobs as executed so they can be retried

        except Exception as e:
            logger.exception(f"Error executing database scheduled jobs: {e}")

    async def _execute_database_unmute(self, job, bot):
        """Execute database-based unmute job"""
        guild = bot.get_guild(job['guild_id'])
        if not guild:
            return

        member = guild.get_member(job['user_id'])
        if not member:
            return

        # Remove timeout
        await member.timeout(None, reason="Scheduled unmute")

        logger.info(f"Executed database unmute for user {job['user_id']} in guild {job['guild_id']}")

    async def _execute_database_unban(self, job, bot):
        """Execute database-based unban job"""
        guild = bot.get_guild(job['guild_id'])
        if not guild:
            return

        try:
            user = await bot.fetch_user(job['user_id'])
            await guild.unban(user, reason="Scheduled unban")
            logger.info(f"Executed database unban for user {job['user_id']} in guild {job['guild_id']}")
        except discord.NotFound:
            logger.warning(f"User {job['user_id']} not found for unban in guild {job['guild_id']}")

    async def _execute_remove_role(self, job, bot):
        """Execute role removal job for redeemed items"""
        guild = bot.get_guild(job['guild_id'])
        if not guild:
            return

        member = guild.get_member(job['user_id'])
        if not member:
            logger.warning(f"Member {job['user_id']} not found in guild {job['guild_id']} for role removal")
            return

        role_id = job['job_data'].get('role_id')
        if not role_id:
            logger.warning(f"No role_id in job data for job {job['job_id']}")
            return

        role = guild.get_role(int(role_id))
        if not role:
            logger.warning(f"Role {role_id} not found in guild {job['guild_id']}")
            return

        # Check if member still has the role
        if role in member.roles:
            try:
                await member.remove_roles(role, reason=f"Item redemption expired: {job['job_data'].get('item_name', 'Unknown item')}")
                logger.info(f"Removed expired role {role.name} from user {job['user_id']} in guild {job['guild_id']}")
            except discord.Forbidden:
                logger.warning(f"Cannot remove role {role.name} from user {job['user_id']} - insufficient permissions")
            except Exception as e:
                logger.error(f"Failed to remove role {role.name} from user {job['user_id']}: {e}")
        else:
            logger.debug(f"User {job['user_id']} no longer has role {role.name} - already removed")
