from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

def check_and_run_backup():
    """
    Called by the /api/backup/cron/ endpoint.
    Executes a backup synchronously if the dirty debounce time has passed.
    """
    from backup.models import BackupState, BackupSettings
    from backup.services import BackupService

    try:
        settings_obj = BackupSettings.objects.first()
        if settings_obj and not settings_obj.auto_backup_enabled:
            return False, "Auto-backup disabled"

        state = BackupState.objects.first()
        if not state:
            return False, "No backup state found"

        if state.is_dirty and state.status == 'IDLE':
            # Check 60-second debounce
            time_since_modified = timezone.now() - state.last_modified
            if time_since_modified >= timedelta(seconds=60):
                # Debounce passed, run backup synchronously for Vercel Cron
                service = BackupService()
                service.run_backup()
                return True, "Auto-backup completed"
            else:
                return False, "Debounce period not met"
        return False, "No pending backups"
    except Exception as e:
        logger.error(f"Cron auto-backup error: {e}")
        raise e

def trigger_manual_backup():
    """
    Called by the /api/backup/trigger/ endpoint.
    Executes a backup synchronously.
    """
    from backup.services import BackupService
    from backup.models import BackupState
    
    state, _ = BackupState.objects.get_or_create(id=1)
    if state.status != 'IDLE':
        raise Exception("Backup is already in progress.")
        
    try:
        BackupService().run_backup()
    except Exception as e:
        logger.error(f"Manual backup failed: {e}")
        raise e
