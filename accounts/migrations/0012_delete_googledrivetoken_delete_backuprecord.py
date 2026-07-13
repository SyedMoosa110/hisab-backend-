# Generated manually - removes GoogleDriveToken and BackupRecord tables

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_backuprecord_googledrivetoken'),
    ]

    operations = [
        migrations.DeleteModel(
            name='BackupRecord',
        ),
        migrations.DeleteModel(
            name='GoogleDriveToken',
        ),
    ]
