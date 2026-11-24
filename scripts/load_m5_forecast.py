"""Load a validated M5 long CSV into NovaLedger forecast tables.

This script writes only forecast_m5_mappings, forecast_m5_imports, and
forecast_demand_history. It never changes stock, shipments, or movements.
"""

import argparse
import csv
import gzip
import hashlib
import json
import sys
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
DELETE_MAPPING_BATCH_SIZE = 100
IMPORT_LOCK_NAME = "novaledger_m5_forecast_import"

sys.path.insert(0, str(ROOT / "backend"))
from database import get_db  # noqa: E402


def open_csv(path: Path):
    if path.name.lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


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
) -> dict:
    """Validate every source series and retain summary for mapped series only."""
    if not path.is_file():
        raise FileNotFoundError(f"Missing processed M5 CSV: {path}")

    source_series = None
    source_selected = False
    source_dates = []
    previous_date = None
    all_reference_dates = None
    seen_source_series = set()
    selected_series = set()
    source_row_count = 0
    selected_row_count = 0
    skipped_row_count = 0
    skipped_series_count = 0

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

    with open_csv(path) as source_file:
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
            parse_daily_sales(quantity_text, row_number)
            source_row_count += 1
            if source_selected:
                selected_row_count += 1
            else:
                skipped_row_count += 1

    all_reference_dates = finish_series(
        source_series, source_dates, all_reference_dates
    )
    if not source_row_count or not selected_series or not all_reference_dates:
        raise ValueError("Processed M5 CSV contains no mapped daily sales rows")
    unused_mappings = set(mappings) - selected_series
    if unused_mappings and not allow_unmapped:
        preview = ", ".join(f"{item}/{store}" for item, store in sorted(unused_mappings)[:3])
        raise ValueError(
            f"Mapping CSV contains series absent from the input, including {preview}"
        )

    return {
        "source_series_count": len(seen_source_series),
        "selected_series_count": len(selected_series),
        "skipped_series_count": skipped_series_count,
        "source_row_count": source_row_count,
        "selected_row_count": selected_row_count,
        "skipped_row_count": skipped_row_count,
        "date_start": all_reference_dates[0],
        "date_end": all_reference_dates[-1],
        "date_count": len(all_reference_dates),
        "selected_keys": selected_series,
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
            "Forecast schema version 5 is required. Start the NovaLedger backend "
            "once to apply migrations before importing M5 data."
        ) from exc


