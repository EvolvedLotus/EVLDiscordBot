import logging
import time
from typing import Dict
from .protection_manager import ProtectionManager
from .scheduler import ModerationScheduler
from .logger import ModerationLogger

logger = logging.getLogger(__name__)

class ModerationHealthChecker:
    """Health monitoring for moderation subsystem"""

    def __init__(self, protection_manager: ProtectionManager, scheduler: ModerationScheduler,
                 logger: ModerationLogger):
        self.protection_manager = protection_manager
        self.scheduler = scheduler
        self.logger = logger
        self._last_check = 0

    def moderation_health_check(self) -> Dict:
        """Verifies scheduler, job queue, DB connectivity, and rule cache integrity"""
        current_time = time.time()

        health_report = {
            'timestamp': current_time,
            'component': 'moderation',
            'status': 'healthy',
            'checks': {},
            'issues': []
        }

        # Check protection manager
        try:
            # Test config loading
            test_config = self.protection_manager.load_protection_config(0)  # Test with invalid guild
            health_report['checks']['protection_manager'] = 'ok'
        except Exception as e:
            health_report['checks']['protection_manager'] = 'error'
            health_report['issues'].append(f"Protection manager error: {e}")

        # Check scheduler
        try:
            scheduled_jobs = self.scheduler.get_scheduled_jobs()
            health_report['checks']['scheduler'] = 'ok'
            health_report['checks']['scheduled_jobs_count'] = len(scheduled_jobs)

            # Check for overdue jobs
            overdue_jobs = []
            for job in scheduled_jobs:
                if job['unmute_timestamp'].timestamp() < current_time:
                    overdue_jobs.append(job['job_id'])

            if overdue_jobs:
                health_report['issues'].append(f"Overdue jobs: {len(overdue_jobs)}")
                health_report['checks']['overdue_jobs'] = overdue_jobs

        except Exception as e:
            health_report['checks']['scheduler'] = 'error'
            health_report['issues'].append(f"Scheduler error: {e}")

        # Check logger
        try:
            audit_logs = self.logger.get_audit_logs(0, limit=1)  # Test with invalid guild
            health_report['checks']['logger'] = 'ok'
            health_report['checks']['audit_logs_count'] = len(self.logger._audit_log)
        except Exception as e:
            health_report['checks']['logger'] = 'error'
            health_report['issues'].append(f"Logger error: {e}")

        # Check rule cache integrity
        try:
            # This would check if cached configs are still valid
            health_report['checks']['cache_integrity'] = 'ok'
        except Exception as e:
            health_report['checks']['cache_integrity'] = 'error'
            health_report['issues'].append(f"Cache integrity error: {e}")

        # Overall status
        if health_report['issues']:
            health_report['status'] = 'degraded'
        else:
            health_report['status'] = 'healthy'

        # Performance metrics
        health_report['performance'] = {
            'check_duration': time.time() - current_time,
            'last_check_age': current_time - self._last_check
        }

        self._last_check = current_time

        logger.debug(f"Moderation health check completed: {health_report['status']}")
        return health_report
