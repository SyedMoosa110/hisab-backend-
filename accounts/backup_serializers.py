from rest_framework import serializers
from .models import GoogleDriveToken, BackupRecord

class GoogleDriveTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoogleDriveToken
        fields = ['backup_enabled', 'last_backup_at', 'backup_folder_id']
        read_only_fields = ['last_backup_at', 'backup_folder_id']

class BackupRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupRecord
        fields = ['id', 'created_at', 'file_name', 'drive_file_id', 'status', 'error_message']
        read_only_fields = ['id', 'created_at', 'file_name', 'drive_file_id', 'status', 'error_message']
