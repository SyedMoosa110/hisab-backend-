# Generated manually for Vercel
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('backup', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='googledrivecredentials',
            name='device_id',
            field=models.CharField(default='default-device', max_length=255),
        ),
    ]
