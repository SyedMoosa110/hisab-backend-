from pathlib import Path

from rest_framework import serializers

from .models import Account, BackupRecord, Category, DuePayment, Note, Party, Transaction


class AccountSerializer(serializers.ModelSerializer):
    current_balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Account
        fields = "__all__"


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"


class PartySerializer(serializers.ModelSerializer):
    class Meta:
        model = Party
        fields = "__all__"


class TransactionSerializer(serializers.ModelSerializer):
    MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024
    ALLOWED_ATTACHMENT_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp'}

    category_name = serializers.CharField(source="category.name", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    party_name = serializers.CharField(source="party.name", read_only=True)

    def validate_attachment(self, attachment):
        if not attachment:
            return attachment
        extension = Path(attachment.name).suffix.lower()
        if extension not in self.ALLOWED_ATTACHMENT_EXTENSIONS:
            raise serializers.ValidationError('Only PDF and image receipts are allowed.')
        if attachment.size > self.MAX_ATTACHMENT_SIZE:
            raise serializers.ValidationError('Attachment must be 5 MB or smaller.')
        return attachment

    class Meta:
        model = Transaction
        fields = "__all__"


class DuePaymentSerializer(serializers.ModelSerializer):
    party_name = serializers.CharField(source="party.name", read_only=True)

    class Meta:
        model = DuePayment
        fields = "__all__"


class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Note
        fields = "__all__"


class BackupRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupRecord
        fields = "__all__"

