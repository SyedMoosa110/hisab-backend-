from decimal import Decimal
from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Company(TimeStampedModel):
    name = models.CharField(max_length=255, unique=True)
    is_upgraded = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Account(TimeStampedModel):
    ACCOUNT_TYPES = [
        ("cash", "Cash"),
        ("bank", "Bank"),
        ("easypaisa", "Easypaisa"),
        ("jazzcash", "JazzCash"),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="accounts", null=True, blank=True)
    name = models.CharField(max_length=120)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Category(TimeStampedModel):
    CATEGORY_TYPES = [("income", "Income"), ("expense", "Expense")]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="categories", null=True, blank=True)
    name = models.CharField(max_length=120)
    category_type = models.CharField(max_length=10, choices=CATEGORY_TYPES)
    color = models.CharField(max_length=20, default="#2563eb")

    class Meta:
        verbose_name_plural = "Categories"
        unique_together = ("name", "category_type")

    def __str__(self):
        return f"{self.name} ({self.category_type})"


class Party(TimeStampedModel):
    PARTY_TYPES = [
        ("customer", "Customer"),
        ("vendor", "Vendor"),
        ("staff", "Staff"),
        ("other", "Other"),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="parties", null=True, blank=True)
    name = models.CharField(max_length=160)
    party_type = models.CharField(max_length=20, choices=PARTY_TYPES, default="other")
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Transaction(TimeStampedModel):
    TRANSACTION_TYPES = [("income", "Income"), ("expense", "Expense")]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="transactions", null=True, blank=True)
    PAYMENT_METHODS = [
        ("cash", "Cash"),
        ("bank", "Bank Transfer"),
        ("card", "Card"),
        ("easypaisa", "Easypaisa"),
        ("jazzcash", "JazzCash"),
        ("cheque", "Cheque"),
        ("other", "Other"),
    ]

    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    title = models.CharField(max_length=180)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="transactions")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transactions")
    party = models.ForeignKey(Party, on_delete=models.SET_NULL, blank=True, null=True, related_name="transactions")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    reference_number = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    attachment = models.FileField(upload_to="receipts/%Y/%m/", blank=True, null=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["date", "transaction_type"]),
            models.Index(fields=["category", "date"]),
            models.Index(fields=["payment_method", "date"]),
            models.Index(fields=["account", "date"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.amount}"


class DuePayment(TimeStampedModel):
    DUE_TYPES = [("payable", "Payable"), ("receivable", "Receivable")]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="due_payments", null=True, blank=True)
    STATUS = [("pending", "Pending"), ("paid", "Paid"), ("overdue", "Overdue")]

    party = models.ForeignKey(Party, on_delete=models.SET_NULL, blank=True, null=True)
    due_type = models.CharField(max_length=20, choices=DUE_TYPES)
    title = models.CharField(max_length=180)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["due_date"]

    def __str__(self):
        return self.title


class Note(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="notes", null=True, blank=True)
    title = models.CharField(max_length=180)
    body = models.TextField()
    reminder_date = models.DateField(blank=True, null=True)
    is_done = models.BooleanField(default=False)

    def __str__(self):
        return self.title



class AuditLog(TimeStampedModel):
    ACTIONS = [("created", "Created"), ("updated", "Updated"), ("deleted", "Deleted")]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="audit_logs", null=True, blank=True)

    model_name = models.CharField(max_length=80)
    object_id = models.PositiveIntegerField(blank=True, null=True)
    action = models.CharField(max_length=20, choices=ACTIONS)
    summary = models.TextField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]


class Stock(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="stocks", null=True, blank=True)
    name = models.CharField(max_length=120, unique=True)
    quantity = models.IntegerField(default=0)  # Total quantity of stock added
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    def __str__(self):
        return self.name


class Sale(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="sale_records", null=True, blank=True)
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name="sales")
    quantity = models.IntegerField()
    sale_price = models.DecimalField(max_digits=14, decimal_places=2)
    total_price = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="sales")
    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales")
    notes = models.TextField(blank=True)
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    customer_phone = models.CharField(max_length=50, blank=True, null=True)
    customer_address = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        self.total_price = Decimal(self.quantity) * Decimal(self.sale_price)
        
        # Ensure category named "Sales" exists
        sales_category, _ = Category.objects.get_or_create(
            name="Sales",
            category_type="income",
            defaults={"color": "#10b981"}
        )

        # Handle automatic creation of Party record
        party = None
        if self.customer_name:
            clean_name = self.customer_name.strip()
            # Try to match by phone number if provided
            if self.customer_phone:
                party = Party.objects.filter(company=self.company, phone=self.customer_phone).first()
            
            # If not matched by phone, try to match by name
            if not party:
                party = Party.objects.filter(company=self.company, name__iexact=clean_name).first()
            if not party:
                party = Party.objects.filter(company=self.company, name__istartswith=clean_name).first()
            
            # If still not found, create a new customer party record with customer ID
            if not party:
                cust_count = Party.objects.filter(company=self.company, party_type='customer').count()
                cust_id = f"CUST-{cust_count + 1:04d}"
                party = Party.objects.create(
                    company=self.company,
                    name=f"{clean_name} ({cust_id})",
                    party_type="customer",
                    phone=self.customer_phone or "",
                    address=self.customer_address or "",
                    notes=f"Automatically created from Sale on {self.date}."
                )
        
        if not self.transaction:
            tx = Transaction.objects.create(
                company=self.company,
                transaction_type="income",
                title=f"Stock Sale: {self.stock.name} x {self.quantity}",
                category=sales_category,
                account=self.account,
                party=party,
                amount=self.total_price,
                date=self.date,
                notes=self.notes or f"Automated transaction for sale of {self.stock.name}."
            )
            self.transaction = tx
        else:
            tx = self.transaction
            tx.title = f"Stock Sale: {self.stock.name} x {self.quantity}"
            tx.account = self.account
            tx.party = party
            tx.amount = self.total_price
            tx.date = self.date
            tx.notes = self.notes or f"Automated transaction for sale of {self.stock.name}."
            tx.save()
            
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.transaction:
            self.transaction.delete()
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"Sale: {self.stock.name} x {self.quantity}"


class UserProfile(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    business_name = models.CharField(max_length=255, blank=True)
    owner_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="user_profiles", null=True, blank=True)
    role = models.CharField(max_length=20, choices=[('admin', 'Admin'), ('manager', 'Manager'), ('staff', 'Staff')], default='staff')

    def __str__(self):
        return f"{self.user.username} - {self.company.name if self.company else 'No Company'} ({self.role})"


class GoogleDriveToken(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gdrive_token')
    access_token = models.TextField()
    refresh_token = models.TextField(null=True, blank=True)
    expires_at = models.DateTimeField()
    backup_enabled = models.BooleanField(default=False)
    last_backup_at = models.DateTimeField(null=True, blank=True)
    backup_folder_id = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Google Drive Token for {self.user.email}"


class BackupRecord(TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed')
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='backup_records')
    file_name = models.CharField(max_length=255)
    drive_file_id = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Backup {self.file_name} - {self.status}"

