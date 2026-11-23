# NovaLedger

A full-stack Warehouse Management System built with modern web technologies to streamline inventory operations, stock movements, supplier management, customer management, and warehouse workflows.

## Overview

NovaLedger is designed for organizations that require secure and efficient inventory management. The system provides role-based access control, product management, shipment tracking, stock adjustments, audit logging, and administrative controls within a modern web application. The backend exposes a versioned RESTful API (`/v1`) that powers the React frontend and can also be consumed independently.

## Features

* Versioned RESTful API (`/v1`) covering every module, with interactive Swagger docs
* JWT authentication with secure password hashing using bcrypt
* Role-based access control (Admin, Manager, Operator)
* Configurable permission matrix for each module
* Complete audit trail for user and system activities
* Product catalog with search, filtering, archiving, and low-stock monitoring
* Filter-aware product CSV exports for reporting and spreadsheet workflows
* Bulk product import using CSV and Excel files
* Stock movement tracking with paginated history and filtering
* Inbound shipment management
* Outbound shipment management
* Supplier management
* Customer management
* File attachment support for shipment documents
* Dashboard with inventory statistics and recent activities
* User and permission management
* Docker support with an Nginx frontend, loopback-only published ports, and a persistent data volume
* GitHub Actions checks for the API tests, frontend build, and a container smoke test

---

# Project Structure

```text
PythonProject/
│
├── README.md
├── docker-compose.yml
├── .env.example
├── .github/
│   ├── dependabot.yml
│   └── workflows/ci.yml
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── file_utils.py
│   ├── security.py
│   ├── schemas.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pytest.ini
│   ├── tests/
│   └── routes/
│       ├── auth.py
│       ├── admin.py
│       ├── products.py
│       ├── movements.py
│       ├── suppliers.py
│       ├── customers.py
│       ├── inbound.py
│       ├── outbound.py
│       └── attachments.py
│
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── security-headers.conf
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    └── src/
        ├── App.jsx
        ├── api.js
        ├── Sidebar.jsx
        ├── AuthContext.jsx
        ├── main.jsx
        └── pages/
            ├── Login.jsx
            ├── Dashboard.jsx
            ├── Products.jsx
            ├── Stock.jsx
            ├── Inbound.jsx
            ├── Outbound.jsx
            ├── Suppliers.jsx
            ├── Customers.jsx
            ├── Activity.jsx
            ├── Users.jsx
            ├── Permissions.jsx
            └── AuditLog.jsx
```

---

# System Architecture

```text
React + Vite + TailwindCSS
            │
            │ JWT Authentication
            ▼
FastAPI REST API (/v1)
            │
            ▼
SQLite Database
```

The frontend authenticates users through the backend using JWT. Every protected request includes a bearer token that is validated before access is granted. Permissions are enforced according to the user's assigned role, while all significant actions are recorded in the audit log. Every resource is exposed under a single `/v1` prefix, so the same API that drives the React frontend can be called directly by scripts, Postman, or third-party integrations.

---

# Technology Stack

| Component        | Technology                 |
| ---------------- | --------------------------- |
| Frontend         | React 19, Vite             |
| Styling          | Tailwind CSS               |
| Routing          | React Router 7             |
| Backend          | FastAPI                    |
| API Style        | RESTful, versioned (`/v1`) |
| Authentication   | JWT (PyJWT), bcrypt        |
| Database         | SQLite                     |
| File Processing  | python-multipart, openpyxl |
| Server           | Uvicorn                    |
| Containerization | Docker                     |
| Orchestration    | Docker Compose             |
| Static web server | Nginx                      |
| Tests            | pytest                     |
| CI               | GitHub Actions             |
| Linting          | ESLint                     |

---

# User Roles

| Role     | Permissions                                                            |
| -------- | ---------------------------------------------------------------------- |
| Admin    | Full access to all modules and administrative functions                |
| Manager  | Read and write access to operational modules without delete privileges |
| Operator | Inventory operations with read-only access to selected modules         |

Development administrator credentials:

```text
Username: admin
Password: admin123
```

The local development database is seeded with this account. Docker starts in
production mode and requires a unique initial administrator password in `.env`.
New user accounts and password resets require at least 12 characters. Change
the administrator password after first login as well.

---

# Installation

## Docker Installation

Clone the repository.

```bash
git clone https://github.com/adib-26/Warehouse-Management-System.git
cd Warehouse-Management-System
```

Copy the environment template, set a unique signing key and initial
administrator password, then build and start the application. Generate the key
with `openssl rand -hex 32`; set `INITIAL_ADMIN_PASSWORD` to a unique password
with at least 16 characters.
The bcrypt-backed account password fields accept up to 72 UTF-8 bytes.

