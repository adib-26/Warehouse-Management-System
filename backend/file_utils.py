from fastapi import HTTPException, UploadFile
import csv
import io
import os
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from pymysql.err import DataError, IntegrityError

from config import MAX_UPLOAD_BYTES

IMPORT_INTERRUPTED_DETAIL = (
    "The import was rolled back because another update locked the same records "
    "or the database connection was lost. No rows were imported; retry the file."
)


def safe_filename(filename: str) -> str:
    """Keep a display name while stripping both POSIX and Windows path parts."""
    normalized = filename.replace("\\", "/")
    name = PurePosixPath(normalized).name
    printable = "".join(character for character in name if character.isprintable())
    return printable[:180] or "attachment"


def read_upload(file: UploadFile) -> bytes:
    """Read an uploaded file, rejecting it once it exceeds MAX_UPLOAD_BYTES.

    Call this from a plain ``def`` endpoint. FastAPI runs those in a worker
    thread, so this blocking read and the database work that follows it do not
    stall the event loop for every other request.
    """
    chunks = []
    total = 0

    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File is too large; maximum size is {MAX_UPLOAD_BYTES} bytes",
            )
        chunks.append(chunk)

    return b"".join(chunks)


def _header(value) -> str:
    return "" if value is None else str(value).strip().lower()


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def iter_spreadsheet_rows(content: bytes, ext: str):
    """Yield ``(row_number, {lowercase header: value})`` from a CSV or XLSX upload.

    Row numbers match the spreadsheet, where the header is row 1. Completely
    blank rows are skipped. A file that cannot be parsed raises a 400 error.
    Because rows are yielded lazily, a parse error part-way through a file
    reaches the caller's transaction handling, so the import is rolled back.
    """
    if ext == ".csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail="CSV files must be UTF-8 encoded. Re-save the file as CSV UTF-8 and try again.",
            ) from exc
        reader = csv.DictReader(io.StringIO(text, newline=""))
        try:
            for row_number, row in enumerate(reader, start=2):
                values = {
                    _header(key): value for key, value in row.items() if key is not None
                }
                if all(_is_blank(value) for value in values.values()):
                    continue
                yield row_number, values
        except csv.Error as exc:
            raise HTTPException(
                status_code=400, detail=f"Could not read the CSV file: {exc}"
            ) from exc
        return

    if ext != ".xlsx":
        raise HTTPException(status_code=400, detail="Only CSV and XLSX files are supported")
    try:
        import openpyxl
        from openpyxl.utils.exceptions import InvalidFileException
    except ImportError as exc:
        raise HTTPException(
            status_code=500, detail="openpyxl is required for XLSX files"
        ) from exc

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="Could not read the XLSX file. Check that it is a valid Excel workbook."
        ) from exc
    try:
        sheet = workbook.active
        # Some producers store a wrong sheet size; read every stored row instead.
        sheet.reset_dimensions()
        rows = sheet.iter_rows(values_only=True)
        headers = [_header(value) for value in next(rows, ())]
        for row_number, row in enumerate(rows, start=2):
            if all(_is_blank(value) for value in row):
                continue
            yield row_number, dict(zip(headers, row))
    finally:
        workbook.close()


def import_row_error(exc: Exception) -> str:
    """Describe a rejected import row without exposing raw database messages."""
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            return str(detail.get("message") or detail)
        return str(detail)
    if isinstance(exc, DataError):
        return "A value is too long or out of range"
    if isinstance(exc, IntegrityError):
        return "The row conflicts with existing data"
    return str(exc)


def write_upload_file(directory: Path, stored_name: str, content: bytes) -> Path:
    """Atomically publish a completed upload and return its final path."""
    directory.mkdir(parents=True, exist_ok=True)
    final_path = directory / stored_name
    temporary_path = directory / f".{stored_name}.{uuid.uuid4().hex}.uploading"
    try:
        with temporary_path.open("xb") as output:
            output.write(content)
        os.replace(temporary_path, final_path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise
    return final_path


def stage_file_deletion(file_path: Path) -> Path | None:
    """Move a file out of service so a database deletion can be rolled back."""
    if not file_path.exists():
        return None
    staged_path = file_path.with_name(f".{file_path.name}.{uuid.uuid4().hex}.deleting")
    os.replace(file_path, staged_path)
    return staged_path
