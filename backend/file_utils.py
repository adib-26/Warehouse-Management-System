from fastapi import HTTPException, UploadFile
import os
import uuid
from pathlib import Path, PurePosixPath

from config import MAX_UPLOAD_BYTES


def safe_filename(filename: str) -> str:
    """Keep a display name while stripping both POSIX and Windows path parts."""
    normalized = filename.replace("\\", "/")
    name = PurePosixPath(normalized).name
    printable = "".join(character for character in name if character.isprintable())
    return printable[:180] or "attachment"


async def read_upload(file: UploadFile) -> bytes:
    chunks = []
    total = 0

    while True:
        chunk = await file.read(1024 * 1024)
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
