import os
import json
import zipfile
import requests
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from django.db import connection

def get_google_credentials(token_model):
    """
    Constructs google.oauth2.credentials.Credentials from the GoogleDriveToken model.
    """
    creds = Credentials(
        token=token_model.access_token,
        refresh_token=token_model.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", ""),
        client_secret=getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "")
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_model.access_token = creds.token
        token_model.expires_at = timezone.now() + timezone.timedelta(seconds=creds.expiry - timezone.now().timestamp() if creds.expiry else 3600)
        token_model.save()
    return creds

def backup_database_to_json(user):
    """
    Creates a temporary JSON dump of database tables belonging to the user's company/data.
    Since we are using Neon PostgreSQL, we dump core records for the user's company.
    """
    from accounts.models import Account, Category, Party, Transaction, Stock, Sale, DuePayment, Note
    company = getattr(user.profile, 'company', None)
    if not company:
        return None

    data = {
        "company": {"id": company.id, "name": company.name},
        "accounts": list(Account.objects.filter(company=company).values()),
        "categories": list(Category.objects.filter(company=company).values()),
        "parties": list(Party.objects.filter(company=company).values()),
        "transactions": list(Transaction.objects.filter(company=company).values()),
        "stock": list(Stock.objects.filter(company=company).values()),
        "sales": list(Sale.objects.filter(company=company).values()),
        "dues": list(DuePayment.objects.filter(company=company).values()),
        "notes": list(Note.objects.filter(company=company).values())
    }

    # Handle decimals and dates serialization
    def default_serializer(obj):
        if isinstance(obj, datetime) or hasattr(obj, 'isoformat'):
            return obj.isoformat()
        import decimal
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        raise TypeError(f"Type {type(obj)} not serializable")

    temp_dir = os.path.join(settings.BASE_DIR, 'tmp_backups')
    os.makedirs(temp_dir, exist_ok=True)
    
    timestamp = timezone.now().strftime('%Y-%m-%d-%H%M%S')
    json_filename = f"backup-{user.id}-{timestamp}.json"
    json_path = os.path.join(temp_dir, json_filename)
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, default=default_serializer, indent=2)

    zip_filename = f"backup-{timezone.now().strftime('%Y-%m-%d')}.zip"
    zip_path = os.path.join(temp_dir, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(json_path, arcname=json_filename)
        
        # Include media files associated with the user's transactions if any
        for tx in Transaction.objects.filter(company=company, attachment__isnull=False):
            if tx.attachment and os.path.exists(tx.attachment.path):
                zipf.write(tx.attachment.path, arcname=f"media/{os.path.basename(tx.attachment.name)}")
                
    try:
        os.remove(json_path)
    except OSError:
        pass
        
    return zip_path

def upload_backup_to_drive(user, file_path):
    """
    Uploads a backup zip file directly to Google Drive in the user's specific folder.
    """
    from accounts.models import GoogleDriveToken, BackupRecord
    try:
        token_model = GoogleDriveToken.objects.get(user=user)
    except GoogleDriveToken.DoesNotExist:
        raise Exception("Google Drive is not authenticated for this user.")

    creds = get_google_credentials(token_model)
    service = build('drive', 'v3', credentials=creds)

    # Ensure backup folder exists
    folder_id = token_model.backup_folder_id
    if not folder_id:
        # Check if folder exists on Drive first
        query = "name = 'LedgerPro-Backups' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
        items = results.get('files', [])
        if items:
            folder_id = items[0]['id']
        else:
            # Create folder
            folder_metadata = {
                'name': 'LedgerPro-Backups',
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = service.files().create(body=folder_metadata, fields='id').execute()
            folder_id = folder.get('id')
        
        token_model.backup_folder_id = folder_id
        token_model.save()

    # Upload backup zip
    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, mimetype='application/zip')
    drive_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    
    # Update token's last backup timestamp
    token_model.last_backup_at = timezone.now()
    token_model.save()
    
    return drive_file.get('id')

def run_backup_for_user(user):
    """
    Wrapper to run database JSON dump and drive upload, updating history record.
    """
    from accounts.models import BackupRecord
    
    file_name = f"backup-{timezone.now().strftime('%Y-%m-%d')}.zip"
    record = BackupRecord.objects.create(
        user=user,
        file_name=file_name,
        status='pending'
    )
    
    file_path = None
    try:
        file_path = backup_database_to_json(user)
        if not file_path:
            raise Exception("No company/data found for user profile.")
            
        drive_file_id = upload_backup_to_drive(user, file_path)
        record.drive_file_id = drive_file_id
        record.status = 'success'
        record.save()
    except Exception as e:
        record.status = 'failed'
        record.error_message = str(e)
        record.save()
        raise e
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
