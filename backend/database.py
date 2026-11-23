import sqlite3

from config import DATABASE_PATH, UPLOAD_DIR


def get_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

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

    seed_auth(cur)

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

        password_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            ("admin", password_hash, "Administrator", "admin"),
        )

    if cur.execute("SELECT COUNT(*) FROM permissions").fetchone()[0] == 0:
        for role, modules in DEFAULT_MATRIX.items():
            for module, (r, w, d) in modules.items():
                cur.execute(
                    "INSERT INTO permissions (role, module, can_read, can_write, can_delete) VALUES (?, ?, ?, ?, ?)",
                    (role, module, r, w, d),
                )
