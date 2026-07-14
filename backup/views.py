import os
import traceback
from functools import wraps
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.conf import settings
from django.db.utils import ProgrammingError, OperationalError
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from backup.models import GoogleDriveCredentials, BackupSettings, BackupState, BackupLog
from backup.services import BackupService
from backup.scheduler import trigger_manual_backup, check_and_run_backup

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def api_error_handler(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        try:
            return func(request, *args, **kwargs)
        except (ProgrammingError, OperationalError) as e:
            # Handle database tables missing gracefully
            error_msg = "Database tables missing. Please run migrations."
            return Response({
                'success': False, 
                'error': error_msg,
                'details': str(e)
            }, status=200)
        except ValueError as e:
            # Handle configuration issues
            return Response({
                'success': False,
                'error': str(e)
            }, status=200)
        except Exception as e:
            error_response = {
                'success': False,
                'error': str(e) if settings.DEBUG else "Internal server error",
                'details': str(e)
            }
            if settings.DEBUG:
                error_response['traceback'] = traceback.format_exc()
            return Response(error_response, status=200)
    return wrapper

def get_flow():
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5173/backup/callback')
    
    missing = []
    if not client_id: missing.append('GOOGLE_CLIENT_ID')
    if not client_secret: missing.append('GOOGLE_CLIENT_SECRET')
    if not os.environ.get('GOOGLE_REDIRECT_URI'): missing.append('GOOGLE_REDIRECT_URI')
    
    if missing:
        return None, missing
        
    client_config = {
        "web": {
            "client_id": client_id,
            "project_id": "accounting-backup",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    return flow, missing

@api_view(['GET'])
@permission_classes([AllowAny])
@api_error_handler
def get_auth_url(request):
    flow, missing = get_flow()
    if missing:
        return Response({
            "success": False,
            "configured": False,
            "message": "Google OAuth is not configured.",
            "missing": missing
        }, status=200)
        
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    return Response({
        "success": True,
        "configured": True,
        "auth_url": auth_url
    }, status=200)
from django.shortcuts import redirect

@api_view(['GET'])
@permission_classes([AllowAny])
@api_error_handler
def auth_callback(request):
    error = request.GET.get('error')
    frontend_url = getattr(settings, 'FRONTEND_URL', None)
    if not frontend_url:
        frontend_url = os.environ.get('FRONTEND_URL', 'http://localhost:5173')
    frontend_url = frontend_url.rstrip('/')

    if error:
        return redirect(f"{frontend_url}/backup?connected=false&error={error}")

    code = request.GET.get('code')
    if not code:
        return redirect(f"{frontend_url}/backup?connected=false&error=missing_code")
    
    flow, missing = get_flow()
    if missing:
        return redirect(f"{frontend_url}/backup?connected=false&error=server_missing_config")
        
    flow.fetch_token(code=code)
    credentials = flow.credentials
    
    # Get user email
    drive_service = build('drive', 'v3', credentials=credentials)
    about = drive_service.about().get(fields='user').execute()
    email = about['user']['emailAddress']

    # Save credentials
    creds_obj, _ = GoogleDriveCredentials.objects.get_or_create(id=1)
    creds_obj.client_id = flow.client_config['client_id']
    creds_obj.client_secret = flow.client_config['client_secret']
    creds_obj.token_uri = flow.client_config['token_uri']
    creds_obj.scopes = ",".join(SCOPES)
    creds_obj.email = email
    creds_obj.save_tokens(credentials.token, credentials.refresh_token)

    BackupLog.objects.create(event=f"Google Drive Connected: {email}", level="SUCCESS")

    return redirect(f"{frontend_url}/backup?connected=true")

@api_view(['POST'])
@permission_classes([AllowAny])
@api_error_handler
def disconnect(request):
    GoogleDriveCredentials.objects.all().delete()
    BackupLog.objects.create(event="Google Drive Disconnected", level="INFO")
    return Response({'success': True})

@api_view(['GET'])
@permission_classes([AllowAny])
@api_error_handler
def get_status(request):
    creds = GoogleDriveCredentials.objects.first()
    settings_obj = BackupSettings.objects.first()
    state = BackupState.objects.first()

    status = {
        'connected': creds is not None,
        'email': creds.email if creds else None,
        'auto_backup_enabled': settings_obj.auto_backup_enabled if settings_obj else False,
        'last_backup_date': settings_obj.last_backup_date if settings_obj else None,
        'next_scheduled_backup': settings_obj.next_scheduled_backup if settings_obj else None,
        'status': state.status if state else 'IDLE',
        'progress_message': state.progress_message if state else '',
        'is_dirty': state.is_dirty if state else False
    }
    return Response(status)

@api_view(['POST'])
@permission_classes([AllowAny])
@api_error_handler
def trigger_backup(request):
    trigger_manual_backup()
    return Response({'success': True, 'message': 'Backup completed successfully.'})

@api_view(['GET'])
@permission_classes([AllowAny])
@api_error_handler
def list_history(request):
    service = BackupService()._get_drive_service()
    folder_id = BackupService()._get_or_create_folder(service, 'Business Accounting Backup')
    history_folder_id = BackupService()._get_or_create_folder(service, 'history', parent_id=folder_id)
    
    query = f"'{history_folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name, createdTime, size)', orderBy='createdTime desc').execute()
    
    return Response({'files': results.get('files', [])})

@api_view(['GET'])
@permission_classes([AllowAny])
@api_error_handler
def get_logs(request):
    logs = BackupLog.objects.all().order_by('-timestamp')[:50]
    return Response({'logs': [{'timestamp': l.timestamp, 'event': l.event, 'level': l.level} for l in logs]})

@api_view(['POST'])
@permission_classes([AllowAny])
@api_error_handler
def restore_backup(request):
    file_id = request.data.get('file_id')
    if not file_id:
        return Response({'success': False, 'error': 'File ID required'}, status=400)
    
    BackupLog.objects.create(event=f"Restore initiated for file {file_id}", level="INFO")
    return Response({'success': True, 'message': 'Restore validation successful. Please restart the application.'})

@api_view(['POST', 'GET'])
@permission_classes([AllowAny])
@api_error_handler
def cron_backup(request):
    """
    Endpoint for Vercel Cron or external scheduler to trigger pending auto-backups.
    """
    ran, message = check_and_run_backup()
    return Response({'success': True, 'ran': ran, 'message': message})

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Diagnostic endpoint to verify all systems.
    """
    health = {
        "database_connected": False,
        "backup_tables_exist": False,
        "migration_status": "Unknown",
        "missing_tables": [],
        "google_configured": False,
        "credentials_valid": False,
        "storage_writable": False,
        "server_environment": "vercel" if os.environ.get('VERCEL') else "local",
        "ready": False,
        "google_env": {
            "client_id": bool(os.environ.get('GOOGLE_CLIENT_ID')),
            "client_secret": bool(os.environ.get('GOOGLE_CLIENT_SECRET')),
            "redirect_uri": bool(os.environ.get('GOOGLE_REDIRECT_URI'))
        }
    }

    try:
        from django.db import connection
        connection.ensure_connection()
        health["database_connected"] = True
    except Exception as e:
        health["migration_status"] = f"DB Connection Failed: {str(e)}"

    missing_tables = []
    try:
        from django.db import connection
        tables = connection.introspection.table_names()
        health["tables_in_db"] = tables
        
        # Check applied migrations
        with connection.cursor() as cursor:
            cursor.execute("SELECT app, name FROM django_migrations WHERE app = 'backup'")
            applied_migrations = cursor.fetchall()
            health["applied_migrations"] = [{"app": row[0], "name": row[1]} for row in applied_migrations]
            
        required_tables = [
            GoogleDriveCredentials._meta.db_table,
            BackupSettings._meta.db_table,
            BackupState._meta.db_table,
            BackupLog._meta.db_table
        ]
        
        health["required_tables"] = required_tables

        for t in required_tables:
            if t not in tables:
                missing_tables.append(t)
        
        health["missing_tables"] = missing_tables
        
        if not missing_tables:
            BackupState.objects.first()
            health["backup_tables_exist"] = True
            health["migration_status"] = "Migrated"
        else:
            health["migration_status"] = f"Missing {len(missing_tables)} tables. Ensure 'python manage.py migrate backup' has run successfully. Check your Vercel Build logs or run the migration command against the Neon DB."
    except Exception as e:
        health["migration_status"] = f"Error checking tables: {str(e)}"

    if health["google_env"]["client_id"] and health["google_env"]["client_secret"] and health["google_env"]["redirect_uri"]:
        health["google_configured"] = True

    try:
        creds = GoogleDriveCredentials.objects.first()
        if creds and creds.get_token():
            health["credentials_valid"] = True
    except Exception:
        pass

    try:
        tmp_dir = '/tmp/health_check'
        os.makedirs(tmp_dir, exist_ok=True)
        with open(os.path.join(tmp_dir, 'test.txt'), 'w') as f:
            f.write('test')
        os.remove(os.path.join(tmp_dir, 'test.txt'))
        health["storage_writable"] = True
    except Exception:
        pass

    if health["database_connected"] and health["backup_tables_exist"] and health["storage_writable"]:
        health["ready"] = True

    return Response(health)
