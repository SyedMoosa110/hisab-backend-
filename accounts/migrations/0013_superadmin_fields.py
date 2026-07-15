# Generated manually - adds is_portal_admin and is_blocked to UserProfile, and designates the first superadmin

from django.db import migrations, models

def make_first_user_superadmin(apps, schema_editor):
    UserProfile = apps.get_model('accounts', 'UserProfile')
    # Try finding by email/username first
    profile = UserProfile.objects.filter(user__username='superadmin@gmail.com').first()
    if not profile:
        profile = UserProfile.objects.filter(user__email='superadmin@gmail.com').first()
    if not profile:
        # Fallback to the first created profile
        profile = UserProfile.objects.first()
        
    if profile:
        profile.is_portal_admin = True
        profile.save()

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_delete_googledrivetoken_delete_backuprecord'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='is_portal_admin',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='is_blocked',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(make_first_user_superadmin, reverse_code=migrations.RunPython.noop),
    ]
