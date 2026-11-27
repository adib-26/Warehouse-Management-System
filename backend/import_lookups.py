"""Record lookups shared by the inbound and outbound spreadsheet imports."""

PRODUCT_COLUMNS = "id, name, quantity, batch_tracking_enabled_at"
_ACTIVE_PRODUCT = "deleted=0 AND archived=0 AND is_forecast_test=0"
_PARTY_LABELS = {"suppliers": "supplier", "customers": "customer"}


def lock_import_product(cur, sku: str, name: str):
    """Return the product an import row refers to, locked FOR UPDATE, or None.

    SKUs are unique. Names are not, so a name must match exactly one product.
    The name is resolved with a plain read first: a locking read filtered on
    LOWER(name) scans the whole table, and InnoDB would then keep every product
    locked until the import commits.
    """
    if sku:
        return cur.execute(
            f"SELECT {PRODUCT_COLUMNS} FROM products "
            f"WHERE sku=? AND {_ACTIVE_PRODUCT} FOR UPDATE",
            (sku,),
        ).fetchone()
    matches = cur.execute(
        f"SELECT id FROM products WHERE LOWER(name)=? AND {_ACTIVE_PRODUCT} LIMIT 2",
        (name.lower(),),
    ).fetchall()
    if len(matches) > 1:
        raise ValueError(f"More than one product is named '{name}'; use its SKU instead")
    if not matches:
        return None
    return cur.execute(
        f"SELECT {PRODUCT_COLUMNS} FROM products "
        f"WHERE id=? AND LOWER(name)=? AND {_ACTIVE_PRODUCT} FOR UPDATE",
        (matches[0]["id"], name.lower()),
    ).fetchone()


def find_import_party(cur, table: str, name: str):
    """Return the single active supplier or customer with this name, or None."""
    label = _PARTY_LABELS[table]
    rows = cur.execute(
        f"SELECT id, name FROM {table} WHERE LOWER(name)=? AND deleted=0 LIMIT 2",
        (name.lower(),),
    ).fetchall()
    if len(rows) > 1:
        raise ValueError(f"More than one {label} is named '{name}'")
    return rows[0] if rows else None
