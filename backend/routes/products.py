from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from fastapi.responses import StreamingResponse
from database import IntegrityError, get_db, is_transaction_failure, savepoint
from file_utils import (
    IMPORT_INTERRUPTED_DETAIL,
    import_row_error,
    iter_spreadsheet_rows,
    read_upload,
    safe_filename,
)
from schemas import TEXT_MAX_LENGTH, ProductCreate, ProductReorderSettingsRequest, ProductUpdate
from security import require_permission, log_audit
from typing import Optional
import csv
import io
import os
from datetime import date
from decimal import Decimal
from quantity import as_quantity

router = APIRouter()
compat_reorder_router = APIRouter()

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
# GET /v1/products/export writes readable headers. Accept them on import so an
# export can be edited and uploaded again.
IMPORT_HEADER_ALIASES = {
    "low stock threshold": "low_stock",
    "low_stock_threshold": "low_stock",
}
IMPORT_TEXT_LIMITS = {
    "name": 200,
    "sku": 100,
    "category": 128,
    "tags": 255,
    "description": TEXT_MAX_LENGTH,
}


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

    # M5 catalog records are a forecasting sandbox, never normal inventory.
    where = "WHERE deleted=0 AND is_forecast_test=0"
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
    # Timestamps have one-second precision and imports write many rows per
    # second, so add the id as a tiebreaker to keep pages stable.
    order = "ORDER BY quantity ASC, id ASC" if low_stock else "ORDER BY updated_at DESC, id DESC"
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
    where = "WHERE deleted=0 AND is_forecast_test=0"
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
        f"FROM products {where} ORDER BY name, sku"
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
        "SELECT DISTINCT category, tags FROM products "
        "WHERE deleted=0 AND is_forecast_test=0 ORDER BY category"
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
        "SELECT * FROM products WHERE id=? AND deleted=0 AND is_forecast_test=0",
        (product_id,),
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
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO products
                    (name, sku, description, category, tags, quantity, low_stock, is_forecast_test)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (p.name, p.sku, p.description, p.category, p.tags, p.quantity, p.low_stock),
            )
            product_id = cur.lastrowid
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="SKU already exists") from exc

        cur.execute(
            "INSERT INTO movements (product_id, action_type, delta, reason, source) VALUES (?, 'CREATE', ?, ?, 'catalog')",
            (product_id, p.quantity, "Product created"),
        )
        log_audit(cur, user, "CREATE", "products", "product", product_id, f"Created product '{p.name}' ({p.sku})")
        conn.commit()

        row = cur.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    response.headers["Location"] = f"/v1/products/{product_id}"
    return dict(row)


@router.patch("/{product_id}")
def update_product(product_id: int, p: ProductUpdate, user: dict = Depends(require_permission("products", "write"))):
    conn = get_db()
    try:
        return _update_product(conn, product_id, p, user)
    except Exception:
        # Release the product row lock immediately on any failure.
        conn.rollback()
        raise
    finally:
        conn.close()


def _update_product(conn, product_id: int, p: ProductUpdate, user: dict):
    conn.execute("BEGIN IMMEDIATE")
    cur = conn.cursor()

    existing = cur.execute(
        "SELECT * FROM products WHERE id=? AND deleted=0 AND is_forecast_test=0 FOR UPDATE",
        (product_id,),
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")

    fields = {}
    for key, value in p.model_dump(exclude_unset=True).items():
        if value is not None:
            fields[key] = value

    if "archived" in fields:
        fields["archived"] = 1 if fields["archived"] else 0

    if "quantity" in fields and existing["batch_tracking_enabled_at"]:
        raise HTTPException(
            status_code=409,
            detail="Batch-tracked stock is managed through inventory batches.",
        )

    if (
        fields.get("archived") == 1
        and not existing["archived"]
        and existing["batch_tracking_enabled_at"]
        and Decimal(str(existing["quantity"])) > 0
    ):
        raise HTTPException(
            status_code=409,
            detail="A product with batch-tracked stock cannot be archived until its stock is cleared.",
        )

    if not fields:
        return dict(existing)

    if "sku" in fields:
        cur.execute("SELECT id FROM products WHERE sku=? AND id!=?", (fields["sku"], product_id))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="SKU already exists")

    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values())

    try:
        cur.execute(
            f"UPDATE products SET {set_clause}, updated_at=datetime('now') "
            "WHERE id=? AND is_forecast_test=0",
            values + [product_id],
        )
    except IntegrityError as exc:
        # Another request claimed the SKU after the check above.
        raise HTTPException(status_code=409, detail="SKU already exists") from exc

    quantity_delta = (
        Decimal(str(fields.get("quantity", existing["quantity"])))
        - Decimal(str(existing["quantity"]))
    )
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
            f"Adjusted '{existing['name']}' by {quantity_delta:+.2f} from the product editor",
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
    return dict(row)


