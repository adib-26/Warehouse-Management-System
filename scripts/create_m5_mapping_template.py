"""Create a fill-in mapping CSV from the M5 wide sales source."""

import argparse
import csv
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SALES = ROOT / "datasets" / "m5" / "raw" / "m5-forecasting-accuracy" / "sales_train_evaluation.csv"
DEFAULT_OUTPUT = ROOT / "datasets" / "m5" / "processed" / "m5_mapping.csv"
OUTPUT_COLUMNS = ("item_id", "store_id", "product_id", "warehouse_id")


def create_template(sales_path: Path, output_path: Path, force: bool = False) -> int:
    if not sales_path.is_file():
        raise FileNotFoundError(f"Missing M5 sales source: {sales_path}")
    if sales_path.resolve() == output_path.resolve():
        raise ValueError("Mapping output cannot overwrite the M5 sales source")
    if output_path.exists() and not force:
        raise FileExistsError(f"Mapping file already exists: {output_path} (use --force to replace it)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    series_count = 0
    seen_series = set()
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as temp_file:
            temporary_path = Path(temp_file.name)
            writer = csv.writer(temp_file)
            writer.writerow(OUTPUT_COLUMNS)

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
                    key = (item_id, store_id)
                    if key in seen_series:
                        raise ValueError(f"Duplicate M5 item/store series at row {row_number}: {key}")
                    if len(item_id) > 64 or len(store_id) > 32:
                        raise ValueError(f"M5 identifiers are too long at row {row_number}")
                    seen_series.add(key)
                    writer.writerow((item_id, store_id, "", ""))
                    series_count += 1

        if not series_count:
            raise ValueError("M5 sales source contains no item/store series")
        if output_path.exists() and not force:
            raise FileExistsError(f"Mapping file already exists: {output_path} (use --force to replace it)")
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return series_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an M5 item/store to NovaLedger product/warehouse mapping template."
    )
    parser.add_argument("--sales", type=Path, default=DEFAULT_SALES, help="Original M5 wide sales CSV")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Mapping CSV to create")
    parser.add_argument("--force", action="store_true", help="Replace an existing mapping template")
    args = parser.parse_args()

    try:
        count = create_template(args.sales, args.output, args.force)
    except Exception as exc:
        parser.error(str(exc))
    print(f"Created {count:,} M5 mappings at {args.output}")
    print(
        "Fill product_id and warehouse_id with active NovaLedger M5 test IDs "
        "(is_forecast_test=1) before importing."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
