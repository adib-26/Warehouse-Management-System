from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from database import get_db
from config import UPLOAD_DIR
from file_utils import read_upload, safe_filename, write_upload_file
from schemas import InboundCreate
from security import require_permission, log_audit
from typing import Optional
from datetime import date
import csv
import io
import os
import uuid

router = APIRouter()

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
@router.post("", status_code=201)
def create_inbound(
    ib: InboundCreate,
    response: Response,
    user: dict = Depends(require_permission("inbound", "write")),
):
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    cur = conn.cursor()

    product = cur.execute(
        "SELECT id, name, quantity FROM products WHERE id=? AND deleted=0 AND archived=0",
        (ib.product_id,),
    ).fetchone()
    if not product:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found")

    supplier = cur.execute(
        "SELECT id, name FROM suppliers WHERE id=? AND deleted=0",
        (ib.supplier_id,),
    ).fetchone()
    if not supplier:
        conn.close()
        raise HTTPException(status_code=404, detail="Supplier not found")

    if ib.quantity <= 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Quantity must be positive")

    received_date = ib.received_date or date.today().isoformat()

    cur.execute(
        """
        INSERT INTO inbound_shipments (product_id, supplier_id, quantity, invoice_ref, received_date, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ib.product_id, ib.supplier_id, ib.quantity, ib.invoice_ref, received_date, ib.notes),
    )
    shipment_id = cur.lastrowid

    new_qty = product["quantity"] + ib.quantity
    cur.execute(
        "UPDATE products SET quantity=quantity + ?, updated_at=datetime('now') WHERE id=?",
        (ib.quantity, ib.product_id),
    )

    cur.execute(
        "INSERT INTO movements (product_id, action_type, delta, reason, source) VALUES (?, 'STOCK_IN', ?, ?, 'inbound')",
        (ib.product_id, ib.quantity, f"Inbound from {supplier['name']}: {ib.invoice_ref or 'no ref'}"),
    )

    log_audit(cur, user, "STOCK_IN", "inbound", "inbound_shipment", shipment_id, f"Received {ib.quantity}x '{product['name']}' from {supplier['name']} ({ib.invoice_ref or 'no ref'})")
    conn.commit()

    row = cur.execute("SELECT * FROM inbound_shipments WHERE id=?", (shipment_id,)).fetchone()
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

    where = "WHERE 1=1"
    params = []

    if product_id:
        where += " AND ib.product_id = ?"
        params.append(product_id)

    if supplier_id:
        where += " AND ib.supplier_id = ?"
        params.append(supplier_id)

    total = cur.execute(
        f"SELECT COUNT(*) FROM inbound_shipments ib {where}", params
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
        "SELECT id FROM inbound_shipments WHERE id=?", (shipment_id,)
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
            "SELECT id FROM inbound_shipments WHERE id=?", (shipment_id,)
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
            product_name = str(row_data.get("product_name", "")).strip()
            product_sku = str(row_data.get("sku", row_data.get("product_sku", ""))).strip()
            supplier_name = str(row_data.get("supplier_name", "")).strip()
            quantity = int(row_data.get("quantity", 0))
            invoice_ref = str(row_data.get("invoice_ref", "")).strip()
            received_date = str(row_data.get("received_date", "")).strip()
            notes = str(row_data.get("notes", "")).strip()

            if quantity <= 0:
                errors.append(f"Row {row_num}: Quantity must be positive")
                return

            if product_sku:
                product = cur.execute(
                    "SELECT id, name, quantity FROM products WHERE sku=? AND deleted=0 AND archived=0",
                    (product_sku,),
                ).fetchone()
            elif product_name:
                product = cur.execute(
                    "SELECT id, name, quantity FROM products WHERE LOWER(name)=? AND deleted=0 AND archived=0",
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

            if not received_date:
                received_date = date.today().isoformat()

            cur.execute(
                """
                INSERT INTO inbound_shipments (product_id, supplier_id, quantity, invoice_ref, received_date, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (product["id"], supplier["id"], quantity, invoice_ref, received_date, notes),
            )

            new_qty = product["quantity"] + quantity
            cur.execute(
                "UPDATE products SET quantity=?, updated_at=datetime('now') WHERE id=?",
                (new_qty, product["id"]),
            )

            cur.execute(
                "INSERT INTO movements (product_id, action_type, delta, reason, source) VALUES (?, 'STOCK_IN', ?, ?, 'inbound')",
                (product["id"], quantity, f"Bulk inbound: {invoice_ref or 'no ref'}"),
            )

            imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    if ext == ".csv":
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        for i, row in enumerate(reader, start=2):
            process_row(row, i)
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
            data = dict(zip(headers, row))
            process_row(data, i)
        wb.close()

    log_audit(cur, user, "BULK_IMPORT", "inbound", "file", None, f"Imported {imported} inbound records from {file.filename}")
    conn.commit()
    conn.close()

    return {
        "imported": imported,
        "errors": errors[:20],
        "total_errors": len(errors),
    }
