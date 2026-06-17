from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    # Auth
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.dashboard, name="dashboard"),

    # Master data
    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_new, name="project_new"),
    path("projects/<int:pk>/edit/", views.project_edit, name="project_edit"),

    path("vendors/", views.vendor_list, name="vendor_list"),
    path("vendors/new/", views.vendor_new, name="vendor_new"),
    path("vendors/<int:pk>/edit/", views.vendor_edit, name="vendor_edit"),

    path("categories/", views.category_list, name="category_list"),
    path("categories/new/", views.category_new, name="category_new"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),

    path("materials/", views.material_list, name="material_list"),
    path("materials/new/", views.material_new, name="material_new"),
    path("materials/<int:pk>/edit/", views.material_edit, name="material_edit"),

    # Purchase Requisitions
    path("requisitions/", views.pr_list, name="pr_list"),
    path("requisitions/new/", views.pr_new, name="pr_new"),
    path("requisitions/<int:pk>/", views.pr_detail, name="pr_detail"),
    path("requisitions/<int:pk>/edit/", views.pr_edit, name="pr_edit"),
    path("requisitions/<int:pk>/submit/", views.pr_submit, name="pr_submit"),
    path("requisitions/<int:pk>/approve/", views.pr_approve, name="pr_approve"),
    path("requisitions/<int:pk>/reject/", views.pr_reject, name="pr_reject"),

    # Purchase Orders
    path("purchase-orders/", views.po_list, name="po_list"),
    path("purchase-orders/new/", views.po_new, name="po_new"),
    path("purchase-orders/<int:pk>/", views.po_detail, name="po_detail"),
    path("purchase-orders/<int:pk>/edit/", views.po_edit, name="po_edit"),
    path("purchase-orders/<int:pk>/issue/", views.po_issue, name="po_issue"),
    path("purchase-orders/<int:pk>/cancel/", views.po_cancel, name="po_cancel"),
    path("purchase-orders/<int:pk>/close/", views.po_close, name="po_close"),

    # Goods Receipt Notes
    path("grns/", views.grn_list, name="grn_list"),
    path("grns/new/<int:po_pk>/", views.grn_new, name="grn_new"),
    path("grns/<int:pk>/", views.grn_detail, name="grn_detail"),
    path("grns/<int:pk>/confirm/", views.grn_confirm, name="grn_confirm"),
    path("grns/<int:pk>/cancel/", views.grn_cancel, name="grn_cancel"),

    # Vendor Bills
    path("bills/", views.bill_list, name="bill_list"),
    path("bills/new/<int:po_pk>/", views.bill_new, name="bill_new"),
    path("bills/<int:pk>/", views.bill_detail, name="bill_detail"),
    path("bills/<int:pk>/match/", views.bill_match, name="bill_match"),
    path("bills/<int:pk>/approve/", views.bill_approve, name="bill_approve"),
    path("bills/<int:pk>/mark-paid/", views.bill_mark_paid, name="bill_mark_paid"),
]
