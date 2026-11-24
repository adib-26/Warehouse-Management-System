"""Convert M5's wide daily sales file into a forecasting-ready long CSV."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "datasets" / "m5" / "raw" / "m5-forecasting-accuracy"
DEFAULT_SALES = RAW / "sales_train_evaluation.csv"
DEFAULT_CALENDAR = RAW / "calendar.csv"
DEFAULT_OUTPUT = ROOT / "datasets" / "m5" / "processed" / "m5_daily_sales.csv.gz"
HASH_CHUNK_BYTES = 1024 * 1024

OUTPUT_COLUMNS = ("item_id", "store_id", "date", "daily_sales")
DAY_COLUMN = re.compile(r"^d_(\d+)$")
DEFAULT_COMPRESSION_LEVEL = 6


def load_day_to_date(calendar_path: Path) -> dict[str, str]:
    with calendar_path.open("r", encoding="utf-8-sig", newline="") as calendar_file:
        reader = csv.DictReader(calendar_file, strict=True)
        if not reader.fieldnames or not {"d", "date"}.issubset(reader.fieldnames):
            raise ValueError("Calendar CSV must contain 'd' and 'date' columns")

        day_to_date = {}
        date_to_day = {}
        for row in reader:
            day = row["d"]
            sale_date = date.fromisoformat(row["date"]).isoformat()
            if not day:
                raise ValueError("Calendar CSV contains an empty day identifier")
            if day in day_to_date:
                raise ValueError(f"Duplicate day identifier in calendar: {day}")
            if sale_date in date_to_day:
                raise ValueError(
                    f"Duplicate calendar date {sale_date} for {date_to_day[sale_date]} and {day}"
                )
            day_to_date[day] = sale_date
            date_to_day[sale_date] = day

    if not day_to_date:
        raise ValueError("Calendar CSV contains no dates")
    return day_to_date


def default_metadata_path(output_path: Path) -> Path:
    """Return a stable sidecar filename for a CSV or gzipped CSV output."""
    name = output_path.name
    if name.endswith(".csv.gz"):
        name = name[: -len(".csv.gz")]
    else:
        name = output_path.stem
    return output_path.with_name(f"{name}.metadata.json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        while block := source_file.read(HASH_CHUNK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    """Use a project-relative path in metadata whenever possible."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


@contextmanager
def open_output(path: Path, compressed: bool, compression_level: int):
    if compressed:
        with path.open("wb") as raw_file:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_file,
                compresslevel=compression_level,
                mtime=0,
            ) as compressed_file:
                with io.TextIOWrapper(
                    compressed_file,
                    encoding="utf-8",
                    newline="",
                ) as output_file:
                    yield output_file
    else:
        with path.open("w", encoding="utf-8", newline="") as output_file:
            yield output_file


def validate_and_enrich_day_columns(
    day_columns: list[tuple[str, int]], day_to_date: dict[str, str]
) -> list[tuple[str, str, int]]:
    """Validate the M5 day axis and attach each source column's sale date."""
    if not day_columns:
        raise ValueError("Sales CSV contains no daily columns named d_1, d_2, ...")

    day_numbers = [int(DAY_COLUMN.fullmatch(day).group(1)) for day, _ in day_columns]
    if day_numbers[0] != 1:
        raise ValueError("M5 sales day identifiers must start at d_1")
    for previous, current in zip(day_numbers, day_numbers[1:]):
        if current != previous + 1:
            raise ValueError(
                f"Sales day columns are not consecutive: d_{previous}, d_{current}"
            )

    missing_days = [day for day, _ in day_columns if day not in day_to_date]
    if missing_days:
        preview = ", ".join(missing_days[:5])
        raise ValueError(f"Calendar is missing sales day identifiers: {preview}")

    enriched_columns = [
        (day, day_to_date[day], index) for day, index in day_columns
    ]
    previous_date = None
    for day, sale_date, _ in enriched_columns:
        current_date = date.fromisoformat(sale_date)
        if previous_date is not None and current_date != previous_date + timedelta(days=1):
            raise ValueError(
                f"Calendar dates are not consecutive between {previous_day} and {day}"
            )
        previous_day = day
        previous_date = current_date

    return enriched_columns


