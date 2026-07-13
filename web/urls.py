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
    path("vendors/<int:pk>/", views.vendor_detail, name="vendor_detail"),
    path("vendors/<int:pk>/edit/", views.vendor_edit, name="vendor_edit"),
    path("vendors/<int:pk>/<str:kind>/add/", views.vendor_child_add, name="vendor_child_add"),
    path("vendors/<int:pk>/<str:kind>/<int:child_pk>/delete/",
         views.vendor_child_delete, name="vendor_child_delete"),

    path("categories/", views.category_list, name="category_list"),
    path("categories/new/", views.category_new, name="category_new"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),

    path("materials/", views.material_list, name="material_list"),
    path("materials/new/", views.material_new, name="material_new"),
    path("materials/<int:pk>/edit/", views.material_edit, name="material_edit"),

    # Generic attachments
    path("attachments/<str:model>/<int:object_id>/add/", views.attachment_add, name="attachment_add"),
    path("attachments/<int:pk>/delete/", views.attachment_delete, name="attachment_delete"),

    # Approval workflow
    path("approvals/", views.approval_inbox, name="approval_inbox"),
    path("approvals/rules/", views.approval_rule_list, name="approval_rule_list"),
    path("approvals/rules/new/", views.approval_rule_new, name="approval_rule_new"),
    path("approvals/rules/<int:pk>/edit/", views.approval_rule_edit, name="approval_rule_edit"),
    path("approvals/steps/<int:pk>/approve/", views.approval_step_approve, name="approval_step_approve"),
    path("approvals/steps/<int:pk>/reject/", views.approval_step_reject, name="approval_step_reject"),

    # Purchase Requisitions
    path("requisitions/", views.pr_list, name="pr_list"),
    path("requisitions/new/", views.pr_new, name="pr_new"),
    path("requisitions/<int:pk>/", views.pr_detail, name="pr_detail"),
    path("requisitions/<int:pk>/edit/", views.pr_edit, name="pr_edit"),
    path("requisitions/<int:pk>/submit/", views.pr_submit, name="pr_submit"),
    path("requisitions/<int:pk>/approve/", views.pr_approve, name="pr_approve"),
    path("requisitions/<int:pk>/reject/", views.pr_reject, name="pr_reject"),
    path("requisitions/<int:pk>/to-rfq/", views.pr_to_rfq, name="pr_to_rfq"),

    # Requests for Quotation
    path("rfqs/", views.rfq_list, name="rfq_list"),
    path("rfqs/new/", views.rfq_new, name="rfq_new"),
    path("rfqs/<int:pk>/", views.rfq_detail, name="rfq_detail"),
    path("rfqs/<int:pk>/edit/", views.rfq_edit, name="rfq_edit"),
    path("rfqs/<int:pk>/send/", views.rfq_send, name="rfq_send"),
    path("rfqs/<int:pk>/close/", views.rfq_close, name="rfq_close"),
    path("rfqs/<int:pk>/cancel/", views.rfq_cancel, name="rfq_cancel"),

    # Supplier Quotations & comparison
    path("rfqs/<int:rfq_pk>/quotations/new/", views.quotation_new, name="quotation_new"),
    path("rfqs/<int:rfq_pk>/quotations/compare/", views.quotation_compare, name="quotation_compare"),
    path("quotations/<int:pk>/select/", views.quotation_select, name="quotation_select"),
    path("quotations/<int:pk>/reject/", views.quotation_reject, name="quotation_reject"),

    # Purchase Orders
    path("purchase-orders/", views.po_list, name="po_list"),
    path("purchase-orders/new/", views.po_new, name="po_new"),
    path("purchase-orders/<int:pk>/", views.po_detail, name="po_detail"),
    path("purchase-orders/<int:pk>/edit/", views.po_edit, name="po_edit"),
    path("purchase-orders/<int:pk>/submit-approval/", views.po_submit_approval, name="po_submit_approval"),
    path("purchase-orders/<int:pk>/reopen/", views.po_reopen, name="po_reopen"),
    path("purchase-orders/<int:pk>/email/", views.po_email, name="po_email"),
    path("purchase-orders/<int:pk>/pdf/", views.po_pdf, name="po_pdf"),
    path("requisitions/<int:pk>/pdf/", views.pr_pdf, name="pr_pdf"),
    path("purchase-orders/<int:pk>/issue/", views.po_issue, name="po_issue"),
    path("purchase-orders/<int:pk>/cancel/", views.po_cancel, name="po_cancel"),
    path("purchase-orders/<int:pk>/close/", views.po_close, name="po_close"),

    # Inventory
    path("stock/", views.stock_list, name="stock_list"),
    path("stock/ledger/", views.stock_ledger, name="stock_ledger"),

    # Goods Receipt Notes
    path("grns/", views.grn_list, name="grn_list"),
    path("grns/new/<int:po_pk>/", views.grn_new, name="grn_new"),
    path("grns/<int:pk>/", views.grn_detail, name="grn_detail"),
    path("grns/<int:pk>/confirm/", views.grn_confirm, name="grn_confirm"),
    path("grns/<int:pk>/cancel/", views.grn_cancel, name="grn_cancel"),

    # Quality Inspections
    path("grns/<int:grn_pk>/inspect/", views.inspection_new, name="inspection_new"),
    path("inspections/<int:pk>/", views.inspection_detail, name="inspection_detail"),
    path("inspections/<int:pk>/submit/", views.inspection_submit, name="inspection_submit"),

    # Vendor Bills
    path("bills/", views.bill_list, name="bill_list"),
    path("bills/new/<int:po_pk>/", views.bill_new, name="bill_new"),
    path("bills/<int:pk>/", views.bill_detail, name="bill_detail"),
    path("bills/<int:pk>/match/", views.bill_match, name="bill_match"),
    path("bills/<int:pk>/approve/", views.bill_approve, name="bill_approve"),
    path("bills/<int:pk>/mark-paid/", views.bill_mark_paid, name="bill_mark_paid"),

    # Supplier Payments
    path("payments/", views.payment_list, name="payment_list"),
    path("payments/new/", views.payment_new, name="payment_new"),
    path("payments/<int:pk>/post/", views.payment_post, name="payment_post"),
    path("payments/<int:pk>/cancel/", views.payment_cancel, name="payment_cancel"),
    path("payments/schedules/new/", views.schedule_new, name="schedule_new"),

    # Purchase Returns
    path("returns/", views.return_list, name="return_list"),
    path("returns/new/<int:po_pk>/", views.return_new, name="return_new"),
    path("returns/<int:pk>/", views.return_detail, name="return_detail"),
    path("returns/<int:pk>/confirm/", views.return_confirm, name="return_confirm"),
    path("returns/<int:pk>/cancel/", views.return_cancel, name="return_cancel"),

    # Purchase Contracts
    path("contracts/", views.contract_list, name="contract_list"),
    path("contracts/new/", views.contract_new, name="contract_new"),
    path("contracts/<int:pk>/", views.contract_detail, name="contract_detail"),
    path("contracts/<int:pk>/edit/", views.contract_edit, name="contract_edit"),
    path("contracts/<int:pk>/activate/", views.contract_activate, name="contract_activate"),
    path("contracts/<int:pk>/terminate/", views.contract_terminate, name="contract_terminate"),
    path("contracts/<int:pk>/renew/", views.contract_renew, name="contract_renew"),
]
