from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

def link_existing_to_first_user(apps, schema_editor):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    first_user = User.objects.first()
    
    GoogleDriveCredentials = apps.get_model('backup', 'GoogleDriveCredentials')
    BackupSettings = apps.get_model('backup', 'BackupSettings')
    BackupState = apps.get_model('backup', 'BackupState')
    BackupLog = apps.get_model('backup', 'BackupLog')

    if not first_user:
        # If no user exists, we must clear credentials/settings/states to avoid constraint issues
        GoogleDriveCredentials.objects.all().delete()
        BackupSettings.objects.all().delete()
        BackupState.objects.all().delete()
        BackupLog.objects.all().delete()
        return

    # Link existing GoogleDriveCredentials
    creds = list(GoogleDriveCredentials.objects.all())
    if creds:
        creds[0].user = first_user
        creds[0].save()
        if len(creds) > 1:
            for c in creds[1:]:
                c.delete()

    # Link existing BackupSettings
    settings_list = list(BackupSettings.objects.all())
    if settings_list:
        settings_list[0].user = first_user
        settings_list[0].save()
        if len(settings_list) > 1:
            for s in settings_list[1:]:
                s.delete()

    # Link existing BackupState
    states = list(BackupState.objects.all())
    if states:
        states[0].user = first_user
        states[0].save()
        if len(states) > 1:
            for st in states[1:]:
                st.delete()

    # Link existing BackupLog
    BackupLog.objects.all().update(user=first_user)

class Migration(migrations.Migration):

    dependencies = [
        ('backup', '0002_googledrivecredentials_device_id'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Add fields as nullable first
        migrations.AddField(
            model_name='googledrivecredentials',
            name='user',
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='google_drive_credentials',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='backupsettings',
            name='user',
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='backup_settings',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='backupstate',
            name='user',
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='backup_state',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='backuplog',
            name='user',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='backup_logs',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        
        # 2. Run data migration to link existing records to first user
        migrations.RunPython(link_existing_to_first_user),
        
        # 3. Alter fields to be non-nullable
        migrations.AlterField(
            model_name='googledrivecredentials',
            name='user',
            field=models.OneToOneField(
                null=False,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='google_drive_credentials',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='backupsettings',
            name='user',
            field=models.OneToOneField(
                null=False,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='backup_settings',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='backupstate',
            name='user',
            field=models.OneToOneField(
                null=False,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='backup_state',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
