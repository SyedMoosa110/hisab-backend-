from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_transaction_attachment_to_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='address',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='company',
            name='phone',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
