# pharmacy_backend/sales/views.py

from django.db.models import Sum
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from permissions.roles import IsPharmacistOrAdmin, IsCashier

from .models import Sale
from .serializers import SaleSerializer


# ======================================================================
# SALES REPORTING (READ-ONLY)
# ======================================================================

class SaleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Sales Reporting ViewSet (READ-ONLY)

    PURPOSE:
    - View completed sales
    - Daily summaries
    - Receipt views
    - Analytics & audits

    IMPORTANT:
    - Sales are CREATED ONLY via POS Checkout
    - No stock mutation happens here
    """

    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated, IsPharmacistOrAdmin]

    def get_queryset(self):
        qs = (
            Sale.objects
            .select_related("user")
            .prefetch_related("items", "items__product")
            .order_by("-created_at")
        )

        params = self.request.query_params

        date_from = params.get("date_from")
        date_to = params.get("date_to")
        cashier_id = params.get("cashier_id")
        payment_method = params.get("payment_method")

        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        if cashier_id:
            qs = qs.filter(user_id=cashier_id)

        if payment_method:
            qs = qs.filter(payment_method__iexact=payment_method)

        return qs

    # -------------------- DAILY SUMMARY --------------------

    @action(detail=False, methods=["get"], url_path="daily-summary")
    def daily_summary(self, request):
        today = timezone.now().date()

        qs = Sale.objects.filter(created_at__date=today)

        summary = qs.aggregate(
            total_revenue=Sum("total_amount"),
        )

        return Response(
            {
                "date": today,
                "total_transactions": qs.count(),
                "total_revenue": summary["total_revenue"] or 0,
            },
            status=status.HTTP_200_OK,
        )

    # -------------------- RECEIPT VIEW --------------------

    @action(detail=True, methods=["get"], url_path="receipt")
    def receipt(self, request, pk=None):
        sale = self.get_object()

        return Response(
            SaleSerializer(sale).data,
            status=status.HTTP_200_OK,
        )


# ======================================================================
# POS CHECKOUT (WRITE ONLY)
# ======================================================================

class SaleCreateView(APIView):
    """
    POS Checkout Endpoint

    GUARANTEES:
    - Atomic transaction
    - FIFO stock deduction
    - StockMovement audit
    - Sale created ONLY if stock deduction succeeds

    NOTE:
    - All business logic lives in SaleSerializer.create()
    """

    permission_classes = [IsAuthenticated, IsCashier]

    def post(self, request):
        serializer = SaleSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        sale = serializer.save()

        return Response(
            {
                "sale_id": sale.id,
                "invoice_no": sale.invoice_no,
                "total_amount": sale.total_amount,
                "status": sale.status,
                "created_at": sale.created_at,
            },
            status=status.HTTP_201_CREATED,
        )
