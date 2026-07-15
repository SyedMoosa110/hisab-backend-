from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

def check_and_run_backup():
    """
    Called by the /api/backup/cron/ endpoint.
    Loops through all users with auto-backup enabled and runs backups if the debounce period has met.
    """
    from backup.models import BackupSettings, BackupState
    from backup.services import BackupService

    try:
        settings_objs = BackupSettings.objects.filter(auto_backup_enabled=True)
        ran_any = False
        messages = []

        for settings_obj in settings_objs:
            user = settings_obj.user
            try:
                state, _ = BackupState.objects.get_or_create(user=user)
                if state.is_dirty and state.status == 'IDLE':
                    # Check 60-second debounce
                    time_since_modified = timezone.now() - state.last_modified
                    if time_since_modified >= timedelta(seconds=60):
                        service = BackupService(user=user)
                        service.run_backup()
                        ran_any = True
                        messages.append(f"Auto-backup completed for user {user.username}")
                    else:
                        messages.append(f"Debounce period not met for user {user.username}")
            except Exception as e:
                logger.error(f"Cron auto-backup error for user {user.username}: {e}")
                messages.append(f"Error for user {user.username}: {str(e)}")

        if not messages:
            return False, "No users have pending auto-backups."
        return ran_any, "; ".join(messages)

    except Exception as e:
        logger.error(f"Cron auto-backup failure: {e}")
        raise e

def trigger_manual_backup(user):
    """
    Called by the /api/backup/trigger/ endpoint.
    Executes a backup synchronously.
    """
    from backup.services import BackupService
    from backup.models import BackupState
    
    state, _ = BackupState.objects.get_or_create(user=user)
    if state.status != 'IDLE':
        raise Exception("Backup is already in progress.")
        
    try:
        BackupService(user=user).run_backup()
    except Exception as e:
        logger.error(f"Manual backup failed for user {user.username}: {e}")
        raise e
