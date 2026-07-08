import shutil
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.db.models import Case, Count, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from .models import Account, BackupRecord, Category, DuePayment, Note, Party, Transaction
from .serializers import (
    AccountSerializer,
    BackupRecordSerializer,
    CategorySerializer,
    DuePaymentSerializer,
    NoteSerializer,
    PartySerializer,
    TransactionSerializer,
)


def money(value):
    return Decimal(value or 0)


def filtered_transactions(request):
    qs = Transaction.objects.select_related("category", "account", "party")
    start = request.query_params.get("start")
    end = request.query_params.get("end")
    category = request.query_params.get("category")
    method = request.query_params.get("payment_method")
    min_amount = request.query_params.get("min_amount")
    max_amount = request.query_params.get("max_amount")
    keyword = request.query_params.get("keyword")
    tx_type = request.query_params.get("transaction_type")

    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    if category:
        qs = qs.filter(category_id=category)
    if method:
        qs = qs.filter(payment_method=method)
    if min_amount:
        qs = qs.filter(amount__gte=min_amount)
    if max_amount:
        qs = qs.filter(amount__lte=max_amount)
    if tx_type:
        qs = qs.filter(transaction_type=tx_type)
    if keyword:
        qs = qs.filter(
            Q(title__icontains=keyword)
            | Q(notes__icontains=keyword)
            | Q(reference_number__icontains=keyword)
            | Q(party__name__icontains=keyword)
            | Q(category__name__icontains=keyword)
        )
    return qs


class AccountViewSet(viewsets.ModelViewSet):
    serializer_class = AccountSerializer
    queryset = Account.objects.all()

    def get_queryset(self):
        delta = Sum(
            Case(
                When(transactions__transaction_type="income", then=F("transactions__amount")),
                When(transactions__transaction_type="expense", then=-F("transactions__amount")),
                default=Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
        return Account.objects.annotate(
            current_balance=F("opening_balance") + Coalesce(delta, Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)))
        )


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    queryset = Category.objects.all().order_by("category_type", "name")


class PartyViewSet(viewsets.ModelViewSet):
    serializer_class = PartySerializer
    queryset = Party.objects.all().order_by("name")


class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer
    queryset = Transaction.objects.select_related("category", "account", "party")

    def get_queryset(self):
        return filtered_transactions(self.request)

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset()[:200], many=True)
        return Response(serializer.data)


class DuePaymentViewSet(viewsets.ModelViewSet):
    serializer_class = DuePaymentSerializer
    queryset = DuePayment.objects.select_related("party")


class NoteViewSet(viewsets.ModelViewSet):
    serializer_class = NoteSerializer
    queryset = Note.objects.all()


class BackupRecordViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BackupRecordSerializer
    queryset = BackupRecord.objects.all()
    permission_classes = [IsAdminUser]


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf_view(request):
    return Response({"detail": "CSRF cookie set."})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    user = authenticate(username=request.data.get("username"), password=request.data.get("password"))
    if not user or not user.is_staff:
        return Response({"detail": "Invalid admin credentials."}, status=status.HTTP_400_BAD_REQUEST)
    login(request, user)
    return Response({"username": user.username, "is_staff": user.is_staff})


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response({"detail": "Logged out"})


@api_view(["GET"])
def me_view(request):
    return Response({"username": request.user.username, "is_staff": request.user.is_staff})


