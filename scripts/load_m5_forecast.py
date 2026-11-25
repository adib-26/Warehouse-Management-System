"""Load a validated M5 long CSV into NovaLedger forecast tables.

This script writes only forecast_m5_mappings, forecast_m5_imports, and
forecast_demand_history. It never changes stock, shipments, or movements.
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "datasets" / "m5" / "processed" / "m5_daily_sales.csv.gz"
OUTPUT_COLUMNS = ("item_id", "store_id", "date", "daily_sales")
MAPPING_COLUMNS = ("item_id", "store_id", "product_id", "warehouse_id")
MAX_SIGNED_INT = 2_147_483_647
MAX_DAILY_SALES = 9_999_999_999
HASH_CHUNK_BYTES = 1024 * 1024
MAPPING_BATCH_SIZE = 1_000
IMPORT_LOCK_NAME = "novaledger_m5_forecast_import"
STAGE_TABLE = "tmp_m5_forecast_stage"
STAGE_SCOPE_TABLE = "tmp_m5_forecast_stage_scope"
VALIDATION_PROGRESS_ROWS = 1_000_000
STAGING_PROGRESS_ROWS = 100_000

sys.path.insert(0, str(ROOT / "scripts"))
from project_env import load_project_env  # noqa: E402

load_project_env(ROOT)
sys.path.insert(0, str(ROOT / "backend"))
from database import get_db  # noqa: E402


class DigestingReader(io.RawIOBase):
    """A raw reader that computes a checksum as the CSV reader consumes bytes."""

    def __init__(self, raw_file):
        self._raw_file = raw_file
        self._digest = hashlib.sha256()
        self.byte_count = 0
        super().__init__()

    def readable(self):
        return True

    def readinto(self, buffer):
        read_count = self._raw_file.readinto(buffer)
        if read_count:
            chunk = memoryview(buffer)[:read_count]
            self._digest.update(chunk)
            self.byte_count += read_count
        return read_count

    @property
    def hexdigest(self) -> str:
        return self._digest.hexdigest()

    def close(self):
        if not self.closed:
            self._raw_file.close()
        super().close()


@contextmanager
def open_csv_with_digest(path: Path):
    """Open a CSV while hashing exactly the bytes consumed from its source file.

    The manifest hashes the compressed artifact, rather than its decompressed
    text. Wrapping the underlying binary stream lets preflight validation and
    checksum verification share one pass even for ``.csv.gz`` inputs.
    """

    raw_file = path.open("rb", buffering=0)
    digesting_file = DigestingReader(raw_file)
    buffered_file = io.BufferedReader(digesting_file, buffer_size=HASH_CHUNK_BYTES)
    binary_file = (
        gzip.GzipFile(fileobj=buffered_file, mode="rb")
        if path.name.lower().endswith(".gz")
        else buffered_file
    )
    text_file = io.TextIOWrapper(binary_file, encoding="utf-8-sig", newline="")
    try:
        yield text_file, digesting_file
    finally:
        # GzipFile deliberately leaves a caller-provided file object open. Close
        # the buffer too so the original descriptor is always released.
        try:
            text_file.close()
        finally:
            buffered_file.close()


def input_snapshot(path: Path) -> tuple[int, int, int, int]:
    """Return a stable-enough identity check for an input file during streaming."""

    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(HASH_CHUNK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        # Match the converter manifest's representation for external files.
        return str(path)


def default_metadata_path(input_path: Path) -> Path:
    name = input_path.name
    if name.endswith(".csv.gz"):
        name = name[: -len(".csv.gz")]
    else:
        name = input_path.stem
    return input_path.with_name(f"{name}.metadata.json")


def parse_positive_id(value: str, field: str, row_number: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid {field} in mapping row {row_number}: {value!r}"
        ) from exc
    if parsed <= 0 or parsed > MAX_SIGNED_INT:
        raise ValueError(
            f"{field} in mapping row {row_number} must be between 1 and {MAX_SIGNED_INT}"
        )
    return parsed


def parse_daily_sales(value: str, row_number: int) -> int:
    try:
        quantity = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid daily_sales at input row {row_number}: {value!r}"
        ) from exc
    if quantity < 0:
        raise ValueError(f"Negative daily_sales at input row {row_number}")
    if quantity > MAX_DAILY_SALES:
        raise ValueError(
            f"daily_sales exceeds DECIMAL(12,2) capacity at input row {row_number}"
        )
    return quantity


def parse_date(value: str, row_number: int) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid ISO date at input row {row_number}: {value!r}"
        ) from exc
    if parsed.isoformat() != value:
        raise ValueError(f"Date is not canonical ISO format at input row {row_number}")
    return parsed.isoformat()


def load_mapping_file(path: Path) -> dict[tuple[str, str], tuple[int, int]]:
    """Load one explicit M5 series to NovaLedger product/warehouse mapping."""
    if not path.is_file():
        raise FileNotFoundError(f"Missing M5 mapping CSV: {path}")

    mappings = {}
    mapped_targets = {}
    with path.open("r", encoding="utf-8-sig", newline="") as mapping_file:
        reader = csv.DictReader(mapping_file, strict=True)
        if not reader.fieldnames:
            raise ValueError("Mapping CSV is empty")
        original_headers = list(reader.fieldnames)
        headers = [header.strip() for header in original_headers]
        if len(headers) != len(set(headers)):
            raise ValueError("Mapping CSV contains duplicate column names")
        missing = set(MAPPING_COLUMNS) - set(headers)
        if missing:
            raise ValueError(
                "Mapping CSV is missing required columns: " + ", ".join(sorted(missing))
            )

        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"Mapping row {row_number} has extra fields")
            normalized = {
                header.strip(): row.get(header)
                for header in original_headers
            }
            item_id = (normalized.get("item_id") or "").strip()
            store_id = (normalized.get("store_id") or "").strip()
            if not item_id or not store_id:
                raise ValueError(f"Mapping row {row_number} needs item_id and store_id")
            if len(item_id) > 64 or len(store_id) > 32:
                raise ValueError(f"M5 identifiers are too long in mapping row {row_number}")
            key = (item_id, store_id)
            if key in mappings:
                raise ValueError(f"Duplicate item/store mapping at row {row_number}: {key}")

            target = (
                parse_positive_id(normalized.get("product_id"), "product_id", row_number),
                parse_positive_id(
                    normalized.get("warehouse_id"), "warehouse_id", row_number
                ),
            )
            other_key = mapped_targets.get(target)
            if other_key is not None:
                raise ValueError(
                    f"Mapping row {row_number} reuses product/warehouse {target} already "
                    f"mapped from {other_key}; each M5 item/store needs its own target pair"
                )
            mappings[key] = target
            mapped_targets[target] = key

    if not mappings:
        raise ValueError("Mapping CSV contains no item/store mappings")
    return mappings


def mapping_sha256(mappings: dict[tuple[str, str], tuple[int, int]]) -> str:
    digest = hashlib.sha256()
    for (item_id, store_id), (product_id, warehouse_id) in sorted(mappings.items()):
        digest.update(
            f"{item_id}\x1f{store_id}\x1f{product_id}\x1f{warehouse_id}\n".encode("utf-8")
        )
    return digest.hexdigest()


def validate_manifest(manifest_path: Path, input_path: Path, input_sha256: str) -> dict:
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Missing M5 dataset manifest: {manifest_path}. "
            "Use --skip-manifest-check only for a separately validated dataset."
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read dataset manifest {manifest_path}: {exc}") from exc

    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported M5 dataset manifest schema version")
    columns = tuple(column.get("name") for column in manifest.get("columns", []))
    if columns != OUTPUT_COLUMNS:
        raise ValueError("Dataset manifest does not describe the expected M5 long schema")
    output = manifest.get("output", {})
    if output.get("file") != display_path(input_path):
        raise ValueError("Dataset manifest points to a different output file")
    if output.get("sha256") != input_sha256:
        raise ValueError("Dataset manifest checksum does not match the M5 input")
    coverage = manifest.get("coverage", {})
    if not isinstance(coverage.get("row_count"), int) or coverage["row_count"] < 1:
        raise ValueError("Dataset manifest has no valid row count")
    return manifest


def validate_input(
    path: Path,
    mappings: dict[tuple[str, str], tuple[int, int]],
    allow_unmapped: bool,
    stage_writer=None,
) -> dict:
    """Validate every source series and optionally stage mapped rows once.

    The source is intentionally checked in full, including unmapped series, so
    a sparse import cannot hide a corrupt conversion.  When a stage writer is
    supplied, only mapped rows are retained and the later database activation
    never has to reread the full source artifact.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Missing processed M5 CSV: {path}")

    starting_snapshot = input_snapshot(path)
    source_series = None
    source_selected = False
    source_dates = []
    previous_date = None
    all_reference_dates = None
    seen_source_series = set()
    selected_series = set()
    selected_store_ids = set()
    source_row_count = 0
    selected_row_count = 0
    skipped_row_count = 0
    skipped_series_count = 0
    next_progress_row = VALIDATION_PROGRESS_ROWS

    def finish_series(key, dates, reference):
        if key is None:
            return reference
        actual_dates = tuple(dates)
        if not actual_dates:
            raise ValueError(f"M5 series has no observations: {key}")
        if reference is None:
            return actual_dates
        if actual_dates != reference:
            raise ValueError(
                f"M5 series {key} does not have the expected complete date coverage"
            )
        return reference

    with open_csv_with_digest(path) as (source_file, digesting_file):
        reader = csv.reader(source_file, strict=True)
        headers = next(reader, None)
        if headers != list(OUTPUT_COLUMNS):
            raise ValueError(
                f"Processed M5 CSV must have columns in this order: {', '.join(OUTPUT_COLUMNS)}"
            )

        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(OUTPUT_COLUMNS):
                raise ValueError(
                    f"Malformed processed M5 row {row_number}: expected 4 fields, found {len(row)}"
                )
            item_id, store_id, date_text, quantity_text = row
            if not item_id or not store_id:
                raise ValueError(f"Missing item_id or store_id at input row {row_number}")
            if len(item_id) > 64 or len(store_id) > 32:
                raise ValueError(f"M5 identifier is too long at input row {row_number}")
            key = (item_id, store_id)

            if key != source_series:
                all_reference_dates = finish_series(
                    source_series, source_dates, all_reference_dates
                )
                if key in seen_source_series:
                    raise ValueError(f"M5 series is split across multiple blocks: {key}")
                seen_source_series.add(key)
                source_series = key
                source_selected = key in mappings
                if not source_selected and not allow_unmapped:
                    raise ValueError(f"No product/warehouse mapping for M5 series {key}")
                if source_selected:
                    selected_series.add(key)
                    selected_store_ids.add(store_id)
                else:
                    skipped_series_count += 1
                source_dates = []
                previous_date = None

            sale_date_text = parse_date(date_text, row_number)
            sale_date = date.fromisoformat(sale_date_text)
            if previous_date is not None and sale_date != previous_date + timedelta(days=1):
                raise ValueError(
                    f"Duplicate or missing day in series {key} at input row {row_number}"
                )
            previous_date = sale_date
            source_dates.append(sale_date_text)
            quantity = parse_daily_sales(quantity_text, row_number)
            source_row_count += 1
            if source_selected:
                selected_row_count += 1
                if stage_writer is not None:
                    stage_writer.add(item_id, store_id, sale_date_text, quantity)
            else:
                skipped_row_count += 1

            if source_row_count >= next_progress_row:
                print(
                    f"Verified {source_row_count:,} source rows; selected "
                    f"{selected_row_count:,} and skipped {skipped_row_count:,}.",
                    file=sys.stderr,
                    flush=True,
                )
                while source_row_count >= next_progress_row:
                    next_progress_row += VALIDATION_PROGRESS_ROWS

    all_reference_dates = finish_series(
        source_series, source_dates, all_reference_dates
    )
    ending_snapshot = input_snapshot(path)
    if ending_snapshot != starting_snapshot:
        raise ValueError("Processed M5 input changed during validation")
    if digesting_file.byte_count != starting_snapshot[2]:
        raise ValueError("Could not checksum every byte of the processed M5 input")
    if not source_row_count or not selected_series or not all_reference_dates:
        raise ValueError("Processed M5 CSV contains no mapped daily sales rows")
    unused_mappings = set(mappings) - selected_series
    if unused_mappings and not allow_unmapped:
        preview = ", ".join(f"{item}/{store}" for item, store in sorted(unused_mappings)[:3])
        raise ValueError(
            f"Mapping CSV contains series absent from the input, including {preview}"
        )
    if stage_writer is not None:
        stage_writer.flush()
        if stage_writer.row_count != selected_row_count:
            raise RuntimeError(
                "Selected-row staging count does not match validated M5 input"
            )

    return {
        "source_series_count": len(seen_source_series),
        "selected_series_count": len(selected_series),
        "selected_store_count": len(selected_store_ids),
        "skipped_series_count": skipped_series_count,
        "source_row_count": source_row_count,
        "selected_row_count": selected_row_count,
        "skipped_row_count": skipped_row_count,
        "date_start": all_reference_dates[0],
        "date_end": all_reference_dates[-1],
        "date_count": len(all_reference_dates),
        "selected_keys": selected_series,
        "dataset_sha256": digesting_file.hexdigest,
    }


