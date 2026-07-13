# backups_cron.py or similar script
import os
import sys
import django

# Setup Django environment if run as standalone script
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

from django.utils import timezone
from accounts.models import GoogleDriveToken
from accounts.backup_utils import run_backup_for_user

def run_all_automated_backups():
    """
    Finds all users with active daily automatic backup enabled and triggers a Google Drive backup.
    """
    tokens = GoogleDriveToken.objects.filter(backup_enabled=True)
    success_count = 0
    fail_count = 0

    print(f"[{timezone.now()}] Starting automated daily backup for {tokens.count()} users...")
    
    for token in tokens:
        try:
            print(f"Running backup for user: {token.user.email}")
            run_backup_for_user(token.user)
            success_count += 1
        except Exception as e:
            print(f"Failed backup for user {token.user.email}: {str(e)}")
            fail_count += 1

    print(f"[{timezone.now()}] Automated backups finished. Success: {success_count}, Failed: {fail_count}")

if __name__ == "__main__":
    run_all_automated_backups()
