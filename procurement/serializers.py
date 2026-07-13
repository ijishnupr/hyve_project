"""DRF serializers for the procurement API."""
from django.db import transaction
from rest_framework import serializers

from .models import (
    ApprovalRequest,
    ApprovalRule,
    ApprovalStep,
    Attachment,
    AuditLog,
    ContractLine,
    GoodsReceiptNote,
    GRNLine,
    Material,
    MaterialCategory,
    Notification,
    Payment,
    PaymentSchedule,
    Project,
    PurchaseContract,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderRevision,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    PurchaseReturn,
    PurchaseReturnLine,
    QCChecklistItem,
    QualityInspection,
    RequestForQuotation,
    RFQLine,
    StockItem,
    StockLedgerEntry,
    SupplierAddress,
    SupplierBankAccount,
    SupplierContact,
    SupplierDocument,
    SupplierQuotation,
    SupplierQuotationLine,
    Vendor,
    VendorBill,
    VendorBillLine,
)


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------
class ApprovalRuleSerializer(serializers.ModelSerializer):
    document_type_display = serializers.CharField(
        source="get_document_type_display", read_only=True)

    class Meta:
        model = ApprovalRule
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class ApprovalStepSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    acted_by_name = serializers.CharField(source="acted_by.get_username", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = ApprovalStep
        fields = ["id", "request", "level", "role_required", "status", "status_display",
                  "acted_by", "acted_by_name", "acted_at", "comments", "due_at",
                  "is_overdue", "created_at", "updated_at"]
        read_only_fields = fields


class ApprovalRequestSerializer(serializers.ModelSerializer):
    steps = ApprovalStepSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    document_type_display = serializers.CharField(
        source="get_document_type_display", read_only=True)
    document_label = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRequest
        fields = ["id", "content_type", "object_id", "document_label", "document_type",
                  "document_type_display", "amount", "status", "status_display",
                  "current_level", "steps", "created_at", "updated_at"]
        read_only_fields = fields

    def get_document_label(self, obj):
        return str(obj.document) if obj.document else None


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.get_username", read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "content_type", "object_id", "document_label", "action",
                  "from_status", "to_status", "note", "actor", "actor_name", "created_at"]
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "kind", "kind_display", "message", "url", "is_read",
                  "recipient", "recipient_role", "created_at"]
        read_only_fields = fields


class AttachmentSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ["id", "content_type", "object_id", "title", "kind", "kind_display",
                  "file", "file_url", "uploaded_by", "created_at", "updated_at"]
        read_only_fields = ["uploaded_by", "created_at", "updated_at"]

    def get_file_url(self, obj):
        return obj.file.url if obj.file else None


class StockItemSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.name", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    unit = serializers.CharField(source="material.get_unit_display", read_only=True)

    class Meta:
        model = StockItem
        fields = ["id", "material", "material_name", "unit", "project", "project_name",
                  "quantity_on_hand", "updated_at"]
        read_only_fields = fields


class StockLedgerEntrySerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.name", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    movement_display = serializers.CharField(source="get_movement_display", read_only=True)

    class Meta:
        model = StockLedgerEntry
        fields = ["id", "material", "material_name", "project", "project_name", "movement",
                  "movement_display", "quantity", "balance_after", "remarks", "created_at"]
        read_only_fields = fields


class PurchaseOrderRevisionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.get_username", read_only=True)

    class Meta:
        model = PurchaseOrderRevision
        fields = ["id", "revision", "subtotal", "tax_amount", "total", "note",
                  "created_by", "created_by_name", "created_at"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------
class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class SupplierContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierContact
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class SupplierAddressSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = SupplierAddress
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class SupplierBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierBankAccount
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class SupplierDocumentSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = SupplierDocument
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class VendorSerializer(serializers.ModelSerializer):
    contacts = SupplierContactSerializer(many=True, read_only=True)
    addresses = SupplierAddressSerializer(many=True, read_only=True)
    bank_accounts = SupplierBankAccountSerializer(many=True, read_only=True)
    documents = SupplierDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Vendor
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class MaterialCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialCategory
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class MaterialSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    unit_display = serializers.CharField(source="get_unit_display", read_only=True)

    class Meta:
        model = Material
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _LineMixin:
    """Shared validation: replace lines wholesale on update."""

    line_field = "lines"

    def _create_lines(self, parent, lines_data, model, fk_name):
        objs = [model(**{fk_name: parent}, **line) for line in lines_data]
        model.objects.bulk_create(objs)


# ---------------------------------------------------------------------------
# Purchase Requisition
# ---------------------------------------------------------------------------
class PurchaseRequisitionLineSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.name", read_only=True)

    class Meta:
        model = PurchaseRequisitionLine
        fields = ["id", "material", "material_name", "quantity", "remarks"]


class PurchaseRequisitionSerializer(serializers.ModelSerializer):
    lines = PurchaseRequisitionLineSerializer(many=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = PurchaseRequisition
        fields = [
            "id",
            "number",
            "project",
            "project_name",
            "status",
            "status_display",
            "required_by",
            "notes",
            "requested_by",
            "approved_by",
            "approved_at",
            "rejection_reason",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "number",
            "status",
            "requested_by",
            "approved_by",
            "approved_at",
            "rejection_reason",
            "created_at",
            "updated_at",
        ]

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("At least one line item is required.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        pr = PurchaseRequisition.objects.create(
            requested_by=self.context["request"].user, **validated_data
        )
        PurchaseRequisitionLine.objects.bulk_create(
            [PurchaseRequisitionLine(requisition=pr, **line) for line in lines]
        )
        return pr

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            PurchaseRequisitionLine.objects.bulk_create(
                [PurchaseRequisitionLine(requisition=instance, **line) for line in lines]
            )
        return instance


# ---------------------------------------------------------------------------
# Request for Quotation
# ---------------------------------------------------------------------------
class RFQLineSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.name", read_only=True)

    class Meta:
        model = RFQLine
        fields = ["id", "material", "material_name", "quantity", "remarks"]


class RequestForQuotationSerializer(serializers.ModelSerializer):
    lines = RFQLineSerializer(many=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = RequestForQuotation
        fields = [
            "id", "number", "project", "project_name", "requisition", "status",
            "status_display", "vendors", "issue_date", "response_deadline",
            "terms", "notes", "sent_at", "is_expired", "created_by", "lines",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "number", "status", "sent_at", "created_by", "created_at", "updated_at",
        ]

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("At least one line item is required.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        vendors = validated_data.pop("vendors", [])
        rfq = RequestForQuotation.objects.create(
            created_by=self.context["request"].user, **validated_data
        )
        if vendors:
            rfq.vendors.set(vendors)
        RFQLine.objects.bulk_create([RFQLine(rfq=rfq, **line) for line in lines])
        return rfq

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != RequestForQuotation.Status.DRAFT:
            raise serializers.ValidationError("Only draft RFQs can be edited.")
        lines = validated_data.pop("lines", None)
        vendors = validated_data.pop("vendors", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if vendors is not None:
            instance.vendors.set(vendors)
        if lines is not None:
            instance.lines.all().delete()
            RFQLine.objects.bulk_create([RFQLine(rfq=instance, **line) for line in lines])
        return instance


class SupplierQuotationLineSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.name", read_only=True)
    line_subtotal = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    line_tax = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = SupplierQuotationLine
        fields = ["id", "material", "material_name", "quantity", "unit_price",
                  "tax_rate", "line_subtotal", "line_tax", "line_total"]


class SupplierQuotationSerializer(serializers.ModelSerializer):
    lines = SupplierQuotationLineSerializer(many=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    rfq_number = serializers.CharField(source="rfq.number", read_only=True)

    class Meta:
        model = SupplierQuotation
        fields = [
            "id", "number", "rfq", "rfq_number", "vendor", "vendor_name", "status",
            "status_display", "quotation_date", "valid_until", "delivery_days",
            "warranty_months", "payment_terms_days", "notes", "subtotal",
            "tax_amount", "total", "purchase_order", "created_by", "lines",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "number", "status", "subtotal", "tax_amount", "total",
            "purchase_order", "created_by", "created_at", "updated_at",
        ]

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("At least one line item is required.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        quotation = SupplierQuotation.objects.create(
            created_by=self.context["request"].user, **validated_data
        )
        SupplierQuotationLine.objects.bulk_create(
            [SupplierQuotationLine(quotation=quotation, **line) for line in lines]
        )
        quotation.recalculate_totals()
        return quotation

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != SupplierQuotation.Status.RECEIVED:
            raise serializers.ValidationError("Only received quotations can be edited.")
        lines = validated_data.pop("lines", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            SupplierQuotationLine.objects.bulk_create(
                [SupplierQuotationLine(quotation=instance, **line) for line in lines]
            )
        instance.recalculate_totals()
        return instance


# ---------------------------------------------------------------------------
# Purchase Order
# ---------------------------------------------------------------------------
class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.name", read_only=True)
    line_subtotal = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    line_tax = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    pending_quantity = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = [
            "id",
            "material",
            "material_name",
            "quantity",
            "unit_price",
            "tax_rate",
            "received_quantity",
            "line_subtotal",
            "line_tax",
            "line_total",
            "pending_quantity",
        ]
        read_only_fields = ["received_quantity"]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True)
    revisions = PurchaseOrderRevisionSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "number",
            "vendor",
            "vendor_name",
            "project",
            "project_name",
            "requisition",
            "contract",
            "status",
            "status_display",
            "order_date",
            "expected_delivery_date",
            "delivery_address",
            "payment_terms_days",
            "terms_and_conditions",
            "subtotal",
            "tax_amount",
            "total",
            "revision",
            "emailed_at",
            "created_by",
            "approved_by",
            "approved_at",
            "lines",
            "revisions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "number",
            "status",
            "subtotal",
            "tax_amount",
            "total",
            "revision",
            "emailed_at",
            "created_by",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("At least one line item is required.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        po = PurchaseOrder.objects.create(
            created_by=self.context["request"].user, **validated_data
        )
        PurchaseOrderLine.objects.bulk_create(
            [PurchaseOrderLine(purchase_order=po, **line) for line in lines]
        )
        po.recalculate_totals()
        return po

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != PurchaseOrder.Status.DRAFT:
            raise serializers.ValidationError(
                "Only draft purchase orders can be edited."
            )
        lines = validated_data.pop("lines", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            PurchaseOrderLine.objects.bulk_create(
                [PurchaseOrderLine(purchase_order=instance, **line) for line in lines]
            )
        instance.recalculate_totals()
        return instance


# ---------------------------------------------------------------------------
# Goods Receipt Note
# ---------------------------------------------------------------------------
class GRNLineSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(
        source="po_line.material.name", read_only=True
    )

    class Meta:
        model = GRNLine
        fields = [
            "id",
            "po_line",
            "material_name",
            "received_quantity",
            "accepted_quantity",
            "rejected_quantity",
            "remarks",
        ]


class GoodsReceiptNoteSerializer(serializers.ModelSerializer):
    lines = GRNLineSerializer(many=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    po_number = serializers.CharField(source="purchase_order.number", read_only=True)

    class Meta:
        model = GoodsReceiptNote
        fields = [
            "id",
            "number",
            "purchase_order",
            "po_number",
            "status",
            "status_display",
            "received_date",
            "challan_number",
            "vehicle_number",
            "notes",
            "received_by",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "number",
            "status",
            "received_by",
            "created_at",
            "updated_at",
        ]

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("At least one line item is required.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        grn = GoodsReceiptNote.objects.create(
            received_by=self.context["request"].user, **validated_data
        )
        GRNLine.objects.bulk_create([GRNLine(grn=grn, **line) for line in lines])
        return grn

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != GoodsReceiptNote.Status.DRAFT:
            raise serializers.ValidationError("Only draft GRNs can be edited.")
        lines = validated_data.pop("lines", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            GRNLine.objects.bulk_create(
                [GRNLine(grn=instance, **line) for line in lines]
            )
        return instance


# ---------------------------------------------------------------------------
# Quality Inspection
# ---------------------------------------------------------------------------
class QCChecklistItemSerializer(serializers.ModelSerializer):
    result_display = serializers.CharField(source="get_result_display", read_only=True)

    class Meta:
        model = QCChecklistItem
        fields = ["id", "description", "result", "result_display", "remarks"]


class QualityInspectionSerializer(serializers.ModelSerializer):
    items = QCChecklistItemSerializer(many=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    grn_number = serializers.CharField(source="grn.number", read_only=True)

    class Meta:
        model = QualityInspection
        fields = ["id", "number", "grn", "grn_number", "status", "status_display",
                  "inspected_by", "inspected_at", "remarks", "items",
                  "created_at", "updated_at"]
        read_only_fields = ["number", "status", "inspected_by", "inspected_at",
                            "created_at", "updated_at"]

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop("items", [])
        inspection = QualityInspection.objects.create(**validated_data)
        QCChecklistItem.objects.bulk_create(
            [QCChecklistItem(inspection=inspection, **it) for it in items])
        return inspection

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != QualityInspection.Status.PENDING:
            raise serializers.ValidationError("Completed inspections cannot be edited.")
        items = validated_data.pop("items", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if items is not None:
            instance.items.all().delete()
            QCChecklistItem.objects.bulk_create(
                [QCChecklistItem(inspection=instance, **it) for it in items])
        return instance


# ---------------------------------------------------------------------------
# Vendor Bill
# ---------------------------------------------------------------------------
class VendorBillLineSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(
        source="po_line.material.name", read_only=True
    )
    line_subtotal = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    line_tax = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = VendorBillLine
        fields = [
            "id",
            "po_line",
            "material_name",
            "quantity",
            "unit_price",
            "tax_rate",
            "line_subtotal",
            "line_tax",
            "line_total",
        ]


class PaymentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    type_display = serializers.CharField(source="get_payment_type_display", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    bill_number = serializers.CharField(source="bill.number", read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "number", "vendor", "vendor_name", "bill", "bill_number",
                  "purchase_order", "payment_type", "type_display", "method",
                  "method_display", "status", "status_display", "amount",
                  "payment_date", "reference", "notes", "created_by",
                  "created_at", "updated_at"]
        read_only_fields = ["number", "status", "created_by", "created_at", "updated_at"]

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class PurchaseReturnLineSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="po_line.material.name", read_only=True)

    class Meta:
        model = PurchaseReturnLine
        fields = ["id", "po_line", "material_name", "quantity", "remarks"]


class PurchaseReturnSerializer(serializers.ModelSerializer):
    lines = PurchaseReturnLineSerializer(many=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    resolution_display = serializers.CharField(source="get_resolution_display", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    po_number = serializers.CharField(source="purchase_order.number", read_only=True)

    class Meta:
        model = PurchaseReturn
        fields = ["id", "number", "purchase_order", "po_number", "grn", "vendor",
                  "vendor_name", "status", "status_display", "resolution",
                  "resolution_display", "return_date", "reason", "credit_note_number",
                  "created_by", "lines", "created_at", "updated_at"]
        read_only_fields = ["number", "status", "created_by", "created_at", "updated_at"]

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("At least one line item is required.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        ret = PurchaseReturn.objects.create(
            created_by=self.context["request"].user, **validated_data)
        PurchaseReturnLine.objects.bulk_create(
            [PurchaseReturnLine(purchase_return=ret, **line) for line in lines])
        return ret

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != PurchaseReturn.Status.DRAFT:
            raise serializers.ValidationError("Only draft returns can be edited.")
        lines = validated_data.pop("lines", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            PurchaseReturnLine.objects.bulk_create(
                [PurchaseReturnLine(purchase_return=instance, **line) for line in lines])
        return instance


class ContractLineSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.name", read_only=True)

    class Meta:
        model = ContractLine
        fields = ["id", "material", "material_name", "unit_price", "tax_rate", "max_quantity"]


class PurchaseContractSerializer(serializers.ModelSerializer):
    lines = ContractLineSerializer(many=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    type_display = serializers.CharField(source="get_contract_type_display", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    remaining_value = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseContract
        fields = ["id", "number", "title", "vendor", "vendor_name", "contract_type",
                  "type_display", "status", "status_display", "start_date", "end_date",
                  "total_value", "consumed_value", "remaining_value", "auto_renew",
                  "renewed_from", "is_expired", "terms", "created_by", "lines",
                  "created_at", "updated_at"]
        read_only_fields = ["number", "status", "consumed_value", "renewed_from",
                            "created_by", "created_at", "updated_at"]

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        contract = PurchaseContract.objects.create(
            created_by=self.context["request"].user, **validated_data)
        ContractLine.objects.bulk_create(
            [ContractLine(contract=contract, **line) for line in lines])
        return contract

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            ContractLine.objects.bulk_create(
                [ContractLine(contract=instance, **line) for line in lines])
        return instance


class PaymentScheduleSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)

    class Meta:
        model = PaymentSchedule
        fields = ["id", "vendor", "vendor_name", "bill", "purchase_order", "due_date",
                  "amount", "status", "status_display", "is_overdue", "note",
                  "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class VendorBillSerializer(serializers.ModelSerializer):
    lines = VendorBillLineSerializer(many=True)
    payments = PaymentSerializer(many=True, read_only=True)
    amount_paid = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    outstanding = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    match_status_display = serializers.CharField(
        source="get_match_status_display", read_only=True
    )
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    po_number = serializers.CharField(source="purchase_order.number", read_only=True)

    class Meta:
        model = VendorBill
        fields = [
            "id",
            "number",
            "vendor_invoice_number",
            "vendor",
            "vendor_name",
            "purchase_order",
            "po_number",
            "status",
            "status_display",
            "match_status",
            "match_status_display",
            "match_notes",
            "bill_date",
            "due_date",
            "subtotal",
            "tax_amount",
            "total",
            "amount_paid",
            "outstanding",
            "created_by",
            "lines",
            "payments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "number",
            "status",
            "match_status",
            "match_notes",
            "subtotal",
            "tax_amount",
            "total",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("At least one line item is required.")
        return value

    def validate(self, attrs):
        # On create, ensure every billed PO line belongs to the bill's PO.
        po = attrs.get("purchase_order") or getattr(self.instance, "purchase_order", None)
        lines = attrs.get("lines")
        if po and lines:
            for line in lines:
                if line["po_line"].purchase_order_id != po.id:
                    raise serializers.ValidationError(
                        "All bill lines must reference lines from the selected PO."
                    )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        bill = VendorBill.objects.create(
            created_by=self.context["request"].user, **validated_data
        )
        VendorBillLine.objects.bulk_create(
            [VendorBillLine(bill=bill, **line) for line in lines]
        )
        bill.recalculate_totals()
        return bill

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status not in {
            VendorBill.Status.DRAFT,
            VendorBill.Status.DISPUTED,
        }:
            raise serializers.ValidationError(
                "Only draft or disputed bills can be edited."
            )
        lines = validated_data.pop("lines", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            VendorBillLine.objects.bulk_create(
                [VendorBillLine(bill=instance, **line) for line in lines]
            )
        instance.recalculate_totals()
        return instance