def _ids_in_batches(ids, size):
    values = list(ids)
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def _require_forecast_schema(cur):
    try:
        cur.execute("SELECT is_forecast_test FROM products LIMIT 0")
        cur.execute("SELECT is_forecast_test FROM warehouses LIMIT 0")
        cur.execute("SELECT id FROM forecast_m5_imports LIMIT 0")
    except Exception as exc:
        raise RuntimeError(
            "The NovaLedger forecast-import schema is required. Start the backend "
            "once to apply migrations before importing M5 data."
        ) from exc


def _validate_mapping_targets(cur, mappings: dict) -> None:
    """Require every requested target to be an active, isolated test target."""

    product_ids = sorted({product_id for product_id, _ in mappings.values()})
    warehouse_ids = sorted({warehouse_id for _, warehouse_id in mappings.values()})
    active_products = set()
    for batch in _ids_in_batches(product_ids, 5_000):
        placeholders = ", ".join(["?"] * len(batch))
        active_products.update(
            int(row["id"])
            for row in cur.execute(
                f"""
                SELECT id FROM products
                WHERE id IN ({placeholders})
                  AND deleted=0 AND archived=0 AND is_forecast_test=1
                """,
                batch,
            ).fetchall()
        )
    active_warehouses = set()
    for batch in _ids_in_batches(warehouse_ids, 5_000):
        placeholders = ", ".join(["?"] * len(batch))
        active_warehouses.update(
            int(row["id"])
            for row in cur.execute(
                f"""
                SELECT id FROM warehouses
                WHERE id IN ({placeholders})
                  AND active=1 AND is_forecast_test=1
                """,
                batch,
            ).fetchall()
        )
    missing_products = sorted(set(product_ids) - active_products)
    missing_warehouses = sorted(set(warehouse_ids) - active_warehouses)
    if missing_products:
        raise ValueError(
            "Mappings must use active M5 test product IDs; invalid IDs: "
            + ", ".join(map(str, missing_products[:10]))
        )
    if missing_warehouses:
        raise ValueError(
            "Mappings must use active M5 test warehouse IDs; invalid IDs: "
            + ", ".join(map(str, missing_warehouses[:10]))
        )


