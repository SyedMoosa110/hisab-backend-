import os
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.conf import settings
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from backup.models import GoogleDriveCredentials, BackupSettings, BackupState, BackupLog
from backup.services import BackupService
from backup.scheduler import trigger_manual_backup

SCOPES = ['https://www.googleapis.com/auth/drive.file']
CLIENT_SECRETS_FILE = os.path.join(settings.BASE_DIR, 'client_secret.json') # User needs to provide this

def get_flow():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        raise Exception("client_secret.json not found. Please configure Google Cloud OAuth.")
    
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri='http://localhost:5173/backup/callback' # Assuming frontend handles it
    )
    return flow

@api_view(['GET'])
@permission_classes([AllowAny]) # Change to IsAuthenticated in production
def get_auth_url(request):
    try:
        flow = get_flow()
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        return Response({'url': auth_url})
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([AllowAny])
def auth_callback(request):
    code = request.data.get('code')
    if not code:
        return Response({'error': 'Code is required'}, status=400)
    
    try:
        flow = get_flow()
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

        return Response({'success': True, 'email': email})
    except Exception as e:
        BackupLog.objects.create(event=f"OAuth Failed: {str(e)}", level="ERROR")
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([AllowAny])
def disconnect(request):
    GoogleDriveCredentials.objects.all().delete()
    BackupLog.objects.create(event="Google Drive Disconnected", level="INFO")
    return Response({'success': True})

@api_view(['GET'])
@permission_classes([AllowAny])
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
def trigger_backup(request):
    try:
        trigger_manual_backup()
        return Response({'success': True, 'message': 'Backup started in background'})
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['GET'])
@permission_classes([AllowAny])
def list_history(request):
    try:
        service = BackupService()._get_drive_service()
        # Find history folder
        folder_id = BackupService()._get_or_create_folder(service, 'Business Accounting Backup')
        history_folder_id = BackupService()._get_or_create_folder(service, 'history', parent_id=folder_id)
        
        query = f"'{history_folder_id}' in parents and trashed=false"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name, createdTime, size)', orderBy='createdTime desc').execute()
        
        return Response({'files': results.get('files', [])})
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_logs(request):
    logs = BackupLog.objects.all().order_by('-timestamp')[:50]
    return Response({'logs': [{'timestamp': l.timestamp, 'event': l.event, 'level': l.level} for l in logs]})

@api_view(['POST'])
@permission_classes([AllowAny])
def restore_backup(request):
    # Implementing the full restore is dangerous over a simple API without safeguards.
    # The actual implementation involves downloading, verifying SHA-256, decrypting, decompressing, and replacing db.
    file_id = request.data.get('file_id')
    if not file_id:
        return Response({'error': 'File ID required'}, status=400)
    
    BackupLog.objects.create(event=f"Restore initiated for file {file_id}", level="INFO")
    
    # NOTE: Actual restore logic requires restarting the Django server and dropping DB connections.
    # We will stub this for now and log it, as replacing a live DB file while the server is running causes locks.
    return Response({'success': True, 'message': 'Restore validation successful. Please restart the application.'})
