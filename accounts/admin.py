from django.contrib import admin

from .models import Account, Category, DuePayment, Note, Party, Transaction, Stock, Sale, UserProfile, Company

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_upgraded", "created_at")
    list_filter = ("is_upgraded",)
    search_fields = ("name",)

admin.site.register(Account)
admin.site.register(Category)
admin.site.register(Party)
admin.site.register(Transaction)
admin.site.register(DuePayment)
admin.site.register(Note)
admin.site.register(Stock)
admin.site.register(Sale)
admin.site.register(UserProfile)