```bash
cp .env.example .env
# Edit .env: replace SECRET_KEY and INITIAL_ADMIN_PASSWORD before starting.
docker compose up --build
```

Access the application:

| Service           | URL                           |
| ----------------- | ------------------------------ |
| Frontend          | http://localhost:5173         |
| Backend           | http://localhost:8000 (local only) |
| REST API          | http://localhost:8000/v1 (local only) |
| Health check      | http://localhost:8000/health (local only) |
| API Documentation | http://localhost:8000/docs (local only) |

Docker serves a built React frontend through Nginx. It stores the SQLite
database and uploaded files in the `warehouse-data` named volume, so they
survive container recreation. Stop the stack with `docker compose down`. Add
`-v` only when you intend to delete that data. The frontend proxies `/v1` to the
backend, so it works through one browser origin by default. `VITE_API_URL` is an
optional build-time override for a separately hosted public API.

Both published ports bind to `127.0.0.1` by default. If port 8000 or 5173 is
already in use, set `BACKEND_PORT` or `FRONTEND_PORT` in `.env`; the container
ports remain 8000 and 80 respectively. Deliberately change a bind address only
when a network design requires it.

The API reads `APP_ENV`, `SECRET_KEY`, `INITIAL_ADMIN_USERNAME`,
`INITIAL_ADMIN_PASSWORD`, `CORS_ORIGINS`, `DATABASE_PATH`, `UPLOAD_DIR`, and
`MAX_UPLOAD_BYTES` from the environment. Production startup rejects the built-in
development signing key and weak first-run administrator passwords. Existing
databases keep their current users; use the administration screen to change an
existing account password. Changing `SECRET_KEY` invalidates all active JWTs.
The frontend proxy receives the same `MAX_UPLOAD_BYTES` value, so uploads are
rejected consistently at the configured limit.

### Database upgrades and backups

SQLite schema versions are stored in `PRAGMA user_version` and applied during
startup. Keep the `warehouse-data` volume when updating the application image.
Before a production upgrade, create an online SQLite backup from the running
container:

```bash
docker compose exec -T backend python -c "import sqlite3; source=sqlite3.connect('/data/wms.db'); backup=sqlite3.connect('/data/wms-pre-upgrade.db'); source.backup(backup); backup.close(); source.close()"
```

Future schema changes belong in numbered functions in `backend/database.py`;
increment `SCHEMA_VERSION` and register each migration in `SCHEMA_MIGRATIONS`.
Never edit an already released migration, since existing installations have
recorded which versions have run.

### Production deployment notes

For an internet-facing deployment, keep the Compose ports loopback-only and
place a TLS-terminating reverse proxy (such as Caddy, Traefik, or a managed
load balancer) in front of the frontend. Serve HTTPS before exposing the app;
do not publish the backend directly. Enable HSTS only at that HTTPS boundary.

The included database is SQLite and the application is designed for a single
backend instance sharing one `warehouse-data` volume. SQLite supports one
writer at a time; do not horizontally scale the backend or mount that volume on
multiple hosts. Move to a server database before a multi-instance deployment.

---

## Manual Installation

### Backend

```bash
cd backend

python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt

uvicorn main:app --reload --port 8000
```

Development defaults are suitable for local use. For a shared deployment, set
`APP_ENV=production`, generate a unique `SECRET_KEY`, and set the initial admin
credentials before starting Uvicorn. Production mode enforces those settings.

Optional development environment variables:

```bash
export SECRET_KEY="replace-with-a-long-random-secret"
export CORS_ORIGINS="http://localhost:5173"
```

Windows:

```bash
set SECRET_KEY=replace-with-a-long-random-secret
set CORS_ORIGINS=http://localhost:5173
```

### Frontend

```bash
cd frontend

npm ci

npm run dev
```

The frontend uses the Vite development proxy by default, so start the backend on
port 8000 before running the frontend. Set `VITE_API_URL` only when the browser
must call a separately hosted API origin:

```bash
VITE_API_URL=https://api.example.com npm run dev
```

### Development checks

Run the same checks used by CI:

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pip check
python -m compileall -q .
pytest -q
pip-audit -r requirements.txt
pip-audit -r requirements-dev.txt

cd ../frontend
npm ci
npm run lint
npm run build
npm audit --audit-level=high
```

Open:

```text
http://localhost:5173
```

---

# RESTful API Reference

All endpoints are served under the base path `/v1`. Interactive, always-up-to-date documentation (Swagger UI) is available at `http://localhost:8000/docs`.

