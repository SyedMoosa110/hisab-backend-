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
    def __init__(self, user):
        self.device_name = os.environ.get('COMPUTERNAME', 'Unknown Device')
        self.user = user

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
            BackupLog.objects.create(user=self.user, event=message, level=level)
        except Exception:
            pass # Failsafe if DB is not initialized
        self._update_progress(message)

    def _update_progress(self, message):
        try:
            state, _ = BackupState.objects.get_or_create(user=self.user)
            state.progress_message = message
            state.save()
        except Exception:
            pass

    def _get_drive_service(self):
        try:
            creds_obj = self.user.google_drive_credentials
        except GoogleDriveCredentials.DoesNotExist:
            raise ValueError("No valid Google Drive credentials found for this user.")
            
        access_token = creds_obj.get_token()
        if not access_token:
            raise ValueError("Google Drive access token not found.")
            
        refresh_token = creds_obj.get_refresh_token()
        
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            raise TypeError(f"Decrypted tokens must be strings! Access Token: {type(access_token)}, Refresh Token: {type(refresh_token)}")

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            client_id=creds_obj.client_id,
            client_secret=creds_obj.client_secret,
            token_uri=creds_obj.token_uri
        )
        return build('drive', 'v3', credentials=creds)

    def run_backup(self):
        state, _ = BackupState.objects.get_or_create(user=self.user)
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
            service = self._get_drive_service()
            
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

            settings_obj, _ = BackupSettings.objects.get_or_create(user=self.user)
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
        # We always snapshot as JSON using Django's dumpdata. 
        # This is the only way to support safe multi-tenant company-filtered restores 
        # on both SQLite and PostgreSQL.
        timestamp = int(time.time())
        snapshot_path = os.path.join(temp_dir, f'snapshot_{timestamp}.json')

        from django.core.management import call_command
        with open(snapshot_path, 'w', encoding='utf-8') as f:
            call_command(
                'dumpdata', 
                format='json', 
                exclude=['contenttypes', 'auth.Permission'],
                stdout=f
            )
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
            for byte_block in iter(lambda: f.read(4096), b""):
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
            "google_account_email": self.user.google_drive_credentials.email,
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

    def decrypt_file(self, encrypted_path, aes_key):
        decrypted_path = encrypted_path.replace('.enc', '.decrypted')
        aesgcm = AESGCM(aes_key)
        
        with open(encrypted_path, 'rb') as f:
            data = f.read()
            
        nonce = data[:12]
        ct = data[12:]
        
        try:
            pt = aesgcm.decrypt(nonce, ct, None)
        except Exception as e:
            raise ValueError(f"Decryption failed. Incorrect key or corrupted file: {e}")
            
        with open(decrypted_path, 'wb') as f:
            f.write(pt)
            
        return decrypted_path

    def decompress_file(self, compressed_path):
        decompressed_path = compressed_path.replace('.gz', '.json').replace('.decrypted', '')
        with gzip.open(compressed_path, 'rb') as f_in:
            with open(decompressed_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        return decompressed_path

    def run_restore(self, company_id):
        import time
        from django.db import transaction
        from accounts.models import Sale, Transaction, DuePayment, Stock, Note, AuditLog, Category, Party, Account

        start_time = time.time()
        
        def log_stage(stage_name, prev_time=None):
            now = time.time()
            if prev_time:
                elapsed = now - prev_time
                self._log(f"{stage_name} (took {elapsed:.2f}s)", level="INFO")
            else:
                self._log(stage_name, level="INFO")
            return now

        t = log_stage("Restore Started")
        t = log_stage("Connecting to Drive...", t)
        
        temp_dir = self._get_temp_dir()
        aes_key = self._derive_aes_key(settings.SECRET_KEY)
        service = self._get_drive_service()
        
        try:
            folder_id = self._get_or_create_folder(service, 'Business Accounting Backup')
            query = f"name='latest.enc' and '{folder_id}' in parents and trashed=false"
            results = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            items = results.get('files', [])
            if not items:
                raise ValueError("Could not find latest.enc in Google Drive.")
            file_id = items[0]['id']

            t = log_stage("Downloading latest.enc", t)
            encrypted_path = os.path.join(temp_dir, 'latest.enc')
            request = service.files().get_media(fileId=file_id)
            with open(encrypted_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                    
            t = log_stage("Downloading metadata.json", t)
            query = f"name='metadata.json' and '{folder_id}' in parents and trashed=false"
            meta_results = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            meta_items = meta_results.get('files', [])
            if not meta_items:
                raise ValueError("Could not find metadata.json in Google Drive.")
            meta_id = meta_items[0]['id']
            
            meta_path = os.path.join(temp_dir, 'metadata.json')
            m_request = service.files().get_media(fileId=meta_id)
            with open(meta_path, 'wb') as fh:
                m_downloader = MediaIoBaseDownload(fh, m_request)
                m_done = False
                while m_done is False:
                    _, m_done = m_downloader.next_chunk()
                    
            with open(meta_path, 'r') as mf:
                meta_json = json.load(mf)
                
            t = log_stage("Metadata verified", t)
            
            version_val = meta_json.get('version') or meta_json.get('backup_version')
            timestamp_val = meta_json.get('timestamp') or meta_json.get('backup_timestamp')
            sha_val = meta_json.get('sha256_checksum')
            enc_val = meta_json.get('encryption')

            if not version_val or not timestamp_val or not sha_val or not enc_val:
                raise ValueError("Missing required metadata fields (version, timestamp, sha256_checksum, or encryption).")
            
            if enc_val != 'AES-256-GCM':
                raise ValueError("Unsupported encryption algorithm in metadata.")
                
            t = log_stage("SHA verified", t)
            checksum = self.generate_sha256(encrypted_path)
            if checksum != sha_val:
                raise ValueError("Backup integrity verification failed. Checksum mismatch.")
                
            t = log_stage("Decrypting", t)
            decrypted_path = self.decrypt_file(encrypted_path, aes_key)
            
            t = log_stage("Decompressing", t)
            json_path = self.decompress_file(decrypted_path)
            
            t = log_stage("Parsing JSON", t)
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            t = log_stage("Filtering company data", t)
            excluded_apps = {'auth', 'sessions', 'admin', 'contenttypes', 'backup'}
            excluded_models = {'accounts.company', 'accounts.userprofile'}
            
            filtered_records = []
            for obj in data:
                model_name = obj.get('model', '')
                app_label = model_name.split('.')[0]
                if app_label in excluded_apps or model_name in excluded_models:
                    continue
                fields = obj.get('fields', {})
                if fields.get('company') == company_id:
                    filtered_records.append(obj)
            
            t = log_stage("Deleting existing records", t)
            deletion_order = [Sale, Transaction, DuePayment, Stock, Note, AuditLog, Category, Party, Account]
            import_order = [Account, Party, Category, Stock, AuditLog, Note, DuePayment, Transaction, Sale]
            
            try:
                with transaction.atomic():
                    for model in deletion_order:
                        model.objects.filter(company_id=company_id).delete()
                        
                    t = log_stage("Importing records", t)
                    
                    # Group records by model
                    records_by_model = {}
                    for obj in filtered_records:
                        model_name = obj.get('model', '')
                        if model_name not in records_by_model:
                            records_by_model[model_name] = []
                        records_by_model[model_name].append(obj)
                        
                    for model in import_order:
                        model_name = model._meta.label_lower
                        model_records = records_by_model.get(model_name, [])
                        instances = []
                        for rec in model_records:
                            fields = rec.get('fields', {})
                            pk = rec.get('pk')
                            instances.append(model(**fields, pk=pk))
                        
                        if instances:
                            model.objects.bulk_create(instances)
                            
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                self._log(f"Restore Failed during database transaction: {str(e)}", level="ERROR")
                self._log(error_trace, level="ERROR")
                raise ValueError(f"Database import failed: {str(e)}")
                
            t = log_stage("Restore completed", t)
            self._log("Restore Successful", level="SUCCESS")
            
        except Exception as e:
            self._log(f"Restore Failed: {str(e)}", level="ERROR")
            raise
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
