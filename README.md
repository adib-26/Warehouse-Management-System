# NovaLedger

A full-stack Warehouse Management System built with modern web technologies to streamline inventory operations, stock movements, supplier management, customer management, and warehouse workflows.

## Overview

NovaLedger is designed for organizations that require secure and efficient inventory management. The system provides role-based access control, product management, shipment tracking, stock adjustments, audit logging, and administrative controls within a modern web application.

## Features

* JWT authentication with secure password hashing using bcrypt
* Role-based access control (Admin, Manager, Operator)
* Configurable permission matrix for each module
* Complete audit trail for user and system activities
* Product catalog with search, filtering, archiving, and low-stock monitoring
* Bulk product import using CSV and Excel files
* Stock adjustment with undo functionality
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
│       ├── stock.py
│       ├── history.py
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
FastAPI REST API
            │
            ▼
SQLite Database
```

The frontend authenticates users through the backend using JWT. Every protected request includes a bearer token that is validated before access is granted. Permissions are enforced according to the user's assigned role, while all significant actions are recorded in the audit log.

---

# Technology Stack

| Component        | Technology                 |
| ---------------- | -------------------------- |
| Frontend         | React 19, Vite             |
| Styling          | Tailwind CSS               |
| Routing          | React Router 7             |
| Backend          | FastAPI                    |
| Authentication   | JWT, bcrypt                |
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

| Service           | URL                        |
| ----------------- | -------------------------- |
| Frontend          | http://localhost:5173      |
| Backend           | http://localhost:8000      |
| API Documentation | http://localhost:8000/docs |

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

# API Overview

### Authentication

| Method | Endpoint      | Description           |
| ------ | ------------- | --------------------- |
| POST   | `/auth/login` | Authenticate user     |
| GET    | `/auth/me`    | Retrieve current user |

### Products

* Product management
* Product search and filtering
* Bulk upload
* Product archiving
* Low stock monitoring

### Inventory

* Stock adjustments
* Undo stock movement

### Shipments

* Inbound shipment management
* Outbound shipment management
* Bulk imports

### Suppliers

* Create, update, search, and manage suppliers

### Customers

* Create, update, search, and manage customers

### Attachments

* Upload and download shipment-related documents

### Administration

* User management
* Permission management
* Audit log

Interactive API documentation is available at:

```text
http://localhost:8000/docs
```

---

# Application Modules

| Module      | Description                      |
| ----------- | -------------------------------- |
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

# Production Recommendations

* Replace SQLite with PostgreSQL for larger deployments.
* Configure a secure JWT secret.
* Change the default administrator password.
* Store sensitive configuration using environment variables.
* Restrict CORS origins appropriately.
* Back up uploaded files or migrate them to cloud object storage.

---

# Future Enhancements

* PostgreSQL support
* Refresh token authentication
* Advanced analytics dashboard
* CSV and PDF report generation
* Email notifications
* Continuous Integration and Continuous Deployment (CI/CD)
* Cloud storage integration

---

# Author

Mahbub

Warehouse Management System