def ensure_database_mappings(conn, mappings: dict) -> dict:
    """Verify sandbox targets and materialize immutable source mappings."""
    cur = conn.cursor()
    try:
        _require_forecast_schema(cur)
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

        database_mappings = {
            (row["item_id"], row["store_id"]): (
                int(row["id"]),
                int(row["product_id"]),
                int(row["warehouse_id"]),
            )
            for row in cur.execute(
                "SELECT id, item_id, store_id, product_id, warehouse_id "
                "FROM forecast_m5_mappings"
            ).fetchall()
        }
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
        WHERE id=?
        """,
        (status, loaded_rows, error, run_id),
    )
    conn.commit()


def delete_stale_history_after_replace(
    conn, mapping_ids, date_start: str, date_end: str
) -> int:
    """Prune only obsolete dates after all replacement rows were written safely."""
    deleted_rows = 0
    cur = conn.cursor()
    for batch in _ids_in_batches(mapping_ids, DELETE_MAPPING_BATCH_SIZE):
        placeholders = ", ".join(["?"] * len(batch))
        cur.execute(
            f"""
            DELETE FROM forecast_demand_history
            WHERE source='M5'
              AND m5_mapping_id IN ({placeholders})
              AND (demand_date < ? OR demand_date > ?)
            """,
            batch + [date_start, date_end],
        )
        deleted_rows += cur.rowcount
        conn.commit()
    return deleted_rows


def import_rows(
    conn,
    path: Path,
    mappings: dict,
    expected_rows: int,
    batch_size: int,
) -> int:
    cur = conn.cursor()
    insert_sql = """
        INSERT INTO forecast_demand_history
            (product_id, warehouse_id, demand_date, quantity_sold, source, m5_mapping_id)
        VALUES (?, ?, ?, ?, 'M5', ?) AS incoming
        ON DUPLICATE KEY UPDATE
            quantity_sold = incoming.quantity_sold,
            m5_mapping_id = incoming.m5_mapping_id
    """
    batch = []
    loaded_rows = 0

    try:
        with open_csv(path) as source_file:
            reader = csv.reader(source_file, strict=True)
            if next(reader, None) != list(OUTPUT_COLUMNS):
                raise ValueError("Processed M5 CSV header changed after validation")
            for row_number, row in enumerate(reader, start=2):
                if len(row) != len(OUTPUT_COLUMNS):
                    raise ValueError(f"Malformed processed M5 row {row_number}")
                item_id, store_id, date_text, quantity_text = row
                mapping = mappings.get((item_id, store_id))
                if mapping is None:
                    continue
                mapping_id, product_id, warehouse_id = mapping
                batch.append(
                    (
                        product_id,
                        warehouse_id,
                        parse_date(date_text, row_number),
                        parse_daily_sales(quantity_text, row_number),
                        mapping_id,
                    )
                )
                if len(batch) >= batch_size:
                    cur.executemany(insert_sql, batch)
                    conn.commit()
                    loaded_rows += len(batch)
                    batch.clear()
                    if loaded_rows % 100_000 == 0:
                        print(
                            f"Loaded {loaded_rows:,} of {expected_rows:,} M5 daily rows",
                            file=sys.stderr,
                            flush=True,
                        )
        if batch:
            cur.executemany(insert_sql, batch)
            conn.commit()
            loaded_rows += len(batch)
        if loaded_rows != expected_rows:
            raise ValueError(
                f"Input changed during import: expected {expected_rows:,} rows, "
                f"loaded {loaded_rows:,}"
            )
    except Exception:
        conn.rollback()
        raise
    return loaded_rows


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
        help="Rows per committed upsert batch (1-10000, default 5000)",
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
        dataset_digest = sha256_file(args.input)
        manifest_path = None if args.skip_manifest_check else (args.manifest or default_metadata_path(args.input))
        manifest = (
            None
            if manifest_path is None
            else validate_manifest(manifest_path, args.input, dataset_digest)
        )
        summary = validate_input(args.input, mappings, args.allow_unmapped)
        if manifest is not None:
            coverage = manifest["coverage"]
            if coverage["row_count"] != summary["source_row_count"]:
                raise ValueError("Dataset manifest row count does not match the M5 input")
            if coverage.get("date_start") != summary["date_start"] or coverage.get("date_end") != summary["date_end"]:
                raise ValueError("Dataset manifest date coverage does not match the M5 input")
        if sha256_file(args.input) != dataset_digest:
            raise ValueError("Processed M5 input changed during preflight validation")

        selected_mappings = {key: mappings[key] for key in summary["selected_keys"]}
        selected_mapping_digest = mapping_sha256(selected_mappings)
        print(
            f"Validated {summary['selected_row_count']:,} mapped rows across "
            f"{summary['selected_series_count']:,} series from {summary['date_start']} "
            f"through {summary['date_end']}",
            file=sys.stderr,
        )
        if summary["skipped_series_count"]:
            print(
                f"Skipping {summary['skipped_row_count']:,} rows in "
                f"{summary['skipped_series_count']:,} unmapped series.",
                file=sys.stderr,
            )

        conn = get_db()
        acquire_import_lock(conn)
        lock_acquired = True
        resolved_mappings = ensure_database_mappings(conn, selected_mappings)
        if sha256_file(args.input) != dataset_digest:
            raise ValueError("Processed M5 input changed before import")

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
        if sha256_file(args.input) != dataset_digest:
            raise ValueError("Processed M5 input changed before write")
        loaded_rows = import_rows(
            conn,
            args.input,
            resolved_mappings,
            summary["selected_row_count"],
            args.batch_size,
        )
        if sha256_file(args.input) != dataset_digest:
            raise ValueError(
                "Processed M5 input changed during import; rerun with --replace using a stable input"
            )
        if args.replace:
            deleted_rows = delete_stale_history_after_replace(
                conn,
                [mapping[0] for mapping in resolved_mappings.values()],
                summary["date_start"],
                summary["date_end"],
            )
            if deleted_rows:
                print(
                    f"Pruned {deleted_rows:,} obsolete M5 rows outside the replacement coverage.",
                    file=sys.stderr,
                )
        finish_import_run(conn, run_id, "success", loaded_rows)
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
