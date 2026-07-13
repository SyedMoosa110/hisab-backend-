from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from . import backup_views

router = DefaultRouter()
router.register("accounts", views.AccountViewSet)
router.register("categories", views.CategoryViewSet)
router.register("parties", views.PartyViewSet)
router.register("transactions", views.TransactionViewSet)
router.register("dues", views.DuePaymentViewSet)
router.register("notes", views.NoteViewSet)
router.register("stock", views.StockViewSet)
router.register("sales", views.SaleViewSet)


urlpatterns = [
    path("", include(router.urls)),
    path("auth/csrf/", views.csrf_view),
    path("auth/login/", views.login_view),
    path("auth/register/", views.register_view),
    path("auth/logout/", views.logout_view),
    path("auth/me/", views.me_view),
    path("auth/change-password/", views.change_password_view),
    path("dashboard/", views.dashboard_view),
    path("reports/", views.reports_view),
    path("export/excel/", views.export_excel_view),
    path("export/pdf/", views.export_pdf_view),
    path("export-sales/excel/", views.export_sales_excel_view),
    path("export-sales/pdf/", views.export_sales_pdf_view),
    path("export-stock/excel/", views.export_stock_excel_view),
    path("export-stock/pdf/", views.export_stock_pdf_view),
    path("import/transactions/", views.import_transactions_view),
    path("import/sales/", views.import_sales_view),
    path("import/stock/", views.import_stock_view),
    
    # Backup & Google Drive Routes
    path("auth/google/", backup_views.google_oauth_redirect),
    path("auth/google/callback/", backup_views.google_oauth_callback),
    path("backup/settings/", backup_views.BackupSettingsView.as_view()),
    path("backup/trigger/", backup_views.TriggerBackupView.as_view()),
    path("backup/history/", backup_views.BackupHistoryView.as_view()),
]

