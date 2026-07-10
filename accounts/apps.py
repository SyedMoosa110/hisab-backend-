from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        import os
        # Only run in the active process (not the loader) to avoid double execution
        if os.environ.get('RUN_MAIN') == 'true':
            try:
                from django.core.management import call_command
                print("--- Automatically generating migrations ---")
                call_command('makemigrations', 'accounts')
                print("--- Automatically applying migrations ---")
                call_command('migrate')
                print("--- Migrations completed successfully! ---")
            except Exception as e:
                print(f"Auto-migration failed: {e}")
