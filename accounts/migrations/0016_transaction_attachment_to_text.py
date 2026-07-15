from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_company_logo_base64'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='attachment',
            field=models.TextField(blank=True, null=True),
        ),
    ]