@compat_reorder_router.put("/{product_id}/reorder-settings")
@router.put("/{product_id}/reorder-settings")
def update_product_reorder_settings(
    product_id: int,
    settings: ProductReorderSettingsRequest,
    user: dict = Depends(require_permission("products", "write")),
):
    """Create or update one product's reorder policy at a warehouse."""
    conn = get_db()
    try:
        product = conn.execute(
            "SELECT id, sku, name FROM products "
            "WHERE id=? AND deleted=0 AND archived=0 AND is_forecast_test=0",
            (product_id,),
        ).fetchone()
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        warehouse = conn.execute(
            "SELECT id, warehouse_code, name FROM warehouses "
            "WHERE id=? AND active=1 AND is_forecast_test=0",
            (settings.warehouse_id,),
        ).fetchone()
        if warehouse is None:
            raise HTTPException(status_code=404, detail="Active warehouse not found")

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO product_reorder_settings
                (product_id, warehouse_id, lead_time_days, safety_stock,
                 review_period_days)
            VALUES (?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                lead_time_days=VALUES(lead_time_days),
                safety_stock=VALUES(safety_stock),
                review_period_days=VALUES(review_period_days)
            """,
            (
                product_id,
                settings.warehouse_id,
                settings.lead_time_days,
                settings.safety_stock,
                settings.review_period_days,
            ),
        )
        log_audit(
            cur,
            user,
            "UPDATE",
            "products",
            "product_reorder_settings",
            product_id,
            (
                f"Set reorder settings for {product['sku']} at "
                f"{warehouse['warehouse_code']}: lead time "
                f"{settings.lead_time_days} days, safety stock "
                f"{settings.safety_stock:g}, review period "
                f"{settings.review_period_days} days."
            ),
        )
        conn.commit()
        saved = conn.execute(
            """
            SELECT s.product_id, p.sku, p.name AS product_name,
                   s.warehouse_id, w.warehouse_code, w.name AS warehouse_name,
                   s.lead_time_days, s.safety_stock, s.review_period_days,
                   s.updated_at
            FROM product_reorder_settings s
            JOIN products p ON p.id=s.product_id
            JOIN warehouses w ON w.id=s.warehouse_id
            WHERE s.product_id=? AND s.warehouse_id=?
            """,
            (product_id, settings.warehouse_id),
        ).fetchone()
        return dict(saved)
    finally:
        conn.close()


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, user: dict = Depends(require_permission("products", "delete"))):
    conn = get_db()
    try:
        conn.execute("START TRANSACTION")
        cur = conn.cursor()

        existing = cur.execute(
            "SELECT * FROM products WHERE id=? AND deleted=0 AND is_forecast_test=0 FOR UPDATE",
            (product_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Product not found")

        tracked_batches = cur.execute(
            "SELECT COUNT(*) AS n FROM inventory_batches WHERE product_id=?",
            (product_id,),
        ).fetchone()["n"]
        if existing["batch_tracking_enabled_at"] or int(tracked_batches) > 0:
            raise HTTPException(
                status_code=409,
                detail="Products with batch history cannot be deleted; archive the product after clearing its stock.",
            )

        cur.execute(
            "UPDATE products SET deleted=1, updated_at=datetime('now') "
            "WHERE id=? AND is_forecast_test=0",
            (product_id,),
        )

        cur.execute(
            "INSERT INTO movements (product_id, action_type, reason, source) VALUES (?, 'DELETE', ?, 'catalog')",
            (product_id, "Product deleted"),
        )
        log_audit(cur, user, "DELETE", "products", "product", product_id, f"Deleted product '{existing['name']}' ({existing['sku']})")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return Response(status_code=204)


def _cell_text(value) -> str:
    return "" if value is None else str(value).strip()


def _default_if_blank(value, default):
    return default if _cell_text(value) == "" else value


@router.post("/imports")
def import_products(file: UploadFile = File(...), user: dict = Depends(require_permission("products", "write"))):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only CSV and XLSX files are supported")

    content = read_upload(file)
    conn = get_db()
    imported = 0
    errors = []

    def insert_row(cur, data, row_num):
        nonlocal imported
        data = {IMPORT_HEADER_ALIASES.get(key, key): value for key, value in data.items()}
        text = {field: _cell_text(data.get(field)) for field in IMPORT_TEXT_LIMITS}
        if not text["name"] or not text["sku"]:
            errors.append(f"Row {row_num}: Name and SKU are required")
            return
        for field, limit in IMPORT_TEXT_LIMITS.items():
            if len(text[field]) > limit:
                errors.append(f"Row {row_num}: {field} is longer than {limit} characters")
                return

        quantity = as_quantity(_default_if_blank(data.get("quantity"), 0))
        low_stock = as_quantity(_default_if_blank(data.get("low_stock"), 10))

        try:
            # A plain INSERT inside a savepoint: a failed row leaves no partial
            # product behind, and over-long values are rejected, not truncated.
            with savepoint(cur, f"product_import_row_{row_num}"):
                cur.execute(
                    """
                    INSERT INTO products
                        (name, sku, description, category, tags, quantity, low_stock, is_forecast_test)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        text["name"],
                        text["sku"],
                        text["description"],
                        text["category"],
                        text["tags"],
                        quantity,
                        low_stock,
                    ),
                )
                cur.execute(
                    "INSERT INTO movements (product_id, action_type, delta, reason, source) "
                    "VALUES (?, 'CREATE', ?, 'Product imported', 'import')",
                    (cur.lastrowid, quantity),
                )
        except IntegrityError as exc:
            if exc.args and exc.args[0] == 1062:
                errors.append(f"Row {row_num}: SKU '{text['sku']}' already exists")
                return
            raise
        imported += 1

    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        for row_num, data in iter_spreadsheet_rows(content, ext):
            try:
                insert_row(cur, data, row_num)
            except Exception as exc:
                if is_transaction_failure(exc):
                    raise
                errors.append(f"Row {row_num}: {import_row_error(exc)}")

        log_audit(cur, user, "BULK_IMPORT", "products", "file", None, f"Imported {imported} products from {safe_filename(file.filename or '')}")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if is_transaction_failure(exc):
            raise HTTPException(status_code=409, detail=IMPORT_INTERRUPTED_DETAIL) from exc
        raise
    finally:
        conn.close()

    return {
        "imported": imported,
        "errors": errors[:10],
        "total_errors": len(errors),
    }
