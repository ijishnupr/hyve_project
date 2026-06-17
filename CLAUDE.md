# CLAUDE.md

Guidance for working in this repository. This file documents the **features and
business logic** of the project so future work stays consistent with the domain
rules. Read it before changing models, services, or the procure-to-pay flow.

## What this project is

A **purchase / procurement module for a construction company**. It is a
production-style **Django + Django REST Framework** backend (with a
server-rendered Django frontend, see [Frontend](#frontend-web-app)) that models
the full *procure-to-pay* cycle for construction sites and enforces the business
rules at every transition.

```
Purchase Requisition  ──▶  Purchase Order  ──▶  Goods Receipt (GRN)  ──▶  Vendor Bill
   (site raises)            (issued to vendor)    (materials received)    (3-way matched)
```

## Tech stack

- **Python / Django** with **Django REST Framework** for the JSON API.
- **SimpleJWT** for API auth (access/refresh tokens); **Django sessions** for the
  server-rendered web frontend.
- **django-filter** (filtering), **drf-spectacular** (OpenAPI schema + Swagger/ReDoc).
- **Celery + Redis** for async jobs/email (`procurement/tasks.py`, `core/celery.py`).
- **WhiteNoise** for static serving; **Docker** + **GitHub Actions CI**.
- **DB**: PostgreSQL in prod (via `DATABASE_URL`), SQLite fallback for local dev.
- **pytest** for tests (`procurement/tests/`).

## App layout

| App | Responsibility |
|-----|----------------|
| `core/` | Project settings, root URLs, WSGI/ASGI, Celery app. |
| `accounts/` | Custom `User` model with roles; JWT login/register/me API. |
| `procurement/` | All domain models, services, serializers, API viewsets, filters, permissions, admin, seed command, tests. |
| `web/` | Server-rendered (Django templates) frontend — the UI for the whole flow. |

## Domain model (`procurement/models.py`)

Master data:
- **Project** — a construction site purchases are made against. Has `code`, `status`
  (PLANNING/ACTIVE/ON_HOLD/COMPLETED), `budget`, `manager`.
- **Vendor** — supplier; `gstin`, `payment_terms_days`, `rating`, `is_active`.
- **MaterialCategory** — self-referential tree (`parent`).
- **Material** — purchasable item; `unit` (construction `UnitOfMeasure`:
  NOS/BAG/KG/TON/CUM/SQM/RMT/LTR/QTL/BRASS), `hsn_code`, `default_tax_rate`.

Documents (each has a `lines` child model):
- **PurchaseRequisition** (+ `PurchaseRequisitionLine`) — internal request from a site.
- **PurchaseOrder** (+ `PurchaseOrderLine`) — binding order to a vendor; stores
  denormalised money totals (`subtotal`/`tax_amount`/`total`).
- **GoodsReceiptNote** / GRN (+ `GRNLine`) — materials physically received against a PO.
- **VendorBill** (+ `VendorBillLine`) — vendor invoice, 3-way matched.

Cross-cutting:
- **TimeStampedModel** — abstract base adding `created_at` / `updated_at`.
- **DocumentCounter** — generates gap-free, per-year, human-readable numbers
  (`PR-2026-00001`, `PO-…`, `GRN-…`, `BILL-…`). Uses `select_for_update` inside a
  transaction so numbering is safe under concurrency. Numbers are auto-assigned in
  each document's `save()` and are `editable=False`.

### Money math (important)
- All money is `Decimal`, quantised to 2 places (`TWO_PLACES = Decimal("0.01")`).
- Line totals are **computed properties** on the line models:
  `line_subtotal = quantity * unit_price`, `line_tax = line_subtotal * tax_rate/100`,
  `line_total = line_subtotal + line_tax`.
- PO/Bill header totals are **denormalised** and recomputed from lines via
  `recalculate_totals()` — never set them by hand; call that method after editing lines.

## Business logic — the rules live in `procurement/services.py`

State transitions are intentionally kept **out of views/serializers** so they are
testable and reused by API, admin, web UI, and tasks. Each raises
`services.TransitionError` (mapped to HTTP 400 in the API via `_transition()`),
which the web UI surfaces as a Django message.

**Purchase Requisition** `DRAFT → SUBMITTED → APPROVED/REJECTED → CONVERTED`
- `submit_requisition` — DRAFT only; must have ≥1 line.
- `approve_requisition` / `reject_requisition` — SUBMITTED only; records approver,
  timestamp, and (reject) reason.

**Purchase Order** `DRAFT → ISSUED → PARTIALLY_RECEIVED → RECEIVED → CLOSED` (or `CANCELLED`)
- `issue_purchase_order` — DRAFT only; must have ≥1 line; recomputes totals; sets
  approver; **marks the source requisition CONVERTED** if it was APPROVED.
- `cancel_purchase_order` — not allowed once RECEIVED/CLOSED or if any CONFIRMED GRN exists.
- `close_purchase_order` — only from (PARTIALLY_)RECEIVED.
- `PurchaseOrder.refresh_receipt_status()` recomputes ISSUED/PARTIALLY_RECEIVED/RECEIVED
  from the received quantities on its lines.

**Goods Receipt Note** `DRAFT → CONFIRMED` (or `CANCELLED`)
- `confirm_grn` (atomic) — DRAFT only; parent PO must be ISSUED/PARTIALLY_RECEIVED;
  every line must reference a PO line of the same PO; `accepted ≤ received`; cumulative
  accepted must not exceed the ordered quantity. On success it **posts accepted
  quantities onto the PO lines** (`po_line.received_quantity += accepted`) and refreshes
  the PO status.
- `cancel_grn` (atomic) — **reverses** the posted quantities if the GRN was CONFIRMED,
  then refreshes PO status.

**Vendor Bill** `DRAFT → MATCHED → APPROVED → PAID` (or `DISPUTED` / `CANCELLED`)
- `run_three_way_match` — recomputes totals, then for each billed PO line checks
  (1) billed unit price is within `price_tolerance` (default 0.01) of the PO price, and
  (2) billed quantity ≤ received (accepted) quantity. Any violation → `match_status =
  EXCEPTION`, `status = DISPUTED`, with reasons in `match_notes`. Clean → `MATCHED`.
- `approve_bill` — MATCHED only. `mark_bill_paid` — APPROVED only.
- Uniqueness: one `vendor_invoice_number` per vendor (DB constraint).

## Roles & permissions

`accounts.Role`: **ADMIN, PROCUREMENT_MANAGER, SITE_ENGINEER, ACCOUNTANT, VIEWER**.
User convenience predicates: `can_manage_procurement` / `can_approve` (ADMIN,
PROCUREMENT_MANAGER), `can_manage_bills` (ADMIN, ACCOUNTANT).

API permission classes (`procurement/permissions.py`):
- `IsProcurementManagerOrReadOnly` — read for any authenticated user; writes for
  procurement managers/admins (masters, PR, PO, GRN).
- `CanApprove` — gates approval actions (PR approve/reject, PO issue/cancel/close).
- `CanManageBills` — bill writes for accountants/admins.

The web UI mirrors these checks (`web/views.py` permission helpers) so buttons/actions
are hidden or rejected for users lacking the role.

## API surface

- Auth: `POST /api/auth/login` (JWT + user), `/refresh`, `/verify`, `/register`
  (admin only), `GET /api/auth/me`.
- Resources (DRF router, `procurement/urls.py`): `/api/projects`, `/vendors`,
  `/material-categories`, `/materials`, `/requisitions`, `/purchase-orders`,
  `/grns`, `/bills` — each full CRUD + paginated/filterable/searchable.
- Custom actions (POST): requisitions `submit|approve|reject`; purchase-orders
  `issue|cancel|close`; grns `confirm|cancel`; bills `match|approve|mark-paid`.
- Docs: `/api/schema`, `/api/docs` (Swagger), `/api/redoc`. Health: `/health`.

## Frontend (web app)

Server-rendered **Django templates** (Bootstrap 5 via CDN — no JS build step),
under `web/`. Uses **Django session auth** (separate from the API's JWT). Routes are
mounted at the site root in `core/urls.py` (`/` dashboard, `/login`, `/projects`,
`/vendors`, `/materials`, `/requisitions`, `/purchase-orders`, `/grns`, `/bills`).

- `web/views.py` — login/logout, dashboard (counts + recent docs), and per-entity
  list/detail/create/edit views plus buttons that call the **same
  `procurement.services` transition functions** as the API.
- `web/forms.py` — `ModelForm`s and inline **formsets** for document line items.
- `web/templates/web/` — `base.html` (nav, messages), `login.html`, `dashboard.html`,
  reusable master list/form templates, and per-document list/detail/form templates.
- Line-item rows use a tiny vanilla-JS "add row" clone helper in `base.html`
  (`static/web/app.js` if extracted) — no framework.

**Golden rule for the UI:** never re-implement domain rules in views/templates —
always delegate state changes to `procurement.services`, and recompute totals via
`recalculate_totals()`. The UI is a thin layer over the service functions.

## Local development

```bash
# deps + DB
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo_data       # creates admin / admin12345 + masters
.venv/bin/python manage.py runserver            # HTTP only — keep DJANGO_DEBUG=True
```

- **Copy `.env.example` to `.env`** before running. With no `.env`, `DJANGO_DEBUG`
  defaults to `False`, which turns on `SECURE_SSL_REDIRECT` + 1-year HSTS and breaks
  the local HTTP dev server (browser force-upgrades to HTTPS).
- Web UI: `http://127.0.0.1:8000/` (log in with `admin` / `admin12345`).
- API docs: `http://127.0.0.1:8000/api/docs/`.
- Tests: `.venv/bin/pytest`. Lint/format: `ruff` (see `pyproject.toml`).

## Conventions

- Keep state transitions in `services.py`; keep views/serializers/templates thin.
- Money is always `Decimal` quantised to 2 dp; quantities to 3 dp.
- Document numbers are system-generated — never accept them as user input.
- New transitions should raise `TransitionError` on rule violations and have a
  matching test in `procurement/tests/`.
</content>
</invoke>