Unless noted otherwise, every endpoint requires a valid JWT bearer token in the `Authorization` header, and access is additionally gated by the caller's role permissions for that module.

### Authentication — `/v1/auth`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| POST   | `/v1/auth/login` | Authenticate with username and password, returns a JWT and user profile |
| GET    | `/v1/auth/me` | Retrieve the currently authenticated user |

### Products — `/v1/products`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/products` | List products, with search, filtering, and pagination |
| GET    | `/v1/products/export` | Download the current product filters as CSV |
| GET    | `/v1/products/facets` | List category and tag values used by the catalog filters |
| GET    | `/v1/products/{product_id}` | Retrieve a single product |
| POST   | `/v1/products` | Create a new product |
| PATCH  | `/v1/products/{product_id}` | Update an existing product |
| DELETE | `/v1/products/{product_id}` | Archive/delete a product |
| POST   | `/v1/products/imports` | Bulk import products from a CSV or Excel file |

### Stock Movements — `/v1/movements`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/movements` | List stock movements, filterable by product and action type, paginated |
| POST   | `/v1/movements` | Record a stock adjustment (in, out, or correction) |
| DELETE | `/v1/movements/{movement_id}` | Undo/reverse a stock movement |

### Stats — `/v1/stats`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/stats` | Retrieve dashboard/inventory statistics |

### Suppliers — `/v1/suppliers`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/suppliers` | List suppliers, with search and pagination |
| GET    | `/v1/suppliers/{supplier_id}` | Retrieve a single supplier |
| POST   | `/v1/suppliers` | Create a new supplier |
| PATCH  | `/v1/suppliers/{supplier_id}` | Update an existing supplier |
| DELETE | `/v1/suppliers/{supplier_id}` | Delete a supplier |

### Customers — `/v1/customers`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/customers` | List customers, with search and pagination |
| GET    | `/v1/customers/{customer_id}` | Retrieve a single customer |
| POST   | `/v1/customers` | Create a new customer |
| PATCH  | `/v1/customers/{customer_id}` | Update an existing customer |
| DELETE | `/v1/customers/{customer_id}` | Delete a customer |

### Inbound Shipments — `/v1/inbound-shipments`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| POST   | `/v1/inbound-shipments` | Create a new inbound shipment |
| GET    | `/v1/inbound-shipments` | List inbound shipments, with filtering and pagination |
| GET    | `/v1/inbound-shipments/{shipment_id}/attachments` | List attachments for a shipment |
| POST   | `/v1/inbound-shipments/{shipment_id}/attachments` | Upload an attachment to a shipment |
| POST   | `/v1/inbound-shipments/imports` | Bulk import inbound shipments from a file |

### Outbound Shipments — `/v1/outbound-shipments`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| POST   | `/v1/outbound-shipments` | Create a new outbound shipment |
| GET    | `/v1/outbound-shipments` | List outbound shipments, with filtering and pagination |
| GET    | `/v1/outbound-shipments/{shipment_id}/attachments` | List attachments for a shipment |
| POST   | `/v1/outbound-shipments/{shipment_id}/attachments` | Upload an attachment to a shipment |
| POST   | `/v1/outbound-shipments/imports` | Bulk import outbound shipments from a file |

### Attachments — `/v1/attachments`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/attachments/{attachment_id}` | Download an attachment |
| DELETE | `/v1/attachments/{attachment_id}` | Delete an attachment |

### Administration — `/v1/admin`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/admin/users` | List all users |
| POST   | `/v1/admin/users` | Create a new user |
| PATCH  | `/v1/admin/users/{user_id}` | Update a user (role, password, active status) |
| GET    | `/v1/admin/permissions` | Retrieve the role permission matrix |
| PUT    | `/v1/admin/permissions` | Update the role permission matrix |
| GET    | `/v1/admin/audit-logs` | Retrieve audit logs from the admin panel |

### Audit — `/v1/audit-logs`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/audit-logs` | Retrieve a filterable, paginated audit log report |

---

# Application Modules

| Module      | Description                      |
| ----------- | --------------------------------- |
| Login       | User authentication              |
| Dashboard   | Inventory summary and statistics |
| Products    | Product catalog management       |
| Stock       | Inventory adjustments            |
| Inbound     | Incoming shipments               |
| Outbound    | Outgoing shipments               |
| Suppliers   | Supplier directory               |
| Customers   | Customer directory               |
| Activity    | Inventory history                |
| Users       | User administration              |
| Permissions | Role permission management       |
| Audit Log   | System activity records          |

Navigation is generated dynamically based on the authenticated user's permissions.

---

# Author

Mahbub

Warehouse Management System
