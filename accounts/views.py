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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from rest_framework import status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from .models import Account, BackupRecord, Category, Company, DuePayment, Note, Party, Transaction, Stock, Sale, UserProfile
from .serializers import (
    AccountSerializer,
    BackupRecordSerializer,
    CategorySerializer,
    DuePaymentSerializer,
    NoteSerializer,
    PartySerializer,
    TransactionSerializer,
    StockSerializer,
    SaleSerializer,
)


def money(value):
    return Decimal(value or 0)


def filtered_transactions(request):
    qs = Transaction.objects.select_related("category", "account", "party")
    if request.user.is_authenticated:
        try:
            qs = qs.filter(company=request.user.profile.company)
        except AttributeError:
            pass
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
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        delta = Sum(
            Case(
                When(transactions__transaction_type="income", then=F("transactions__amount")),
                When(transactions__transaction_type="expense", then=-F("transactions__amount")),
                default=Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
        return Account.objects.filter(company=company).annotate(
            current_balance=F("opening_balance") + Coalesce(delta, Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)))
        )

    def perform_create(self, serializer):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        serializer.save(company=company)


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    queryset = Category.objects.all()

    def get_queryset(self):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        return Category.objects.filter(company=company).order_by("category_type", "name")

    def perform_create(self, serializer):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        serializer.save(company=company)


class PartyViewSet(viewsets.ModelViewSet):
    serializer_class = PartySerializer
    queryset = Party.objects.all()

    def get_queryset(self):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        return Party.objects.filter(company=company).order_by("name")

    def perform_create(self, serializer):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        serializer.save(company=company)


class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer
    queryset = Transaction.objects.select_related("category", "account", "party")

    def get_queryset(self):
        return filtered_transactions(self.request)

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset()[:200], many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        serializer.save(company=company)


class DuePaymentViewSet(viewsets.ModelViewSet):
    serializer_class = DuePaymentSerializer
    queryset = DuePayment.objects.select_related("party")

    def get_queryset(self):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        return DuePayment.objects.filter(company=company).select_related("party")

    def perform_create(self, serializer):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        serializer.save(company=company)


class NoteViewSet(viewsets.ModelViewSet):
    serializer_class = NoteSerializer
    queryset = Note.objects.all()

    def get_queryset(self):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        return Note.objects.filter(company=company)

    def perform_create(self, serializer):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        serializer.save(company=company)


class BackupRecordViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BackupRecordSerializer
    queryset = BackupRecord.objects.all()
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        return BackupRecord.objects.filter(company=company)


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf_view(request):
    from django.middleware.csrf import get_token
    return Response({
        "detail": "CSRF cookie set.",
        "csrfToken": get_token(request)
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    business_name = request.data.get("business_name")
    owner_name = request.data.get("owner_name")
    email = request.data.get("email")
    phone = request.data.get("phone")
    password = request.data.get("password")

    if not business_name or not owner_name or not email or not phone or not password:
        return Response({"detail": "All fields are required."}, status=status.HTTP_400_BAD_REQUEST)

    from django.contrib.auth.models import User
    if User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
        return Response({"detail": "This email is already registered."}, status=status.HTTP_400_BAD_REQUEST)

    from django.db import transaction
    if Company.objects.filter(name=business_name).exists():
        return Response({"detail": "This business name is already registered."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            company = Company.objects.create(name=business_name)
            user = User.objects.create(
                username=email,
                email=email,
                first_name=owner_name,
                is_staff=True
            )
            user.set_password(password)
            user.save()

            UserProfile.objects.create(
                user=user,
                business_name=business_name,
                owner_name=owner_name,
                phone=phone,
                company=company,
                role='admin'
            )

        return Response({
            "detail": "Account created successfully! Please login.",
            "username": user.username,
            "company_name": company.name
        })
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    username_or_business = request.data.get("username")
    password = request.data.get("password")

    user = authenticate(username=username_or_business, password=password)

    if not user and username_or_business:
        # Try to find a user by their associated business name or company name
        profile = UserProfile.objects.filter(company__name__iexact=username_or_business).first()
        if not profile:
            profile = UserProfile.objects.filter(business_name__iexact=username_or_business).first()
        
        if profile:
            user = authenticate(username=profile.user.username, password=password)

    if not user or not user.is_staff:
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_400_BAD_REQUEST)
    login(request, user)
    
    company_name = "Default Business"
    role = "staff"
    owner_name = user.first_name or user.username
    try:
        if hasattr(user, 'profile'):
            company_name = user.profile.company.name if user.profile.company else "Default Business"
            role = user.profile.role
            owner_name = user.profile.owner_name or user.first_name or user.username
    except Exception:
        pass

    return Response({
        "username": user.username,
        "owner_name": owner_name,
        "is_staff": user.is_staff,
        "company_name": company_name,
        "role": role
    })



class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return


@api_view(["POST"])
@authentication_classes([CsrfExemptSessionAuthentication])
def logout_view(request):
    logout(request)
    return Response({"detail": "Logged out"})


@api_view(["GET"])
def me_view(request):
    company_name = "Default Business"
    role = "staff"
    owner_name = request.user.first_name or request.user.username
    try:
        if hasattr(request.user, 'profile'):
            company_name = request.user.profile.company.name if request.user.profile.company else "Default Business"
            role = request.user.profile.role
            owner_name = request.user.profile.owner_name or request.user.first_name or request.user.username
    except Exception:
        pass
    return Response({
        "username": request.user.username,
        "owner_name": owner_name,
        "is_staff": request.user.is_staff,
        "company_name": company_name,
        "role": role
    })


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


def period_summary(company, start, end):
    totals = Transaction.objects.filter(company=company, date__gte=start, date__lte=end).aggregate(
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
    
    company = request.user.profile.company if request.user.is_authenticated and hasattr(request.user, 'profile') else None
    tx = Transaction.objects.filter(company=company)
    totals = tx.aggregate(
        income=Sum("amount", filter=Q(transaction_type="income")),
        expense=Sum("amount", filter=Q(transaction_type="expense")),
    )
    income = money(totals["income"])
    expense = money(totals["expense"])
    opening = money(Account.objects.filter(company=company).aggregate(total=Sum("opening_balance"))["total"])
    pending = DuePayment.objects.filter(company=company).exclude(status="paid")
    pending_totals = pending.aggregate(
        payable=Sum("amount", filter=Q(due_type="payable")),
        receivable=Sum("amount", filter=Q(due_type="receivable")),
    )
    
    accounts = Account.objects.filter(company=company).annotate(
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
                "today": period_summary(company, today, today),
                "week": period_summary(company, week_start, today),
                "month": period_summary(company, month_start, today),
                "year": period_summary(company, year_start, today),
            },
            "account_summaries": account_summaries,
            "recent_transactions": TransactionSerializer(tx.select_related("category", "account", "party")[:8], many=True).data,
            "pending_dues": DuePaymentSerializer(pending.select_related("party")[:8], many=True).data,
        }
    )


@api_view(["GET"])
def reports_view(request):
    qs = filtered_transactions(request)
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
            "by_date": [{"date": row["grouped_date"], "transaction_type": row["transaction_type"], "total": row["total"]} for row in by_date],
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
    company = request.user.profile.company if request.user.is_authenticated and hasattr(request.user, 'profile') else None
    record = BackupRecord.objects.create(
        company=company,
        backup_type=request.data.get("backup_type", "manual"),
        file=f"backups/{filename}",
        notes=request.data.get("notes", ""),
    )
    return Response(BackupRecordSerializer(record).data)


class StockViewSet(viewsets.ModelViewSet):
    serializer_class = StockSerializer
    queryset = Stock.objects.all()

    def get_queryset(self):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        return Stock.objects.filter(company=company).annotate(
            sold_stock=Coalesce(Sum("sales__quantity"), Value(0)),
            remaining_stock=F("quantity") - Coalesce(Sum("sales__quantity"), Value(0))
        ).order_by("name")

    def perform_create(self, serializer):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        serializer.save(company=company)


class SaleViewSet(viewsets.ModelViewSet):
    serializer_class = SaleSerializer
    queryset = Sale.objects.select_related("stock", "account").order_by("-date", "-created_at")

    def get_queryset(self):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        return Sale.objects.filter(company=company).select_related("stock", "account").order_by("-date", "-created_at")

    def perform_create(self, serializer):
        company = self.request.user.profile.company if self.request.user.is_authenticated and hasattr(self.request.user, 'profile') else None
        serializer.save(company=company)


@api_view(["GET"])
def export_sales_excel_view(request):
    company = request.user.profile.company if request.user.is_authenticated and hasattr(request.user, 'profile') else None
    qs = Sale.objects.filter(company=company).select_related("stock", "account").order_by("-date", "-created_at")
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales Statement"
    ws.append(["Date", "Stock Item", "Quantity", "Sale Price (Rs)", "Total Price (Rs)", "Account", "Notes"])
    for sale in qs:
        ws.append([
            sale.date.isoformat() if sale.date else "",
            sale.stock.name if sale.stock else "",
            sale.quantity,
            sale.sale_price,
            sale.total_price,
            sale.account.name if sale.account else "",
            sale.notes
        ])
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="sales-statement.xlsx"'
    wb.save(response)
    return response


@api_view(["GET"])
def export_sales_pdf_view(request):
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="sales-statement.pdf"'
    
    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        textColor=colors.HexColor('#0f766e'),
        spaceAfter=4
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=15
    )
    
    cell_style = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#1e293b')
    )

    cell_header_style = ParagraphStyle(
        'CellHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.white
    )

    story.append(Paragraph("LedgerPro", title_style))
    story.append(Paragraph("Sales Ledger Statement - Generated on " + timezone.now().strftime("%Y-%m-%d %H:%M"), subtitle_style))
    story.append(Spacer(1, 10))
    
    headers = [
        Paragraph("Date", cell_header_style),
        Paragraph("Stock Item", cell_header_style),
        Paragraph("Qty", cell_header_style),
        Paragraph("Rate (Rs)", cell_header_style),
        Paragraph("Total Price (Rs)", cell_header_style),
        Paragraph("Account", cell_header_style)
    ]
    
    table_data = [headers]
    
    company = request.user.profile.company if request.user.is_authenticated and hasattr(request.user, 'profile') else None
    sales = Sale.objects.filter(company=company).select_related("stock", "account").order_by("-date", "-created_at")
    total_sales_amount = Decimal(0)
    
    for sale in sales:
        total_sales_amount += sale.total_price or Decimal(0)
        table_data.append([
            Paragraph(sale.date.isoformat() if sale.date else "-", cell_style),
            Paragraph(sale.stock.name if sale.stock else "-", cell_style),
            Paragraph(str(sale.quantity), cell_style),
            Paragraph(f"Rs {sale.sale_price:,.0f}", cell_style),
            Paragraph(f"Rs {sale.total_price:,.0f}", cell_style),
            Paragraph(sale.account.name if sale.account else "-", cell_style)
        ])
        
    col_widths = [70, 150, 40, 75, 85, 95]
    sales_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    t_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ])
    
    for i in range(1, len(table_data)):
        bg_color = colors.HexColor('#f8fafc') if i % 2 == 0 else colors.white
        t_style.add('BACKGROUND', (0, i), (-1, i), bg_color)
        
    sales_table.setStyle(t_style)
    story.append(sales_table)
    story.append(Spacer(1, 15))
    
    summary_data = [
        [Paragraph("<strong>Total Sales:</strong>", cell_style), Paragraph(f"<strong>Rs {total_sales_amount:,.0f}</strong>", cell_style)]
    ]
    summary_table = Table(summary_data, colWidths=[100, 150])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, colors.HexColor('#0f766e')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(summary_table)
    doc.build(story)
    return response


