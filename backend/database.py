import sqlite3

from config import (
    DATABASE_PATH,
    INITIAL_ADMIN_PASSWORD,
    INITIAL_ADMIN_USERNAME,
    UPLOAD_DIR,
    validate_initial_admin_credentials,
)

BASE_SCHEMA_VERSION = 1


def _migration_2_add_movement_source(cur):
    """Classify new movements so only standalone adjustments can be reversed."""
    columns = {row["name"] for row in cur.execute("PRAGMA table_info(movements)")}
    if "source" not in columns:
        # Existing rows cannot be classified reliably, so retain them as immutable
        # history rather than risking a shipment or catalog entry being reversed.
        cur.execute(
            "ALTER TABLE movements ADD COLUMN source TEXT NOT NULL DEFAULT 'legacy'"
        )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_movements_source_created "
        "ON movements (source, created_at)"
    )


SCHEMA_VERSION = 2
# Add a numbered migration here and increment SCHEMA_VERSION for future schema changes.
SCHEMA_MIGRATIONS = {2: _migration_2_add_movement_source}


def get_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    current_version = cur.execute("PRAGMA user_version").fetchone()[0]
    if current_version > SCHEMA_VERSION:
        conn.close()
        raise RuntimeError(
            f"Database schema version {current_version} is newer than this application supports ({SCHEMA_VERSION})"
        )
    conn.execute("PRAGMA journal_mode = WAL")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        sku TEXT UNIQUE NOT NULL,
        description TEXT DEFAULT '',
        category TEXT DEFAULT '',
        tags TEXT DEFAULT '',
        quantity INTEGER DEFAULT 0,
        low_stock INTEGER DEFAULT 10,
        archived INTEGER DEFAULT 0,
        deleted INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        action_type TEXT NOT NULL DEFAULT 'STOCK_ADJUST',
        delta INTEGER DEFAULT 0,
        reason TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        contact_person TEXT DEFAULT '',
        email TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        address TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        deleted INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS inbound_shipments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        supplier_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        invoice_ref TEXT DEFAULT '',
        received_date TEXT DEFAULT (date('now')),
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (product_id) REFERENCES products(id),
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        contact_person TEXT DEFAULT '',
        email TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        address TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        deleted INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS outbound_shipments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        customer_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        so_ref TEXT DEFAULT '',
        dispatch_date TEXT DEFAULT (date('now')),
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (product_id) REFERENCES products(id),
        FOREIGN KEY (customer_id) REFERENCES customers(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        stored_name TEXT NOT NULL,
        file_size INTEGER DEFAULT 0,
        mime_type TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT DEFAULT '',
        role TEXT NOT NULL DEFAULT 'operator',
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        module TEXT NOT NULL,
        can_read INTEGER DEFAULT 0,
        can_write INTEGER DEFAULT 0,
        can_delete INTEGER DEFAULT 0,
        UNIQUE (role, module)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT DEFAULT '',
        action TEXT NOT NULL,
        module TEXT DEFAULT '',
        entity_type TEXT DEFAULT '',
        entity_id INTEGER,
        details TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )
    """)

    cur.executescript("""
    CREATE INDEX IF NOT EXISTS idx_products_active_updated
        ON products (deleted, archived, updated_at);
    CREATE INDEX IF NOT EXISTS idx_products_stock
        ON products (deleted, archived, quantity, low_stock);
    CREATE INDEX IF NOT EXISTS idx_movements_product_created
        ON movements (product_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_inbound_created
        ON inbound_shipments (created_at);
    CREATE INDEX IF NOT EXISTS idx_outbound_created
        ON outbound_shipments (created_at);
    CREATE INDEX IF NOT EXISTS idx_attachments_entity
        ON attachments (entity_type, entity_id);
    CREATE INDEX IF NOT EXISTS idx_audit_logs_created
        ON audit_logs (created_at);
    """)

    # Version 0 databases are existing installations that predate schema tracking.
    # The CREATE TABLE statements above establish the version 1 baseline for both
    # those installations and fresh databases.
    if current_version == 0:
        current_version = BASE_SCHEMA_VERSION
        cur.execute(f"PRAGMA user_version = {BASE_SCHEMA_VERSION}")
    while current_version < SCHEMA_VERSION:
        next_version = current_version + 1
        migration = SCHEMA_MIGRATIONS.get(next_version)
        if migration is None:
            conn.close()
            raise RuntimeError(f"Missing database migration for schema version {next_version}")
        migration(cur)
        cur.execute(f"PRAGMA user_version = {next_version}")
        current_version = next_version

    try:
        seed_auth(cur)
    except Exception:
        conn.close()
        raise

    conn.commit()
    conn.close()

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


MODULES = ["products", "stock", "inbound", "outbound", "suppliers", "customers", "reports", "admin"]
ROLES = ["admin", "manager", "operator"]

DEFAULT_MATRIX = {
    "admin": {m: (1, 1, 1) for m in MODULES},
    "manager": {m: ((1, 1, 0) if m != "admin" else (0, 0, 0)) for m in MODULES},
    "operator": {
        m: (
            (0, 0, 0) if m == "admin"
            else (1, 1, 0) if m in ("stock", "inbound", "outbound")
            else (1, 0, 0)
        )
        for m in MODULES
    },
}


def seed_auth(cur):
    if cur.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        import bcrypt

        validate_initial_admin_credentials()
        password_hash = bcrypt.hashpw(INITIAL_ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            (INITIAL_ADMIN_USERNAME, password_hash, "Administrator", "admin"),
        )

    if cur.execute("SELECT COUNT(*) FROM permissions").fetchone()[0] == 0:
        for role, modules in DEFAULT_MATRIX.items():
            for module, (r, w, d) in modules.items():
                cur.execute(
                    "INSERT INTO permissions (role, module, can_read, can_write, can_delete) VALUES (?, ?, ?, ?, ?)",
                    (role, module, r, w, d),
                )
