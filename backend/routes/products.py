from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from sqlite3 import IntegrityError
from database import get_db
from schemas import ProductCreate, ProductUpdate
from security import require_permission, log_audit
from typing import Optional
import csv
import io
import os

router = APIRouter()

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


@router.get("")
def list_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    sku: Optional[str] = None,
    low_stock: Optional[bool] = None,
    archived: Optional[bool] = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("products", "read")),
):
    conn = get_db()
    cur = conn.cursor()

    where = "WHERE deleted=0"
    params = []

    if archived is True:
        where += " AND archived=1"
    else:
        where += " AND archived=0"

    if q:
        where += " AND (LOWER(name) LIKE ? OR LOWER(sku) LIKE ? OR LOWER(description) LIKE ?)"
        like = f"%{q.lower()}%"
        params.extend([like, like, like])

    if category:
        where += " AND LOWER(category) = ?"
        params.append(category.lower())

    if tag:
        where += " AND LOWER(tags) LIKE ?"
        params.append(f"%{tag.lower()}%")

    if sku:
        where += " AND LOWER(sku) LIKE ?"
        params.append(f"%{sku.lower()}%")

    if low_stock:
        where += " AND quantity <= low_stock"

    total = cur.execute(f"SELECT COUNT(*) FROM products {where}", params).fetchone()[0]
    order = "ORDER BY quantity ASC" if low_stock else "ORDER BY updated_at DESC"
    rows = cur.execute(
        f"SELECT * FROM products {where} {order} LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()

    return {
        "data": [dict(r) for r in rows],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.get("/{product_id}")
def get_product(product_id: int, user: dict = Depends(require_permission("products", "read"))):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM products WHERE id=? AND deleted=0", (product_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    return dict(row)


@router.post("", status_code=201)
def create_product(
    p: ProductCreate,
    response: Response,
    user: dict = Depends(require_permission("products", "write")),
):
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO products (name, sku, description, category, tags, quantity, low_stock)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (p.name, p.sku, p.description, p.category, p.tags, p.quantity, p.low_stock),
        )
        product_id = cur.lastrowid
    except IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="SKU already exists")

    cur.execute(
        "INSERT INTO movements (product_id, action_type, delta, reason) VALUES (?, 'CREATE', ?, ?)",
        (product_id, p.quantity, "Product created"),
    )
    log_audit(cur, user, "CREATE", "products", "product", product_id, f"Created product '{p.name}' ({p.sku})")
    conn.commit()

    row = cur.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    conn.close()

    response.headers["Location"] = f"/v1/products/{product_id}"
    return dict(row)


@router.patch("/{product_id}")
def update_product(product_id: int, p: ProductUpdate, user: dict = Depends(require_permission("products", "write"))):
    conn = get_db()
    cur = conn.cursor()

    existing = cur.execute(
        "SELECT * FROM products WHERE id=? AND deleted=0", (product_id,)
    ).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found")

    fields = {}
    for key, value in p.model_dump(exclude_unset=True).items():
        if value is not None:
            fields[key] = value

    if "archived" in fields:
        fields["archived"] = 1 if fields["archived"] else 0

    if not fields:
        conn.close()
        return dict(existing)

    if "sku" in fields:
        cur.execute("SELECT id FROM products WHERE sku=? AND id!=?", (fields["sku"], product_id))
        if cur.fetchone():
            conn.close()
            raise HTTPException(status_code=409, detail="SKU already exists")

    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values())

    cur.execute(f"UPDATE products SET {set_clause}, updated_at=datetime('now') WHERE id=?", values + [product_id])

    if "archived" in fields and fields["archived"] != existing["archived"]:
        action = "archived" if fields["archived"] else "unarchived"
        cur.execute(
            "INSERT INTO movements (product_id, action_type, reason) VALUES (?, 'ARCHIVE', ?)",
            (product_id, f"Product {action}"),
        )
        log_audit(cur, user, "ARCHIVE", "products", "product", product_id, f"Product {action}")
    else:
        cur.execute(
            "INSERT INTO movements (product_id, action_type, reason) VALUES (?, 'UPDATE', ?)",
            (product_id, "Product updated"),
        )
        log_audit(cur, user, "UPDATE", "products", "product", product_id, f"Updated fields: {', '.join(fields)}")
    conn.commit()

    row = cur.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    conn.close()
    return dict(row)


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, user: dict = Depends(require_permission("products", "delete"))):
    conn = get_db()
    cur = conn.cursor()

    existing = cur.execute(
        "SELECT * FROM products WHERE id=? AND deleted=0", (product_id,)
    ).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found")

    cur.execute("UPDATE products SET deleted=1, updated_at=datetime('now') WHERE id=?", (product_id,))

    cur.execute(
        "INSERT INTO movements (product_id, action_type, reason) VALUES (?, 'DELETE', ?)",
        (product_id, "Product deleted"),
    )
    log_audit(cur, user, "DELETE", "products", "product", product_id, f"Deleted product '{existing['name']}' ({existing['sku']})")
    conn.commit()
    conn.close()
    return Response(status_code=204)


@router.post("/imports")
async def import_products(file: UploadFile = File(...), user: dict = Depends(require_permission("products", "write"))):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only CSV and XLSX files are supported")

    content = await file.read()
    conn = get_db()
    cur = conn.cursor()
    imported = 0
    errors = []

    def insert_row(data, row_num):
        nonlocal imported
        try:
            cur.execute(
                """
                INSERT OR IGNORE INTO products (name, sku, description, category, tags, quantity, low_stock)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(data.get("name", "") or "").strip(),
                    str(data.get("sku", "") or "").strip(),
                    str(data.get("description", "") or "").strip(),
                    str(data.get("category", "") or "").strip(),
                    str(data.get("tags", "") or "").strip(),
                    int(data.get("quantity", 0) or 0),
                    int(data.get("low_stock", 10) or 10),
                ),
            )
            if cur.lastrowid:
                imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    if ext == ".csv":
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        for i, row in enumerate(reader, start=2):
            insert_row(row, i)
    elif ext == ".xlsx":
        try:
            import openpyxl
        except ImportError:
            conn.close()
            raise HTTPException(status_code=500, detail="openpyxl is required for XLSX files")

        wb = openpyxl.load_workbook(io.BytesIO(content))
        ws = wb.active
        rows_iter = iter(ws.iter_rows(values_only=True))
        headers = [str(h).lower().strip() if h else "" for h in next(rows_iter, [])]
        for i, row in enumerate(rows_iter, start=2):
            insert_row(dict(zip(headers, row)), i)

    log_audit(cur, user, "BULK_IMPORT", "products", "file", None, f"Imported {imported} products from {file.filename}")
    conn.commit()
    conn.close()

    return {
        "imported": imported,
        "errors": errors[:10],
        "total_errors": len(errors),
    }
