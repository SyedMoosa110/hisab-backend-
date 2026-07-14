import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from backup.models import GoogleDriveCredentials, BackupSettings, BackupState, BackupLog

print("=== ACTUAL TABLES IN DB ===")
tables = connection.introspection.table_names()
for t in sorted(tables):
    print(t)

print("\n=== EXPECTED TABLES ===")
print("GoogleDriveCredentials:", GoogleDriveCredentials._meta.db_table)
print("BackupSettings:", BackupSettings._meta.db_table)
print("BackupState:", BackupState._meta.db_table)
print("BackupLog:", BackupLog._meta.db_table)
