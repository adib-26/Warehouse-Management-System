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
| Layer      | Technology                |
|------------|---------------------------|
| Frontend   | React, Vite, TailwindCSS  |
| Backend    | FastAPI (Python)          |
| Database   | SQLite                    |
| Versioning | Git + GitHub              |

## Setup Instructions

### Clone the repository
```bash
git clone https://github.com/adib-26/Warehouse-Management-System.git
cd Warehouse-Management-System
```

### Backend Setup (FastAPI)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
.venv\Scripts\activate      # Windows

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend Setup (React + Vite)
```bash
cd frontend
npm install
npm run dev
```

### Project Structure

Warehouse-Management-System/
├── backend/
│   ├── main.py
│   ├── models.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   └── Products.jsx
│   ├── package.json
│   └── vite.config.js
├── README.md

<img width="693" height="625" alt="Screenshot 2026-01-18 at 1 13 31 PM" src="https://github.com/user-attachments/assets/5c173325-9d4b-42fd-b591-7cae133dda4f" />