def build_metadata(
    *,
    sales_path: Path,
    sales_sha256: str,
    calendar_path: Path,
    calendar_sha256: str,
    output_path: Path,
    output_sha256: str,
    compression_level: int,
    day_columns: list[tuple[str, str, int]],
    series_count: int,
    item_count: int,
    store_count: int,
    daily_row_count: int,
    total_daily_sales: int,
    zero_daily_sales: int,
    min_daily_sales: int,
    max_daily_sales: int,
) -> dict:
    compressed = output_path.suffix.lower() == ".gz"
    return {
        "schema_version": 1,
        "dataset": {
            "description": "M5 daily unit sales in forecasting-ready long format.",
            "row_order": ["source series order", "date ascending within each series"],
        },
        "columns": [
            {
                "name": "item_id",
                "type": "string",
                "nullable": False,
                "description": "M5 product identifier.",
            },
            {
                "name": "store_id",
                "type": "string",
                "nullable": False,
                "description": "M5 store identifier.",
            },
            {
                "name": "date",
                "type": "date (ISO 8601)",
                "nullable": False,
                "description": "Calendar date mapped from the M5 d_n identifier.",
            },
            {
                "name": "daily_sales",
                "type": "integer",
                "nullable": False,
                "description": "Units sold for the item and store on the date; zeroes are retained.",
            },
        ],
        "source": {
            "sales_file": display_path(sales_path),
            "sales_file_sha256": sales_sha256,
            "calendar_file": display_path(calendar_path),
            "calendar_file_sha256": calendar_sha256,
        },
        "coverage": {
            "series_count": series_count,
            "item_count": item_count,
            "store_count": store_count,
            "row_count": daily_row_count,
            "day_count": len(day_columns),
            "day_start": day_columns[0][0],
            "day_end": day_columns[-1][0],
            "date_start": day_columns[0][1],
            "date_end": day_columns[-1][1],
        },
        "daily_sales_summary": {
            "total_units": total_daily_sales,
            "zero_sales_row_count": zero_daily_sales,
            "nonzero_sales_row_count": daily_row_count - zero_daily_sales,
            "min_units": min_daily_sales,
            "max_units": max_daily_sales,
        },
        "output": {
            "file": display_path(output_path),
            "sha256": output_sha256,
            "format": "csv",
            "compression": {
                "algorithm": "gzip" if compressed else None,
                "level": compression_level if compressed else None,
            },
        },
    }


