"""Regression tests for the M5 wide-to-long conversion script."""

import csv
import gzip
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "prepare_m5.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("prepare_m5", SCRIPT)
prepare_m5 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prepare_m5
assert SPEC.loader is not None
SPEC.loader.exec_module(prepare_m5)
import validate_m5


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output_file:
        csv.writer(output_file).writerows(rows)


class PrepareM5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.calendar = self.root / "calendar.csv"
        self.sales = self.root / "sales.csv"

        write_csv(
            self.calendar,
            [
                ["date", "d"],
                ["2011-01-29", "d_1"],
                ["2011-01-30", "d_2"],
                ["2011-01-31", "d_3"],
            ],
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_converts_wide_rows_to_chronological_gzip_csv(self) -> None:
        write_csv(
            self.sales,
            [
                ["id", "item_id", "store_id", "d_2", "d_1", "d_3"],
                ["one", "ITEM_001", "CA_1", "2", "4", "0"],
                ["two", "ITEM_002", "CA_1", "3", "1", "5"],
            ],
        )
        output = self.root / "daily_sales.csv.gz"

        series_count, row_count = prepare_m5.prepare_dataset(
            self.sales, self.calendar, output
        )

        self.assertEqual((series_count, row_count), (2, 6))
        with gzip.open(output, "rt", encoding="utf-8", newline="") as output_file:
            self.assertEqual(
                list(csv.reader(output_file)),
                [
                    ["item_id", "store_id", "date", "daily_sales"],
                    ["ITEM_001", "CA_1", "2011-01-29", "4"],
                    ["ITEM_001", "CA_1", "2011-01-30", "2"],
                    ["ITEM_001", "CA_1", "2011-01-31", "0"],
                    ["ITEM_002", "CA_1", "2011-01-29", "1"],
                    ["ITEM_002", "CA_1", "2011-01-30", "3"],
                    ["ITEM_002", "CA_1", "2011-01-31", "5"],
                ],
            )

        first_build = output.read_bytes()
        prepare_m5.prepare_dataset(self.sales, self.calendar, output)
        self.assertEqual(output.read_bytes(), first_build)

    def test_invalid_input_leaves_previous_output_intact(self) -> None:
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1"],
                ["ITEM_001", "CA_1", "2"],
                ["ITEM_001", "CA_1", "3"],
            ],
        )
        output = self.root / "daily_sales.csv"
        output.write_text("known-good-output\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Duplicate item/store series"):
            prepare_m5.prepare_dataset(self.sales, self.calendar, output)

        self.assertEqual(output.read_text(encoding="utf-8"), "known-good-output\n")

    def test_rejects_day_gaps_and_unmapped_days(self) -> None:
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1", "d_3"],
                ["ITEM_001", "CA_1", "1", "3"],
            ],
        )
        with self.assertRaisesRegex(ValueError, "not consecutive"):
            prepare_m5.prepare_dataset(
                self.sales, self.calendar, self.root / "gap.csv"
            )

        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_4"],
                ["ITEM_001", "CA_1", "1"],
            ],
        )
        with self.assertRaisesRegex(ValueError, "Calendar is missing sales day"):
            prepare_m5.prepare_dataset(
                self.sales, self.calendar, self.root / "unmapped.csv"
            )

    def test_rejects_negative_and_malformed_sales_values(self) -> None:
        for value, expected_error in (("-1", "Negative sales value"), ("one", "Invalid sales value")):
            with self.subTest(value=value):
                write_csv(
                    self.sales,
                    [
                        ["item_id", "store_id", "d_1"],
                        ["ITEM_001", "CA_1", value],
                    ],
                )
                with self.assertRaisesRegex(ValueError, expected_error):
                    prepare_m5.prepare_dataset(
                        self.sales, self.calendar, self.root / f"{value}.csv"
                    )

    def test_rejects_nonconsecutive_calendar_dates(self) -> None:
        write_csv(
            self.calendar,
            [
                ["date", "d"],
                ["2011-01-29", "d_1"],
                ["2011-01-31", "d_2"],
            ],
        )
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1", "d_2"],
                ["ITEM_001", "CA_1", "1", "2"],
            ],
        )

        with self.assertRaisesRegex(ValueError, "Calendar dates are not consecutive"):
            prepare_m5.prepare_dataset(
                self.sales, self.calendar, self.root / "invalid-calendar.csv"
            )

    def test_writes_a_manifest_with_schema_coverage_and_checksums(self) -> None:
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1", "d_2", "d_3"],
                ["ITEM_001", "CA_1", "0", "2", "1"],
                ["ITEM_002", "CA_2", "3", "0", "0"],
            ],
        )
        output = self.root / "daily_sales.csv.gz"
        metadata = prepare_m5.default_metadata_path(output)

        prepare_m5.prepare_dataset(self.sales, self.calendar, output, metadata_path=metadata)

        manifest = json.loads(metadata.read_text(encoding="utf-8"))
        self.assertEqual(
            [column["name"] for column in manifest["columns"]],
            ["item_id", "store_id", "date", "daily_sales"],
        )
        self.assertEqual(
            manifest["coverage"],
            {
                "date_end": "2011-01-31",
                "date_start": "2011-01-29",
                "day_count": 3,
                "day_end": "d_3",
                "day_start": "d_1",
                "item_count": 2,
                "row_count": 6,
                "series_count": 2,
                "store_count": 2,
            },
        )
        self.assertEqual(manifest["daily_sales_summary"]["total_units"], 6)
        self.assertEqual(manifest["daily_sales_summary"]["zero_sales_row_count"], 3)
        self.assertEqual(manifest["output"]["sha256"], prepare_m5.sha256_file(output))
        self.assertEqual(manifest["source"]["sales_file_sha256"], prepare_m5.sha256_file(self.sales))

    def test_rejects_an_empty_sales_row(self) -> None:
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1"],
                ["ITEM_001", "CA_1", "2"],
                [],
            ],
        )

        with self.assertRaisesRegex(ValueError, "Empty sales row"):
            prepare_m5.prepare_dataset(
                self.sales, self.calendar, self.root / "empty-row.csv"
            )

    def test_replacing_output_without_metadata_removes_default_manifest(self) -> None:
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1"],
                ["ITEM_001", "CA_1", "2"],
            ],
        )
        output = self.root / "daily_sales.csv.gz"
        default_manifest = prepare_m5.default_metadata_path(output)
        default_manifest.write_text("stale manifest\n", encoding="utf-8")

        prepare_m5.prepare_dataset(self.sales, self.calendar, output)

        self.assertTrue(output.exists())
        self.assertFalse(default_manifest.exists())

    def test_manifest_creation_failure_keeps_existing_dataset_and_manifest(self) -> None:
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1"],
                ["ITEM_001", "CA_1", "2"],
            ],
        )
        output = self.root / "daily_sales.csv.gz"
        manifest = prepare_m5.default_metadata_path(output)
        output.write_text("previous dataset\n", encoding="utf-8")
        manifest.write_text("previous manifest\n", encoding="utf-8")

        with mock.patch.object(
            prepare_m5,
            "write_json_temp",
            side_effect=OSError("simulated manifest write failure"),
        ):
            with self.assertRaisesRegex(OSError, "simulated manifest write failure"):
                prepare_m5.prepare_dataset(
                    self.sales,
                    self.calendar,
                    output,
                    metadata_path=manifest,
                )

        self.assertEqual(output.read_text(encoding="utf-8"), "previous dataset\n")
        self.assertEqual(manifest.read_text(encoding="utf-8"), "previous manifest\n")

    def test_manifest_replacement_failure_removes_the_stale_manifest(self) -> None:
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1"],
                ["ITEM_001", "CA_1", "2"],
            ],
        )
        output = self.root / "daily_sales.csv.gz"
        manifest = prepare_m5.default_metadata_path(output)
        output.write_text("previous dataset\n", encoding="utf-8")
        manifest.write_text("previous manifest\n", encoding="utf-8")
        original_replace = prepare_m5.os.replace

        def fail_manifest_replacement(source, destination):
            if Path(destination) == manifest:
                raise OSError("simulated manifest replacement failure")
            return original_replace(source, destination)

        with mock.patch.object(
            prepare_m5.os,
            "replace",
            side_effect=fail_manifest_replacement,
        ):
            with self.assertRaisesRegex(OSError, "simulated manifest replacement failure"):
                prepare_m5.prepare_dataset(
                    self.sales,
                    self.calendar,
                    output,
                    metadata_path=manifest,
                )

        self.assertNotEqual(output.read_bytes(), b"previous dataset\n")
        self.assertFalse(manifest.exists())

    def test_validates_complete_coverage_and_keeps_zero_days_in_average(self) -> None:
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1", "d_2", "d_3"],
                ["ITEM_001", "CA_1", "0", "2", "1"],
                ["ITEM_002", "CA_2", "3", "0", "0"],
            ],
        )
        output = self.root / "daily_sales.csv.gz"
        manifest = prepare_m5.default_metadata_path(output)
        prepare_m5.prepare_dataset(
            self.sales, self.calendar, output, metadata_path=manifest
        )

        report = validate_m5.validate_dataset(
            self.sales, self.calendar, output, manifest
        )

        self.assertEqual(report["status"], "passed")
        self.assertTrue(report["manifest_verified"])
        self.assertEqual(report["coverage"]["row_count"], 6)
        self.assertEqual(report["sales_summary"]["zero_sales_row_count"], 3)
        self.assertEqual(
            report["sales_summary"]["mean_daily_sales_including_zero_days"], 1.0
        )

    def test_rejects_duplicate_product_store_date_combinations(self) -> None:
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1", "d_2", "d_3"],
                ["ITEM_001", "CA_1", "0", "2", "1"],
            ],
        )
        output = self.root / "duplicate.csv"
        write_csv(
            output,
            [
                ["item_id", "store_id", "date", "daily_sales"],
                ["ITEM_001", "CA_1", "2011-01-29", "0"],
                ["ITEM_001", "CA_1", "2011-01-29", "0"],
                ["ITEM_001", "CA_1", "2011-01-31", "1"],
            ],
        )

        with self.assertRaisesRegex(ValueError, "Duplicate item/store/date"):
            validate_m5.validate_dataset(self.sales, self.calendar, output)

    def test_rejects_incorrect_date_mapping(self) -> None:
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1", "d_2", "d_3"],
                ["ITEM_001", "CA_1", "0", "2", "1"],
            ],
        )
        output = self.root / "wrong-date.csv"
        write_csv(
            output,
            [
                ["item_id", "store_id", "date", "daily_sales"],
                ["ITEM_001", "CA_1", "2011-01-30", "0"],
                ["ITEM_001", "CA_1", "2011-01-30", "2"],
                ["ITEM_001", "CA_1", "2011-01-31", "1"],
            ],
        )

        with self.assertRaisesRegex(ValueError, "Date mapping"):
            validate_m5.validate_dataset(self.sales, self.calendar, output)

    def test_rejects_negative_processed_sales(self) -> None:
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1", "d_2", "d_3"],
                ["ITEM_001", "CA_1", "0", "2", "1"],
            ],
        )
        output = self.root / "negative.csv"
        write_csv(
            output,
            [
                ["item_id", "store_id", "date", "daily_sales"],
                ["ITEM_001", "CA_1", "2011-01-29", "-1"],
                ["ITEM_001", "CA_1", "2011-01-30", "2"],
                ["ITEM_001", "CA_1", "2011-01-31", "1"],
            ],
        )

        with self.assertRaisesRegex(ValueError, "Negative sales quantity"):
            validate_m5.validate_dataset(self.sales, self.calendar, output)

    def test_rejects_removed_zero_sales_date(self) -> None:
        write_csv(
            self.sales,
            [
                ["item_id", "store_id", "d_1", "d_2", "d_3"],
                ["ITEM_001", "CA_1", "0", "2", "1"],
            ],
        )
        output = self.root / "missing-zero.csv"
        write_csv(
            output,
            [
                ["item_id", "store_id", "date", "daily_sales"],
                ["ITEM_001", "CA_1", "2011-01-30", "2"],
                ["ITEM_001", "CA_1", "2011-01-31", "1"],
            ],
        )

        with self.assertRaisesRegex(ValueError, "coverage"):
            validate_m5.validate_dataset(self.sales, self.calendar, output)


if __name__ == "__main__":
    unittest.main()
