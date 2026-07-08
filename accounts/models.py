from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Account(TimeStampedModel):
    ACCOUNT_TYPES = [
        ("cash", "Cash"),
        ("bank", "Bank"),
        ("easypaisa", "Easypaisa"),
        ("jazzcash", "JazzCash"),
    ]

    name = models.CharField(max_length=120)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Category(TimeStampedModel):
    CATEGORY_TYPES = [("income", "Income"), ("expense", "Expense")]

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
    title = models.CharField(max_length=180)
    body = models.TextField()
    reminder_date = models.DateField(blank=True, null=True)
    is_done = models.BooleanField(default=False)

    def __str__(self):
        return self.title


class BackupRecord(TimeStampedModel):
    BACKUP_TYPES = [("manual", "Manual"), ("daily", "Daily"), ("weekly", "Weekly")]

    backup_type = models.CharField(max_length=20, choices=BACKUP_TYPES, default="manual")
    file = models.FileField(upload_to="backups/")
    notes = models.CharField(max_length=200, blank=True)


class AuditLog(TimeStampedModel):
    ACTIONS = [("created", "Created"), ("updated", "Updated"), ("deleted", "Deleted")]

    model_name = models.CharField(max_length=80)
    object_id = models.PositiveIntegerField(blank=True, null=True)
    action = models.CharField(max_length=20, choices=ACTIONS)
    summary = models.TextField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
