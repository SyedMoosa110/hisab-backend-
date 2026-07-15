from django.urls import path
from . import views

urlpatterns = [
    path('auth/url/', views.get_auth_url, name='backup_auth_url'),
    path('auth/callback/', views.auth_callback, name='backup_auth_callback'),
    path('disconnect/', views.disconnect, name='backup_disconnect'),
    path('status/', views.get_status, name='backup_status'),
    path('trigger/', views.trigger_backup, name='backup_trigger'),
    path('history/', views.list_history, name='backup_history'),
    path('logs/', views.get_logs, name='backup_logs'),
    path('restore/', views.restore_backup, name='backup_restore'),
    path('cron/', views.cron_backup, name='backup_cron'),
    path('health/', views.health_check, name='backup_health'),
    path('migrate/', views.trigger_migrate, name='backup_trigger_migrate'),
]
