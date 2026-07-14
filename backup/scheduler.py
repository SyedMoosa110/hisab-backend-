from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

def check_and_run_backup():
    # Import inside to avoid circular imports / AppRegistryNotReady
    from backup.models import BackupState, BackupSettings
    from backup.services import BackupService

    try:
        settings_obj = BackupSettings.objects.first()
        if settings_obj and not settings_obj.auto_backup_enabled:
            return

        state = BackupState.objects.first()
        if not state:
            return

        if state.is_dirty and state.status == 'IDLE':
            # Check 60-second debounce
            time_since_modified = timezone.now() - state.last_modified
            if time_since_modified >= timedelta(seconds=60):
                # Debounce passed, run backup
                service = BackupService()
                service.run_backup()
    except Exception as e:
        logger.error(f"Scheduler error: {e}")

def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(check_and_run_backup, 'interval', seconds=10, id='auto_backup_checker', replace_existing=True)
        scheduler.start()

def trigger_manual_backup():
    from backup.services import BackupService
    from backup.models import BackupState
    
    state, _ = BackupState.objects.get_or_create(id=1)
    if state.status != 'IDLE':
        raise Exception("Backup is already in progress.")
        
    def run_manual():
        try:
            BackupService().run_backup()
        except Exception as e:
            logger.error(f"Manual backup failed: {e}")

    scheduler.add_job(run_manual, 'date', run_date=timezone.now(), id='manual_backup', replace_existing=True)
