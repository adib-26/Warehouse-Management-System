"""Add clearly synthetic batch records to isolated M5 forecast-test products.

This development fixture never writes to operational products or warehouses.
The default is a read-only preview; pass ``--apply`` to create sample lots.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from project_env import load_project_env  # noqa: E402

load_project_env(ROOT)
sys.path.insert(0, str(ROOT / "backend"))
from database import get_db  # noqa: E402


LOTS = (
    ("01", 100, 30, 30),
    ("02", 200, 45, 14),
    ("03", 150, 90, 7),
)


def seed_sample_batches(product_limit: int, apply: bool) -> dict:
    conn = get_db()
    try:
        if apply:
            conn.execute("START TRANSACTION")
        cur = conn.cursor()
        candidates = cur.execute(
            """
            SELECT m.id AS mapping_id, m.product_id, m.warehouse_id,
                   p.sku, p.name AS product_name, w.warehouse_code
            FROM forecast_m5_mappings m
            JOIN products p ON p.id=m.product_id
            JOIN warehouses w ON w.id=m.warehouse_id
            WHERE p.is_forecast_test=1 AND w.is_forecast_test=1
              AND m.id=(
                  SELECT MIN(m2.id) FROM forecast_m5_mappings m2
                  WHERE m2.product_id=p.id
              )
              AND p.deleted=0 AND p.quantity=0
              AND p.batch_tracking_enabled_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM inventory_batches b WHERE b.product_id=p.id
              )
            ORDER BY m.id
            LIMIT ?
            """,
            (product_limit,),
        ).fetchall()

        if not apply:
            return {
                "preview_products": len(candidates),
                "preview_batches": len(candidates) * len(LOTS),
                "created_products": 0,
                "created_batches": 0,
                "units_added": 0,
            }

        created_products = 0
        created_batches = 0
        units_added = 0
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        today = now.date()

        for candidate in candidates:
            product = cur.execute(
                "SELECT id, quantity, is_forecast_test, batch_tracking_enabled_at "
                "FROM products WHERE id=? FOR UPDATE",
                (candidate["product_id"],),
            ).fetchone()
            warehouse = cur.execute(
                "SELECT id, is_forecast_test FROM warehouses WHERE id=?",
                (candidate["warehouse_id"],),
            ).fetchone()
            already_has_batches = cur.execute(
                "SELECT id FROM inventory_batches WHERE product_id=? LIMIT 1",
                (candidate["product_id"],),
            ).fetchone()
            if (
                product is None
                or warehouse is None
                or not product["is_forecast_test"]
                or not warehouse["is_forecast_test"]
                or product["quantity"] != 0
                or product["batch_tracking_enabled_at"] is not None
                or already_has_batches is not None
            ):
                continue

            for suffix, quantity, expiry_days, received_days in LOTS:
                batch_number = f"SYNTH-M5-{candidate['product_id']}-{suffix}"
                received_at = now - timedelta(days=received_days)
                expiry_date = today + timedelta(days=expiry_days)
                manufacturing_date = received_at.date() - timedelta(days=180)
                cur.execute(
                    """
                    INSERT INTO inventory_batches
                        (batch_number, product_id, warehouse_id, supplier_id,
                         received_quantity, remaining_quantity, manufacturing_date,
                         expiry_date, received_date, status)
                    VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, 'available')
                    """,
                    (
                        batch_number,
                        candidate["product_id"],
                        candidate["warehouse_id"],
                        quantity,
                        quantity,
                        manufacturing_date,
                        expiry_date,
                        received_at,
                    ),
                )
                batch_id = cur.lastrowid
                cur.execute(
                    """
                    INSERT INTO movements
                        (product_id, action_type, delta, reason, source, batch_id, warehouse_id)
                    VALUES (?, 'STOCK_IN', ?, ?, 'batch-seed', ?, ?)
                    """,
                    (
                        candidate["product_id"],
                        quantity,
                        f"Synthetic development batch {batch_number}",
                        batch_id,
                        candidate["warehouse_id"],
                    ),
                )
                created_batches += 1
                units_added += quantity

            # Sum the just-created lots for this product. The fixture's batch
            # quantities are intentionally independent of M5 demand history.
            product_total = sum(lot[1] for lot in LOTS)
            cur.execute(
                "UPDATE products SET quantity=?, batch_tracking_enabled_at=?, "
                "updated_at=UTC_TIMESTAMP() WHERE id=? AND quantity=0",
                (product_total, now, candidate["product_id"]),
            )
            if cur.rowcount != 1:
                raise RuntimeError(
                    f"Could not mark forecast-test product {candidate['product_id']} as batch tracked"
                )
            created_products += 1

        conn.commit()
        return {
            "preview_products": len(candidates),
            "preview_batches": len(candidates) * len(LOTS),
            "created_products": created_products,
            "created_batches": created_batches,
            "units_added": units_added,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview or seed synthetic batch lots in M5 test products only."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Maximum forecast-test products to seed (default: 10)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write synthetic batch records; without this flag the script only previews",
    )
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be at least 1")

    try:
        result = seed_sample_batches(args.count, args.apply)
    except Exception as exc:
        print(f"Sample batch seeding failed: {exc}", file=sys.stderr)
        return 1

    if args.apply:
        print(
            f"Created {result['created_batches']} synthetic batches for "
            f"{result['created_products']} M5 test products; added "
            f"{result['units_added']} units."
        )
    else:
        print(
            f"Would create {result['preview_batches']} synthetic batches for "
            f"{result['preview_products']} M5 test products. Re-run with --apply to write."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
