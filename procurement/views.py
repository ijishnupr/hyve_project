"""API viewsets for the procurement module."""
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .filters import (
    GRNFilter,
    MaterialFilter,
    PurchaseOrderFilter,
    PurchaseRequisitionFilter,
    RFQFilter,
    SupplierQuotationFilter,
    VendorBillFilter,
    VendorFilter,
)
from .models import (
    ApprovalRequest,
    ApprovalRule,
    ApprovalStep,
    Attachment,
    GoodsReceiptNote,
    Material,
    MaterialCategory,
    PurchaseContract,
    Payment,
    PaymentSchedule,
    PurchaseReturn,
    QualityInspection,
    StockItem,
    StockLedgerEntry,
    Project,
    PurchaseOrder,
    PurchaseRequisition,
    RequestForQuotation,
    SupplierAddress,
    SupplierBankAccount,
    SupplierContact,
    SupplierDocument,
    SupplierQuotation,
    Vendor,
    VendorBill,
)
from .permissions import (
    CanApprove,
    CanManageBills,
    IsProcurementManagerOrReadOnly,
)
from .serializers import (
    ApprovalRequestSerializer,
    ApprovalRuleSerializer,
    ApprovalStepSerializer,
    AttachmentSerializer,
    PurchaseContractSerializer,
    PaymentScheduleSerializer,
    PaymentSerializer,
    PurchaseReturnSerializer,
    QualityInspectionSerializer,
    StockItemSerializer,
    StockLedgerEntrySerializer,
    GoodsReceiptNoteSerializer,
    MaterialCategorySerializer,
    MaterialSerializer,
    ProjectSerializer,
    PurchaseOrderSerializer,
    PurchaseRequisitionSerializer,
    RequestForQuotationSerializer,
    SupplierAddressSerializer,
    SupplierBankAccountSerializer,
    SupplierContactSerializer,
    SupplierDocumentSerializer,
    SupplierQuotationSerializer,
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
# Approval workflow
# ---------------------------------------------------------------------------
class ApprovalRuleViewSet(viewsets.ModelViewSet):
    queryset = ApprovalRule.objects.all()
    serializer_class = ApprovalRuleSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_fields = ["document_type", "is_active", "level"]
    search_fields = ["name", "role_required"]
    ordering_fields = ["document_type", "level", "min_amount"]


class ApprovalRequestViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        ApprovalRequest.objects.select_related("content_type")
        .prefetch_related("steps__acted_by").all()
    )
    serializer_class = ApprovalRequestSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["document_type", "status"]
    ordering_fields = ["created_at", "amount"]


class ApprovalStepViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ApprovalStep.objects.select_related("request", "acted_by").all()
    serializer_class = ApprovalStepSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "role_required", "request"]

    @extend_schema(
        request={"application/json": {"type": "object",
                 "properties": {"comments": {"type": "string"}}}},
        responses=ApprovalStepSerializer,
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        step = _transition(services.approve_step, self.get_object(),
                           user=request.user, comments=request.data.get("comments", ""))
        return Response(self.get_serializer(step).data)

    @extend_schema(
        request={"application/json": {"type": "object",
                 "properties": {"comments": {"type": "string"}}}},
        responses=ApprovalStepSerializer,
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        step = _transition(services.reject_step, self.get_object(),
                          user=request.user, comments=request.data.get("comments", ""))
        return Response(self.get_serializer(step).data)

    @extend_schema(responses=ApprovalStepSerializer(many=True))
    @action(detail=False, methods=["get"], url_path="my-pending")
    def my_pending(self, request):
        steps = services.pending_steps_for_user(request.user)
        return Response(self.get_serializer(steps, many=True).data)


class AttachmentViewSet(viewsets.ModelViewSet):
    queryset = Attachment.objects.select_related("content_type", "uploaded_by").all()
    serializer_class = AttachmentSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["content_type", "object_id", "kind"]

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class StockItemViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StockItem.objects.select_related("material", "project").all()
    serializer_class = StockItemSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["material", "project"]
    search_fields = ["material__name", "project__name"]
    ordering_fields = ["quantity_on_hand", "updated_at"]


class StockLedgerEntryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StockLedgerEntry.objects.select_related("material", "project").all()
    serializer_class = StockLedgerEntrySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["material", "project", "movement"]
    ordering_fields = ["created_at"]


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


class SupplierContactViewSet(viewsets.ModelViewSet):
    queryset = SupplierContact.objects.select_related("vendor").all()
    serializer_class = SupplierContactSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_fields = ["vendor", "is_primary"]
    search_fields = ["name", "email", "phone"]


class SupplierAddressViewSet(viewsets.ModelViewSet):
    queryset = SupplierAddress.objects.select_related("vendor").all()
    serializer_class = SupplierAddressSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_fields = ["vendor", "kind", "is_default"]
    search_fields = ["line1", "city", "state", "pincode"]


class SupplierBankAccountViewSet(viewsets.ModelViewSet):
    queryset = SupplierBankAccount.objects.select_related("vendor").all()
    serializer_class = SupplierBankAccountSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_fields = ["vendor", "is_default"]
    search_fields = ["bank_name", "account_number", "ifsc"]


class SupplierDocumentViewSet(viewsets.ModelViewSet):
    queryset = SupplierDocument.objects.select_related("vendor").all()
    serializer_class = SupplierDocumentSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_fields = ["vendor", "kind"]
    search_fields = ["title"]


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
# Request for Quotation
# ---------------------------------------------------------------------------
class RequestForQuotationViewSet(viewsets.ModelViewSet):
    queryset = (
        RequestForQuotation.objects.select_related("project", "created_by")
        .prefetch_related("lines__material", "vendors")
        .all()
    )
    serializer_class = RequestForQuotationSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_class = RFQFilter
    search_fields = ["number", "notes", "terms"]
    ordering_fields = ["created_at", "issue_date", "response_deadline", "number"]

    @extend_schema(request=None, responses=RequestForQuotationSerializer)
    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        rfq = _transition(services.send_rfq, self.get_object(), user=request.user)
        return Response(self.get_serializer(rfq).data)

    @extend_schema(request=None, responses=RequestForQuotationSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        rfq = _transition(services.close_rfq, self.get_object())
        return Response(self.get_serializer(rfq).data)

    @extend_schema(request=None, responses=RequestForQuotationSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        rfq = _transition(services.cancel_rfq, self.get_object())
        return Response(self.get_serializer(rfq).data)


class SupplierQuotationViewSet(viewsets.ModelViewSet):
    queryset = (
        SupplierQuotation.objects.select_related("rfq", "vendor", "created_by")
        .prefetch_related("lines__material")
        .all()
    )
    serializer_class = SupplierQuotationSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_class = SupplierQuotationFilter
    search_fields = ["number", "notes"]
    ordering_fields = ["total", "delivery_days", "created_at", "number"]

    @extend_schema(request=None, responses=SupplierQuotationSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def select(self, request, pk=None):
        _transition(services.select_quotation, self.get_object(), user=request.user)
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(request=None, responses=SupplierQuotationSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        q = _transition(services.reject_quotation, self.get_object())
        return Response(self.get_serializer(q).data)


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

    @extend_schema(request=None, responses=ApprovalRequestSerializer)
    @action(detail=True, methods=["post"], url_path="submit-approval")
    def submit_approval(self, request, pk=None):
        req = _transition(services.submit_po_for_approval, self.get_object(), user=request.user)
        return Response(ApprovalRequestSerializer(req).data)

    @extend_schema(request=None, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def issue(self, request, pk=None):
        po = _transition(services.issue_purchase_order, self.get_object(), user=request.user)
        return Response(self.get_serializer(po).data)

    @extend_schema(request=None, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def reopen(self, request, pk=None):
        po = _transition(services.reopen_purchase_order, self.get_object(), user=request.user)
        return Response(self.get_serializer(po).data)

    @extend_schema(request=None, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=["post"])
    def email(self, request, pk=None):
        po = self.get_object()
        services.email_purchase_order(po)
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


class QualityInspectionViewSet(viewsets.ModelViewSet):
    queryset = (
        QualityInspection.objects.select_related("grn", "inspected_by")
        .prefetch_related("items").all()
    )
    serializer_class = QualityInspectionSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_fields = ["status", "grn"]
    search_fields = ["number", "remarks"]
    ordering_fields = ["created_at", "number"]

    @extend_schema(request=None, responses=QualityInspectionSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        insp = _transition(services.submit_inspection, self.get_object(), user=request.user)
        return Response(self.get_serializer(insp).data)


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


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related("vendor", "bill", "created_by").all()
    serializer_class = PaymentSerializer
    permission_classes = [CanManageBills]
    filterset_fields = ["vendor", "bill", "status", "payment_type", "method"]
    search_fields = ["number", "reference"]
    ordering_fields = ["payment_date", "amount", "created_at"]

    @extend_schema(request=None, responses=PaymentSerializer)
    @action(detail=True, methods=["post"])
    def post_payment(self, request, pk=None):
        payment = _transition(services.post_payment, self.get_object())
        return Response(self.get_serializer(payment).data)

    @extend_schema(request=None, responses=PaymentSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        payment = _transition(services.cancel_payment, self.get_object())
        return Response(self.get_serializer(payment).data)


class PaymentScheduleViewSet(viewsets.ModelViewSet):
    queryset = PaymentSchedule.objects.select_related("vendor", "bill").all()
    serializer_class = PaymentScheduleSerializer
    permission_classes = [CanManageBills]
    filterset_fields = ["vendor", "bill", "status"]
    ordering_fields = ["due_date", "amount"]


class PurchaseContractViewSet(viewsets.ModelViewSet):
    queryset = (
        PurchaseContract.objects.select_related("vendor", "created_by")
        .prefetch_related("lines__material").all()
    )
    serializer_class = PurchaseContractSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_fields = ["status", "vendor", "contract_type"]
    search_fields = ["number", "title"]
    ordering_fields = ["created_at", "start_date", "end_date", "number"]

    @extend_schema(request=None, responses=PurchaseContractSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def activate(self, request, pk=None):
        c = _transition(services.activate_contract, self.get_object())
        return Response(self.get_serializer(c).data)

    @extend_schema(request=None, responses=PurchaseContractSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def terminate(self, request, pk=None):
        c = _transition(services.terminate_contract, self.get_object())
        return Response(self.get_serializer(c).data)

    @extend_schema(
        request={"application/json": {"type": "object", "properties": {
            "start_date": {"type": "string"}, "end_date": {"type": "string"}}}},
        responses=PurchaseContractSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def renew(self, request, pk=None):
        c = _transition(
            services.renew_contract, self.get_object(),
            start_date=request.data.get("start_date"),
            end_date=request.data.get("end_date"), user=request.user)
        return Response(self.get_serializer(c).data)


class PurchaseReturnViewSet(viewsets.ModelViewSet):
    queryset = (
        PurchaseReturn.objects.select_related("purchase_order", "vendor", "created_by")
        .prefetch_related("lines__po_line__material").all()
    )
    serializer_class = PurchaseReturnSerializer
    permission_classes = [IsProcurementManagerOrReadOnly]
    filterset_fields = ["status", "vendor", "purchase_order", "resolution"]
    search_fields = ["number", "reason", "credit_note_number"]
    ordering_fields = ["created_at", "return_date", "number"]

    @extend_schema(request=None, responses=PurchaseReturnSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        ret = _transition(services.confirm_return, self.get_object())
        return Response(self.get_serializer(ret).data)

    @extend_schema(request=None, responses=PurchaseReturnSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        ret = _transition(services.cancel_return, self.get_object())
        return Response(self.get_serializer(ret).data)
