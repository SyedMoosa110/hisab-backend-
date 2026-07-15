from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.apps import apps
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

def mark_database_dirty(sender, instance, **kwargs):
    from backup.models import BackupState, BackupSettings
    
    try:
        company = getattr(instance, 'company', None)
        if not company:
            return
            
        from django.contrib.auth.models import User
        users = User.objects.filter(profile__company=company)
        
        for user in users:
            settings_obj = BackupSettings.objects.filter(user=user).first()
            if settings_obj and not settings_obj.auto_backup_enabled:
                continue

            state, _ = BackupState.objects.get_or_create(user=user)
            state.is_dirty = True
            state.last_modified = timezone.now()
            state.save()
            logger.info(f"Database marked dirty for user {user.username} by {sender.__name__} modification.")
    except Exception as e:
        logger.error(f"Failed to mark database dirty: {e}")

def register_signals():
    try:
        accounts_app = apps.get_app_config('accounts')
        for model in accounts_app.get_models():
            if model.__name__ == 'AuditLog':
                continue
            post_save.connect(mark_database_dirty, sender=model)
            post_delete.connect(mark_database_dirty, sender=model)
            
        logger.info("Backup signals registered successfully.")
    except Exception as e:
        logger.error(f"Failed to register backup signals: {e}")

register_signals()
