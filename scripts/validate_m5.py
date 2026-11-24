"""Validate a long-format M5 dataset against its wide source and calendar."""

import argparse
import csv
import gzip
import json
import sys
from pathlib import Path

from prepare_m5 import (
    DEFAULT_CALENDAR,
    DEFAULT_OUTPUT,
    DEFAULT_SALES,
    DAY_COLUMN,
    OUTPUT_COLUMNS,
    default_metadata_path,
    display_path,
    load_day_to_date,
    sha256_file,
    validate_and_enrich_day_columns,
)


def open_csv(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def parse_quantity(value: str, filename: str, row_number: int) -> int:
    try:
        quantity = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid sales quantity in {filename} at row {row_number}: {value!r}"
        ) from exc
    if quantity < 0:
        raise ValueError(
            f"Negative sales quantity in {filename} at row {row_number}: {quantity}"
        )
    return quantity


def check_equal(label: str, actual, expected) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: expected {expected!r}, found {actual!r}")


def load_and_check_manifest(
    manifest_path: Path,
    output_path: Path,
    sales_path: Path,
    calendar_path: Path,
) -> dict | None:
    if not manifest_path.exists():
        return None
    if not manifest_path.is_file():
        raise ValueError(f"Manifest path is not a regular file: {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read dataset manifest {manifest_path}: {exc}") from exc

    expected_columns = list(OUTPUT_COLUMNS)
    actual_columns = [column.get("name") for column in manifest.get("columns", [])]
    check_equal("Manifest column order", actual_columns, expected_columns)
    check_equal(
        "Manifest output path",
        manifest.get("output", {}).get("file"),
        display_path(output_path),
    )
    check_equal(
        "Manifest output SHA-256",
        manifest.get("output", {}).get("sha256"),
        sha256_file(output_path),
    )
    check_equal(
        "Manifest sales source path",
        manifest.get("source", {}).get("sales_file"),
        display_path(sales_path),
    )
    check_equal(
        "Manifest sales source SHA-256",
        manifest.get("source", {}).get("sales_file_sha256"),
        sha256_file(sales_path),
    )
    check_equal(
        "Manifest calendar source path",
        manifest.get("source", {}).get("calendar_file"),
        display_path(calendar_path),
    )
    check_equal(
        "Manifest calendar source SHA-256",
        manifest.get("source", {}).get("calendar_file_sha256"),
        sha256_file(calendar_path),
    )
    return manifest


