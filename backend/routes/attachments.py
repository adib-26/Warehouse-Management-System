from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from database import get_db, MODULES
from config import UPLOAD_DIR
from security import get_current_user, check_permission, log_audit
import os

router = APIRouter()

def entity_module(entity_type: str) -> str:
    # Attachment permissions follow the module the entity belongs to
    # (currently 'inbound' and 'outbound' shipments).
    return entity_type if entity_type in MODULES else "products"


@router.get("/{attachment_id}")
def download_attachment(attachment_id: int, user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM attachments WHERE id=?", (attachment_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")

    attachment = dict(row)
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
    row = cur.execute(
        "SELECT * FROM attachments WHERE id=?", (attachment_id,)
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Attachment not found")

    attachment = dict(row)
    check_permission(user, entity_module(attachment["entity_type"]), "write")
    file_path = UPLOAD_DIR / attachment["stored_name"]

    if os.path.exists(file_path):
        os.remove(file_path)

    cur.execute("DELETE FROM attachments WHERE id=?", (attachment_id,))
    log_audit(cur, user, "DELETE", entity_module(attachment["entity_type"]), "attachment", attachment_id, f"Deleted attachment '{attachment['filename']}'")
    conn.commit()
    conn.close()

    return Response(status_code=204)
