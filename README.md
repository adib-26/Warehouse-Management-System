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
* Bulk product import using CSV and Excel files
* Stock movement tracking with paginated history and filtering
* Inbound shipment management
* Outbound shipment management
* Supplier management
* Customer management
* File attachment support for shipment documents
* Dashboard with inventory statistics and recent activities
* User and permission management
* Docker support for simplified deployment

---

# Project Structure

```text
PythonProject/
│
├── README.md
├── docker-compose.yml
│
├── backend/
│   ├── Dockerfile
│   ├── main.py
│   ├── database.py
│   ├── security.py
│   ├── schemas.py
│   ├── requirements.txt
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
| Linting          | ESLint                     |

---

# User Roles

| Role     | Permissions                                                            |
| -------- | ---------------------------------------------------------------------- |
| Admin    | Full access to all modules and administrative functions                |
| Manager  | Read and write access to operational modules without delete privileges |
| Operator | Inventory operations with read-only access to selected modules         |

Default administrator credentials:

```text
Username: admin
Password: admin123
```

For production deployments, change the default password immediately.

---

# Installation

## Docker Installation

Clone the repository.

```bash
git clone https://github.com/adib-26/Warehouse-Management-System.git
cd Warehouse-Management-System
```

Build and start the application.

```bash
docker compose up --build
```

Access the application:

| Service           | URL                           |
| ----------------- | ------------------------------ |
| Frontend          | http://localhost:5173         |
| Backend           | http://localhost:8000         |
| REST API          | http://localhost:8000/v1      |
| API Documentation | http://localhost:8000/docs    |

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

Optional environment variable:

```bash
export SECRET_KEY="your-secret-key"
```

Windows:

```bash
set SECRET_KEY=your-secret-key
```

### Frontend

```bash
cd frontend

npm install

npm run dev
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
# Application Preview

Watch the complete application walkthrough on YouTube.

[![Watch Demo](https://img.youtube.com/vi/i4acmU_XxhI/maxresdefault.jpg)](https://youtu.be/i4acmU_XxhI)
---



---

# Author

Mahbub

Warehouse Management System
