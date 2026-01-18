from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from sqlite3 import IntegrityError
import sqlite3

DB = "wms.db"

app = FastAPI(title="Essential WMS")

# Allow frontend (Vite dev server) to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # allow everything during development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def db():
    return sqlite3.connect(DB, check_same_thread=False)

def db():
    return sqlite3.connect(DB, check_same_thread=False)


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY,
        name TEXT,
        sku TEXT UNIQUE,
        description TEXT,
        category TEXT,
        quantity INTEGER,
        low_stock INTEGER DEFAULT 10,
        deleted INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS movements (
        id INTEGER PRIMARY KEY,
        product_id INTEGER,
        delta INTEGER,
        reason TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()


class Product(BaseModel):
    name: str
    sku: str
    description: str
    category: str
    quantity: int
    low_stock: int = 10


class StockMove(BaseModel):
    sku: str
    delta: int
    reason: str


@app.get("/")
def root():
    return {"status": "API running"}


@app.get("/products")
def list_products(q: Optional[str] = None):
    conn = db()
    cur = conn.cursor()

    sql = """
    SELECT id, name, sku, description, category, quantity, low_stock
    FROM products
    WHERE deleted=0
    """
    params = ()

    if q:
        # case-insensitive search
        sql += " AND (LOWER(name) LIKE LOWER(?) OR LOWER(sku) LIKE LOWER(?))"
        q_lower = f"%{q}%"
        params = (q_lower, q_lower)

    rows = cur.execute(sql, params).fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "name": r[1],
            "sku": r[2],
            "description": r[3],
            "category": r[4],
            "quantity": r[5],
            "low_stock": r[6],
        }
        for r in rows
    ]



@app.post("/products")
def create_product(p: Product):
    conn = db()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO products
            (name, sku, description, category, quantity, low_stock)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (p.name, p.sku, p.description, p.category, p.quantity, p.low_stock))
        conn.commit()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="SKU already exists")
    finally:
        conn.close()

    return {"status": "created"}


@app.post("/stock")
def move_stock(m: StockMove):
    conn = db()
    cur = conn.cursor()

    product = cur.execute(
        "SELECT id, quantity FROM products WHERE sku=? AND deleted=0",
        (m.sku,)
    ).fetchone()

    if not product:
        raise HTTPException(404, "Product not found")

    new_qty = product[1] + m.delta
    if new_qty < 0:
        raise HTTPException(400, "Insufficient stock")

    cur.execute(
        "UPDATE products SET quantity=? WHERE id=?",
        (new_qty, product[0])
    )

    cur.execute("""
        INSERT INTO movements (product_id, delta, reason, created_at)
        VALUES (?, ?, ?, ?)
    """, (product[0], m.delta, m.reason, datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()
    return {"quantity": new_qty}


@app.get("/history")
def history(limit: int = 20):
    conn = db()
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT p.name, p.description, m.delta, m.reason, m.created_at
        FROM movements m
        JOIN products p ON p.id = m.product_id
        ORDER BY m.id DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()

    return [
        {
            "name": r[0],
            "description": r[1],
            "delta": r[2],
            "reason": r[3],
            "at": r[4],
        }
        for r in rows
    ]


@app.post("/undo")
def undo_last():
    conn = db()
    cur = conn.cursor()

    last = cur.execute("""
        SELECT id, product_id, delta
        FROM movements
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    if not last:
        raise HTTPException(400, "Nothing to undo")

    # revert quantity
    cur.execute(
        "UPDATE products SET quantity = quantity - ? WHERE id=?",
        (last[2], last[1])
    )

    # delete last movement
    cur.execute("DELETE FROM movements WHERE id=?", (last[0],))

    conn.commit()
    conn.close()
    return {"status": "undone"}