from django.contrib import admin

from .models import (
    DocumentCounter,
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


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "budget", "manager")
    list_filter = ("status",)
    search_fields = ("code", "name", "location")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "gstin", "phone", "rating", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "gstin")


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent")
    search_fields = ("name",)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "unit", "default_tax_rate", "is_active")
    list_filter = ("unit", "is_active", "category")
    search_fields = ("code", "name", "hsn_code")


class PurchaseRequisitionLineInline(admin.TabularInline):
    model = PurchaseRequisitionLine
    extra = 0


@admin.register(PurchaseRequisition)
class PurchaseRequisitionAdmin(admin.ModelAdmin):
    list_display = ("number", "project", "status", "required_by", "requested_by")
    list_filter = ("status",)
    search_fields = ("number",)
    inlines = [PurchaseRequisitionLineInline]
    readonly_fields = ("number",)


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "vendor", "project", "status", "total", "order_date")
    list_filter = ("status",)
    search_fields = ("number",)
    inlines = [PurchaseOrderLineInline]
    readonly_fields = ("number", "subtotal", "tax_amount", "total")


class GRNLineInline(admin.TabularInline):
    model = GRNLine
    extra = 0


@admin.register(GoodsReceiptNote)
class GoodsReceiptNoteAdmin(admin.ModelAdmin):
    list_display = ("number", "purchase_order", "status", "received_date", "received_by")
    list_filter = ("status",)
    search_fields = ("number", "challan_number")
    inlines = [GRNLineInline]
    readonly_fields = ("number",)


class VendorBillLineInline(admin.TabularInline):
    model = VendorBillLine
    extra = 0


@admin.register(VendorBill)
class VendorBillAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "vendor_invoice_number",
        "vendor",
        "purchase_order",
        "status",
        "match_status",
        "total",
    )
    list_filter = ("status", "match_status")
    search_fields = ("number", "vendor_invoice_number")
    inlines = [VendorBillLineInline]
    readonly_fields = ("number", "subtotal", "tax_amount", "total", "match_status", "match_notes")


@admin.register(DocumentCounter)
class DocumentCounterAdmin(admin.ModelAdmin):
    list_display = ("prefix", "year", "last_value")
