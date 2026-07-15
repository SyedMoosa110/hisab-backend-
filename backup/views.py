import os
import traceback
from functools import wraps
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.conf import settings
from django.db.utils import ProgrammingError, OperationalError
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from rest_framework.authentication import SessionAuthentication
from django.core.management import call_command

from backup.models import GoogleDriveCredentials, BackupSettings, BackupState, BackupLog
from backup.services import BackupService
from backup.scheduler import trigger_manual_backup, check_and_run_backup

SCOPES = ['https://www.googleapis.com/auth/drive.file']

class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return

def api_error_handler(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        try:
            return func(request, *args, **kwargs)
        except (ProgrammingError, OperationalError) as e:
            error_msg = "Database tables missing. Please run migrations."
            return Response({
                'success': False, 
                'error': error_msg,
                'details': str(e)
            }, status=200)
        except ValueError as e:
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
@permission_classes([IsAuthenticated])
@authentication_classes([CsrfExemptSessionAuthentication])
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
        
    auth_url, state = flow.authorization_url(prompt='consent', access_type='offline')
    request.session['oauth_state'] = state
    request.session['device_id'] = request.headers.get('X-Device-Id', 'default-device')
    request.session['user_id'] = request.user.id
    
    if hasattr(flow, 'code_verifier'):
        request.session['code_verifier'] = flow.code_verifier
        
    request.session.modified = True

    return Response({
        "success": True,
        "configured": True,
        "auth_url": auth_url
    }, status=200)

from django.http import HttpResponseRedirect

def auth_callback(request):
    # Hardcode for testing as requested
    frontend_url = "https://hisab-frontend-fawn.vercel.app"
    
    # Resolve user
    user = None
    if request.user.is_authenticated:
        user = request.user
    else:
        user_id = request.session.get('user_id')
        if user_id:
            from django.contrib.auth.models import User
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                pass
                
    if not user:
        return HttpResponseRedirect(f"{frontend_url}/?connected=false&error=unauthenticated")

    error = request.GET.get('error')
    if error:
        return HttpResponseRedirect(f"{frontend_url}/?connected=false&error={error}")

    authorization_code = request.GET.get('code')
    if not authorization_code:
        return HttpResponseRedirect(f"{frontend_url}/?connected=false&error=missing_code")
    
    flow, missing = get_flow()
    if missing:
        return HttpResponseRedirect(f"{frontend_url}/?connected=false&error=server_missing_config")
        
    code_verifier = request.session.get('code_verifier')
    if code_verifier:
        flow.code_verifier = code_verifier
        
    try:
        flow.fetch_token(code=authorization_code)
    except Exception as e:
        return HttpResponseRedirect(f"{frontend_url}/?connected=false&error=token_exchange_failed")
        
    try:
        credentials = flow.credentials
        drive_service = build('drive', 'v3', credentials=credentials)
        about = drive_service.about().get(fields='user').execute()
        email = about['user']['emailAddress']

        # Get or create credentials specifically for this user
        creds_obj, _ = GoogleDriveCredentials.objects.get_or_create(user=user)
        creds_obj.client_id = flow.client_config['client_id']
        creds_obj.client_secret = flow.client_config['client_secret']
        creds_obj.token_uri = flow.client_config['token_uri']
        creds_obj.scopes = ",".join(SCOPES)
        creds_obj.email = email
        creds_obj.device_id = request.session.get('device_id', 'default-device')
        creds_obj.save_tokens(credentials.token, credentials.refresh_token)

        BackupLog.objects.create(user=user, event=f"Google Drive Connected: {email}", level="SUCCESS")
    except Exception as e:
        return HttpResponseRedirect(f"{frontend_url}/?connected=false&error=database_save_failed")
        
    return HttpResponseRedirect(f"{frontend_url}/?connected=true")

import logging
logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CsrfExemptSessionAuthentication])
def disconnect(request):
    try:
        creds = GoogleDriveCredentials.objects.filter(user=request.user).first()
        if not creds:
            return Response({
                "success": True,
                "connected": False,
                "message": "Already disconnected"
            })
            
        token = None
        try:
            token = creds.get_token()
        except Exception:
            token = None
            
        if token:
            try:
                import requests
                requests.post('https://oauth2.googleapis.com/revoke',
                    params={'token': token},
                    headers={'content-type': 'application/x-www-form-urlencoded'}
                )
            except Exception:
                pass
                
        creds.delete()
        
        if hasattr(request, 'session'):
            request.session.pop('oauth_state', None)
            request.session.pop('code_verifier', None)
            request.session.pop('user_id', None)
            request.session.modified = True
            
        BackupLog.objects.create(user=request.user, event="Google Drive Disconnected", level="INFO")
        
        return Response({
            "success": True,
            "message": "Google Drive disconnected successfully."
        })
    except Exception as e:
        import traceback
        logger.exception("Disconnect failed")
        return Response({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }, status=200)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CsrfExemptSessionAuthentication])
