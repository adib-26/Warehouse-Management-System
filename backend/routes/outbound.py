from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from database import get_db
from config import UPLOAD_DIR
from file_utils import read_upload, safe_filename, write_upload_file
from schemas import OutboundCreate
from security import require_permission, log_audit
from typing import Optional
from datetime import date, datetime
import csv
import io
import os
import uuid

router = APIRouter()

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


def _cell_text(value) -> str:
    """Normalize CSV and XLSX cells without turning blank cells into 'None'."""
    return "" if value is None else str(value).strip()


def _import_date(value, row_number: int) -> str:
    if value is None or _cell_text(value) == "":
        return date.today().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(_cell_text(value)).isoformat()
    except ValueError as exc:
        raise ValueError(
            f"Row {row_number}: dispatch_date must use YYYY-MM-DD"
        ) from exc


@router.post("", status_code=201)
def create_outbound(
    ob: OutboundCreate,
    response: Response,
    user: dict = Depends(require_permission("outbound", "write")),
):
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()

        product = cur.execute(
            """
            SELECT id, name, quantity
            FROM products
            WHERE id=? AND deleted=0 AND archived=0 AND is_forecast_test=0
            """,
            (ob.product_id,),
        ).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        customer = cur.execute(
            "SELECT id, name FROM customers WHERE id=? AND deleted=0",
            (ob.customer_id,),
        ).fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        if ob.warehouse_id is not None:
            warehouse = cur.execute(
                """
                SELECT id FROM warehouses
                WHERE id=? AND active=1 AND is_forecast_test=0
                """,
                (ob.warehouse_id,),
            ).fetchone()
            if not warehouse:
                raise HTTPException(status_code=404, detail="Warehouse not found or inactive")

        if ob.quantity <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be positive")
        if ob.quantity > product["quantity"]:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock (available: {product['quantity']})",
            )

        dispatch_date = (ob.dispatch_date or date.today()).isoformat()
        cur.execute(
            """
            UPDATE products
            SET quantity=quantity - ?, updated_at=datetime('now')
            WHERE id=? AND is_forecast_test=0 AND quantity >= ?
            """,
            (ob.quantity, ob.product_id, ob.quantity),
        )
        if cur.rowcount != 1:
            available = cur.execute(
                "SELECT quantity FROM products WHERE id=?", (ob.product_id,)
            ).fetchone()[0]
            raise HTTPException(
                status_code=409,
                detail=f"Insufficient stock (available: {available})",
            )

        cur.execute(
            """
            INSERT INTO outbound_shipments
                (product_id, customer_id, warehouse_id, quantity, so_ref, dispatch_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ob.product_id,
                ob.customer_id,
                ob.warehouse_id,
                ob.quantity,
                ob.so_ref,
                dispatch_date,
                ob.notes,
            ),
        )
        shipment_id = cur.lastrowid

        if ob.warehouse_id is not None:
            cur.execute(
                """
                INSERT INTO forecast_demand_history
                    (product_id, warehouse_id, demand_date, quantity_sold, source)
                VALUES (?, ?, ?, ?, 'WMS') AS incoming
                ON DUPLICATE KEY UPDATE
                    quantity_sold = quantity_sold + incoming.quantity_sold
                """,
                (ob.product_id, ob.warehouse_id, dispatch_date, ob.quantity),
            )

        new_qty = product["quantity"] - ob.quantity
        cur.execute(
            """
            INSERT INTO movements (product_id, action_type, delta, reason, source)
            VALUES (?, 'STOCK_OUT', ?, ?, 'outbound')
            """,
            (
                ob.product_id,
                -ob.quantity,
                f"Outbound to {customer['name']}: {ob.so_ref or 'no ref'}",
            ),
        )
        log_audit(
            cur,
            user,
            "STOCK_OUT",
            "outbound",
            "outbound_shipment",
            shipment_id,
            f"Dispatched {ob.quantity}x '{product['name']}' to {customer['name']} "
            f"({ob.so_ref or 'no ref'})",
        )
        conn.commit()
        row = cur.execute(
            "SELECT * FROM outbound_shipments WHERE id=?", (shipment_id,)
        ).fetchone()
        resource = dict(row)
        resource["product_name"] = product["name"]
        resource["customer_name"] = customer["name"]
        resource["quantity_after"] = new_qty
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    response.headers["Location"] = f"/v1/outbound-shipments/{shipment_id}"
    return resource


@router.get("")
def list_outbound(
    product_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("outbound", "read")),
):
    conn = get_db()
    cur = conn.cursor()

    where = "WHERE p.is_forecast_test=0"
    params = []

    if product_id:
        where += " AND ob.product_id = ?"
        params.append(product_id)

    if customer_id:
        where += " AND ob.customer_id = ?"
        params.append(customer_id)

    if warehouse_id:
        where += " AND ob.warehouse_id = ?"
        params.append(warehouse_id)

    total = cur.execute(
        f"SELECT COUNT(*) FROM outbound_shipments ob "
        f"JOIN products p ON p.id = ob.product_id {where}",
        params,
    ).fetchone()[0]

    rows = cur.execute(
        f"""
        SELECT ob.*, p.name AS product_name, p.sku AS product_sku,
               c.name AS customer_name,
               w.name AS warehouse_name, w.warehouse_code
        FROM outbound_shipments ob
        JOIN products p ON p.id = ob.product_id
        JOIN customers c ON c.id = ob.customer_id
        LEFT JOIN warehouses w ON w.id = ob.warehouse_id
        {where}
        ORDER BY ob.created_at DESC LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()

    result = []
    for r in rows:
        row_dict = dict(r)
        attachments = cur.execute(
            "SELECT id, filename, file_size, mime_type FROM attachments WHERE entity_type='outbound' AND entity_id=?",
            (row_dict["id"],),
        ).fetchall()
        row_dict["attachments"] = [dict(a) for a in attachments]
        result.append(row_dict)

    conn.close()
    return {
        "data": result,
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.get("/{shipment_id}/attachments")
def list_shipment_attachments(shipment_id: int, user: dict = Depends(require_permission("outbound", "read"))):
    conn = get_db()
    shipment = conn.execute(
        "SELECT ob.id FROM outbound_shipments ob "
        "JOIN products p ON p.id=ob.product_id "
        "WHERE ob.id=? AND p.is_forecast_test=0",
        (shipment_id,),
    ).fetchone()
    if not shipment:
        conn.close()
        raise HTTPException(status_code=404, detail="Shipment not found")

    rows = conn.execute(
        "SELECT id, filename, file_size, mime_type, created_at FROM attachments WHERE entity_type='outbound' AND entity_id=?",
        (shipment_id,),
    ).fetchall()
    conn.close()
    return {"data": [dict(r) for r in rows]}


@router.post("/{shipment_id}/attachments", status_code=201)
async def upload_shipment_attachment(
    shipment_id: int,
    response: Response,
    file: UploadFile = File(...),
    user: dict = Depends(require_permission("outbound", "write")),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await read_upload(file)
    original_name = safe_filename(file.filename)
    stored_name = uuid.uuid4().hex

    conn = get_db()
    cur = conn.cursor()
    try:
        shipment = cur.execute(
            "SELECT ob.id FROM outbound_shipments ob "
            "JOIN products p ON p.id=ob.product_id "
            "WHERE ob.id=? AND p.is_forecast_test=0",
            (shipment_id,),
        ).fetchone()
        if not shipment:
            raise HTTPException(status_code=404, detail="Shipment not found")

        try:
            file_path = write_upload_file(UPLOAD_DIR, stored_name, content)
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Could not store attachment") from exc

        try:
            cur.execute(
                """
                INSERT INTO attachments (entity_type, entity_id, filename, stored_name, file_size, mime_type)
                VALUES ('outbound', ?, ?, ?, ?, ?)
                """,
                (shipment_id, original_name, stored_name, len(content), file.content_type or "application/octet-stream"),
            )
            attachment_id = cur.lastrowid
            log_audit(cur, user, "UPLOAD", "outbound", "attachment", attachment_id, f"Uploaded '{original_name}' to outbound shipment #{shipment_id}")
            row = cur.execute(
                "SELECT id, filename, file_size, mime_type, created_at FROM attachments WHERE id=?",
                (attachment_id,),
            ).fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            file_path.unlink(missing_ok=True)
            raise
    finally:
        conn.close()

    response.headers["Location"] = f"/v1/attachments/{attachment_id}"
    return dict(row)


@router.post("/imports")
async def import_outbound(file: UploadFile = File(...), user: dict = Depends(require_permission("outbound", "write"))):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only CSV and XLSX files are supported")

    content = await read_upload(file)
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    cur = conn.cursor()
    imported = 0
    errors = []
    # Track quantities across rows so multiple rows for the same product
    # can't jointly dispatch more than is available.
    running_qty = {}

    def process_row(row_data, row_num):
        nonlocal imported
        try:
            normalized = {
                _cell_text(key).lower(): value
                for key, value in row_data.items()
                if key is not None
            }
            product_name = _cell_text(normalized.get("product_name"))
            product_sku = _cell_text(
                normalized.get("sku", normalized.get("product_sku"))
            )
            customer_name = _cell_text(normalized.get("customer_name"))
            quantity = int(normalized.get("quantity") or 0)
            so_ref = _cell_text(normalized.get("so_ref"))
            dispatch_date = _import_date(normalized.get("dispatch_date"), row_num)
            notes = _cell_text(normalized.get("notes"))
            warehouse_code = _cell_text(normalized.get("warehouse_code"))

            if quantity <= 0:
                errors.append(f"Row {row_num}: Quantity must be positive")
                return

            if product_sku:
                product = cur.execute(
                    """
                    SELECT id, name, quantity FROM products
                    WHERE sku=? AND deleted=0 AND archived=0 AND is_forecast_test=0
                    """,
                    (product_sku,),
                ).fetchone()
            elif product_name:
                product = cur.execute(
                    """
                    SELECT id, name, quantity FROM products
                    WHERE LOWER(name)=? AND deleted=0 AND archived=0 AND is_forecast_test=0
                    """,
                    (product_name.lower(),),
                ).fetchone()
            else:
                errors.append(f"Row {row_num}: Missing product_name or sku")
                return

            if not product:
                errors.append(f"Row {row_num}: Product '{product_name or product_sku}' not found")
                return

            customer = cur.execute(
                "SELECT id, name FROM customers WHERE LOWER(name)=? AND deleted=0",
                (customer_name.lower(),),
            ).fetchone()

            if not customer:
                errors.append(f"Row {row_num}: Customer '{customer_name}' not found")
                return

            warehouse_id = None
            if warehouse_code:
                warehouse = cur.execute(
                    """
                    SELECT id FROM warehouses
                    WHERE warehouse_code=? AND active=1 AND is_forecast_test=0
                    """,
                    (warehouse_code,),
                ).fetchone()
                if not warehouse:
                    errors.append(f"Row {row_num}: Warehouse '{warehouse_code}' not found or inactive")
                    return
                warehouse_id = warehouse["id"]

            available = running_qty.get(product["id"], product["quantity"])
            if quantity > available:
                errors.append(
                    f"Row {row_num}: Insufficient stock for '{product['name']}' (available: {available})"
                )
                return

            savepoint = f"outbound_import_row_{row_num}"
            cur.execute(f"SAVEPOINT {savepoint}")
            try:
                cur.execute(
                    """
                    INSERT INTO outbound_shipments
                        (product_id, customer_id, warehouse_id, quantity, so_ref, dispatch_date, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (product["id"], customer["id"], warehouse_id, quantity, so_ref, dispatch_date, notes),
                )

                if warehouse_id is not None:
                    cur.execute(
                        """
                        INSERT INTO forecast_demand_history
                            (product_id, warehouse_id, demand_date, quantity_sold, source)
                        VALUES (?, ?, ?, ?, 'WMS') AS incoming
                        ON DUPLICATE KEY UPDATE quantity_sold = quantity_sold + incoming.quantity_sold
                        """,
                        (product["id"], warehouse_id, dispatch_date, quantity),
                    )

                cur.execute(
                    """
                    UPDATE products
                    SET quantity=quantity - ?, updated_at=datetime('now')
                    WHERE id=? AND is_forecast_test=0 AND quantity >= ?
                    """,
                    (quantity, product["id"], quantity),
                )
                if cur.rowcount != 1:
                    raise ValueError(
                        f"Insufficient stock for '{product['name']}' due to a concurrent update"
                    )

                cur.execute(
                    "INSERT INTO movements (product_id, action_type, delta, reason, source) VALUES (?, 'STOCK_OUT', ?, ?, 'outbound')",
                    (product["id"], -quantity, f"Bulk outbound: {so_ref or 'no ref'}"),
                )
            except Exception:
                cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                cur.execute(f"RELEASE SAVEPOINT {savepoint}")
                raise
            cur.execute(f"RELEASE SAVEPOINT {savepoint}")

            running_qty[product["id"]] = available - quantity

            imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    try:
        if ext == ".csv":
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
            for i, row in enumerate(reader, start=2):
                process_row(row, i)
        elif ext == ".xlsx":
            try:
                import openpyxl
            except ImportError as exc:
                raise HTTPException(
                    status_code=500, detail="openpyxl is required for XLSX files"
                ) from exc

            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            try:
                ws = wb.active
                rows_iter = iter(ws.iter_rows(values_only=True))
                headers = [_cell_text(header).lower() for header in next(rows_iter, [])]
                for i, row in enumerate(rows_iter, start=2):
                    process_row(dict(zip(headers, row)), i)
            finally:
                wb.close()

        log_audit(
            cur,
            user,
            "BULK_IMPORT",
            "outbound",
            "file",
            None,
            f"Imported {imported} outbound records from {file.filename}",
        )
        conn.commit()
        return {
            "imported": imported,
            "errors": errors[:20],
            "total_errors": len(errors),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
