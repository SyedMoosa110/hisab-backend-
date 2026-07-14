from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.apps import apps
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

def mark_database_dirty(sender, instance, **kwargs):
    # Avoid circular import
    from backup.models import BackupState, BackupSettings
    
    try:
        settings_obj = BackupSettings.objects.first()
        if settings_obj and not settings_obj.auto_backup_enabled:
            return

        state, _ = BackupState.objects.get_or_create(id=1)
        state.is_dirty = True
        state.last_modified = timezone.now()
        state.save()
        logger.info(f"Database marked dirty by {sender.__name__} modification.")
    except Exception as e:
        logger.error(f"Failed to mark database dirty: {e}")

# We want to connect the signal to all models in the 'accounts' app
# and potentially other important models.
def register_signals():
    try:
        accounts_app = apps.get_app_config('accounts')
        for model in accounts_app.get_models():
            # Don't trigger backup on AuditLog changes to avoid loops or unnecessary backups
            if model.__name__ == 'AuditLog':
                continue
            post_save.connect(mark_database_dirty, sender=model)
            post_delete.connect(mark_database_dirty, sender=model)
            
        logger.info("Backup signals registered successfully.")
    except Exception as e:
        logger.error(f"Failed to register backup signals: {e}")

# Call register_signals when this module is imported (by apps.py ready())
register_signals()