def validate_dataset(
    sales_path: Path,
    calendar_path: Path,
    output_path: Path,
    metadata_path: Path | None = None,
) -> dict:
    for path in (sales_path, calendar_path, output_path):
        if not path.is_file():
            raise FileNotFoundError(f"Missing input file: {path}")

    manifest_path = metadata_path or default_metadata_path(output_path)
    if metadata_path is not None and not manifest_path.is_file():
        raise FileNotFoundError(f"Missing dataset manifest: {manifest_path}")
    manifest = load_and_check_manifest(
        manifest_path, output_path, sales_path, calendar_path
    )

    day_to_date = load_day_to_date(calendar_path)
    series_count = 0
    row_count = 0
    zero_sales_row_count = 0
    total_units = 0
    min_units = None
    max_units = None
    item_ids = set()
    store_ids = set()
    series_keys = set()
    prior_output_key = None

    with open_csv(sales_path) as source_file, open_csv(output_path) as output_file:
        source_reader = csv.reader(source_file, strict=True)
        output_reader = csv.reader(output_file, strict=True)
        source_headers = next(source_reader, None)
        output_headers = next(output_reader, None)
        if not source_headers:
            raise ValueError("M5 sales source is empty")
        check_equal("Processed dataset header", output_headers, list(OUTPUT_COLUMNS))
        if len(source_headers) != len(set(source_headers)):
            raise ValueError("M5 sales source contains duplicate column names")
        if not {"item_id", "store_id"}.issubset(source_headers):
            raise ValueError("M5 sales source must contain item_id and store_id columns")

        item_index = source_headers.index("item_id")
        store_index = source_headers.index("store_id")
        day_columns = sorted(
            (
                (name, index)
                for index, name in enumerate(source_headers)
                if DAY_COLUMN.fullmatch(name)
            ),
            key=lambda column: int(column[0][2:]),
        )
        day_columns = validate_and_enrich_day_columns(day_columns, day_to_date)
        expected_dates = [sale_date for _, sale_date, _ in day_columns]

        for source_row in source_reader:
            source_line = source_reader.line_num
            if not source_row:
                raise ValueError(f"Empty source sales row {source_line}")
            if len(source_row) != len(source_headers):
                raise ValueError(
                    f"Malformed source row {source_line}: expected {len(source_headers)} "
                    f"fields, found {len(source_row)}"
                )

            item_id = source_row[item_index]
            store_id = source_row[store_index]
            if not item_id or not store_id:
                raise ValueError(f"Missing item_id or store_id in source row {source_line}")
            series_key = (item_id, store_id)
            if series_key in series_keys:
                raise ValueError(f"Duplicate source item/store series at row {source_line}: {series_key}")
            series_keys.add(series_key)
            item_ids.add(item_id)
            store_ids.add(store_id)

            for day, expected_date, source_index in day_columns:
                output_row = next(output_reader, None)
                if output_row is None:
                    raise ValueError(
                        f"Processed dataset ends before {item_id}/{store_id}/{expected_date}"
                    )
                output_line = output_reader.line_num
                if not output_row:
                    raise ValueError(f"Empty processed data row {output_line}")
                if len(output_row) != len(OUTPUT_COLUMNS):
                    raise ValueError(
                        f"Malformed processed row {output_line}: expected 4 fields, "
                        f"found {len(output_row)}"
                    )

                actual_item, actual_store, actual_date, actual_quantity_text = output_row
                actual_key = (actual_item, actual_store, actual_date)
                if actual_key == prior_output_key:
                    raise ValueError(f"Duplicate item/store/date combination at row {output_line}: {actual_key}")
                expected_key = (item_id, store_id, expected_date)
                if actual_key != expected_key:
                    raise ValueError(
                        f"Date mapping, series order, coverage, or duplicate-row error "
                        f"at processed row {output_line}: expected {expected_key!r}, "
                        f"found {actual_key!r}"
                    )
                prior_output_key = actual_key

                expected_quantity = parse_quantity(
                    source_row[source_index], str(sales_path), source_line
                )
                actual_quantity = parse_quantity(
                    actual_quantity_text, str(output_path), output_line
                )
                check_equal(
                    f"Sales quantity for {item_id}/{store_id}/{day}",
                    actual_quantity,
                    expected_quantity,
                )
                total_units += actual_quantity
                zero_sales_row_count += actual_quantity == 0
                min_units = (
                    actual_quantity
                    if min_units is None
                    else min(min_units, actual_quantity)
                )
                max_units = (
                    actual_quantity
                    if max_units is None
                    else max(max_units, actual_quantity)
                )
                row_count += 1

            series_count += 1
            if series_count % 1_000 == 0:
                print(
                    f"Validated {series_count:,} series ({row_count:,} daily rows)",
                    file=sys.stderr,
                    flush=True,
                )

        extra_row = next(output_reader, None)
        if extra_row is not None:
            raise ValueError(
                f"Processed dataset has extra data after the final expected row "
                f"(processed row {output_reader.line_num})"
            )

    if series_count == 0 or row_count == 0:
        raise ValueError("No item/store/date observations were validated")
    check_equal("Processed row count", row_count, series_count * len(expected_dates))

    coverage = {
        "series_count": series_count,
        "item_count": len(item_ids),
        "store_count": len(store_ids),
        "row_count": row_count,
        "day_count": len(day_columns),
        "day_start": day_columns[0][0],
        "day_end": day_columns[-1][0],
        "date_start": expected_dates[0],
        "date_end": expected_dates[-1],
    }
    sales_summary = {
        "total_units": total_units,
        "zero_sales_row_count": zero_sales_row_count,
        "nonzero_sales_row_count": row_count - zero_sales_row_count,
        "min_units": min_units,
        "max_units": max_units,
    }
    if manifest is not None:
        check_equal("Manifest coverage", manifest.get("coverage"), coverage)
        check_equal(
            "Manifest sales summary",
            manifest.get("daily_sales_summary"),
            sales_summary,
        )

    return {
        "status": "passed",
        "manifest_verified": manifest is not None,
        "checks": {
            "duplicate_item_store_date_combinations": "passed",
            "calendar_date_mapping": "passed",
            "nonnegative_integer_sales": "passed",
            "complete_date_coverage_for_every_series": "passed",
            "zero_sales_days_preserved_and_matched_to_source": "passed",
        },
        "coverage": coverage,
        "sales_summary": {
            **sales_summary,
            "mean_daily_sales_including_zero_days": total_units / row_count,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT, help="Long-format CSV or CSV.gz")
    parser.add_argument("--sales", type=Path, default=DEFAULT_SALES, help="Original M5 sales CSV")
    parser.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR, help="M5 calendar CSV")
    parser.add_argument("--metadata", type=Path, help="Manifest path; defaults to the input sidecar if present")
    args = parser.parse_args()

    report = validate_dataset(args.sales, args.calendar, args.input, args.metadata)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
