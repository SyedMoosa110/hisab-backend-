# Generated manually - adds trial_expiry_date to UserProfile and populates defaults for existing users

from django.db import migrations, models
from datetime import timedelta

def populate_existing_trial_expiry(apps, schema_editor):
    UserProfile = apps.get_model('accounts', 'UserProfile')
    for profile in UserProfile.objects.all():
        if not profile.trial_expiry_date:
            profile.trial_expiry_date = profile.created_at.date() + timedelta(days=90)
            profile.save()

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_superadmin_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='trial_expiry_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(populate_existing_trial_expiry, reverse_code=migrations.RunPython.noop),
    ]
