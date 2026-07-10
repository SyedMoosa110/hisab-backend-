import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_userprofile'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Create Company model
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=255, unique=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        # 2. Add company ForeignKey and role field to UserProfile
        migrations.AddField(
            model_name='userprofile',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='user_profiles', to='accounts.company'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='role',
            field=models.CharField(choices=[('admin', 'Admin'), ('manager', 'Manager'), ('staff', 'Staff')], default='staff', max_length=20),
        ),
        # 3. Add company ForeignKey to business models
        migrations.AddField(
            model_name='account',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='accounts', to='accounts.company'),
        ),
        migrations.AddField(
            model_name='category',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='categories', to='accounts.company'),
        ),
        migrations.AddField(
            model_name='party',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='parties', to='accounts.company'),
        ),
        migrations.AddField(
            model_name='transaction',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='accounts.company'),
        ),
        migrations.AddField(
            model_name='duepayment',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='due_payments', to='accounts.company'),
        ),
        migrations.AddField(
            model_name='note',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notes', to='accounts.company'),
        ),
        migrations.AddField(
            model_name='backuprecord',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='backups', to='accounts.company'),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='audit_logs', to='accounts.company'),
        ),
        migrations.AddField(
            model_name='stock',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='stocks', to='accounts.company'),
        ),
        migrations.AddField(
            model_name='sale',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sale_records', to='accounts.company'),
        ),
    ]
