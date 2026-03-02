from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from permissions.roles import (
    CAP_POS_REFUND,
    CAP_POS_SELL,
    CAP_REPORTS_VIEW_POS,
    HasCapability,
    HasAnyCapability,
)

from sales.models.sale import Sale
from sales.serializers.refund_command import SaleRefundCommandSerializer
from sales.serializers.sale import SaleSerializer
from sales.services.refund_orchestrator import refund_sale_with_stock_restoration
from sales.services.refund_service import (
    RefundError,
    OverRefundError,
)

from accounting.services.exceptions import AccountingServiceError


# ======================================================
# API ERROR NORMALIZATION
# ======================================================


def error_response(*, code: str, message: str, http_status: int):
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

    - list/retrieve: operational visibility
    - refund: protected capability (admin/manager)
    """

    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated]

    # --------------------------------------------------
    # QUERYSET
    # --------------------------------------------------

    def get_queryset(self):
        return (
            Sale.objects
            .select_related("user")
            .prefetch_related(
                "items",
                "items__product",
                "refund_audits",
            )
        )

    # --------------------------------------------------
    # PERMISSIONS
    # --------------------------------------------------

    def get_permissions(self):

        if self.action == "refund":
            self.required_capability = CAP_POS_REFUND
            return [IsAuthenticated(), HasCapability()]

        self.required_any_capabilities = {
            CAP_POS_SELL,
            CAP_REPORTS_VIEW_POS,
        }
        return [IsAuthenticated(), HasAnyCapability()]

    # --------------------------------------------------
    # SERIALIZER SWITCH
    # --------------------------------------------------

    def get_serializer_class(self):
        if self.action == "refund":
            return SaleRefundCommandSerializer
        return SaleSerializer

    # --------------------------------------------------
    # REFUND SALE
    # --------------------------------------------------

    @action(detail=True, methods=["post"], url_path="refund")
    def refund(self, request, pk=None):

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
                refund_reason=command_serializer.validated_data.get(
                    "reason", ""
                ),
            )

        except OverRefundError as exc:
            return error_response(
                code="OVER_REFUND",
                message=str(exc),
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        except AccountingServiceError as exc:
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

        serializer = SaleSerializer(
            refunded_sale,
            context={"request": request},
        )

        return Response(serializer.data, status=status.HTTP_200_OK)