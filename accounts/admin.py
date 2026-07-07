from django.contrib import admin

from .models import Account, BackupRecord, Category, DuePayment, Note, Party, Transaction


admin.site.register(Account)
admin.site.register(Category)
admin.site.register(Party)
admin.site.register(Transaction)
admin.site.register(DuePayment)
admin.site.register(Note)
admin.site.register(BackupRecord)
