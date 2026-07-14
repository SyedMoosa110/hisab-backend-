import os
import time
import json
import gzip
import shutil
import subprocess
import hashlib
from datetime import datetime
from django.conf import settings
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from backup.models import BackupState, BackupLog, GoogleDriveCredentials, BackupSettings

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

class BackupService:
    def __init__(self, device_id=None):
        self.device_name = os.environ.get('COMPUTERNAME', 'Unknown Device')
        self.device_id = device_id

    def _derive_aes_key(self, secret):
        salt = b"backup_salt_123"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return kdf.derive(secret.encode('utf-8'))

    def _get_temp_dir(self):
        temp_dir = '/tmp/backup_temp'
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir

    def _log(self, message, level='INFO'):
        try:
            BackupLog.objects.create(event=message, level=level)
        except Exception:
            pass # Failsafe if DB is not initialized
        self._update_progress(message)

    def _update_progress(self, message):
        try:
            state, _ = BackupState.objects.get_or_create(id=1)
            state.progress_message = message
            state.save()
        except Exception:
            pass

    def _get_drive_services(self):
        if self.device_id:
            creds_qs = GoogleDriveCredentials.objects.filter(device_id=self.device_id)
        else:
            creds_qs = GoogleDriveCredentials.objects.all()
            
        services = []
        for creds_obj in creds_qs:
            access_token = creds_obj.get_token()
            if access_token:
                refresh_token = creds_obj.get_refresh_token()
                
                print(f"[Drive Service DEBUG] access_token type: {type(access_token)}")
                print(f"[Drive Service DEBUG] refresh_token type: {type(refresh_token)}")
                print(f"[Drive Service DEBUG] access_token repr: {repr(access_token)}")
                
                if not isinstance(access_token, str) or not isinstance(refresh_token, str):
                    raise TypeError(f"Decrypted tokens must be strings! Access Token: {type(access_token)}, Refresh Token: {type(refresh_token)}")

                creds = Credentials(
                    token=access_token,
                    refresh_token=refresh_token,
                    client_id=creds_obj.client_id,
                    client_secret=creds_obj.client_secret,
                    token_uri=creds_obj.token_uri
                )
                print(f"[Drive Service DEBUG] Credentials.token type: {type(creds.token)}")
                services.append(build('drive', 'v3', credentials=creds))
                
        if not services:
            raise ValueError("No valid Google Drive credentials found.")
        return services

    def run_backup(self):
        state, _ = BackupState.objects.get_or_create(id=1)
        state.status = 'BACKING_UP'
        state.save()
        
        temp_dir = self._get_temp_dir()
        aes_key = self._derive_aes_key(settings.SECRET_KEY)

        try:
            self._log("Backup Started")
            
            # 1. Snapshot
            self._log("Creating Database Snapshot...")
            snapshot_path = self.create_database_snapshot(temp_dir)
            
            # 2. Compress
            self._log("Compressing Database...")
            compressed_path = self.compress_file(snapshot_path)
            
            # 3. Encrypt
            self._log("Encrypting Backup (AES-256-GCM)...")
            encrypted_path = self.encrypt_file(compressed_path, aes_key)
            
            # 4. Checksum
            self._log("Generating SHA-256...")
            checksum = self.generate_sha256(encrypted_path)
            file_size = os.path.getsize(encrypted_path)
            
            # 5. Upload
            self._log("Uploading to Google Drive...")
            services = self._get_drive_services()
            
            for service in services:
                folder_id = self._get_or_create_folder(service, 'Business Accounting Backup')
                history_folder_id = self._get_or_create_folder(service, 'history', parent_id=folder_id)

                filename = f"{datetime.now().strftime('%Y-%m-%d-%H%M')}.enc"
                
                # Upload to history
                self._upload_file(service, encrypted_path, filename, history_folder_id)
                
                # Update latest.enc
                self._upload_file(service, encrypted_path, 'latest.enc', folder_id, overwrite=True)

                # 6. Metadata
                self._log("Updating Metadata...")
                self.update_metadata(service, folder_id, checksum, file_size, temp_dir)

                # 7. Cleanup
                self.maintain_history(service, history_folder_id)

            self._log("Backup Successful", level="SUCCESS")
            state.status = 'IDLE'
            state.is_dirty = False
            state.save()

            settings_obj, _ = BackupSettings.objects.get_or_create(id=1)
            settings_obj.last_backup_date = datetime.now()
            settings_obj.save()

        except Exception as e:
            self._log(f"Backup Failed: {str(e)}", level="ERROR")
            state.status = 'IDLE'
            state.save()
            raise
        finally:
            # ALWAYS clean up /tmp
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    def create_database_snapshot(self, temp_dir):
        db_settings = settings.DATABASES['default']
        engine = db_settings['ENGINE']
        timestamp = int(time.time())
        snapshot_path = os.path.join(temp_dir, f'snapshot_{timestamp}.db')

        if 'sqlite' in engine:
            db_name = db_settings['NAME']
            # Safe copy using python sqlite3 backup API
            import sqlite3
            def progress(status, remaining, total):
                pass
            con = sqlite3.connect(db_name)
            bck = sqlite3.connect(snapshot_path)
            with bck:
                con.backup(bck, pages=1, progress=progress)
            bck.close()
            con.close()
        elif 'postgresql' in engine:
            from django.core.management import call_command
            snapshot_path = snapshot_path.replace('.db', '.json')
            
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                call_command(
                    'dumpdata', 
                    format='json', 
                    exclude=['contenttypes', 'auth.Permission'],
                    stdout=f
                )
        else:
            raise Exception(f"Unsupported database engine for native backup: {engine}")
        return snapshot_path

    def compress_file(self, filepath):
        compressed_path = f"{filepath}.gz"
        with open(filepath, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        return compressed_path

    def encrypt_file(self, filepath, aes_key):
        encrypted_path = f"{filepath}.enc"
        aesgcm = AESGCM(aes_key)
        nonce = os.urandom(12)
        
        with open(filepath, 'rb') as f:
            data = f.read()
        
        ct = aesgcm.encrypt(nonce, data, None)
        
        with open(encrypted_path, 'wb') as f:
            f.write(nonce + ct)
            
        return encrypted_path

    def generate_sha256(self, filepath):
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096),b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _get_or_create_folder(self, service, folder_name, parent_id=None):
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
            
        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        items = results.get('files', [])
        
        if not items:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                file_metadata['parents'] = [parent_id]
            folder = service.files().create(body=file_metadata, fields='id').execute()
            return folder.get('id')
        return items[0].get('id')

    def _upload_file(self, service, filepath, filename, folder_id, overwrite=False):
        if overwrite:
            query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
            results = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            items = results.get('files', [])
            if items:
                file_id = items[0].get('id')
                media = MediaFileUpload(filepath, resumable=True)
                service.files().update(fileId=file_id, media_body=media).execute()
                return file_id

        file_metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaFileUpload(filepath, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')

    def update_metadata(self, service, folder_id, checksum, file_size, temp_dir):
        db_settings = settings.DATABASES['default']
        metadata = {
            "app_version": "1.0.0",
            "backup_version": "1.0",
            "database_type": "postgresql" if "postgresql" in db_settings['ENGINE'] else "sqlite",
            "database_size": str(file_size),
            "backup_timestamp": datetime.now().isoformat(),
            "last_modified": datetime.now().isoformat(),
            "device_name": self.device_name,
            "device_id": "device-001",
            "google_account_email": "",
            "sha256_checksum": checksum,
            "backup_status": "SUCCESS",
            "created_by": "System",
            "encryption": "AES-256-GCM"
        }
        meta_path = os.path.join(temp_dir, 'metadata.json')
        with open(meta_path, 'w') as f:
            json.dump(metadata, f, indent=4)
        
        self._upload_file(service, meta_path, 'metadata.json', folder_id, overwrite=True)

    def maintain_history(self, service, history_folder_id):
        query = f"'{history_folder_id}' in parents and trashed=false"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name, createdTime)', orderBy='createdTime desc').execute()
        items = results.get('files', [])
        
        if len(items) > 30:
            for item in items[30:]:
                service.files().delete(fileId=item['id']).execute()
