from django.contrib import admin

from .models import Account, BackupRecord, Category, DuePayment, Note, Party, Transaction, Stock, Sale


admin.site.register(Account)
admin.site.register(Category)
admin.site.register(Party)
admin.site.register(Transaction)
admin.site.register(DuePayment)
admin.site.register(Note)
admin.site.register(BackupRecord)
admin.site.register(Stock)
admin.site.register(Sale)
