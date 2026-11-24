from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from database import get_db, MODULES
from config import UPLOAD_DIR
from file_utils import stage_file_deletion
from security import get_current_user, check_permission, log_audit
import os

router = APIRouter()

def entity_module(entity_type: str) -> str:
    # Attachment permissions follow the module the entity belongs to
    # (currently 'inbound' and 'outbound' shipments).
    return entity_type if entity_type in MODULES else "products"


def _is_operational_attachment(cur, attachment: dict) -> bool:
    """Keep attachments linked to the M5 sandbox out of normal WMS APIs."""
    if attachment["entity_type"] == "inbound":
        row = cur.execute(
            "SELECT ib.id FROM inbound_shipments ib "
            "JOIN products p ON p.id=ib.product_id "
            "WHERE ib.id=? AND p.is_forecast_test=0",
            (attachment["entity_id"],),
        ).fetchone()
        return row is not None
    if attachment["entity_type"] == "outbound":
        row = cur.execute(
            "SELECT ob.id FROM outbound_shipments ob "
            "JOIN products p ON p.id=ob.product_id "
            "WHERE ob.id=? AND p.is_forecast_test=0",
            (attachment["entity_id"],),
        ).fetchone()
        return row is not None
    return True


@router.get("/{attachment_id}")
def download_attachment(attachment_id: int, user: dict = Depends(get_current_user)):
    conn = get_db()
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT * FROM attachments WHERE id=?", (attachment_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Attachment not found")
        attachment = dict(row)
        if not _is_operational_attachment(cur, attachment):
            raise HTTPException(status_code=404, detail="Attachment not found")
    finally:
        conn.close()

    check_permission(user, entity_module(attachment["entity_type"]), "read")
    file_path = UPLOAD_DIR / attachment["stored_name"]

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=file_path,
        filename=attachment["filename"],
        media_type=attachment["mime_type"],
    )


@router.delete("/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: int, user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    staged_path = None
    file_path = None
    try:
        row = cur.execute(
            "SELECT * FROM attachments WHERE id=?", (attachment_id,)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Attachment not found")

        attachment = dict(row)
        if not _is_operational_attachment(cur, attachment):
            raise HTTPException(status_code=404, detail="Attachment not found")
        check_permission(user, entity_module(attachment["entity_type"]), "write")
        file_path = UPLOAD_DIR / attachment["stored_name"]
        try:
            staged_path = stage_file_deletion(file_path)
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Could not remove attachment file") from exc

        cur.execute("DELETE FROM attachments WHERE id=?", (attachment_id,))
        log_audit(cur, user, "DELETE", entity_module(attachment["entity_type"]), "attachment", attachment_id, f"Deleted attachment '{attachment['filename']}'")
        conn.commit()
    except Exception:
        conn.rollback()
        if staged_path is not None and file_path is not None and staged_path.exists():
            try:
                os.replace(staged_path, file_path)
            except OSError:
                pass
        raise
    finally:
        conn.close()

    if staged_path is not None:
        try:
            staged_path.unlink(missing_ok=True)
        except OSError:
            # The record is already gone; an orphaned staged file is safer than
            # rolling back a completed database transaction.
            pass

    return Response(status_code=204)
