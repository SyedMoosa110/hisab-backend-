from django.db import migrations

def migrate_existing_data_to_default_company(apps, schema_editor):
    Company = apps.get_model('accounts', 'Company')
    UserProfile = apps.get_model('accounts', 'UserProfile')
    Account = apps.get_model('accounts', 'Account')
    Category = apps.get_model('accounts', 'Category')
    Party = apps.get_model('accounts', 'Party')
    Transaction = apps.get_model('accounts', 'Transaction')
    DuePayment = apps.get_model('accounts', 'DuePayment')
    Note = apps.get_model('accounts', 'Note')
    BackupRecord = apps.get_model('accounts', 'BackupRecord')
    AuditLog = apps.get_model('accounts', 'AuditLog')
    Stock = apps.get_model('accounts', 'Stock')
    Sale = apps.get_model('accounts', 'Sale')

    # If there is any existing data, create a default company
    has_any_data = (
        UserProfile.objects.exists() or Account.objects.exists() or
        Category.objects.exists() or Party.objects.exists() or
        Transaction.objects.exists() or DuePayment.objects.exists() or
        Note.objects.exists() or Stock.objects.exists()
    )

    if has_any_data:
        default_company, _ = Company.objects.get_or_create(name="Default Business")
        
        # Link all orphaned items to the default company
        for model in [UserProfile, Account, Category, Party, Transaction, DuePayment, Note, BackupRecord, AuditLog, Stock, Sale]:
            model.objects.filter(company__isnull=True).update(company=default_company)
        
        # Ensure default profiles are marked as admin
        UserProfile.objects.filter(company=default_company).update(role='admin')

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_userprofile_business_name_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_existing_data_to_default_company),
    ]
