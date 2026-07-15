from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

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
    
    # Superadmin portal actions
    path("superadmin/users/", views.superadmin_users_view),
    path("superadmin/users/<int:profile_id>/toggle_block/", views.superadmin_toggle_block_view),
    path("superadmin/users/<int:profile_id>/toggle_upgrade/", views.superadmin_toggle_upgrade_view),
]

