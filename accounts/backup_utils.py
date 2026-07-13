import os
import json
import zipfile
import requests
from datetime import datetime
from django.conf import settings
from django.utils import timezone

def get_active_access_token(token_model):
    """
    Refreshes the Google OAuth 2.0 access token using requests if it has expired.
    """
    now = timezone.now()
    # If token is expired or expires in the next 60 seconds, refresh it
    if token_model.expires_at <= now + timezone.timedelta(seconds=60):
        if not token_model.refresh_token:
            raise Exception("No refresh token stored. Please re-authenticate.")
            
        payload = {
            "client_id": getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", ""),
            "client_secret": getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "refresh_token": token_model.refresh_token,
            "grant_type": "refresh_token"
        }
        res = requests.post("https://oauth2.googleapis.com/token", data=payload)
        if res.status_code != 200:
            raise Exception(f"Failed to refresh access token: {res.text}")
            
        data = res.json()
        token_model.access_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        token_model.expires_at = now + timezone.timedelta(seconds=expires_in)
        token_model.save()
        
    return token_model.access_token

def backup_database_to_json(user, timestamp=None):
    """
    Creates a temporary JSON dump of database tables belonging to the user's company/data.
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

    import tempfile
    temp_dir = os.path.join(tempfile.gettempdir(), 'ledgerpro_backups')
    os.makedirs(temp_dir, exist_ok=True)
    
    if not timestamp:
        timestamp = timezone.now().strftime('%Y-%m-%d-%H%M%S')
    json_filename = f"backup-{user.id}-{timestamp}.json"
    json_path = os.path.join(temp_dir, json_filename)
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, default=default_serializer, indent=2)

    zip_filename = f"backup-{user.id}-{timestamp}.zip"
    zip_path = os.path.join(temp_dir, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(json_path, arcname=json_filename)
        
        # Include media files associated with the user's transactions if any
        for tx in Transaction.objects.filter(company=company, attachment__isnull=False):
            try:
                if tx.attachment and tx.attachment.name:
                    file_path = tx.attachment.path
                    if os.path.exists(file_path):
                        zipf.write(file_path, arcname=f"media/{os.path.basename(tx.attachment.name)}")
            except Exception:
                pass
                
    try:
        os.remove(json_path)
    except OSError:
        pass
        
    return zip_path

def upload_backup_to_drive(user, file_path):
    """
    Uploads a backup zip file directly to Google Drive using HTTP multipart requests.
    """
    from accounts.models import GoogleDriveToken
    try:
        token_model = GoogleDriveToken.objects.get(user=user)
    except GoogleDriveToken.DoesNotExist:
        raise Exception("Google Drive is not authenticated for this user.")

    access_token = get_active_access_token(token_model)
    headers = {"Authorization": f"Bearer {access_token}"}

    # Ensure backup folder exists
    folder_id = token_model.backup_folder_id
    if not folder_id:
        # Search for folder named 'LedgerPro-Backups'
        query = "name = 'LedgerPro-Backups' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = requests.get(
            f"https://www.googleapis.com/drive/v3/files?q={query}",
            headers=headers
        )
        if res.status_code != 200:
            raise Exception(f"Failed to query Google Drive folder: {res.text}")
            
        items = res.json().get("files", [])
        if items:
            folder_id = items[0]["id"]
        else:
            # Create folder
            folder_metadata = {
                "name": "LedgerPro-Backups",
                "mimeType": "application/vnd.google-apps.folder"
            }
            create_res = requests.post(
                "https://www.googleapis.com/drive/v3/files",
                headers=headers,
                json=folder_metadata
            )
            if create_res.status_code != 200:
                raise Exception(f"Failed to create Google Drive folder: {create_res.text}")
            folder_id = create_res.json().get("id")
            
        token_model.backup_folder_id = folder_id
        token_model.save()

    # Upload backup zip using Google Drive Multipart Upload protocol
    base_name = os.path.basename(file_path)
    # base_name looks like: backup-{user_id}-{timestamp}.zip
    # Let's convert it to backup-{timestamp}.zip for Google Drive
    parts = base_name.split('-')
    if len(parts) >= 3:
        drive_name = f"backup-{'-'.join(parts[2:])}"
    else:
        drive_name = base_name

    file_metadata = {
        "name": drive_name,
        "parents": [folder_id]
    }
    
    files = {
        "data": ("metadata", json.dumps(file_metadata), "application/json; charset=UTF-8"),
        "file": (drive_name, open(file_path, "rb"), "application/zip")
    }

    upload_res = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
        headers=headers,
        files=files
    )

    # Close file handles
    files["file"][1].close()

    if upload_res.status_code not in (200, 201):
        raise Exception(f"Failed to upload zip backup to Drive: {upload_res.text}")
        
    drive_file_id = upload_res.json().get("id")
    
    # Update token's last backup timestamp
    token_model.last_backup_at = timezone.now()
    token_model.save()
    
    return drive_file_id

def run_backup_for_user(user):
    """
    Wrapper to run database JSON dump and drive upload, updating history record.
    """
    from accounts.models import BackupRecord
    
    timestamp = timezone.now().strftime('%Y-%m-%d-%H%M%S')
    file_name = f"backup-{timestamp}.zip"
    record = BackupRecord.objects.create(
        user=user,
        file_name=file_name,
        status='pending'
    )
    
    file_path = None
    try:
        file_path = backup_database_to_json(user, timestamp=timestamp)
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
