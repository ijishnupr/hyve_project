"""DRF serializers for the procurement API."""
from django.db import transaction
from rest_framework import serializers

from .models import (
    GoodsReceiptNote,
    GRNLine,
    Material,
    MaterialCategory,
    Project,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    Vendor,
    VendorBill,
    VendorBillLine,
)


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------
class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class VendorSerializer(serializers.ModelSerializer):
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
            "created_by",
            "approved_by",
            "approved_at",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "number",
            "status",
            "subtotal",
            "tax_amount",
            "total",
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


class VendorBillSerializer(serializers.ModelSerializer):
    lines = VendorBillLineSerializer(many=True)
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
            "created_by",
            "lines",
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
