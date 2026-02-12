Directory structure:
└── adib-26-warehouse-management-system/
    ├── README.md
    ├── docker-compose.yml
    ├── Dockerfile
    ├── package.json
    ├── requirements.txt
    ├── backend/
    │   ├── Dockerfile
    │   ├── main.py
    │   └── requirements.txt
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


Files Content:

================================================
FILE: README.md
================================================
# Warehouse Management System

A modern inventory dashboard built with React (Vite + TailwindCSS) on the frontend and FastAPI + SQLite on the backend.  
Designed for efficient product management with a clean UI and robust API.

## Features
- Search products by name or SKU
- Add, update, and delete products
- Responsive product table with category and quantity
- FastAPI backend with REST endpoints
- Tailwind-powered frontend for modern UI
- SQLite database integration

## Tech Stack

| Layer            | Technology                |
|------------------|---------------------------|
| Frontend         | React, Vite, TailwindCSS  |
| Backend          | FastAPI (Python)          |
| Database         | SQLite                    |
| Version Control  | Git + GitHub              |
| Containerization | Docker + Docker Compose   |

## Setup Instructions

### Clone the repository
```bash
git clone https://github.com/adib-26/Warehouse-Management-System.git
cd Warehouse-Management-System
```
### Option 1: Run with Docker (Recommended)

Make sure Docker Desktop is running.

```bash
docker compose up --build
```
### Option 2: Manual Setup

## Backend (FastAPI)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
.venv\Scripts\activate      # Windows

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```

<img width="799" height="762" alt="Screenshot 2026-02-11 at 11 41 36 PM" src="https://github.com/user-attachments/assets/31ef111d-ca6b-458f-ae7b-4b25880ca588" />


================================================
FILE: backend/Dockerfile
================================================
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# Run FastAPI with Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