def write_json_temp(destination: Path, contents: dict) -> Path:
    """Write deterministic JSON to a same-directory temporary file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)
        json.dump(contents, temp_file, indent=2, sort_keys=True)
        temp_file.write("\n")
    os.chmod(temp_path, 0o644)
    return temp_path


def ensure_regular_file_or_absent(path: Path, label: str) -> None:
    if path.exists() and not path.is_file():
        raise ValueError(f"{label} path must be a regular file or a new path: {path}")


def move_aside(path: Path) -> Path | None:
    """Move an existing sidecar out of its live location until replacement succeeds."""
    if not path.exists():
        return None
    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{path.name}.previous.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    ) as temp_file:
        backup_path = Path(temp_file.name)
    try:
        os.replace(path, backup_path)
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise
    return backup_path


def prepare_dataset(
    sales_path: Path,
    calendar_path: Path,
    output_path: Path,
    compression_level: int = DEFAULT_COMPRESSION_LEVEL,
    metadata_path: Path | None = None,
) -> tuple[int, int]:
    if not 1 <= compression_level <= 9:
        raise ValueError("Compression level must be between 1 and 9")
    for path in (sales_path, calendar_path):
        if not path.is_file():
            raise FileNotFoundError(f"Missing input file: {path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    default_sidecar_path = default_metadata_path(output_path)
    if output_path.resolve() in {sales_path.resolve(), calendar_path.resolve()}:
        raise ValueError("Output path must be different from both input files")
    if metadata_path is not None and metadata_path.resolve() in {
        sales_path.resolve(),
        calendar_path.resolve(),
        output_path.resolve(),
    }:
        raise ValueError("Metadata path must be different from input and output files")
    ensure_regular_file_or_absent(output_path, "Output")
    ensure_regular_file_or_absent(default_sidecar_path, "Default metadata")
    if metadata_path is not None:
        ensure_regular_file_or_absent(metadata_path, "Metadata")

    source_hashes = None
    if metadata_path is not None:
        source_hashes = {
            "sales": sha256_file(sales_path),
            "calendar": sha256_file(calendar_path),
        }
    day_to_date = load_day_to_date(calendar_path)
    daily_row_count = 0
    series_count = 0
    total_daily_sales = 0
    zero_daily_sales = 0
    min_daily_sales = None
    max_daily_sales = None
    item_ids = set()
    store_ids = set()
    temp_path = None
    metadata_temp_path = None
    manifest_backups = []
    output_replaced = False

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)

        with sales_path.open("r", encoding="utf-8-sig", newline="") as sales_file:
            reader = csv.reader(sales_file, strict=True)
            headers = next(reader, None)
            if not headers:
                raise ValueError("Sales CSV is empty")
            if len(headers) != len(set(headers)):
                raise ValueError("Sales CSV contains duplicate column names")
            if not {"item_id", "store_id"}.issubset(headers):
                raise ValueError("Sales CSV must contain 'item_id' and 'store_id' columns")

            item_id_index = headers.index("item_id")
            store_id_index = headers.index("store_id")
            day_columns = sorted(
                (
                    (column, index)
                    for index, column in enumerate(headers)
                    if DAY_COLUMN.fullmatch(column)
                ),
                key=lambda item: int(DAY_COLUMN.fullmatch(item[0]).group(1)),
            )
            day_columns = validate_and_enrich_day_columns(day_columns, day_to_date)
            with open_output(
                temp_path,
                output_path.suffix.lower() == ".gz",
                compression_level,
            ) as output_file:
                writer = csv.writer(output_file)
                writer.writerow(OUTPUT_COLUMNS)
                seen_series = set()
                for row in reader:
                    line_number = reader.line_num
                    if not row:
                        raise ValueError(f"Empty sales row {line_number}")
                    if len(row) != len(headers):
                        raise ValueError(
                            f"Expected {len(headers)} fields but found {len(row)} "
                            f"on sales row {line_number}"
                        )

                    item_id = row[item_id_index]
                    store_id = row[store_id_index]
                    if not item_id or not store_id:
                        raise ValueError(
                            f"Missing item_id or store_id on sales row {line_number}"
                        )
                    series_key = (item_id, store_id)
                    if series_key in seen_series:
                        raise ValueError(
                            f"Duplicate item/store series {item_id}/{store_id} "
                            f"on sales row {line_number}"
                        )
                    seen_series.add(series_key)
                    item_ids.add(item_id)
                    store_ids.add(store_id)

                    sales_values = [
                        _parse_sales(row[index], day, line_number)
                        for day, _, index in day_columns
                    ]

                    writer.writerows(
                        (
                            item_id,
                            store_id,
                            sale_date,
                            sales_value,
                        )
                        for (_, sale_date, _), sales_value in zip(day_columns, sales_values)
                    )
                    series_count += 1
                    daily_row_count += len(day_columns)
                    total_daily_sales += sum(sales_values)
                    zero_daily_sales += sales_values.count(0)
                    series_min = min(sales_values)
                    series_max = max(sales_values)
                    min_daily_sales = (
                        series_min
                        if min_daily_sales is None
                        else min(min_daily_sales, series_min)
                    )
                    max_daily_sales = (
                        series_max
                        if max_daily_sales is None
                        else max(max_daily_sales, series_max)
                    )
                    if series_count % 1_000 == 0:
                        print(
                            f"Processed {series_count:,} series "
                            f"({daily_row_count:,} daily rows)",
                            file=sys.stderr,
                            flush=True,
                        )

        if series_count == 0:
            raise ValueError("Sales CSV contains no data rows")
        assert min_daily_sales is not None
        assert max_daily_sales is not None

        if source_hashes is not None and source_hashes != {
            "sales": sha256_file(sales_path),
            "calendar": sha256_file(calendar_path),
        }:
            raise RuntimeError("M5 input files changed while the dataset was being prepared")

        os.chmod(temp_path, 0o644)
        if metadata_path is not None:
            metadata = build_metadata(
                sales_path=sales_path,
                sales_sha256=source_hashes["sales"],
                calendar_path=calendar_path,
                calendar_sha256=source_hashes["calendar"],
                output_path=output_path,
                output_sha256=sha256_file(temp_path),
                compression_level=compression_level,
                day_columns=day_columns,
                series_count=series_count,
                item_count=len(item_ids),
                store_count=len(store_ids),
                daily_row_count=daily_row_count,
                total_daily_sales=total_daily_sales,
                zero_daily_sales=zero_daily_sales,
                min_daily_sales=min_daily_sales,
                max_daily_sales=max_daily_sales,
            )
            metadata_temp_path = write_json_temp(metadata_path, metadata)

        manifest_paths = {default_sidecar_path}
        if metadata_path is not None:
            manifest_paths.add(metadata_path)

        try:
            for manifest_path in manifest_paths:
                backup_path = move_aside(manifest_path)
                if backup_path is not None:
                    manifest_backups.append((manifest_path, backup_path))

            os.replace(temp_path, output_path)
            temp_path = None
            output_replaced = True
            if metadata_temp_path is not None:
                os.replace(metadata_temp_path, metadata_path)
                metadata_temp_path = None
        except Exception:
            if output_replaced:
                for manifest_path, _ in manifest_backups:
                    manifest_path.unlink(missing_ok=True)
            else:
                for manifest_path, backup_path in reversed(manifest_backups):
                    os.replace(backup_path, manifest_path)
                manifest_backups.clear()
            raise
        else:
            for _, backup_path in manifest_backups:
                try:
                    backup_path.unlink(missing_ok=True)
                except OSError:
                    pass
            manifest_backups.clear()
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        if metadata_temp_path is not None:
            metadata_temp_path.unlink(missing_ok=True)
        if output_replaced:
            for _, backup_path in manifest_backups:
                try:
                    backup_path.unlink(missing_ok=True)
                except OSError:
                    pass

    return series_count, daily_row_count


def _parse_sales(value: str | None, day: str, line_number: int) -> int:
    try:
        sales = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid sales value for {day} on sales row {line_number}") from exc
    if sales < 0:
        raise ValueError(f"Negative sales value for {day} on sales row {line_number}")
    return sales


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sales", type=Path, default=DEFAULT_SALES, help="M5 sales CSV")
    parser.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR, help="M5 calendar CSV")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Long-format CSV output")
    parser.add_argument(
        "--compression-level",
        type=int,
        choices=range(1, 10),
        default=DEFAULT_COMPRESSION_LEVEL,
        help="gzip compression level when the output ends in .gz (default: 6)",
    )
    metadata_group = parser.add_mutually_exclusive_group()
    metadata_group.add_argument(
        "--metadata",
        type=Path,
        help="Path for the JSON dataset manifest (default: alongside the output)",
    )
    metadata_group.add_argument(
        "--no-metadata",
        action="store_true",
        help="Do not write a JSON dataset manifest",
    )
    args = parser.parse_args()

    metadata_path = None
    if not args.no_metadata:
        metadata_path = args.metadata or default_metadata_path(args.output)
    series_count, row_count = prepare_dataset(
        args.sales,
        args.calendar,
        args.output,
        args.compression_level,
        metadata_path,
    )
    print(f"Wrote {row_count:,} daily rows for {series_count:,} series to {args.output}")
    if metadata_path is not None:
        print(f"Wrote dataset manifest to {metadata_path}")


if __name__ == "__main__":
    main()
