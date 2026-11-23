from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlite3 import IntegrityError
from database import get_db
from file_utils import read_upload
from schemas import ProductCreate, ProductUpdate
from security import require_permission, log_audit
from typing import Optional
import csv
import io
import os
from datetime import date

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
    limit: int = Query(default=50, ge=1, le=500),
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


@router.get("/export")
def export_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    low_stock: Optional[bool] = None,
    archived: Optional[bool] = None,
    user: dict = Depends(require_permission("products", "read")),
):
    where = "WHERE deleted=0"
    params = []
    where += " AND archived=?"
    params.append(1 if archived is True else 0)

    if q:
        where += " AND (LOWER(name) LIKE ? OR LOWER(sku) LIKE ? OR LOWER(description) LIKE ?)"
        like = f"%{q.lower()}%"
        params.extend([like, like, like])
    if category:
        where += " AND LOWER(category)=?"
        params.append(category.lower())
    if tag:
        where += " AND LOWER(tags) LIKE ?"
        params.append(f"%{tag.lower()}%")
    if low_stock:
        where += " AND quantity <= low_stock"

    query = (
        f"SELECT sku, name, category, tags, description, quantity, low_stock, archived, created_at, updated_at "
        f"FROM products {where} ORDER BY name COLLATE NOCASE, sku COLLATE NOCASE"
    )

    def stream_csv():
        conn = get_db()
        try:
            cursor = conn.execute(query, params)
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(["SKU", "Name", "Category", "Tags", "Description", "Quantity", "Low stock threshold", "Archived", "Created at", "Updated at"])
            yield "\ufeff" + output.getvalue()

            while rows := cursor.fetchmany(500):
                output.seek(0)
                output.truncate(0)
                for row in rows:
                    values = list(row)
                    for index, value in enumerate(values):
                        if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
                            values[index] = f"'{value}"
                    writer.writerow(values)
                yield output.getvalue()
        finally:
            conn.close()

    return StreamingResponse(
        stream_csv(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="products-{date.today().isoformat()}.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/facets")
def get_product_facets(user: dict = Depends(require_permission("products", "read"))):
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT category, tags FROM products WHERE deleted=0 ORDER BY category COLLATE NOCASE"
    ).fetchall()
    conn.close()

    categories = sorted({row["category"] for row in rows if row["category"]}, key=str.casefold)
    tags = sorted(
        {
            tag.strip()
            for row in rows
            for tag in (row["tags"] or "").split(",")
            if tag.strip()
        },
        key=str.casefold,
    )
    return {"categories": categories, "tags": tags}


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
        "INSERT INTO movements (product_id, action_type, delta, reason, source) VALUES (?, 'CREATE', ?, ?, 'catalog')",
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
    conn.execute("BEGIN IMMEDIATE")
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

    quantity_delta = fields.get("quantity", existing["quantity"]) - existing["quantity"]
    if quantity_delta:
        action_type = "STOCK_IN" if quantity_delta > 0 else "STOCK_OUT"
        cur.execute(
            "INSERT INTO movements (product_id, action_type, delta, reason, source) VALUES (?, ?, ?, ?, 'catalog')",
            (product_id, action_type, quantity_delta, "Quantity changed from product editor"),
        )
        log_audit(
            cur,
            user,
            "STOCK_ADJUST",
            "stock",
            "product",
            product_id,
            f"Adjusted '{existing['name']}' by {quantity_delta:+d} from the product editor",
        )

    archive_changed = "archived" in fields and fields["archived"] != existing["archived"]
    if archive_changed:
        action = "archived" if fields["archived"] else "unarchived"
        cur.execute(
            "INSERT INTO movements (product_id, action_type, reason, source) VALUES (?, 'ARCHIVE', ?, 'catalog')",
            (product_id, f"Product {action}"),
        )
        log_audit(cur, user, "ARCHIVE", "products", "product", product_id, f"Product {action}")
    elif any(key != "quantity" for key in fields):
        cur.execute(
            "INSERT INTO movements (product_id, action_type, reason, source) VALUES (?, 'UPDATE', ?, 'catalog')",
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
        "INSERT INTO movements (product_id, action_type, reason, source) VALUES (?, 'DELETE', ?, 'catalog')",
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

    content = await read_upload(file)
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    cur = conn.cursor()
    imported = 0
    errors = []

    def insert_row(data, row_num):
        nonlocal imported
        try:
            name = str(data.get("name", "") or "").strip()
            sku = str(data.get("sku", "") or "").strip()
            if not name or not sku:
                errors.append(f"Row {row_num}: Name and SKU are required")
                return

            quantity = int(data.get("quantity", 0) or 0)
            low_stock = int(data.get("low_stock", 10) or 10)
            if quantity < 0 or low_stock < 0:
                errors.append(f"Row {row_num}: Quantity and low_stock must be zero or greater")
                return

            cur.execute(
                """
                INSERT OR IGNORE INTO products (name, sku, description, category, tags, quantity, low_stock)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    sku,
                    str(data.get("description", "") or "").strip(),
                    str(data.get("category", "") or "").strip(),
                    str(data.get("tags", "") or "").strip(),
                    quantity,
                    low_stock,
                ),
            )
            if cur.rowcount == 1:
                product_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO movements (product_id, action_type, delta, reason, source) "
                    "VALUES (?, 'CREATE', ?, 'Product imported', 'import')",
                    (product_id, quantity),
                )
                imported += 1
            else:
                errors.append(f"Row {row_num}: SKU '{sku}' already exists")
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

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = iter(ws.iter_rows(values_only=True))
        headers = [str(h).lower().strip() if h else "" for h in next(rows_iter, [])]
        for i, row in enumerate(rows_iter, start=2):
            insert_row(dict(zip(headers, row)), i)
        wb.close()

    log_audit(cur, user, "BULK_IMPORT", "products", "file", None, f"Imported {imported} products from {file.filename}")
    conn.commit()
    conn.close()

    return {
        "imported": imported,
        "errors": errors[:10],
        "total_errors": len(errors),
    }
