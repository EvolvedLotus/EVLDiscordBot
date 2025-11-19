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
