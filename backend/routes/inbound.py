from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from database import get_db, is_transaction_failure, savepoint
from config import UPLOAD_DIR
from dates import business_today, latest_local_today
from file_utils import (
    IMPORT_INTERRUPTED_DETAIL,
    import_row_error,
    iter_spreadsheet_rows,
    read_upload,
    safe_filename,
    write_upload_file,
)
from import_lookups import find_import_party, lock_import_product
from schemas import InboundCreate
from security import require_permission, log_audit
from typing import Optional
from datetime import date, datetime
from quantity import as_quantity, quantity_for_json
import os
import uuid

router = APIRouter()

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


def _cell_text(value) -> str:
    """Normalize CSV/XLSX cells without turning blanks into the string 'None'."""
    return "" if value is None else str(value).strip()


def _import_date(value) -> str:
    if value is None or _cell_text(value) == "":
        return business_today().isoformat()
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        try:
            parsed = date.fromisoformat(_cell_text(value))
        except ValueError as exc:
            raise ValueError("received_date must use YYYY-MM-DD") from exc
    if parsed > latest_local_today():
        raise ValueError("received_date cannot be in the future")
    return parsed.isoformat()


@router.post("", status_code=201)
def create_inbound(
    ib: InboundCreate,
    response: Response,
    user: dict = Depends(require_permission("inbound", "write")),
):
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()

        product = cur.execute(
            "SELECT id, name, quantity, batch_tracking_enabled_at FROM products "
            "WHERE id=? AND deleted=0 AND archived=0 AND is_forecast_test=0 FOR UPDATE",
            (ib.product_id,),
        ).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        if product["batch_tracking_enabled_at"]:
            raise HTTPException(
                status_code=409,
                detail="Receive stock for this product with POST /api/batches so its lot is recorded.",
            )

        supplier = cur.execute(
            "SELECT id, name FROM suppliers WHERE id=? AND deleted=0",
            (ib.supplier_id,),
        ).fetchone()
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")

        if ib.received_date and ib.received_date > latest_local_today():
            raise HTTPException(
                status_code=422,
                detail="received_date cannot be in the future",
            )
        received_date = (ib.received_date or business_today()).isoformat()
        cur.execute(
            """
            INSERT INTO inbound_shipments (product_id, supplier_id, quantity, invoice_ref, received_date, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ib.product_id,
                ib.supplier_id,
                ib.quantity,
                ib.invoice_ref,
                received_date,
                ib.notes,
            ),
        )
        shipment_id = cur.lastrowid

        cur.execute(
            "UPDATE products SET quantity=quantity + ?, updated_at=datetime('now') "
            "WHERE id=? AND is_forecast_test=0",
            (ib.quantity, ib.product_id),
        )
        new_qty = cur.execute(
            "SELECT quantity FROM products WHERE id=? AND is_forecast_test=0",
            (ib.product_id,),
        ).fetchone()["quantity"]

        cur.execute(
            "INSERT INTO movements (product_id, action_type, delta, reason, source) "
            "VALUES (?, 'STOCK_IN', ?, ?, 'inbound')",
            (
                ib.product_id,
                ib.quantity,
                f"Inbound from {supplier['name']}: {ib.invoice_ref or 'no ref'}",
            ),
        )
        log_audit(
            cur,
            user,
            "STOCK_IN",
            "inbound",
            "inbound_shipment",
            shipment_id,
            f"Received {ib.quantity}x '{product['name']}' from {supplier['name']} "
            f"({ib.invoice_ref or 'no ref'})",
        )
        conn.commit()
        row = cur.execute(
            "SELECT * FROM inbound_shipments WHERE id=?", (shipment_id,)
        ).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    resource = dict(row)
    resource["product_name"] = product["name"]
    resource["supplier_name"] = supplier["name"]
    resource["quantity_after"] = quantity_for_json(new_qty)

    response.headers["Location"] = f"/v1/inbound-shipments/{shipment_id}"
    return resource


@router.get("")
def list_inbound(
    product_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("inbound", "read")),
):
    conn = get_db()
    cur = conn.cursor()

    where = "WHERE p.is_forecast_test=0"
    params = []

    if product_id:
        where += " AND ib.product_id = ?"
        params.append(product_id)

    if supplier_id:
        where += " AND ib.supplier_id = ?"
        params.append(supplier_id)

    total = cur.execute(
        f"SELECT COUNT(*) FROM inbound_shipments ib "
        f"JOIN products p ON p.id = ib.product_id {where}",
        params,
    ).fetchone()[0]

    rows = cur.execute(
        f"""
        SELECT ib.*, p.name AS product_name, p.sku AS product_sku,
               s.name AS supplier_name
        FROM inbound_shipments ib
        JOIN products p ON p.id = ib.product_id
        JOIN suppliers s ON s.id = ib.supplier_id
        {where}
        ORDER BY ib.created_at DESC, ib.id DESC LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()

    result = []
    for r in rows:
        row_dict = dict(r)
        attachments = cur.execute(
            "SELECT id, filename, file_size, mime_type FROM attachments WHERE entity_type='inbound' AND entity_id=?",
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
def list_shipment_attachments(shipment_id: int, user: dict = Depends(require_permission("inbound", "read"))):
    conn = get_db()
    shipment = conn.execute(
        "SELECT ib.id FROM inbound_shipments ib "
        "JOIN products p ON p.id=ib.product_id "
        "WHERE ib.id=? AND p.is_forecast_test=0",
        (shipment_id,),
    ).fetchone()
    if not shipment:
        conn.close()
        raise HTTPException(status_code=404, detail="Shipment not found")

    rows = conn.execute(
        "SELECT id, filename, file_size, mime_type, created_at FROM attachments WHERE entity_type='inbound' AND entity_id=?",
        (shipment_id,),
    ).fetchall()
    conn.close()
    return {"data": [dict(r) for r in rows]}


@router.post("/{shipment_id}/attachments", status_code=201)
def upload_shipment_attachment(
    shipment_id: int,
    response: Response,
    file: UploadFile = File(...),
    user: dict = Depends(require_permission("inbound", "write")),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content = read_upload(file)
    original_name = safe_filename(file.filename)
    stored_name = uuid.uuid4().hex

    conn = get_db()
    cur = conn.cursor()
    try:
        shipment = cur.execute(
            "SELECT ib.id FROM inbound_shipments ib "
            "JOIN products p ON p.id=ib.product_id "
            "WHERE ib.id=? AND p.is_forecast_test=0",
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
                VALUES ('inbound', ?, ?, ?, ?, ?)
                """,
                (shipment_id, original_name, stored_name, len(content), file.content_type or "application/octet-stream"),
            )
            attachment_id = cur.lastrowid
            log_audit(cur, user, "UPLOAD", "inbound", "attachment", attachment_id, f"Uploaded '{original_name}' to inbound shipment #{shipment_id}")
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
def import_inbound(file: UploadFile = File(...), user: dict = Depends(require_permission("inbound", "write"))):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only CSV and XLSX files are supported")

    content = read_upload(file)
    conn = get_db()
    imported = 0
    errors = []

    def process_row(cur, normalized, row_num):
        nonlocal imported
        product_name = _cell_text(normalized.get("product_name"))
        product_sku = (
            _cell_text(normalized.get("sku"))
            or _cell_text(normalized.get("product_sku"))
        )
        supplier_name = _cell_text(normalized.get("supplier_name"))
        quantity = as_quantity(normalized.get("quantity"), allow_zero=False)
        invoice_ref = _cell_text(normalized.get("invoice_ref"))
        received_date = _import_date(normalized.get("received_date"))
        notes = _cell_text(normalized.get("notes"))

        if not product_sku and not product_name:
            errors.append(f"Row {row_num}: Missing product_name or sku")
            return
        if len(invoice_ref) > 128:
            errors.append(f"Row {row_num}: invoice_ref is longer than 128 characters")
            return

        product = lock_import_product(cur, product_sku, product_name)
        if not product:
            errors.append(f"Row {row_num}: Product '{product_name or product_sku}' not found")
            return

        if product["batch_tracking_enabled_at"]:
            errors.append(
                f"Row {row_num}: Use the batch API to receive stock for '{product['name']}'"
            )
            return

        if not supplier_name:
            errors.append(f"Row {row_num}: supplier_name is required")
            return
        supplier = find_import_party(cur, "suppliers", supplier_name)
        if not supplier:
            errors.append(f"Row {row_num}: Supplier '{supplier_name}' not found")
            return

        with savepoint(cur, f"inbound_import_row_{row_num}"):
            cur.execute(
                """
                INSERT INTO inbound_shipments
                    (product_id, supplier_id, quantity, invoice_ref, received_date, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    product["id"],
                    supplier["id"],
                    quantity,
                    invoice_ref,
                    received_date,
                    notes,
                ),
            )
            cur.execute(
                "UPDATE products SET quantity=quantity + ?, updated_at=datetime('now') "
                "WHERE id=? AND is_forecast_test=0",
                (quantity, product["id"]),
            )
            cur.execute(
                "INSERT INTO movements (product_id, action_type, delta, reason, source) "
                "VALUES (?, 'STOCK_IN', ?, ?, 'inbound')",
                (product["id"], quantity, f"Bulk inbound: {invoice_ref or 'no ref'}"),
            )

        imported += 1

    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        for row_num, normalized in iter_spreadsheet_rows(content, ext):
            try:
                process_row(cur, normalized, row_num)
            except Exception as exc:
                # Deadlocks and lost connections discard the whole transaction;
                # abort instead of committing whatever rows follow.
                if is_transaction_failure(exc):
                    raise
                errors.append(f"Row {row_num}: {import_row_error(exc)}")

        log_audit(
            cur,
            user,
            "BULK_IMPORT",
            "inbound",
            "file",
            None,
            f"Imported {imported} inbound records from {safe_filename(file.filename or '')}",
        )
        conn.commit()
        return {
            "imported": imported,
            "errors": errors[:20],
            "total_errors": len(errors),
        }
    except Exception as exc:
        conn.rollback()
        if is_transaction_failure(exc):
            raise HTTPException(status_code=409, detail=IMPORT_INTERRUPTED_DETAIL) from exc
        raise
    finally:
        conn.close()
