"""Retired entry point for the obsolete standalone M5 table importer."""

import sys


def main() -> int:
    print(
        "scripts/import_m5.py is retired because it created a second M5 schema "
        "outside NovaLedger migrations. Use these supported commands instead:\n"
        "  python3 scripts/bootstrap_m5_test_catalog.py\n"
        "  python3 scripts/load_m5_forecast.py --mapping datasets/m5/processed/m5_mapping.csv",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
