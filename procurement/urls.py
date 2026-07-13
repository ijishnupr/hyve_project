from rest_framework.routers import DefaultRouter

from .views import (
    ApprovalRequestViewSet,
    ApprovalRuleViewSet,
    ApprovalStepViewSet,
    AttachmentViewSet,
    PaymentScheduleViewSet,
    PaymentViewSet,
    PurchaseContractViewSet,
    PurchaseReturnViewSet,
    QualityInspectionViewSet,
    StockItemViewSet,
    StockLedgerEntryViewSet,
    GoodsReceiptNoteViewSet,
    MaterialCategoryViewSet,
    MaterialViewSet,
    ProjectViewSet,
    PurchaseOrderViewSet,
    PurchaseRequisitionViewSet,
    RequestForQuotationViewSet,
    SupplierAddressViewSet,
    SupplierBankAccountViewSet,
    SupplierContactViewSet,
    SupplierDocumentViewSet,
    SupplierQuotationViewSet,
    VendorBillViewSet,
    VendorViewSet,
)

router = DefaultRouter()
router.register("approval-rules", ApprovalRuleViewSet)
router.register("approval-requests", ApprovalRequestViewSet)
router.register("approval-steps", ApprovalStepViewSet)
router.register("attachments", AttachmentViewSet)
router.register("stock-items", StockItemViewSet)
router.register("stock-ledger", StockLedgerEntryViewSet)
router.register("projects", ProjectViewSet)
router.register("vendors", VendorViewSet)
router.register("supplier-contacts", SupplierContactViewSet)
router.register("supplier-addresses", SupplierAddressViewSet)
router.register("supplier-bank-accounts", SupplierBankAccountViewSet)
router.register("supplier-documents", SupplierDocumentViewSet)
router.register("material-categories", MaterialCategoryViewSet)
router.register("materials", MaterialViewSet)
router.register("requisitions", PurchaseRequisitionViewSet)
router.register("rfqs", RequestForQuotationViewSet)
router.register("quotations", SupplierQuotationViewSet)
router.register("purchase-orders", PurchaseOrderViewSet)
router.register("grns", GoodsReceiptNoteViewSet)
router.register("quality-inspections", QualityInspectionViewSet)
router.register("bills", VendorBillViewSet)
router.register("payments", PaymentViewSet)
router.register("payment-schedules", PaymentScheduleViewSet)
router.register("purchase-returns", PurchaseReturnViewSet)
router.register("purchase-contracts", PurchaseContractViewSet)

urlpatterns = router.urls
