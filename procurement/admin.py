from django.contrib import admin

from .models import (
    ApprovalRequest,
    ApprovalRule,
    ApprovalStep,
    Attachment,
    ContractLine,
    DocumentCounter,
    GoodsReceiptNote,
    PurchaseContract,
    GRNLine,
    Material,
    MaterialCategory,
    Project,
    PurchaseOrder,
    PurchaseOrderLine,
    Payment,
    PaymentSchedule,
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
    SupplierQuotation,
    SupplierQuotationLine,
    SupplierBankAccount,
    SupplierContact,
    SupplierDocument,
    Vendor,
    VendorBill,
    VendorBillLine,
)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "budget", "manager")
    list_filter = ("status",)
    search_fields = ("code", "name", "location")


class SupplierContactInline(admin.TabularInline):
    model = SupplierContact
    extra = 0


class SupplierAddressInline(admin.TabularInline):
    model = SupplierAddress
    extra = 0


class SupplierBankAccountInline(admin.TabularInline):
    model = SupplierBankAccount
    extra = 0


class SupplierDocumentInline(admin.TabularInline):
    model = SupplierDocument
    extra = 0


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "gstin", "phone", "rating", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "gstin")
    inlines = [
        SupplierContactInline,
        SupplierAddressInline,
        SupplierBankAccountInline,
        SupplierDocumentInline,
    ]


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


class RFQLineInline(admin.TabularInline):
    model = RFQLine
    extra = 0


@admin.register(RequestForQuotation)
class RequestForQuotationAdmin(admin.ModelAdmin):
    list_display = ("number", "project", "status", "issue_date", "response_deadline")
    list_filter = ("status",)
    search_fields = ("number",)
    inlines = [RFQLineInline]
    filter_horizontal = ("vendors",)
    readonly_fields = ("number", "sent_at")


class SupplierQuotationLineInline(admin.TabularInline):
    model = SupplierQuotationLine
    extra = 0


@admin.register(SupplierQuotation)
class SupplierQuotationAdmin(admin.ModelAdmin):
    list_display = ("number", "rfq", "vendor", "status", "total", "delivery_days")
    list_filter = ("status",)
    search_fields = ("number",)
    inlines = [SupplierQuotationLineInline]
    readonly_fields = ("number", "subtotal", "tax_amount", "total")


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


@admin.register(ApprovalRule)
class ApprovalRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "document_type", "level", "role_required",
                    "min_amount", "max_amount", "is_active")
    list_filter = ("document_type", "is_active", "level")
    search_fields = ("name", "role_required")


class ApprovalStepInline(admin.TabularInline):
    model = ApprovalStep
    extra = 0
    readonly_fields = ("level", "role_required", "acted_by", "acted_at")


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "document_type", "amount", "status", "current_level", "created_at")
    list_filter = ("document_type", "status")
    inlines = [ApprovalStepInline]


class QCChecklistItemInline(admin.TabularInline):
    model = QCChecklistItem
    extra = 0


@admin.register(QualityInspection)
class QualityInspectionAdmin(admin.ModelAdmin):
    list_display = ("number", "grn", "status", "inspected_by", "inspected_at")
    list_filter = ("status",)
    search_fields = ("number",)
    inlines = [QCChecklistItemInline]
    readonly_fields = ("number",)


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("material", "project", "quantity_on_hand")
    search_fields = ("material__name", "project__name")


@admin.register(StockLedgerEntry)
class StockLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "material", "project", "movement", "quantity", "balance_after")
    list_filter = ("movement",)
    search_fields = ("material__name", "remarks")


class PurchaseReturnLineInline(admin.TabularInline):
    model = PurchaseReturnLine
    extra = 0


@admin.register(PurchaseReturn)
class PurchaseReturnAdmin(admin.ModelAdmin):
    list_display = ("number", "purchase_order", "vendor", "resolution", "status", "return_date")
    list_filter = ("status", "resolution")
    search_fields = ("number",)
    inlines = [PurchaseReturnLineInline]
    readonly_fields = ("number",)


class ContractLineInline(admin.TabularInline):
    model = ContractLine
    extra = 0


@admin.register(PurchaseContract)
class PurchaseContractAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "vendor", "contract_type", "status",
                    "start_date", "end_date", "total_value", "consumed_value")
    list_filter = ("status", "contract_type")
    search_fields = ("number", "title")
    inlines = [ContractLineInline]
    readonly_fields = ("number", "consumed_value")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("number", "vendor", "bill", "payment_type", "method", "amount", "status", "payment_date")
    list_filter = ("status", "payment_type", "method")
    search_fields = ("number", "reference")
    readonly_fields = ("number",)


@admin.register(PaymentSchedule)
class PaymentScheduleAdmin(admin.ModelAdmin):
    list_display = ("vendor", "bill", "due_date", "amount", "status")
    list_filter = ("status",)


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "content_type", "object_id", "uploaded_by", "created_at")
    list_filter = ("kind",)
    search_fields = ("title",)


@admin.register(DocumentCounter)
class DocumentCounterAdmin(admin.ModelAdmin):
    list_display = ("prefix", "year", "last_value")
