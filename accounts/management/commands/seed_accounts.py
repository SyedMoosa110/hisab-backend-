from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import Account, Category, DuePayment, Party, Transaction


class Command(BaseCommand):
    help = "Create starter admin, accounts, categories, parties, transactions, and due reminders."

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "Admin@12345")

        cash, _ = Account.objects.get_or_create(name="Cash Counter", defaults={"account_type": "cash", "opening_balance": 250000})
        bank, _ = Account.objects.get_or_create(name="Bank Alfalah", defaults={"account_type": "bank", "opening_balance": 750000})
        jazz, _ = Account.objects.get_or_create(name="JazzCash", defaults={"account_type": "jazzcash", "opening_balance": 50000})

        for name in ["Sales", "Online Sales", "Commission"]:
            Category.objects.get_or_create(name=name, category_type="income")
        for name in ["Rent", "Salary", "Bills", "Inventory", "Transport"]:
            Category.objects.get_or_create(name=name, category_type="expense")

        customer, _ = Party.objects.get_or_create(name="Al Madina Store", defaults={"party_type": "customer", "phone": "0300-1111111"})
        vendor, _ = Party.objects.get_or_create(name="Hassan Traders", defaults={"party_type": "vendor", "phone": "0312-2222222"})

        if not Transaction.objects.exists():
            Transaction.objects.create(transaction_type="income", title="Retail sales", category=Category.objects.get(name="Sales", category_type="income"), account=cash, party=customer, amount=185000, date=date.today(), payment_method="cash", reference_number="RC-1001")
            Transaction.objects.create(transaction_type="expense", title="Shop rent", category=Category.objects.get(name="Rent", category_type="expense"), account=bank, party=vendor, amount=62000, date=date.today(), payment_method="bank", reference_number="INV-441")
            Transaction.objects.create(transaction_type="income", title="Online order batch", category=Category.objects.get(name="Online Sales", category_type="income"), account=jazz, amount=72000, date=date.today() - timedelta(days=2), payment_method="jazzcash", reference_number="JZ-552")

        DuePayment.objects.get_or_create(title="Supplier invoice", defaults={"party": vendor, "due_type": "payable", "amount": 230000, "due_date": date.today() + timedelta(days=4)})
        DuePayment.objects.get_or_create(title="Wholesale recovery", defaults={"party": customer, "due_type": "receivable", "amount": 165000, "due_date": date.today() + timedelta(days=6)})

        self.stdout.write(self.style.SUCCESS("Seeded account system. Admin: admin / Admin@12345"))
