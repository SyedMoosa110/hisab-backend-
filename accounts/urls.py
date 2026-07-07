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
router.register("backups", views.BackupRecordViewSet, basename="backups")

urlpatterns = [
    path("", include(router.urls)),
    path("auth/csrf/", views.csrf_view),
    path("auth/login/", views.login_view),
    path("auth/logout/", views.logout_view),
    path("auth/me/", views.me_view),
    path("auth/change-password/", views.change_password_view),
    path("dashboard/", views.dashboard_view),
    path("reports/", views.reports_view),
    path("export/excel/", views.export_excel_view),
    path("export/pdf/", views.export_pdf_view),
    path("backup/create/", views.create_backup_view),
]

