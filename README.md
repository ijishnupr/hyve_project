# Construction Procurement (Purchase) Module

A production-ready Django + Django REST Framework backend for the **purchase /
procurement** function of a construction company. It models the full
procurement cycle and enforces the business rules along the way.

```
Purchase Requisition  ──▶  Purchase Order  ──▶  Goods Receipt (GRN)  ──▶  Vendor Bill
     (site raises)            (issued to vendor)     (materials received)    (3-way matched)
```

## Features

- **Master data** — Projects (sites), Vendors, Material Categories, Materials
  (with construction units: BAG, CUM, TON, BRASS, RMT …).
- **Purchase Requisition** — raised by site engineers, submitted, approved/rejected.
- **Purchase Order** — issued to vendors with line items, taxes and auto-computed totals.
- **Goods Receipt Note (GRN)** — records received/accepted/rejected quantities;
  posts received quantities back to the PO and advances its status
  (Issued → Partially Received → Fully Received). Cancelling reverses the posting.
- **Vendor Bill** — captured against a PO and run through **3-way matching**
  (price vs PO, quantity vs received) before approval and payment.
- **Role-based access** — Admin, Procurement Manager, Site Engineer, Accountant, Viewer.
- **Auto-numbering** — gap-free `PR-2026-00001`, `PO-…`, `GRN-…`, `BILL-…` via
  row-locked counters.
- **Production concerns** — JWT auth, throttling, pagination, filtering/search,
  OpenAPI docs, env-driven settings, security hardening when `DEBUG=False`,
  WhiteNoise static serving, Celery for async email/jobs, Docker, CI, tests.

## Tech stack

Django 5.2 · DRF · SimpleJWT · drf-spectacular · django-filter · PostgreSQL ·
Celery + Redis · Gunicorn · WhiteNoise · pytest · ruff.

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                # adjust as needed (SQLite is the default)
python manage.py migrate
python manage.py seed_demo_data     # demo masters + admin/admin12345
python manage.py runserver
```

- API root: `http://localhost:8000/api/`
- Swagger UI: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`
- Admin: `http://localhost:8000/admin/`
- Health check: `http://localhost:8000/health/`

## Authentication

```bash
# Obtain tokens
curl -X POST http://localhost:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username": "admin", "password": "admin12345"}'

# Use the access token
curl http://localhost:8000/api/vendors/ -H 'Authorization: Bearer <access>'
```

## Running with Docker

```bash
cp .env.example .env
docker compose up --build      # web + postgres + redis + celery worker
```

The `web` service runs migrations on startup and serves via Gunicorn on `:8000`.

## Testing & quality

```bash
pytest                 # full test suite (models, services, API flow)
ruff check .           # lint
python manage.py makemigrations --check --dry-run   # migration drift check
```

## Key API endpoints

| Resource            | Endpoint                         | Notable actions |
|---------------------|----------------------------------|-----------------|
| Projects            | `/api/projects/`                 | CRUD            |
| Vendors             | `/api/vendors/`                  | CRUD            |
| Materials           | `/api/materials/`                | CRUD            |
| Requisitions        | `/api/requisitions/`             | `submit`, `approve`, `reject` |
| Purchase Orders     | `/api/purchase-orders/`          | `issue`, `cancel`, `close` |
| Goods Receipts      | `/api/grns/`                     | `confirm`, `cancel` |
| Vendor Bills        | `/api/bills/`                    | `match`, `approve`, `mark-paid` |

Transition actions are `POST`s, e.g. `POST /api/purchase-orders/{id}/issue/`.

## Configuration

All configuration is environment-driven — see `.env.example`. With no
`DATABASE_URL` set, the app falls back to a local SQLite file for convenience.
Set `DJANGO_DEBUG=False` in production to enable HSTS, secure cookies and SSL
redirect automatically.

## Project layout

```
core/         project settings, urls, wsgi/asgi, celery
accounts/     custom user model, JWT auth, roles
procurement/  domain models, services (business rules), serializers, viewsets
              ├─ services.py   state transitions & 3-way matching
              ├─ tasks.py      Celery tasks
              └─ tests/        pytest suite
```
# hyve_project
