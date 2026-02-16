# sales/views/refund.py

from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from sales.models.sale import Sale
from sales.serializers.sale import SaleSerializer
from sales.serializers.refund_command import SaleRefundCommandSerializer
from sales.services.refund_orchestrator import refund_sale_with_stock_restoration
from sales.services.refund_service import (
    RefundError,
    InvalidSaleStateError,
    DuplicateRefundError,
    AccountingPostingError,
)

from permissions.roles import (
    HasCapability,
    CAP_POS_REFUND,
    CAP_REPORTS_VIEW_POS,
    CAP_POS_SELL,
)


# ======================================================
# API ERROR NORMALIZATION
# ======================================================

def error_response(*, code: str, message: str, http_status: int):
    """
    Canonical API error response.
    """
    return Response(
        {"error": {"code": code, "message": message}},
        status=http_status,
    )


# ======================================================
# SALE READ + REFUND VIEWSET
# ======================================================

class SaleRefundViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Sale ViewSet (READ + REFUND).

    - list/retrieve: for staff operational visibility
    - refund: protected capability (admin/manager)
    """

    queryset = (
        Sale.objects
        .select_related("user")
        .prefetch_related(
            "items",
            "items__product",
            "refund_audit",
        )
    )

    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated]

    # Capability hooks used by HasCapability
    required_capability = None

    def get_permissions(self):
        """
        Action-specific permissions.

        Rules (Phase 1.2):
        - refund requires CAP_POS_REFUND (admin/manager)
        - list/retrieve require at least POS visibility capability
          (we allow either selling or viewing POS reports)
        """
        if self.action == "refund":
            self.required_capability = CAP_POS_REFUND
            return [IsAuthenticated(), HasCapability()]

        # Read access:
        # If you want to restrict sales visibility only to admin/manager/pharmacist,
        # keep this as capability-based rather than role-based.
        self.required_any_capabilities = {CAP_POS_SELL, CAP_REPORTS_VIEW_POS}
        from permissions.roles import HasAnyCapability  # local import to avoid circulars
        return [IsAuthenticated(), HasAnyCapability()]

    def get_serializer_class(self):
        """
        Use command serializer for refund action,
        read serializer for everything else.
        """
        if self.action == "refund":
            return SaleRefundCommandSerializer
        return SaleSerializer

    # --------------------------------------------------
    # REFUND SALE (FULL REFUND ONLY)
    # --------------------------------------------------

    @action(detail=True, methods=["post"], url_path="refund")
    def refund(self, request, pk=None):
        """
        Refund a completed sale.
        """
        sale = self.get_object()

        command_serializer = SaleRefundCommandSerializer(
            data=request.data,
            context={"request": request},
        )
        command_serializer.is_valid(raise_exception=True)

        try:
            refunded_sale = refund_sale_with_stock_restoration(
                sale=sale,
                user=request.user,
                refund_reason=command_serializer.validated_data.get("reason", ""),
            )

        except InvalidSaleStateError as exc:
            return error_response(
                code="INVALID_SALE_STATE",
                message=str(exc),
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        except DuplicateRefundError:
            return error_response(
                code="SALE_ALREADY_REFUNDED",
                message="This sale has already been refunded.",
                http_status=status.HTTP_409_CONFLICT,
            )

        except AccountingPostingError as exc:
            return error_response(
                code="ACCOUNTING_POST_FAILED",
                message=str(exc),
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        except RefundError as exc:
            return error_response(
                code="REFUND_FAILED",
                message=str(exc),
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SaleSerializer(refunded_sale)
        return Response(serializer.data, status=status.HTTP_200_OK)
