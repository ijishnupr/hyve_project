"""django-filter FilterSets for list endpoints."""
import django_filters as filters

from .models import (
    GoodsReceiptNote,
    Material,
    PurchaseOrder,
    PurchaseRequisition,
    RequestForQuotation,
    SupplierQuotation,
    Vendor,
    VendorBill,
)


class VendorFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = Vendor
        fields = ["is_active", "name"]


class MaterialFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = Material
        fields = ["category", "unit", "is_active", "name"]


class PurchaseRequisitionFilter(filters.FilterSet):
    created_after = filters.DateFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.DateFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = PurchaseRequisition
        fields = ["status", "project", "requested_by"]


class RFQFilter(filters.FilterSet):
    class Meta:
        model = RequestForQuotation
        fields = ["status", "project", "vendors"]


class SupplierQuotationFilter(filters.FilterSet):
    class Meta:
        model = SupplierQuotation
        fields = ["status", "rfq", "vendor"]


class PurchaseOrderFilter(filters.FilterSet):
    order_after = filters.DateFilter(field_name="order_date", lookup_expr="gte")
    order_before = filters.DateFilter(field_name="order_date", lookup_expr="lte")

    class Meta:
        model = PurchaseOrder
        fields = ["status", "vendor", "project"]


class GRNFilter(filters.FilterSet):
    class Meta:
        model = GoodsReceiptNote
        fields = ["status", "purchase_order"]


class VendorBillFilter(filters.FilterSet):
    class Meta:
        model = VendorBill
        fields = ["status", "match_status", "vendor", "purchase_order"]
