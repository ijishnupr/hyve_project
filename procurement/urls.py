from rest_framework.routers import DefaultRouter

from .views import (
    GoodsReceiptNoteViewSet,
    MaterialCategoryViewSet,
    MaterialViewSet,
    ProjectViewSet,
    PurchaseOrderViewSet,
    PurchaseRequisitionViewSet,
    VendorBillViewSet,
    VendorViewSet,
)

router = DefaultRouter()
router.register("projects", ProjectViewSet)
router.register("vendors", VendorViewSet)
router.register("material-categories", MaterialCategoryViewSet)
router.register("materials", MaterialViewSet)
router.register("requisitions", PurchaseRequisitionViewSet)
router.register("purchase-orders", PurchaseOrderViewSet)
router.register("grns", GoodsReceiptNoteViewSet)
router.register("bills", VendorBillViewSet)

urlpatterns = router.urls
