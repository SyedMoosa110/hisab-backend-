from pathlib import Path

from django.db.models import Sum
from rest_framework import serializers

from .models import Account, Category, DuePayment, Note, Party, Transaction, Stock, Sale


class AccountSerializer(serializers.ModelSerializer):
    current_balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Account
        fields = "__all__"
        read_only_fields = ["company"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"
        read_only_fields = ["company"]


class PartySerializer(serializers.ModelSerializer):
    class Meta:
        model = Party
        fields = "__all__"
        read_only_fields = ["company"]


class TransactionSerializer(serializers.ModelSerializer):
    MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024
    ALLOWED_ATTACHMENT_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp'}

    category_name = serializers.CharField(source="category.name", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    party_name = serializers.CharField(source="party.name", read_only=True)

    def validate_attachment(self, attachment):
        if not attachment:
            return attachment
        if isinstance(attachment, str) and attachment.startswith('data:'):
            try:
                header, data = attachment.split(';base64,', 1)
                mime_type = header.split(':', 1)[1]
                allowed_mimes = {'image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'application/pdf'}
                if mime_type not in allowed_mimes:
                    raise serializers.ValidationError('Only PDF and image receipts are allowed.')
                size_bytes = len(data) * 3 // 4
                if size_bytes > self.MAX_ATTACHMENT_SIZE:
                    raise serializers.ValidationError('Attachment must be 5 MB or smaller.')
            except ValueError:
                raise serializers.ValidationError('Invalid base64 attachment format.')
        return attachment

    class Meta:
        model = Transaction
        fields = "__all__"
        read_only_fields = ["company"]


class DuePaymentSerializer(serializers.ModelSerializer):
    party_name = serializers.CharField(source="party.name", read_only=True)

    class Meta:
        model = DuePayment
        fields = "__all__"
        read_only_fields = ["company"]


class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Note
        fields = "__all__"
        read_only_fields = ["company"]


class StockSerializer(serializers.ModelSerializer):
    sold_stock = serializers.IntegerField(read_only=True)
    remaining_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = Stock
        fields = ["id", "name", "quantity", "unit_price", "sold_stock", "remaining_stock", "created_at", "updated_at"]


class SaleSerializer(serializers.ModelSerializer):
    stock_name = serializers.CharField(source="stock.name", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    total_price = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Sale
        fields = "__all__"
        read_only_fields = ["company"]

    def validate(self, attrs):
        stock = attrs.get('stock')
        quantity = attrs.get('quantity')
        
        sold = stock.sales.aggregate(total=Sum('quantity'))['total'] or 0
        if self.instance:
            sold -= self.instance.quantity
        
        remaining = stock.quantity - sold
        if quantity > remaining:
            raise serializers.ValidationError({
                "quantity": f"Only {remaining} items remaining in stock. You cannot sell {quantity} items."
            })
        return attrs


