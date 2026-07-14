from django.apps import AppConfig

class BackupConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'backup'

    def ready(self):
        # We only import signals. We do NOT start any background threads or APScheduler.
        # This guarantees safety for serverless deployments like Vercel.
        import backup.signals
