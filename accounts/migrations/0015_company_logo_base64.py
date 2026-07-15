# Generated manually - adds logo_base64 to Company

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_userprofile_trial_expiry_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='logo_base64',
            field=models.TextField(blank=True, null=True),
        ),
    ]
