import requests
from django.conf import settings
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from urllib.parse import urlencode

from .models import GoogleDriveToken, BackupRecord
from .backup_serializers import GoogleDriveTokenSerializer, BackupRecordSerializer
from .backup_utils import run_backup_for_user

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def google_oauth_redirect(request):
    """
    Step 1: Redirect the user to Google's OAuth 2.0 server.
    """
    client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
    redirect_uri = getattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "")
    
    if not client_id or not redirect_uri:
        return Response({"detail": "Google OAuth configuration is missing in backend settings."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/drive.file email openid",
        "access_type": "offline",
        "prompt": "consent",
        "state": str(request.user.id)
    }
    
    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return Response({"auth_url": url})


@api_view(["GET"])
@permission_classes([])  # Public callback, but we authenticate using the 'state' parameter or sessions
def google_oauth_callback(request):
    """
    Step 2: Exchange authentication code for tokens and save them.
    """
    code = request.GET.get("code")
    error = request.GET.get("error")
    state = request.GET.get("state")
    
    if error or not code:
        frontend_error_url = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')}/backup?error={error or 'no_code'}"
        return redirect(frontend_error_url)
        
    client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "")
    redirect_uri = getattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "")
    
    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    res = requests.post(GOOGLE_TOKEN_URL, data=payload)
    if res.status_code != 200:
        frontend_error_url = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')}/backup?error=token_exchange_failed"
        return redirect(frontend_error_url)
        
    tokens = res.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)
    
    # Retrieve user
    from django.contrib.auth.models import User
    try:
        user_id = int(state)
        user = User.objects.get(id=user_id)
    except (ValueError, TypeError, User.DoesNotExist):
        if request.user.is_authenticated:
            user = request.user
        else:
            frontend_error_url = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')}/backup?error=user_not_found"
            return redirect(frontend_error_url)
            
    expires_at = timezone.now() + timezone.timedelta(seconds=expires_in)
    
    token_model, created = GoogleDriveToken.objects.get_or_create(user=user, defaults={
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at
    })
    
    if not created:
        token_model.access_token = access_token
        if refresh_token:
            token_model.refresh_token = refresh_token
        token_model.expires_at = expires_at
        token_model.save()
        
    frontend_success_url = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')}/backup?auth=success"
    return redirect(frontend_success_url)


class BackupSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            token = GoogleDriveToken.objects.get(user=request.user)
            serializer = GoogleDriveTokenSerializer(token)
            data = serializer.data
            data['is_authenticated'] = bool(token.refresh_token)
            data['email'] = request.user.email
            return Response(data)
        except GoogleDriveToken.DoesNotExist:
            return Response({
                "is_authenticated": False,
                "backup_enabled": False,
                "last_backup_at": None,
                "backup_folder_id": None
            })

    def post(self, request):
        # Toggle auto-backup settings
        backup_enabled = request.data.get("backup_enabled", False)
        token, created = GoogleDriveToken.objects.get_or_create(user=request.user, defaults={
            "access_token": "",
            "expires_at": timezone.now(),
            "backup_enabled": backup_enabled
        })
        if not created:
            token.backup_enabled = backup_enabled
            token.save()
        return Response(GoogleDriveTokenSerializer(token).data)


class TriggerBackupView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            run_backup_for_user(request.user)
            return Response({"detail": "Manual backup successfully completed and uploaded to Google Drive."})
        except Exception as e:
            return Response({"detail": f"Backup failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BackupHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        records = BackupRecord.objects.filter(user=request.user).order_by('-created_at')[:20]
        serializer = BackupRecordSerializer(records, many=True)
        return Response(serializer.data)
