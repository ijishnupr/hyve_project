"""API viewsets for the procurement module."""
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from . import services
from .filters import (
    GRNFilter,
    MaterialFilter,
    PurchaseOrderFilter,
    PurchaseRequisitionFilter,
    VendorBillFilter,
    VendorFilter,
)
from .models import (
    GoodsReceiptNote,
    Material,
    MaterialCategory,
    Project,
    PurchaseOrder,
    PurchaseRequisition,
    Vendor,
    VendorBill,
)
from .permissions import (
    CanApprove,
    CanManageBills,
    IsProcurementManagerOrReadOnly,
)
from .serializers import (
    GoodsReceiptNoteSerializer,
    MaterialCategorySerializer,
    MaterialSerializer,
    ProjectSerializer,
    PurchaseOrderSerializer,
    PurchaseRequisitionSerializer,
    VendorBillSerializer,
    VendorSerializer,
)


def _transition(fn, *args, **kwargs):
    """Run a service transition, mapping TransitionError -> HTTP 400."""
    try:
        return fn(*args, **kwargs)
    except services.TransitionError as exc:
        raise ValidationError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------
class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    search_fields = ["code", "name", "location"]
    ordering_fields = ["code", "name", "created_at"]
    filterset_fields = ["status", "manager"]


class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_class = VendorFilter
    search_fields = ["code", "name", "gstin", "contact_person"]
    ordering_fields = ["name", "code", "rating", "created_at"]


class MaterialCategoryViewSet(viewsets.ModelViewSet):
    queryset = MaterialCategory.objects.all()
    serializer_class = MaterialCategorySerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    search_fields = ["name"]


class MaterialViewSet(viewsets.ModelViewSet):
    queryset = Material.objects.select_related("category").all()
    serializer_class = MaterialSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_class = MaterialFilter
    search_fields = ["code", "name", "hsn_code"]
    ordering_fields = ["name", "code", "created_at"]


# ---------------------------------------------------------------------------
# Purchase Requisition
# ---------------------------------------------------------------------------
class PurchaseRequisitionViewSet(viewsets.ModelViewSet):
    queryset = (
        PurchaseRequisition.objects.select_related("project", "requested_by")
        .prefetch_related("lines__material")
        .all()
    )
    serializer_class = PurchaseRequisitionSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_class = PurchaseRequisitionFilter
    search_fields = ["number", "notes"]
    ordering_fields = ["created_at", "required_by", "number"]

    @extend_schema(request=None, responses=PurchaseRequisitionSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        pr = _transition(services.submit_requisition, self.get_object())
        return Response(self.get_serializer(pr).data)

    @extend_schema(request=None, responses=PurchaseRequisitionSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def approve(self, request, pk=None):
        pr = _transition(services.approve_requisition, self.get_object(), user=request.user)
        return Response(self.get_serializer(pr).data)

    @extend_schema(
        request={"application/json": {"type": "object", "properties": {"reason": {"type": "string"}}}},
        responses=PurchaseRequisitionSerializer,
    )
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def reject(self, request, pk=None):
        reason = request.data.get("reason", "")
        pr = _transition(
            services.reject_requisition, self.get_object(), user=request.user, reason=reason
        )
        return Response(self.get_serializer(pr).data)


# ---------------------------------------------------------------------------
# Purchase Order
# ---------------------------------------------------------------------------
class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = (
        PurchaseOrder.objects.select_related("vendor", "project", "created_by")
        .prefetch_related("lines__material")
        .all()
    )
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_class = PurchaseOrderFilter
    search_fields = ["number", "terms_and_conditions"]
    ordering_fields = ["created_at", "order_date", "total", "number"]

    @extend_schema(request=None, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def issue(self, request, pk=None):
        po = _transition(services.issue_purchase_order, self.get_object(), user=request.user)
        return Response(self.get_serializer(po).data)

    @extend_schema(request=None, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def cancel(self, request, pk=None):
        po = _transition(services.cancel_purchase_order, self.get_object())
        return Response(self.get_serializer(po).data)

    @extend_schema(request=None, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def close(self, request, pk=None):
        po = _transition(services.close_purchase_order, self.get_object())
        return Response(self.get_serializer(po).data)


# ---------------------------------------------------------------------------
# Goods Receipt Note
# ---------------------------------------------------------------------------
class GoodsReceiptNoteViewSet(viewsets.ModelViewSet):
    queryset = (
        GoodsReceiptNote.objects.select_related("purchase_order", "received_by")
        .prefetch_related("lines__po_line__material")
        .all()
    )
    serializer_class = GoodsReceiptNoteSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_class = GRNFilter
    search_fields = ["number", "challan_number", "vehicle_number"]
    ordering_fields = ["created_at", "received_date", "number"]

    @extend_schema(request=None, responses=GoodsReceiptNoteSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        grn = _transition(services.confirm_grn, self.get_object())
        return Response(self.get_serializer(grn).data)

    @extend_schema(request=None, responses=GoodsReceiptNoteSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        grn = _transition(services.cancel_grn, self.get_object())
        return Response(self.get_serializer(grn).data)


# ---------------------------------------------------------------------------
# Vendor Bill
# ---------------------------------------------------------------------------
class VendorBillViewSet(viewsets.ModelViewSet):
    queryset = (
        VendorBill.objects.select_related("vendor", "purchase_order", "created_by")
        .prefetch_related("lines__po_line__material")
        .all()
    )
    serializer_class = VendorBillSerializer
    permission_classes = [CanManageBills]
    filterset_class = VendorBillFilter
    search_fields = ["number", "vendor_invoice_number"]
    ordering_fields = ["created_at", "bill_date", "total", "number"]

    @extend_schema(request=None, responses=VendorBillSerializer)
    @action(detail=True, methods=["post"])
    def match(self, request, pk=None):
        bill = services.run_three_way_match(self.get_object())
        return Response(self.get_serializer(bill).data)

    @extend_schema(request=None, responses=VendorBillSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        bill = _transition(services.approve_bill, self.get_object())
        return Response(self.get_serializer(bill).data)

    @extend_schema(request=None, responses=VendorBillSerializer)
    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        bill = _transition(services.mark_bill_paid, self.get_object())
        return Response(self.get_serializer(bill).data)
