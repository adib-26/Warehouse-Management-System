from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from database import get_db
from config import UPLOAD_DIR
from file_utils import read_upload, safe_filename, write_upload_file
from schemas import InboundCreate
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
    """Normalize CSV/XLSX cells without turning blanks into the string 'None'."""
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
            f"Row {row_number}: received_date must use YYYY-MM-DD"
        ) from exc


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
            "SELECT id, name, quantity FROM products "
            "WHERE id=? AND deleted=0 AND archived=0 AND is_forecast_test=0",
            (ib.product_id,),
        ).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        supplier = cur.execute(
            "SELECT id, name FROM suppliers WHERE id=? AND deleted=0",
            (ib.supplier_id,),
        ).fetchone()
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")

        received_date = (ib.received_date or date.today()).isoformat()
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
    resource["quantity_after"] = new_qty

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
        ORDER BY ib.created_at DESC LIMIT ? OFFSET ?
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
async def upload_shipment_attachment(
    shipment_id: int,
    response: Response,
    file: UploadFile = File(...),
    user: dict = Depends(require_permission("inbound", "write")),
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
async def import_inbound(file: UploadFile = File(...), user: dict = Depends(require_permission("inbound", "write"))):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only CSV and XLSX files are supported")

    content = await read_upload(file)
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    cur = conn.cursor()
    imported = 0
    errors = []

    def process_row(row_data, row_num):
        nonlocal imported
        try:
            normalized = {
                _cell_text(key).lower(): value
                for key, value in row_data.items()
                if key is not None
            }
            product_name = _cell_text(normalized.get("product_name"))
            product_sku = (
                _cell_text(normalized.get("sku"))
                or _cell_text(normalized.get("product_sku"))
            )
            supplier_name = _cell_text(normalized.get("supplier_name"))
            quantity = int(normalized.get("quantity") or 0)
            invoice_ref = _cell_text(normalized.get("invoice_ref"))
            received_date = _import_date(normalized.get("received_date"), row_num)
            notes = _cell_text(normalized.get("notes"))

            if quantity <= 0:
                errors.append(f"Row {row_num}: Quantity must be positive")
                return

            if product_sku:
                product = cur.execute(
                    "SELECT id, name, quantity FROM products "
                    "WHERE sku=? AND deleted=0 AND archived=0 AND is_forecast_test=0",
                    (product_sku,),
                ).fetchone()
            elif product_name:
                product = cur.execute(
                    "SELECT id, name, quantity FROM products "
                    "WHERE LOWER(name)=? AND deleted=0 AND archived=0 AND is_forecast_test=0",
                    (product_name.lower(),),
                ).fetchone()
            else:
                errors.append(f"Row {row_num}: Missing product_name or sku")
                return

            if not product:
                errors.append(f"Row {row_num}: Product '{product_name or product_sku}' not found")
                return

            supplier = cur.execute(
                "SELECT id, name FROM suppliers WHERE LOWER(name)=? AND deleted=0",
                (supplier_name.lower(),),
            ).fetchone()

            if not supplier:
                errors.append(f"Row {row_num}: Supplier '{supplier_name}' not found")
                return

            savepoint = f"inbound_import_row_{row_num}"
            cur.execute(f"SAVEPOINT {savepoint}")
            try:
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
            except Exception:
                cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                cur.execute(f"RELEASE SAVEPOINT {savepoint}")
                raise
            cur.execute(f"RELEASE SAVEPOINT {savepoint}")

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

            wb = openpyxl.load_workbook(
                io.BytesIO(content), read_only=True, data_only=True
            )
            try:
                ws = wb.active
                rows_iter = iter(ws.iter_rows(values_only=True))
                headers = [
                    _cell_text(header).lower()
                    for header in next(rows_iter, [])
                ]
                for i, row in enumerate(rows_iter, start=2):
                    process_row(dict(zip(headers, row)), i)
            finally:
                wb.close()

        log_audit(
            cur,
            user,
            "BULK_IMPORT",
            "inbound",
            "file",
            None,
            f"Imported {imported} inbound records from {file.filename}",
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
