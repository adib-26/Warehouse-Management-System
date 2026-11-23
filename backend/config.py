import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "wms.db")).expanduser()
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads")).expanduser()
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
SECRET_KEY = os.getenv("SECRET_KEY", "novaledger-dev-secret-change-me").strip()
INITIAL_ADMIN_USERNAME = os.getenv("INITIAL_ADMIN_USERNAME", "admin").strip()
INITIAL_ADMIN_PASSWORD = os.getenv("INITIAL_ADMIN_PASSWORD", "admin123")

try:
    MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
except ValueError as exc:
    raise RuntimeError("MAX_UPLOAD_BYTES must be a positive integer") from exc


def get_cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def validate_runtime_config() -> None:
    if APP_ENV not in {"development", "test", "production"}:
        raise RuntimeError("APP_ENV must be development, test, or production")
    if MAX_UPLOAD_BYTES <= 0:
        raise RuntimeError("MAX_UPLOAD_BYTES must be a positive integer")

    if APP_ENV == "production":
        if (
            len(SECRET_KEY) < 32
            or SECRET_KEY in {"novaledger-dev-secret-change-me", "replace-with-a-long-random-secret"}
            or SECRET_KEY.lower().startswith(("replace-", "change-"))
        ):
            raise RuntimeError("Production requires a unique SECRET_KEY of at least 32 characters")
        if "*" in get_cors_origins():
            raise RuntimeError("Production CORS_ORIGINS must list explicit origins")


def validate_initial_admin_credentials() -> None:
    if not INITIAL_ADMIN_USERNAME:
        raise RuntimeError("INITIAL_ADMIN_USERNAME cannot be empty")
    if not INITIAL_ADMIN_PASSWORD.strip():
        raise RuntimeError("INITIAL_ADMIN_PASSWORD cannot be empty")
    if len(INITIAL_ADMIN_PASSWORD.encode("utf-8")) > 72:
        raise RuntimeError("INITIAL_ADMIN_PASSWORD must be no more than 72 UTF-8 bytes")
    if APP_ENV == "production" and (
        len(INITIAL_ADMIN_PASSWORD) < 16
        or INITIAL_ADMIN_PASSWORD == "admin123"
        or INITIAL_ADMIN_PASSWORD.lower().startswith(("change-", "replace-"))
    ):
        raise RuntimeError(
            "Set INITIAL_ADMIN_PASSWORD to a unique password of at least 16 characters before first production startup"
        )