@api_view(["POST"])
def change_password_view(request):
    old_password = request.data.get("old_password")
    new_password = request.data.get("new_password")
    if not request.user.check_password(old_password):
        return Response({"detail": "Old password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        validate_password(new_password, request.user)
    except ValidationError as error:
        return Response({"detail": error.messages}, status=status.HTTP_400_BAD_REQUEST)
    request.user.set_password(new_password)
    request.user.save()
    update_session_auth_hash(request, request.user)
    return Response({"detail": "Password changed."})


def period_summary(start, end):
    totals = Transaction.objects.filter(date__gte=start, date__lte=end).aggregate(
        income=Sum("amount", filter=Q(transaction_type="income")),
        expense=Sum("amount", filter=Q(transaction_type="expense")),
    )
    income = money(totals["income"])
    expense = money(totals["expense"])
    return {"income": income, "expense": expense, "balance": income - expense}


@api_view(["GET"])
def dashboard_view(request):
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    
    tx = Transaction.objects.all()
    totals = tx.aggregate(
        income=Sum("amount", filter=Q(transaction_type="income")),
        expense=Sum("amount", filter=Q(transaction_type="expense")),
    )
    income = money(totals["income"])
    expense = money(totals["expense"])
    opening = money(Account.objects.aggregate(total=Sum("opening_balance"))["total"])
    pending = DuePayment.objects.exclude(status="paid")
    pending_totals = pending.aggregate(
        payable=Sum("amount", filter=Q(due_type="payable")),
        receivable=Sum("amount", filter=Q(due_type="receivable")),
    )
    
    accounts = Account.objects.annotate(
        account_income=Sum("transactions__amount", filter=Q(transactions__transaction_type="income")),
        account_expense=Sum("transactions__amount", filter=Q(transactions__transaction_type="expense"))
    ).order_by("name")

    account_summaries = []
    for account in accounts:
        inc = money(account.account_income)
        exp = money(account.account_expense)
        account_summaries.append(
            {
                "id": account.id,
                "name": account.name,
                "account_type": account.account_type,
                "opening_balance": account.opening_balance,
                "income": inc,
                "expense": exp,
                "current_balance": account.opening_balance + inc - exp,
            }
        )

    return Response(
        {
            "totals": {
                "income": income,
                "expense": expense,
                "current_balance": opening + income - expense,
                "pending_payable": money(pending_totals["payable"]),
                "pending_receivable": money(pending_totals["receivable"]),
            },
            "periods": {
                "today": period_summary(today, today),
                "week": period_summary(week_start, today),
                "month": period_summary(month_start, today),
                "year": period_summary(year_start, today),
            },
            "account_summaries": account_summaries,
            "recent_transactions": TransactionSerializer(tx.select_related("category", "account", "party")[:8], many=True).data,
            "pending_dues": DuePaymentSerializer(pending.select_related("party")[:8], many=True).data,
        }
    )


@api_view(["GET"])
def reports_view(request):
    qs = filtered_transactions(request)
    by_category = (
        qs.values("category__name", "transaction_type")
        .annotate(total=Sum("amount"))
        .order_by("category__name")
    )
    by_month = (
        qs.annotate(month=TruncMonth("date"))
        .values("month", "transaction_type")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )
    by_date = (
        qs.annotate(grouped_date=TruncDate("date"))
        .values("grouped_date", "transaction_type")
        .annotate(total=Sum("amount"))
        .order_by("grouped_date")
    )
    totals = qs.aggregate(
        income=Sum("amount", filter=Q(transaction_type="income")),
        expense=Sum("amount", filter=Q(transaction_type="expense")),
    )
    income = money(totals["income"])
    expense = money(totals["expense"])
    return Response(
        {
            "summary": {"income": income, "expense": expense, "balance": income - expense},
            "by_category": list(by_category),
            "by_month": list(by_month),
            "by_date": [{"date": row["grouped_date"], "transaction_type": row["transaction_type"], "total": row["total"]} for row in by_date],
            "transactions": TransactionSerializer(qs[:200], many=True).data,
        }
    )


@api_view(["GET"])
def export_excel_view(request):
    qs = filtered_transactions(request)
    wb = Workbook()
    ws = wb.active
    ws.title = "Statement"
    ws.append(["Date", "Type", "Title", "Category", "Account", "Party", "Method", "Reference", "Debit", "Credit"])
    for tx in qs:
        ws.append([
            tx.date.isoformat(),
            tx.transaction_type,
            tx.title,
            tx.category.name,
            tx.account.name,
            tx.party.name if tx.party else "",
            tx.payment_method,
            tx.reference_number,
            tx.amount if tx.transaction_type == "expense" else "",
            tx.amount if tx.transaction_type == "income" else "",
        ])
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="account-statement.xlsx"'
    wb.save(response)
    return response


@api_view(["GET"])
def export_pdf_view(request):
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="account-statement.pdf"'
    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    y = height - 50
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, "Account Statement")
    y -= 30
    pdf.setFont("Helvetica", 9)
    for tx in filtered_transactions(request):
        line = f"{tx.date} | {tx.transaction_type.upper()} | {tx.title} | {tx.category.name} | Rs {tx.amount}"
        pdf.drawString(40, y, line[:115])
        y -= 18
        if y < 50:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 9)
    pdf.save()
    return response


@api_view(["POST"])
@permission_classes([IsAdminUser])
def create_backup_view(request):
    backups_dir = settings.MEDIA_ROOT / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    filename = f"backup-{timezone.now().strftime('%Y%m%d-%H%M%S')}.sqlite3"
    target = backups_dir / filename
    shutil.copyfile(settings.DATABASES["default"]["NAME"], target)
    record = BackupRecord.objects.create(
        backup_type=request.data.get("backup_type", "manual"),
        file=f"backups/{filename}",
        notes=request.data.get("notes", ""),
    )
    return Response(BackupRecordSerializer(record).data)