def validate_database_mapping_targets(conn, mappings: dict) -> None:
    """Fail before an expensive source scan when mapping targets are unsafe."""

    cur = conn.cursor()
    _require_forecast_schema(cur)
    _validate_mapping_targets(cur, mappings)


def ensure_database_mappings(conn, mappings: dict) -> dict:
    """Materialize only the selected immutable source mappings."""

    cur = conn.cursor()
    try:
        _require_forecast_schema(cur)
        _validate_mapping_targets(cur, mappings)
        rows = [
            (item_id, store_id, product_id, warehouse_id)
            for (item_id, store_id), (product_id, warehouse_id) in mappings.items()
        ]
        for batch in _ids_in_batches(rows, MAPPING_BATCH_SIZE):
            cur.executemany(
                """
                INSERT INTO forecast_m5_mappings
                    (item_id, store_id, product_id, warehouse_id)
                VALUES (?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE id = id
                """,
                batch,
            )

        database_mappings = {}
        for batch in _ids_in_batches(mappings.keys(), MAPPING_BATCH_SIZE // 2):
            pair_placeholders = ", ".join(["(?, ?)"] * len(batch))
            batch_params = [value for key in batch for value in key]
            rows = cur.execute(
                "SELECT id, item_id, store_id, product_id, warehouse_id "
                "FROM forecast_m5_mappings "
                f"WHERE (item_id, store_id) IN ({pair_placeholders})",
                batch_params,
            ).fetchall()
            for row in rows:
                database_mappings[(row["item_id"], row["store_id"])] = (
                    int(row["id"]),
                    int(row["product_id"]),
                    int(row["warehouse_id"]),
                )
        resolved = {}
        for key, expected_target in mappings.items():
            actual = database_mappings.get(key)
            if actual is None:
                raise ValueError(
                    f"Could not create mapping for {key}; another source series may "
                    "already use the same product/warehouse pair"
                )
            mapping_id, product_id, warehouse_id = actual
            if (product_id, warehouse_id) != expected_target:
                raise ValueError(
                    f"Existing mapping for {key} points to {(product_id, warehouse_id)}, "
                    f"not {expected_target}; mappings are immutable after import"
                )
            resolved[key] = (mapping_id, product_id, warehouse_id)
        conn.commit()
        return resolved
    except Exception:
        conn.rollback()
        raise


def acquire_import_lock(conn):
    row = conn.execute("SELECT GET_LOCK(?, 60) AS acquired", (IMPORT_LOCK_NAME,)).fetchone()
    if row is None or int(row["acquired"] or 0) != 1:
        raise RuntimeError("Could not acquire the M5 import lock; another import is running")


def release_import_lock(conn):
    try:
        conn.execute("SELECT RELEASE_LOCK(?)", (IMPORT_LOCK_NAME,))
    except Exception:
        # The MySQL connection close also releases a named connection lock.
        pass


def reconcile_abandoned_imports(conn) -> int:
    """Close audit rows left running when an earlier importer lost its connection."""

    cur = conn.cursor()
    cur.execute(
        """
        UPDATE forecast_m5_imports
        SET status='failed',
            completed_at=UTC_TIMESTAMP(),
            error_message=COALESCE(
                error_message,
                'Importer connection ended before the import could complete.'
            )
        WHERE status='running'
        """
    )
    recovered = cur.rowcount
    conn.commit()
    return recovered


def create_import_stage(conn, batch_size: int):
    """Create connection-local storage for validated mapped rows.

    Staging is deliberately temporary: it is invisible to forecast readers,
    discarded if this connection dies, and lets replacement become one atomic
    activation instead of a sequence of partially committed upserts.
    """

    cur = conn.cursor()
    cur.execute(f"DROP TEMPORARY TABLE IF EXISTS `{STAGE_SCOPE_TABLE}`")
    cur.execute(f"DROP TEMPORARY TABLE IF EXISTS `{STAGE_TABLE}`")
    cur.execute(
        f"""
        CREATE TEMPORARY TABLE `{STAGE_TABLE}` (
            item_id VARCHAR(64) NOT NULL,
            store_id VARCHAR(32) NOT NULL,
            demand_date DATE NOT NULL,
            quantity_sold DECIMAL(12,2) NOT NULL,
            PRIMARY KEY (item_id, store_id, demand_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        f"""
        CREATE TEMPORARY TABLE `{STAGE_SCOPE_TABLE}` (
            item_id VARCHAR(64) NOT NULL,
            store_id VARCHAR(32) NOT NULL,
            PRIMARY KEY (item_id, store_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    conn.commit()
    return ImportStageWriter(conn, batch_size)


class ImportStageWriter:
    """Batch selected input rows into the private staging table."""

    def __init__(self, conn, batch_size: int):
        self.conn = conn
        self.batch_size = batch_size
        self._pending = []
        self.row_count = 0
        self._next_progress_row = STAGING_PROGRESS_ROWS

    def add(self, item_id: str, store_id: str, demand_date: str, quantity_sold: int):
        self._pending.append((item_id, store_id, demand_date, quantity_sold))
        if len(self._pending) >= self.batch_size:
            self.flush()

    def flush(self):
        if not self._pending:
            return
        cur = self.conn.cursor()
        cur.executemany(
            f"""
            INSERT INTO `{STAGE_TABLE}`
                (item_id, store_id, demand_date, quantity_sold)
            VALUES (?, ?, ?, ?)
            """,
            self._pending,
        )
        staged_now = len(self._pending)
        self.conn.commit()
        self.row_count += staged_now
        self._pending.clear()
        while self.row_count >= self._next_progress_row:
            print(
                f"Staged {self._next_progress_row:,} selected M5 daily rows.",
                file=sys.stderr,
                flush=True,
            )
            self._next_progress_row += STAGING_PROGRESS_ROWS

    def prepare_scope(self, expected_rows: int, expected_series: int):
        self.flush()
        cur = self.conn.cursor()
        row = cur.execute(
            f"SELECT COUNT(*) AS n FROM `{STAGE_TABLE}`"
        ).fetchone()
        if row is None or int(row["n"]) != expected_rows:
            raise RuntimeError(
                "Temporary M5 staging table does not contain every validated row"
            )
        cur.execute(
            f"""
            INSERT INTO `{STAGE_SCOPE_TABLE}` (item_id, store_id)
            SELECT DISTINCT item_id, store_id FROM `{STAGE_TABLE}`
            """
        )
        row = cur.execute(
            f"SELECT COUNT(*) AS n FROM `{STAGE_SCOPE_TABLE}`"
        ).fetchone()
        if row is None or int(row["n"]) != expected_series:
            raise RuntimeError(
                "Temporary M5 staging scope does not match validated source series"
            )
        self.conn.commit()


def count_existing_history(cur, mapping_ids) -> int:
    total = 0
    for batch in _ids_in_batches(mapping_ids, MAPPING_BATCH_SIZE):
        placeholders = ", ".join(["?"] * len(batch))
        row = cur.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM forecast_demand_history
            WHERE source='M5' AND m5_mapping_id IN ({placeholders})
            """,
            batch,
        ).fetchone()
        total += int(row["n"])
    return total


def has_matching_successful_import(cur, dataset_digest, mapping_digest, summary) -> bool:
    row = cur.execute(
        """
        SELECT id FROM forecast_m5_imports
        WHERE dataset_sha256=?
          AND mapping_sha256=?
          AND source_row_count=?
          AND series_count=?
          AND status='success'
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            dataset_digest,
            mapping_digest,
            summary["selected_row_count"],
            summary["selected_series_count"],
        ),
    ).fetchone()
    return row is not None


def start_import_run(
    conn,
    dataset_digest: str,
    mapping_digest: str,
    input_path: Path,
    manifest_path: Path | None,
    summary: dict,
    replace_existing: bool,
) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO forecast_m5_imports
            (dataset_sha256, mapping_sha256, dataset_path, manifest_path,
             source_row_count, series_count, date_start, date_end, replace_existing)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_digest,
            mapping_digest,
            display_path(input_path),
            display_path(manifest_path) if manifest_path else None,
            summary["selected_row_count"],
            summary["selected_series_count"],
            summary["date_start"],
            summary["date_end"],
            int(replace_existing),
        ),
    )
    run_id = cur.lastrowid
    conn.commit()
    return int(run_id)


