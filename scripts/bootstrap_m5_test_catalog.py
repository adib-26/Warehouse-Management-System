"""Create isolated M5 test products, test warehouses, and a mapping CSV.

The created records live in NovaLedger's shared products and warehouses tables,
but are marked is_forecast_test=1. They are not available to WMS outbound
transactions and are created with zero inventory.
"""

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SALES = (
    ROOT / "datasets" / "m5" / "raw" / "m5-forecasting-accuracy"
    / "sales_train_evaluation.csv"
)
DEFAULT_OUTPUT = ROOT / "datasets" / "m5" / "processed" / "m5_mapping.csv"
PRODUCT_SKU_PREFIX = "M5-TEST::"
WAREHOUSE_CODE_PREFIX = "M5-TEST::"
MAPPING_COLUMNS = ("item_id", "store_id", "product_id", "warehouse_id")
LOCK_NAME = "novaledger_m5_reference_bootstrap"

sys.path.insert(0, str(ROOT / "scripts"))
from project_env import load_project_env  # noqa: E402

load_project_env(ROOT)
sys.path.insert(0, str(ROOT / "backend"))
from database import get_db  # noqa: E402


def read_series(
    sales_path: Path,
    series_limit: int | None = None,
    sample_items: int | None = None,
) -> list[tuple[str, str]]:
    if not sales_path.is_file():
        raise FileNotFoundError(f"Missing M5 sales source: {sales_path}")
    if series_limit is not None and sample_items is not None:
        raise ValueError("Choose either --series-limit or --sample-items, not both")

    series = []
    seen = set()
    with sales_path.open("r", encoding="utf-8-sig", newline="") as source_file:
        reader = csv.reader(source_file, strict=True)
        headers = next(reader, None)
        if not headers or not {"item_id", "store_id"}.issubset(headers):
            raise ValueError("M5 sales source must contain item_id and store_id columns")
        if len(headers) != len(set(headers)):
            raise ValueError("M5 sales source contains duplicate column names")
        item_index = headers.index("item_id")
        store_index = headers.index("store_id")

        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(headers):
                raise ValueError(f"Malformed M5 sales row {row_number}")
            item_id = row[item_index].strip()
            store_id = row[store_index].strip()
            if not item_id or not store_id:
                raise ValueError(f"Missing item_id or store_id in M5 sales row {row_number}")
            if len(item_id) > 64 or len(store_id) > 32:
                raise ValueError(f"M5 identifiers are too long in sales row {row_number}")
            key = (item_id, store_id)
            if key in seen:
                raise ValueError(f"Duplicate M5 item/store series at row {row_number}: {key}")
            seen.add(key)
            series.append(key)
            if series_limit is not None and len(series) >= series_limit:
                break

    if not series:
        raise ValueError("M5 sales source contains no item/store series")
    if sample_items is not None:
        items_in_source_order = list(dict.fromkeys(item_id for item_id, _ in series))
        if sample_items < 1 or sample_items > len(items_in_source_order):
            raise ValueError(
                f"--sample-items must be between 1 and {len(items_in_source_order)}"
            )
        if sample_items == 1:
            selected_indices = {len(items_in_source_order) // 2}
        else:
            selected_indices = {
                position * (len(items_in_source_order) - 1) // (sample_items - 1)
                for position in range(sample_items)
            }
        selected_items = {
            item_id
            for index, item_id in enumerate(items_in_source_order)
            if index in selected_indices
        }
        series = [
            (item_id, store_id)
            for item_id, store_id in series
            if item_id in selected_items
        ]
    return series


def chunks(values, size):
    values = list(values)
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def acquire_lock(conn):
    row = conn.execute("SELECT GET_LOCK(?, 60) AS acquired", (LOCK_NAME,)).fetchone()
    if row is None or int(row["acquired"] or 0) != 1:
        raise RuntimeError("Could not acquire the M5 test catalog bootstrap lock")


def release_lock(conn):
    try:
        conn.execute("SELECT RELEASE_LOCK(?)", (LOCK_NAME,))
    except Exception:
        pass


def require_schema(cur):
    try:
        cur.execute("SELECT is_forecast_test FROM products LIMIT 0")
        cur.execute("SELECT is_forecast_test FROM warehouses LIMIT 0")
    except Exception as exc:
        raise RuntimeError(
            "The NovaLedger forecast schema with M5 test-record support is required. "
            "Start the backend once to apply migrations before bootstrapping M5 "
            "test records."
        ) from exc


def validate_mapping_output_path(sales_path: Path, output_path: Path, force: bool):
    """Reject unsafe mapping targets before catalog records are changed."""

    if sales_path.resolve() == output_path.resolve():
        raise ValueError("Mapping output cannot overwrite the M5 sales source")
    if output_path.exists() or output_path.is_symlink():
        if not output_path.is_file():
            raise ValueError(
                "Mapping output path must be a regular file or a new path: "
                f"{output_path}"
            )
        if not force:
            raise FileExistsError(
                f"Mapping file already exists: {output_path} (use --force to replace it)"
            )
    if output_path.parent.exists() and not output_path.parent.is_dir():
        raise ValueError(
            "Mapping output parent must be a directory or a new path: "
            f"{output_path.parent}"
        )


def existing_products(cur, skus: list[str]) -> dict:
    result = {}
    for batch in chunks(skus, 1_000):
        placeholders = ", ".join(["?"] * len(batch))
        rows = cur.execute(
            f"""
            SELECT id, sku, quantity, archived, deleted, is_forecast_test
            FROM products
            WHERE sku IN ({placeholders})
            """,
            batch,
        ).fetchall()
        result.update({row["sku"]: row for row in rows})
    return result


def existing_warehouses(cur, codes: list[str]) -> dict:
    result = {}
    for batch in chunks(codes, 1_000):
        placeholders = ", ".join(["?"] * len(batch))
        rows = cur.execute(
            f"""
            SELECT id, warehouse_code, active, is_forecast_test
            FROM warehouses
            WHERE warehouse_code IN ({placeholders})
            """,
            batch,
        ).fetchall()
        result.update({row["warehouse_code"]: row for row in rows})
    return result


def write_mapping(
    sales_path: Path, path: Path, series, product_ids, warehouse_ids, force: bool
):
    validate_mapping_output_path(sales_path, path, force)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temp_file:
            temporary_path = Path(temp_file.name)
            writer = csv.writer(temp_file)
            writer.writerow(MAPPING_COLUMNS)
            for item_id, store_id in series:
                writer.writerow(
                    (item_id, store_id, product_ids[item_id], warehouse_ids[store_id])
                )
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def bootstrap(
    sales_path: Path,
    output_path: Path,
    force: bool,
    dry_run: bool,
    series_limit: int | None,
    sample_items: int | None,
) -> dict:
    series = read_series(sales_path, series_limit, sample_items)
    item_ids = sorted({item_id for item_id, _ in series})
    store_ids = sorted({store_id for _, store_id in series})
    product_skus = {item_id: f"{PRODUCT_SKU_PREFIX}{item_id}" for item_id in item_ids}
    warehouse_codes = {store_id: f"{WAREHOUSE_CODE_PREFIX}{store_id}" for store_id in store_ids}
    if any(len(sku) > 128 for sku in product_skus.values()):
        raise ValueError("A generated M5 test product SKU exceeds 128 characters")
    if any(len(code) > 64 for code in warehouse_codes.values()):
        raise ValueError("A generated M5 test warehouse code exceeds 64 characters")
    legacy_skus_by_item = {
        item_id: sorted(
            {
                f"{source_item}_{store_id}"
                for source_item, store_id in series
                if source_item == item_id
            }
        )
        for item_id in item_ids
    }
    all_product_skus = sorted(
        set(product_skus.values())
        | {sku for candidates in legacy_skus_by_item.values() for sku in candidates}
    )
    validate_mapping_output_path(sales_path, output_path, force)
    if dry_run:
        return {
            "series_count": len(series),
            "item_count": len(item_ids),
            "store_count": len(store_ids),
            "output": output_path,
        }

    conn = get_db()
    locked = False
    try:
        acquire_lock(conn)
        locked = True
        cur = conn.cursor()
        require_schema(cur)

        products = existing_products(cur, all_product_skus)
        product_ids = {}
        items_to_create = []
        for item_id in item_ids:
            canonical = products.get(product_skus[item_id])
            if canonical is not None:
                if (
                    not canonical["is_forecast_test"]
                    or canonical["deleted"]
                    or canonical["archived"]
                ):
                    raise ValueError(
                        "Existing canonical M5 product conflicts with test isolation: "
                        + product_skus[item_id]
                    )
                product_ids[item_id] = int(canonical["id"])
                continue

            legacy = next(
                (
                    products[sku]
                    for sku in legacy_skus_by_item[item_id]
                    if sku in products
                    and products[sku]["is_forecast_test"]
                    and not products[sku]["deleted"]
                    and not products[sku]["archived"]
                ),
                None,
            )
            if legacy is not None:
                # Preserve quantities on legacy M5 demo products while keeping
                # the records isolated from all operational inventory routes.
                product_ids[item_id] = int(legacy["id"])
            else:
                items_to_create.append(item_id)

        product_rows = [
            (
                f"M5 test product {item_id}",
                product_skus[item_id],
                f"Synthetic M5 forecasting reference record for {item_id}.",
                "M5 experiment",
                "m5,forecast-test",
                0,
                0,
                1,
            )
            for item_id in items_to_create
        ]
        for batch in chunks(product_rows, 1_000):
            cur.executemany(
                """
                INSERT INTO products
                    (name, sku, description, category, tags, quantity, low_stock, is_forecast_test)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE id = id
                """,
                batch,
            )
        products.update(
            existing_products(cur, [product_skus[item_id] for item_id in items_to_create])
        )
        for item_id in items_to_create:
            product = products.get(product_skus[item_id])
            if (
                product is None
                or not product["is_forecast_test"]
                or product["deleted"]
                or product["archived"]
                or product["quantity"] != 0
            ):
                raise ValueError(
                    "Could not create an isolated zero-stock M5 test product: "
                    + product_skus[item_id]
                )
            product_ids[item_id] = int(product["id"])

        warehouse_rows = [
            (
                warehouse_codes[store_id],
                f"M5 test warehouse {store_id}",
                f"Synthetic M5 forecasting reference location for {store_id}.",
                1,
                1,
            )
            for store_id in store_ids
        ]
        for batch in chunks(warehouse_rows, 1_000):
            cur.executemany(
                """
                INSERT INTO warehouses
                    (warehouse_code, name, address, active, is_forecast_test)
                VALUES (?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE id = id
                """,
                batch,
            )

        warehouses = existing_warehouses(cur, list(warehouse_codes.values()))
        invalid_warehouses = [
            code
            for code, row in warehouses.items()
            if not row["is_forecast_test"] or not row["active"]
        ]
        missing_warehouses = sorted(set(warehouse_codes.values()) - set(warehouses))
        if missing_warehouses or invalid_warehouses:
            preview = (missing_warehouses + invalid_warehouses)[:5]
            raise ValueError(
                "Existing warehouse records conflict with M5 test isolation: "
                + ", ".join(preview)
            )

        warehouse_ids = {
            store_id: int(warehouses[code]["id"])
            for store_id, code in warehouse_codes.items()
        }
        conn.commit()
        write_mapping(sales_path, output_path, series, product_ids, warehouse_ids, force)
        return {
            "series_count": len(series),
            "item_count": len(item_ids),
            "store_count": len(store_ids),
            "output": output_path,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        if locked:
            release_lock(conn)
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create safe M5 test products, warehouses, and a populated mapping CSV."
    )
    parser.add_argument("--sales", type=Path, default=DEFAULT_SALES, help="M5 wide sales CSV")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Mapping CSV to create")
    parser.add_argument("--force", action="store_true", help="Replace an existing mapping CSV")
    parser.add_argument(
        "--series-limit",
        type=int,
        help="Create only the first N M5 series for a small initial experiment",
    )
    parser.add_argument(
        "--sample-items",
        type=int,
        help=(
            "Select N approximately evenly spaced M5 items across the catalog; "
            "include each selected item in every store"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the source and show the records that would be created",
    )
    args = parser.parse_args()

    try:
        if args.series_limit is not None and args.series_limit < 1:
            parser.error("--series-limit must be at least 1")
        if args.sample_items is not None and args.sample_items < 1:
            parser.error("--sample-items must be at least 1")
        if args.series_limit is not None and args.sample_items is not None:
            parser.error("--series-limit and --sample-items cannot be combined")
        summary = bootstrap(
            args.sales,
            args.output,
            args.force,
            args.dry_run,
            args.series_limit,
            args.sample_items,
        )
    except Exception as exc:
        print(f"M5 test catalog bootstrap failed: {exc}", file=sys.stderr)
        return 1
    action = "Would create" if args.dry_run else "Created or reused"
    print(
        f"{action} {summary['item_count']:,} M5 test products, "
        f"{summary['store_count']:,} M5 test warehouses, and "
        f"{summary['series_count']:,} mappings."
    )
    if args.dry_run:
        print(f"Mapping output: {summary['output']}")
    else:
        print(f"Wrote mapping CSV: {summary['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
