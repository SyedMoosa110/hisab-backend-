from django.apps import AppConfig

class BackupConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'backup'

    def ready(self):
        import backup.signals
        from backup.scheduler import start_scheduler
        
        # We start the APScheduler when the app is ready. 
        # For Django's development server, to avoid starting it twice (once for the 
        # parent process and once for the reloader), we check RUN_MAIN.
        import sys
        if 'runserver' in sys.argv:
            import os
            if os.environ.get('RUN_MAIN') == 'true':
                start_scheduler()
        else:
            # If running via gunicorn, uwsgi, or custom scripts
            start_scheduler()