def finish_import_run(conn, run_id: int, status: str, loaded_rows: int, error: str | None = None):
    conn.execute(
        """
        UPDATE forecast_m5_imports
        SET status=?, loaded_row_count=?, completed_at=UTC_TIMESTAMP(), error_message=?
        WHERE id=? AND status='running'
        """,
        (status, loaded_rows, error, run_id),
    )
    conn.commit()


def activate_staged_history(
    conn,
    run_id: int,
    expected_rows: int,
    date_start: str,
    date_end: str,
    replace_existing: bool,
) -> int:
    """Atomically publish staged rows and, when requested, prune stale history."""

    cur = conn.cursor()
    staged = cur.execute(
        f"SELECT COUNT(*) AS n FROM `{STAGE_TABLE}`"
    ).fetchone()
    if staged is None or int(staged["n"]) != expected_rows:
        raise RuntimeError("Temporary M5 staging row count changed before activation")

    cur.execute("START TRANSACTION")
    try:
        cur.execute(
            f"""
            INSERT INTO forecast_demand_history
                (product_id, warehouse_id, demand_date, quantity_sold, source, m5_mapping_id)
            SELECT mapping.product_id,
                   mapping.warehouse_id,
                   stage.demand_date,
                   stage.quantity_sold,
                   'M5',
                   mapping.id
            FROM `{STAGE_TABLE}` AS stage
            JOIN forecast_m5_mappings AS mapping
              ON mapping.item_id=stage.item_id AND mapping.store_id=stage.store_id
            ON DUPLICATE KEY UPDATE
                quantity_sold=VALUES(quantity_sold),
                m5_mapping_id=VALUES(m5_mapping_id)
            """
        )
        mismatch = cur.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM `{STAGE_TABLE}` AS stage
            JOIN forecast_m5_mappings AS mapping
              ON mapping.item_id=stage.item_id AND mapping.store_id=stage.store_id
            LEFT JOIN forecast_demand_history AS history
              ON history.source='M5'
             AND history.m5_mapping_id=mapping.id
             AND history.product_id=mapping.product_id
             AND history.warehouse_id=mapping.warehouse_id
             AND history.demand_date=stage.demand_date
            WHERE history.id IS NULL OR history.quantity_sold <> stage.quantity_sold
            """
        ).fetchone()
        if mismatch is None or int(mismatch["n"]) != 0:
            raise RuntimeError("M5 history verification failed before replacement activation")

        deleted_rows = 0
        if replace_existing:
            cur.execute(
                f"""
                DELETE history
                FROM forecast_demand_history AS history
                JOIN forecast_m5_mappings AS mapping
                  ON mapping.id=history.m5_mapping_id
                JOIN `{STAGE_SCOPE_TABLE}` AS scope
                  ON scope.item_id=mapping.item_id AND scope.store_id=mapping.store_id
                WHERE history.source='M5'
                  AND (history.demand_date < ? OR history.demand_date > ?)
                """,
                (date_start, date_end),
            )
            deleted_rows = cur.rowcount

        active_rows = cur.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM forecast_demand_history AS history
            JOIN forecast_m5_mappings AS mapping
              ON mapping.id=history.m5_mapping_id
            JOIN `{STAGE_SCOPE_TABLE}` AS scope
              ON scope.item_id=mapping.item_id AND scope.store_id=mapping.store_id
            WHERE history.source='M5'
              AND history.demand_date >= ? AND history.demand_date <= ?
            """,
            (date_start, date_end),
        ).fetchone()
        if active_rows is None or int(active_rows["n"]) != expected_rows:
            raise RuntimeError(
                "Published M5 history count does not match the validated source"
            )

        if replace_existing:
            stale_rows = cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM forecast_demand_history AS history
                JOIN forecast_m5_mappings AS mapping
                  ON mapping.id=history.m5_mapping_id
                JOIN `{STAGE_SCOPE_TABLE}` AS scope
                  ON scope.item_id=mapping.item_id AND scope.store_id=mapping.store_id
                WHERE history.source='M5'
                  AND (history.demand_date < ? OR history.demand_date > ?)
                """,
                (date_start, date_end),
            ).fetchone()
            if stale_rows is None or int(stale_rows["n"]) != 0:
                raise RuntimeError("Stale M5 history remains after replacement activation")

        cur.execute(
            """
            UPDATE forecast_m5_imports
            SET status='success', loaded_row_count=?, completed_at=UTC_TIMESTAMP(),
                error_message=NULL
            WHERE id=? AND status='running'
            """,
            (expected_rows, run_id),
        )
        if cur.rowcount != 1:
            raise RuntimeError("Could not finalize the M5 import audit record")
        conn.commit()
        return deleted_rows
    except Exception:
        conn.rollback()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import validated M5 daily sales into isolated NovaLedger forecast tables."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Long-format CSV or CSV.GZ")
    parser.add_argument(
        "--mapping",
        type=Path,
        required=True,
        help="CSV mapping each selected item/store to existing M5 test product/warehouse IDs",
    )
    parser.add_argument(
        "--allow-unmapped",
        action="store_true",
        help="Import only mapped series while validating and skipping the remaining source series",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Explicitly replace existing M5 history for the selected mappings",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Dataset manifest path; defaults to the sidecar next to --input",
    )
    parser.add_argument(
        "--skip-manifest-check",
        action="store_true",
        help="Allow a separately validated long CSV without checking its converter manifest",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5_000,
        help="Rows per committed private staging batch (1-10000, default 5000)",
    )
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 10_000:
        parser.error("--batch-size must be between 1 and 10000")
    if args.skip_manifest_check and args.manifest:
        parser.error("--manifest cannot be combined with --skip-manifest-check")

    conn = None
    lock_acquired = False
    run_id = None
    loaded_rows = 0
    try:
        mappings = load_mapping_file(args.mapping)
        manifest_path = None if args.skip_manifest_check else (args.manifest or default_metadata_path(args.input))
        conn = get_db()
        if args.allow_unmapped:
            # Mapping rows absent from the source are allowed, so validate the
            # schema now and check only source-selected targets after scanning.
            _require_forecast_schema(conn.cursor())
        else:
            # Reject unsafe targets before opening and validating a potentially
            # multi-gigabyte source file. Repeat this check under the import
            # lock before committing mappings or forecast history.
            validate_database_mapping_targets(conn, mappings)
        stage_writer = create_import_stage(conn, args.batch_size)
        summary = validate_input(
            args.input,
            mappings,
            args.allow_unmapped,
            stage_writer=stage_writer,
        )
        dataset_digest = summary["dataset_sha256"]
        manifest = (
            None
            if manifest_path is None
            else validate_manifest(manifest_path, args.input, dataset_digest)
        )
        if manifest is not None:
            coverage = manifest["coverage"]
            if coverage["row_count"] != summary["source_row_count"]:
                raise ValueError("Dataset manifest row count does not match the M5 input")
            if (
                coverage.get("date_start") != summary["date_start"]
                or coverage.get("date_end") != summary["date_end"]
            ):
                raise ValueError(
                    "Dataset manifest date coverage does not match the M5 input"
                )

        selected_mappings = {key: mappings[key] for key in summary["selected_keys"]}
        selected_mapping_digest = mapping_sha256(selected_mappings)
        stage_writer.prepare_scope(
            summary["selected_row_count"], summary["selected_series_count"]
        )
        # Staging is connection-private and safe to perform while forecasts are
        # running. Hold the shared import lock only for durable mapping/history
        # changes so a full-source validation does not unnecessarily block reads.
        acquire_import_lock(conn)
        lock_acquired = True
        if args.allow_unmapped:
            # An allow-unmapped mapping file may intentionally contain targets
            # absent from this source. Validate only the selected subset later.
            _require_forecast_schema(conn.cursor())
        else:
            validate_database_mapping_targets(conn, mappings)
        recovered_runs = reconcile_abandoned_imports(conn)
        if recovered_runs:
            print(
                f"Marked {recovered_runs:,} abandoned M5 import audit run(s) as failed.",
                file=sys.stderr,
            )
        print(
            f"Validated {summary['selected_row_count']:,} selected rows across "
            f"{summary['selected_series_count']:,} series in "
            f"{summary['selected_store_count']:,} stores from {summary['date_start']} "
            f"through {summary['date_end']}",
            file=sys.stderr,
        )
        if summary["skipped_series_count"]:
            print(
                f"Verified and skipped {summary['skipped_row_count']:,} rows in "
                f"{summary['skipped_series_count']:,} unmapped series.",
                file=sys.stderr,
            )

        resolved_mappings = ensure_database_mappings(conn, selected_mappings)
        if set(resolved_mappings) != summary["selected_keys"]:
            raise RuntimeError("Resolved M5 mappings do not match the staged source scope")

        cur = conn.cursor()
        existing_rows = count_existing_history(
            cur, [mapping[0] for mapping in resolved_mappings.values()]
        )
        matching_success = has_matching_successful_import(
            cur, dataset_digest, selected_mapping_digest, summary
        )
        if existing_rows and not args.replace and not matching_success:
            raise ValueError(
                f"{existing_rows:,} existing M5 rows use these mappings. "
                "Use --replace to replace them explicitly, or rerun the same successful import."
            )

        run_id = start_import_run(
            conn,
            dataset_digest,
            selected_mapping_digest,
            args.input,
            manifest_path,
            summary,
            args.replace,
        )
        print(
            "Validated rows are staged; atomically publishing the selected M5 forecast history.",
            file=sys.stderr,
            flush=True,
        )
        deleted_rows = activate_staged_history(
            conn,
            run_id,
            summary["selected_row_count"],
            summary["date_start"],
            summary["date_end"],
            args.replace,
        )
        loaded_rows = summary["selected_row_count"]
        if deleted_rows:
            print(
                f"Pruned {deleted_rows:,} obsolete M5 rows outside the replacement coverage.",
                file=sys.stderr,
            )
        print(
            f"Imported {loaded_rows:,} M5 demand rows in run #{run_id}. Product quantities, "
            "outbound shipments, and stock movements were not modified."
        )
        return 0
    except Exception as exc:
        if conn is not None and run_id is not None:
            try:
                conn.rollback()
                finish_import_run(conn, run_id, "failed", loaded_rows, str(exc))
            except Exception:
                pass
        print(f"M5 forecast import failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            if lock_acquired:
                release_import_lock(conn)
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
