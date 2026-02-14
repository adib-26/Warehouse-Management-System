# 📦 Warehouse Management System

A modern full-stack inventory management dashboard built with:

*  **React (Vite + TailwindCSS)** – Frontend
*  **FastAPI** – Backend API
*  **SQLite** – Database
*  **Docker & Docker Compose** – Containerized deployment

Designed for efficient product tracking with a clean UI and scalable backend architecture.

---

## 🚀 Features

*  Search products by Name or SKU
*  Add new products
*  Update product details
*  Delete products
*  Responsive dashboard UI
*  Category & stock quantity tracking
*  High-performance FastAPI REST API
*  Fully Dockerized setup

---

## 🏗️ Project Structure

```
adib-26-warehouse-management-system/
│
├── README.md
├── docker-compose.yml
├── Dockerfile
├── package.json
├── requirements.txt
│
├── backend/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
│
└── frontend/
    ├── README.md
    ├── Dockerfile
    ├── eslint.config.js
    ├── index.html
    ├── package.json
    ├── postcss.config.js
    ├── tailwind.config.js
    ├── vite.config.js
    └── src/
        ├── App.css
        ├── App.jsx
        ├── ErrorBoundary.jsx
        ├── index.css
        ├── main.jsx
        ├── Sidebar.jsx
        └── pages/
            ├── Activity.jsx
            ├── Dashboard.jsx
            ├── Products.jsx
            └── Stock.jsx
```

---

## 🧠 Architecture Overview

```
Frontend (React + Vite + Tailwind)
        ↓
FastAPI Backend (REST API)
        ↓
SQLite Database
```

The frontend communicates with FastAPI via HTTP REST endpoints.
FastAPI manages CRUD operations and persists data in SQLite.

---

## ⚙️ Tech Stack

| Layer            | Technology     |
| ---------------- | -------------- |
| Frontend         | React + Vite   |
| Styling          | TailwindCSS    |
| Backend          | FastAPI        |
| Database         | SQLite         |
| Dev Server       | Uvicorn        |
| Containerization | Docker         |
| Orchestration    | Docker Compose |
| Linting          | ESLint         |

---

## 🐳 Docker Setup (Recommended)

### 1️⃣ Clone Repository

```bash
git clone https://github.com/adib-26/Warehouse-Management-System.git
cd Warehouse-Management-System
```

### 2️⃣ Build & Run Containers

```bash
docker compose up --build
```

### 3️⃣ Access the Application

Frontend:

```
http://localhost:5173
```

Backend API:

```
http://localhost:8000
```

FastAPI Docs:

```
http://localhost:8000/docs
```

---

## 🖥️ Manual Setup (Without Docker)

---

### 🔹 Backend Setup (FastAPI)

```bash
cd backend

python -m venv .venv

# Mac/Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt

uvicorn main:app --reload --port 8000
```

---

### 🔹 Frontend Setup (React + Vite)

```bash
cd frontend

npm install
npm run dev
```

Then open:

```
http://localhost:5173
```

---

## 📡 API Endpoints (Example)

| Method | Endpoint         | Description           |
| ------ | ---------------- | --------------------- |
| GET    | `/products`      | Retrieve all products |
| GET    | `/products/{id}` | Get product by ID     |
| POST   | `/products`      | Create new product    |
| PUT    | `/products/{id}` | Update product        |
| DELETE | `/products/{id}` | Delete product        |

Full interactive documentation available at:

```
/docs
```

---

## 📊 UI Pages

| Page      | Description             |
| --------- | ----------------------- |
| Dashboard | Overview of inventory   |
| Products  | Manage all products     |
| Stock     | Stock tracking          |
| Activity  | Inventory activity logs |

---

## 🖼️ Application Preview

<img width="797" height="746" alt="Warehouse Dashboard Screenshot" src="https://github.com/user-attachments/assets/8e087684-77a5-4b1e-8861-ec604c4d6c54" />

---

## 🔒 Production Notes

* SQLite is suitable for small-to-medium deployments
* For production-scale apps, consider PostgreSQL
* Use environment variables for production configs
* Enable CORS properly if deploying separately

---

## 🚀 Future Improvements

* JWT Authentication
* Role-based access control
* Inventory analytics dashboard
* Export reports (CSV/PDF)
* PostgreSQL support
* CI/CD pipeline

---

## 👨‍💻 Author

Mahbub
Warehouse Management System


