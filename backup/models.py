from django.db import models
from cryptography.fernet import Fernet
import os
import base64
from django.conf import settings

def get_encryption_key():
    # In production, use an environment variable for the FERNET key.
    # For now, we'll derive a simple key from SECRET_KEY if not provided.
    key = os.environ.get('FERNET_KEY')
    if not key:
        # Pad or truncate SECRET_KEY to 32 bytes and base64 encode
        secret = settings.SECRET_KEY.encode('utf-8')
        secret = (secret * 32)[:32]
        key = base64.urlsafe_b64encode(secret).decode('utf-8')
    return key.encode('utf-8')

class GoogleDriveCredentials(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="google_drive_credentials"
    )
    # Encrypted fields
    token = models.BinaryField()
    refresh_token = models.BinaryField()
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    token_uri = models.CharField(max_length=255)
    scopes = models.TextField() # comma separated
    email = models.EmailField(blank=True, null=True)
    device_id = models.CharField(max_length=255, default='default-device')

    def encrypt_val(self, value):
        if not value: return None
        f = Fernet(get_encryption_key())
        return f.encrypt(value.encode('utf-8'))

    def decrypt_val(self, value):
        if not value: return None
        if isinstance(value, memoryview):
            value = bytes(value)
        elif not isinstance(value, (bytes, str)):
            value = bytes(value)
        f = Fernet(get_encryption_key())
        return f.decrypt(value).decode('utf-8')

    def save_tokens(self, token_str, refresh_token_str):
        self.token = self.encrypt_val(token_str)
        if refresh_token_str:
            self.refresh_token = self.encrypt_val(refresh_token_str)
        self.save()

    def get_token(self):
        return self.decrypt_val(self.token)

    def get_refresh_token(self):
        return self.decrypt_val(self.refresh_token)

class BackupSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backup_settings"
    )
    auto_backup_enabled = models.BooleanField(default=True)
    last_backup_date = models.DateTimeField(null=True, blank=True)
    next_scheduled_backup = models.DateTimeField(null=True, blank=True)
    device_id = models.CharField(max_length=100, default='default-device')

class BackupState(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backup_state"
    )
    is_dirty = models.BooleanField(default=False)
    last_modified = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=50, default='IDLE') # IDLE, BACKING_UP, UPLOADING, QUEUED_OFFLINE
    progress_message = models.CharField(max_length=255, default='')

class BackupLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backup_logs",
        null=True, blank=True
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    event = models.CharField(max_length=255)
    level = models.CharField(max_length=20, default='INFO') # INFO, ERROR, SUCCESS