@api_error_handler
def get_status(request):
    creds = GoogleDriveCredentials.objects.filter(user=request.user).first()
    settings_obj, _ = BackupSettings.objects.get_or_create(user=request.user)
    state, _ = BackupState.objects.get_or_create(user=request.user)

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
@permission_classes([IsAuthenticated])
@authentication_classes([CsrfExemptSessionAuthentication])
@api_error_handler
def trigger_backup(request):
    trigger_manual_backup(request.user)
    return Response({'success': True, 'message': 'Backup completed successfully.'})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CsrfExemptSessionAuthentication])
@api_error_handler
def list_history(request):
    backup_service = BackupService(user=request.user)
    service = backup_service._get_drive_service()
    folder_id = backup_service._get_or_create_folder(service, 'Business Accounting Backup')
    history_folder_id = backup_service._get_or_create_folder(service, 'history', parent_id=folder_id)
    
    query = f"'{history_folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name, createdTime, size)', orderBy='createdTime desc').execute()
    
    return Response({'files': results.get('files', [])})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CsrfExemptSessionAuthentication])
@api_error_handler
def get_logs(request):
    logs = BackupLog.objects.filter(user=request.user).order_by('-timestamp')[:50]
    return Response({'logs': [{'timestamp': l.timestamp, 'event': l.event, 'level': l.level} for l in logs]})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CsrfExemptSessionAuthentication])
@api_error_handler
def restore_backup(request):
    try:
        company_id = request.user.profile.company_id
        if not company_id:
            return Response({'success': False, 'error': 'No company associated with user.'}, status=400)
            
        service = BackupService(user=request.user)
        service.run_restore(company_id)
        
        return Response({
            'success': True, 
            'message': 'Restore completed successfully.'
        })
    except Exception as e:
        import traceback
        return Response({
            'success': False,
            'step': 'Restore',
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)

@api_view(['POST', 'GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CsrfExemptSessionAuthentication])
def trigger_migrate(request):
    """
    Endpoint for admins/superusers to run database migrations programmatically.
    """
    if not request.user.is_superuser:
        return Response({'success': False, 'error': 'Only administrators can run database migrations.'}, status=403)
    try:
        call_command('migrate', interactive=False)
        return Response({
            'success': True,
            'message': 'Database migrations completed successfully!'
        })
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

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
        
        required_tables = [
            GoogleDriveCredentials._meta.db_table,
            BackupSettings._meta.db_table,
            BackupState._meta.db_table,
            BackupLog._meta.db_table
        ]
        
        for t in required_tables:
            if t not in tables:
                missing_tables.append(t)
        
        health["missing_tables"] = missing_tables
        
        if not missing_tables:
            health["backup_tables_exist"] = True
            health["migration_status"] = "Migrated"
        else:
            health["migration_status"] = f"Missing {len(missing_tables)} tables."
    except Exception as e:
        health["migration_status"] = f"Error checking tables: {str(e)}"

    if health["google_env"]["client_id"] and health["google_env"]["client_secret"] and health["google_env"]["redirect_uri"]:
        health["google_configured"] = True

    try:
        if request.user.is_authenticated:
            creds = GoogleDriveCredentials.objects.filter(user=request.user).first()
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
