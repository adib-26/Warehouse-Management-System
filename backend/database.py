import os
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import unquote, urlparse

import pymysql
from pymysql.err import IntegrityError as IntegrityError


class DatabaseError(Exception):
    """Raised when the application cannot reach or query MySQL."""

from config import (
    APP_ENV,
    DATABASE_URL,
    INITIAL_ADMIN_PASSWORD,
    INITIAL_ADMIN_USERNAME,
    UPLOAD_DIR,
    validate_initial_admin_credentials,
)

BASE_SCHEMA_VERSION = 2
SCHEMA_VERSION = 8

DATA_TABLES = (
    "forecast_evaluation_metrics",
    "forecast_results",
    "forecast_m5_imports",
    "forecast_demand_history",
    "forecast_m5_mappings",
    "product_reorder_settings",
    "forecast_runs",
    "audit_logs",
    "attachments",
    "movements",
    "inbound_shipments",
    "outbound_shipments",
    "warehouses",
    "inventory_batches",
    "permissions",
    "users",
    "products",
    "suppliers",
    "customers",
)


def _adapt(sql: str) -> str:
    """Translate the small set of SQLite phrases still used by route SQL."""
    sql = sql.replace("BEGIN IMMEDIATE", "START TRANSACTION")
    sql = sql.replace("INSERT OR IGNORE", "INSERT IGNORE")
    sql = sql.replace("datetime('now', '-7 days')", "(UTC_TIMESTAMP() - INTERVAL 7 DAY)")
    sql = sql.replace("datetime('now')", "UTC_TIMESTAMP()")
    sql = sql.replace("date('now')", "CURDATE()")
    return sql.replace("?", "%s")


def _normalize(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


class Row(dict):
    """Mapping row that also supports the positional access used for aggregates."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(super().values())[key]
        return super().__getitem__(key)

    def __iter__(self):
        return iter(super().values())


class Cursor:
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=None):
        self._raw.execute(_adapt(sql), params or ())
        return self

    def executemany(self, sql, params):
        self._raw.executemany(_adapt(sql), params)
        return self

    def fetchone(self):
        row = self._raw.fetchone()
        if row is None:
            return None
        return Row({key: _normalize(value) for key, value in row.items()})

    def fetchall(self):
        return [
            Row({key: _normalize(value) for key, value in row.items()})
            for row in self._raw.fetchall()
        ]

    def fetchmany(self, size):
        return [
            Row({key: _normalize(value) for key, value in row.items()})
            for row in self._raw.fetchmany(size)
        ]

    def close(self):
        self._raw.close()

    @property
    def lastrowid(self):
        return self._raw.lastrowid

    @property
    def rowcount(self):
        return self._raw.rowcount


class Connection:
    def __init__(self, raw):
        self._raw = raw

    def cursor(self):
        return Cursor(self._raw.cursor(pymysql.cursors.DictCursor))

    def stream_cursor(self):
        """Open an unbuffered cursor for large, ordered result sets."""
        return Cursor(self._raw.cursor(pymysql.cursors.SSDictCursor))

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def _connection_kwargs():
    parsed = urlparse(DATABASE_URL)
    if parsed.scheme != "mysql":
        raise RuntimeError("DATABASE_URL must start with mysql://")
    database = parsed.path.lstrip("/")
    if not parsed.hostname or not parsed.username or not database:
        raise RuntimeError("DATABASE_URL must include a user, host, and database name")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username),
        "password": unquote(parsed.password or ""),
        "database": database,
        "charset": "utf8mb4",
        "autocommit": False,
        "connect_timeout": 10,
        "init_command": "SET time_zone = '+00:00'",
    }


def get_db():
    try:
        raw = pymysql.connect(**_connection_kwargs())
    except pymysql.MySQLError as exc:
        raise DatabaseError(str(exc)) from exc
    return Connection(raw)


def _schema_version(cur) -> int:
    row = cur.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").fetchone()
    return int(row["version"])


def _ensure_index(cur, table_name, name, statement):
    existing = cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = ?
          AND index_name = ?
        """,
        (table_name, name),
    ).fetchone()
    if int(existing["n"]) == 0:
        cur.execute(statement)


def _ensure_innodb(cur, table_name):
    row = cur.execute(
        """
        SELECT engine AS engine
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = ?
        """,
        (table_name,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Required table does not exist: {table_name}")
    if (row["engine"] or "").upper() != "INNODB":
        # Names here are migration-owned constants, never user input.
        cur.execute(f"ALTER TABLE `{table_name}` ENGINE=InnoDB")


def _column_exists(cur, table_name, column_name) -> bool:
    row = cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = ? AND column_name = ?
        """,
        (table_name, column_name),
    ).fetchone()
    return int(row["n"]) > 0


def _table_exists(cur, table_name) -> bool:
    row = cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = ?
        """,
        (table_name,),
    ).fetchone()
    return int(row["n"]) > 0


def _ensure_foreign_key(cur, table_name, constraint_name, statement):
    existing = cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.table_constraints
        WHERE constraint_schema = DATABASE()
          AND table_name = ?
          AND constraint_name = ?
          AND constraint_type = 'FOREIGN KEY'
        """,
        (table_name, constraint_name),
    ).fetchone()
    if int(existing["n"]) == 0:
        cur.execute(statement)


def _migration_3_forecasting_schema(cur):
    """Add shared warehouse support and isolated forecasting records."""
    # The forecast foreign keys require transactional parent tables even if a
    # database was created with a non-InnoDB server default.
    for table_name in ("products", "customers", "outbound_shipments"):
        _ensure_innodb(cur, table_name)

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS warehouses (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            warehouse_code VARCHAR(64) NOT NULL,
            name VARCHAR(255) NOT NULL,
            address TEXT NULL,
            active TINYINT NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_warehouses_code (warehouse_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )

    if not _column_exists(cur, "outbound_shipments", "warehouse_id"):
        cur.execute(
            "ALTER TABLE outbound_shipments ADD COLUMN warehouse_id INT NULL"
        )
    _ensure_index(
        cur,
        "outbound_shipments",
        "idx_outbound_warehouse_dispatch",
        "CREATE INDEX idx_outbound_warehouse_dispatch "
        "ON outbound_shipments (warehouse_id, dispatch_date)",
    )
    _ensure_foreign_key(
        cur,
        "outbound_shipments",
        "fk_outbound_warehouse",
        "ALTER TABLE outbound_shipments ADD CONSTRAINT fk_outbound_warehouse "
        "FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) "
        "ON DELETE RESTRICT ON UPDATE CASCADE",
    )

    statements = (
        """
        CREATE TABLE IF NOT EXISTS forecast_runs (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            model_name VARCHAR(50) NOT NULL,
            source VARCHAR(30) NOT NULL,
            started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'running',
            products_processed INT NOT NULL DEFAULT 0,
            error_message TEXT NULL,
            CONSTRAINT ck_forecast_runs_source CHECK (source IN ('M5', 'WMS')),
            CONSTRAINT ck_forecast_runs_status CHECK (status IN ('running', 'success', 'failed')),
            CONSTRAINT ck_forecast_runs_products CHECK (products_processed >= 0),
            KEY idx_forecast_runs_started (started_at),
            KEY idx_forecast_runs_source_status (source, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS forecast_m5_mappings (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            item_id VARCHAR(64) NOT NULL,
            store_id VARCHAR(32) NOT NULL,
            product_id INT NOT NULL,
            warehouse_id INT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_forecast_m5_source (item_id, store_id),
            UNIQUE KEY uq_forecast_m5_target (product_id, warehouse_id),
            UNIQUE KEY uq_forecast_m5_map_identity (id, product_id, warehouse_id),
            CONSTRAINT fk_forecast_m5_product FOREIGN KEY (product_id)
                REFERENCES products(id) ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT fk_forecast_m5_warehouse FOREIGN KEY (warehouse_id)
                REFERENCES warehouses(id) ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS forecast_demand_history (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            warehouse_id INT NOT NULL,
            demand_date DATE NOT NULL,
            quantity_sold DECIMAL(12,2) NOT NULL,
            source VARCHAR(30) NOT NULL,
            m5_mapping_id BIGINT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_forecast_demand_day_source
                (product_id, warehouse_id, demand_date, source),
            KEY idx_forecast_demand_source_date (source, demand_date),
            CONSTRAINT ck_forecast_demand_source CHECK (source IN ('M5', 'WMS')),
            CONSTRAINT ck_forecast_demand_quantity CHECK (quantity_sold >= 0),
            CONSTRAINT ck_forecast_demand_m5_mapping CHECK (
                (source = 'M5' AND m5_mapping_id IS NOT NULL)
                OR (source = 'WMS' AND m5_mapping_id IS NULL)
            ),
            CONSTRAINT fk_forecast_demand_product FOREIGN KEY (product_id)
                REFERENCES products(id) ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT fk_forecast_demand_warehouse FOREIGN KEY (warehouse_id)
                REFERENCES warehouses(id) ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT fk_forecast_demand_m5_mapping
                FOREIGN KEY (m5_mapping_id, product_id, warehouse_id)
                REFERENCES forecast_m5_mappings(id, product_id, warehouse_id)
                ON DELETE RESTRICT ON UPDATE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS forecast_results (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            run_id BIGINT NOT NULL,
            product_id INT NOT NULL,
            warehouse_id INT NOT NULL,
            forecast_date DATE NOT NULL,
            predicted_demand DECIMAL(12,2) NOT NULL,
            model_name VARCHAR(50) NOT NULL,
            model_version VARCHAR(30) NOT NULL,
            generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_forecast_result_run_series_model_date
                (run_id, product_id, warehouse_id, forecast_date, model_name),
            KEY idx_forecast_result_series_date
                (product_id, warehouse_id, forecast_date),
            CONSTRAINT ck_forecast_result_demand CHECK (predicted_demand >= 0),
            CONSTRAINT fk_forecast_result_run FOREIGN KEY (run_id)
                REFERENCES forecast_runs(id) ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT fk_forecast_result_product FOREIGN KEY (product_id)
                REFERENCES products(id) ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT fk_forecast_result_warehouse FOREIGN KEY (warehouse_id)
                REFERENCES warehouses(id) ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS forecast_evaluation_metrics (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            run_id BIGINT NOT NULL,
            product_id INT NOT NULL,
            warehouse_id INT NOT NULL,
            model_key VARCHAR(50) NOT NULL,
            model_name VARCHAR(50) NOT NULL,
            model_version VARCHAR(30) NOT NULL,
            observation_count SMALLINT UNSIGNED NOT NULL,
            actual_demand_total DECIMAL(20,2) NOT NULL,
            absolute_error_total DECIMAL(20,4) NOT NULL,
            mae DECIMAL(20,4) NOT NULL,
            rmse DECIMAL(20,4) NOT NULL,
            wape_pct DECIMAL(20,4) NULL,
            bias DECIMAL(20,4) NOT NULL,
            mase DECIMAL(20,4) NULL,
            naive_mae_scale DECIMAL(20,4) NULL,
            zero_demand_holdout TINYINT NOT NULL DEFAULT 0,
            generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_forecast_evaluation_run_series_model
                (run_id, product_id, warehouse_id, model_key),
            KEY idx_forecast_evaluation_run_model (run_id, model_key),
            CONSTRAINT ck_forecast_evaluation_observations
                CHECK (observation_count > 0),
            CONSTRAINT ck_forecast_evaluation_actual_total
                CHECK (actual_demand_total >= 0),
            CONSTRAINT ck_forecast_evaluation_absolute_error
                CHECK (absolute_error_total >= 0),
            CONSTRAINT ck_forecast_evaluation_mae CHECK (mae >= 0),
            CONSTRAINT ck_forecast_evaluation_rmse CHECK (rmse >= 0),
            CONSTRAINT ck_forecast_evaluation_wape CHECK (wape_pct IS NULL OR wape_pct >= 0),
            CONSTRAINT ck_forecast_evaluation_zero_holdout
                CHECK (zero_demand_holdout IN (0, 1)),
            CONSTRAINT fk_forecast_evaluation_run FOREIGN KEY (run_id)
                REFERENCES forecast_runs(id) ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT fk_forecast_evaluation_product FOREIGN KEY (product_id)
                REFERENCES products(id) ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT fk_forecast_evaluation_warehouse FOREIGN KEY (warehouse_id)
                REFERENCES warehouses(id) ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS product_reorder_settings (
            product_id INT NOT NULL,
            warehouse_id INT NOT NULL,
            lead_time_days INT NOT NULL,
            safety_stock DECIMAL(12,2) NOT NULL DEFAULT 0,
            review_period_days INT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (product_id, warehouse_id),
            CONSTRAINT ck_reorder_lead_time CHECK (lead_time_days >= 0),
            CONSTRAINT ck_reorder_safety_stock CHECK (safety_stock >= 0),
            CONSTRAINT ck_reorder_review_period CHECK (review_period_days > 0),
            CONSTRAINT fk_reorder_product FOREIGN KEY (product_id)
                REFERENCES products(id) ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT fk_reorder_warehouse FOREIGN KEY (warehouse_id)
                REFERENCES warehouses(id) ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    )
    for statement in statements:
        cur.execute(statement)


def _migration_4_forecasting_hardening(cur):
    """Harden forecast isolation, provenance, and high-volume query paths."""
    for table_name in (
        "products",
        "customers",
        "outbound_shipments",
        "warehouses",
        "forecast_runs",
        "forecast_m5_mappings",
        "forecast_demand_history",
        "forecast_results",
        "product_reorder_settings",
    ):
        _ensure_innodb(cur, table_name)

    if not _column_exists(cur, "products", "is_forecast_test"):
        cur.execute(
            "ALTER TABLE products "
            "ADD COLUMN is_forecast_test TINYINT NOT NULL DEFAULT 0"
        )
    if not _column_exists(cur, "warehouses", "is_forecast_test"):
        cur.execute(
            "ALTER TABLE warehouses "
            "ADD COLUMN is_forecast_test TINYINT NOT NULL DEFAULT 0"
        )

    cur.execute(
        "ALTER TABLE warehouses MODIFY COLUMN updated_at "
        "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
    )
    cur.execute(
        "ALTER TABLE product_reorder_settings MODIFY COLUMN updated_at "
        "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS forecast_m5_imports (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            dataset_sha256 CHAR(64) NOT NULL,
            mapping_sha256 CHAR(64) NOT NULL,
            dataset_path VARCHAR(1024) NOT NULL,
            manifest_path VARCHAR(1024) NULL,
            source_row_count BIGINT UNSIGNED NOT NULL,
            loaded_row_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
            series_count INT UNSIGNED NOT NULL,
            date_start DATE NOT NULL,
            date_end DATE NOT NULL,
            replace_existing TINYINT NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'running',
            started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME NULL,
            error_message TEXT NULL,
            CONSTRAINT ck_forecast_m5_import_status
                CHECK (status IN ('running', 'success', 'failed')),
            CONSTRAINT ck_forecast_m5_import_rows
                CHECK (loaded_row_count <= source_row_count),
            CONSTRAINT ck_forecast_m5_import_dates
                CHECK (date_end >= date_start),
            KEY idx_forecast_m5_import_status_started (status, started_at),
            KEY idx_forecast_m5_import_dataset_mapping
                (dataset_sha256, mapping_sha256, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _ensure_index(
        cur,
        "products",
        "idx_products_forecast_test",
        "CREATE INDEX idx_products_forecast_test "
        "ON products (is_forecast_test, deleted, archived)",
    )
    _ensure_index(
        cur,
        "warehouses",
        "idx_warehouses_forecast_test_active",
        "CREATE INDEX idx_warehouses_forecast_test_active "
        "ON warehouses (is_forecast_test, active, warehouse_code)",
    )
    _ensure_index(
        cur,
        "forecast_demand_history",
        "idx_forecast_demand_series_source_date",
        "CREATE INDEX idx_forecast_demand_series_source_date "
        "ON forecast_demand_history (product_id, warehouse_id, source, demand_date)",
    )
    _ensure_index(
        cur,
        "forecast_demand_history",
        "idx_forecast_demand_m5_mapping_date",
        "CREATE INDEX idx_forecast_demand_m5_mapping_date "
        "ON forecast_demand_history (m5_mapping_id, demand_date)",
    )


def _migration_5_isolate_legacy_m5_products(cur):
    """Hide products created by the retired M5 importer from WMS inventory."""
    if not _column_exists(cur, "products", "is_forecast_test"):
        raise RuntimeError("Forecast test product marker is missing")
    if not _table_exists(cur, "m5_series"):
        return
    if not all(
        _column_exists(cur, "m5_series", column)
        for column in ("item_id", "store_id")
    ):
        return

    # The retired importer created SKUs as <item_id>_<store_id>. The legacy
    # m5_series rows provide a precise provenance match. Preserve quantities,
    # but hide these synthetic products and block their use in WMS operations.
    cur.execute(
        """
        UPDATE products p
        JOIN m5_series s
          ON p.sku = CONCAT(s.item_id, '_', s.store_id)
        SET p.is_forecast_test = 1
        WHERE p.is_forecast_test = 0
        """
    )


def _migration_6_forecast_run_parameters(cur):
    """Store request settings so forecast runs can be reproduced and compared."""
    if not _column_exists(cur, "forecast_runs", "parameters"):
        cur.execute(
            "ALTER TABLE forecast_runs ADD COLUMN parameters JSON NULL"
        )


def _migration_7_forecast_results_per_model(cur):
    """Allow one comparison run to persist multiple model predictions per date."""
    # The replacement starts with run_id too, so create it before removing the
    # older key. On existing databases the legacy key may be the index InnoDB
    # selected to support fk_forecast_result_run.
    _ensure_index(
        cur,
        "forecast_results",
        "uq_forecast_result_run_series_model_date",
        "CREATE UNIQUE INDEX uq_forecast_result_run_series_model_date "
        "ON forecast_results "
        "(run_id, product_id, warehouse_id, forecast_date, model_name)",
    )
    legacy_index = cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'forecast_results'
          AND index_name = 'uq_forecast_result_run_series_date'
        """
    ).fetchone()
    if int(legacy_index["n"]) > 0:
        cur.execute(
            "ALTER TABLE forecast_results "
            "DROP INDEX uq_forecast_result_run_series_date"
        )


def _migration_8_forecast_evaluation_metrics(cur):
    """Persist immutable per-series metrics for fixed M5 benchmark runs."""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS forecast_evaluation_metrics (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            run_id BIGINT NOT NULL,
            product_id INT NOT NULL,
            warehouse_id INT NOT NULL,
            model_key VARCHAR(50) NOT NULL,
            model_name VARCHAR(50) NOT NULL,
            model_version VARCHAR(30) NOT NULL,
            observation_count SMALLINT UNSIGNED NOT NULL,
            actual_demand_total DECIMAL(20,2) NOT NULL,
            absolute_error_total DECIMAL(20,4) NOT NULL,
            mae DECIMAL(20,4) NOT NULL,
            rmse DECIMAL(20,4) NOT NULL,
            wape_pct DECIMAL(20,4) NULL,
            bias DECIMAL(20,4) NOT NULL,
            mase DECIMAL(20,4) NULL,
            naive_mae_scale DECIMAL(20,4) NULL,
            zero_demand_holdout TINYINT NOT NULL DEFAULT 0,
            generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_forecast_evaluation_run_series_model
                (run_id, product_id, warehouse_id, model_key),
            KEY idx_forecast_evaluation_run_model (run_id, model_key),
            CONSTRAINT ck_forecast_evaluation_observations
                CHECK (observation_count > 0),
            CONSTRAINT ck_forecast_evaluation_actual_total
                CHECK (actual_demand_total >= 0),
            CONSTRAINT ck_forecast_evaluation_absolute_error
                CHECK (absolute_error_total >= 0),
            CONSTRAINT ck_forecast_evaluation_mae CHECK (mae >= 0),
            CONSTRAINT ck_forecast_evaluation_rmse CHECK (rmse >= 0),
            CONSTRAINT ck_forecast_evaluation_wape CHECK (wape_pct IS NULL OR wape_pct >= 0),
            CONSTRAINT ck_forecast_evaluation_zero_holdout
                CHECK (zero_demand_holdout IN (0, 1)),
            CONSTRAINT fk_forecast_evaluation_run FOREIGN KEY (run_id)
                REFERENCES forecast_runs(id) ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT fk_forecast_evaluation_product FOREIGN KEY (product_id)
                REFERENCES products(id) ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT fk_forecast_evaluation_warehouse FOREIGN KEY (warehouse_id)
                REFERENCES warehouses(id) ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


SCHEMA_MIGRATIONS = {
    3: _migration_3_forecasting_schema,
    4: _migration_4_forecasting_hardening,
    5: _migration_5_isolate_legacy_m5_products,
    6: _migration_6_forecast_run_parameters,
    7: _migration_7_forecast_results_per_model,
    8: _migration_8_forecast_evaluation_metrics,
}


def _create_schema(cur):
    cur.execute("SET SESSION default_storage_engine = InnoDB")
    statements = [
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INT NOT NULL PRIMARY KEY
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS products (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            sku VARCHAR(128) NOT NULL,
            description TEXT,
            category VARCHAR(128) NOT NULL DEFAULT '',
            tags VARCHAR(255) NOT NULL DEFAULT '',
            quantity INT NOT NULL DEFAULT 0,
            low_stock INT NOT NULL DEFAULT 10,
            archived TINYINT NOT NULL DEFAULT 0,
            deleted TINYINT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_products_sku (sku)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS movements (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            action_type VARCHAR(32) NOT NULL DEFAULT 'STOCK_ADJUST',
            delta INT NOT NULL DEFAULT 0,
            reason TEXT,
            source VARCHAR(32) NOT NULL DEFAULT 'legacy',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_movements_product FOREIGN KEY (product_id) REFERENCES products(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            contact_person VARCHAR(255) NOT NULL DEFAULT '',
            email VARCHAR(255) NOT NULL DEFAULT '',
            phone VARCHAR(64) NOT NULL DEFAULT '',
            address TEXT,
            notes TEXT,
            deleted TINYINT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            contact_person VARCHAR(255) NOT NULL DEFAULT '',
            email VARCHAR(255) NOT NULL DEFAULT '',
            phone VARCHAR(64) NOT NULL DEFAULT '',
            address TEXT,
            notes TEXT,
            deleted TINYINT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS inbound_shipments (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            supplier_id INT NOT NULL,
            quantity INT NOT NULL,
            invoice_ref VARCHAR(128) NOT NULL DEFAULT '',
            received_date DATE NOT NULL DEFAULT (CURRENT_DATE),
            notes TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_inbound_product FOREIGN KEY (product_id) REFERENCES products(id),
            CONSTRAINT fk_inbound_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS outbound_shipments (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            customer_id INT NOT NULL,
            quantity INT NOT NULL,
            so_ref VARCHAR(128) NOT NULL DEFAULT '',
            dispatch_date DATE NOT NULL DEFAULT (CURRENT_DATE),
            notes TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_outbound_product FOREIGN KEY (product_id) REFERENCES products(id),
            CONSTRAINT fk_outbound_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS inventory_batches (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            batch_code VARCHAR(64) NOT NULL,
            quantity INT NOT NULL,
            received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expiry_date DATE NULL,
            CONSTRAINT fk_batches_product FOREIGN KEY (product_id) REFERENCES products(id),
            UNIQUE KEY uq_batch_code (product_id, batch_code)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS attachments (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            entity_type VARCHAR(32) NOT NULL,
            entity_id INT NOT NULL,
            filename VARCHAR(255) NOT NULL,
            stored_name VARCHAR(255) NOT NULL,
            file_size INT NOT NULL DEFAULT 0,
            mime_type VARCHAR(128) NOT NULL DEFAULT '',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(64) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(255) NOT NULL DEFAULT '',
            role VARCHAR(32) NOT NULL DEFAULT 'operator',
            active TINYINT NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_users_username (username)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS permissions (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            role VARCHAR(32) NOT NULL,
            module VARCHAR(32) NOT NULL,
            can_read TINYINT NOT NULL DEFAULT 0,
            can_write TINYINT NOT NULL DEFAULT 0,
            can_delete TINYINT NOT NULL DEFAULT 0,
            UNIQUE KEY uq_permissions_role_module (role, module)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id INT NULL,
            username VARCHAR(64) NOT NULL DEFAULT '',
            action VARCHAR(64) NOT NULL,
            module VARCHAR(32) NOT NULL DEFAULT '',
            entity_type VARCHAR(64) NOT NULL DEFAULT '',
            entity_id INT NULL,
            details TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]
    for statement in statements:
        cur.execute(statement)

    _ensure_index(
        cur,
        "products",
        "idx_products_active_updated",
        "CREATE INDEX idx_products_active_updated ON products (deleted, archived, updated_at)",
    )
    _ensure_index(
        cur,
        "products",
        "idx_products_stock",
        "CREATE INDEX idx_products_stock ON products (deleted, archived, quantity, low_stock)",
    )
    _ensure_index(
        cur,
        "movements",
        "idx_movements_product_created",
        "CREATE INDEX idx_movements_product_created ON movements (product_id, created_at)",
    )
    _ensure_index(
        cur,
        "movements",
        "idx_movements_source_created",
        "CREATE INDEX idx_movements_source_created ON movements (source, created_at)",
    )
    _ensure_index(
        cur,
        "inbound_shipments",
        "idx_inbound_created",
        "CREATE INDEX idx_inbound_created ON inbound_shipments (created_at)",
    )
    _ensure_index(
        cur,
        "outbound_shipments",
        "idx_outbound_created",
        "CREATE INDEX idx_outbound_created ON outbound_shipments (created_at)",
    )
    _ensure_index(
        cur,
        "inventory_batches",
        "idx_batches_expiry",
        "CREATE INDEX idx_batches_expiry ON inventory_batches (product_id, expiry_date, received_at)",
    )
    _ensure_index(
        cur,
        "attachments",
        "idx_attachments_entity",
        "CREATE INDEX idx_attachments_entity ON attachments (entity_type, entity_id)",
    )
    _ensure_index(
        cur,
        "audit_logs",
        "idx_audit_logs_created",
        "CREATE INDEX idx_audit_logs_created ON audit_logs (created_at)",
    )


def _truncate_for_tests(cur):
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    for table in DATA_TABLES:
        cur.execute(f"TRUNCATE TABLE {table}")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")


def init_db():
    conn = get_db()
    cur = conn.cursor()
    migration_lock = "novaledger_schema_migrations"
    lock_acquired = False
    try:
        lock_row = cur.execute(
            "SELECT GET_LOCK(?, 60) AS acquired", (migration_lock,)
        ).fetchone()
        lock_acquired = lock_row is not None and int(lock_row["acquired"] or 0) == 1
        if not lock_acquired:
            raise RuntimeError("Could not acquire the database schema migration lock")

        _create_schema(cur)
        version = _schema_version(cur)
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {version} is newer than this application supports ({SCHEMA_VERSION})"
            )
        if version == 0:
            # The base schema is created by _create_schema. Record its latest
            # pre-migration version so fresh and existing databases share one path.
            cur.execute("INSERT INTO schema_migrations (version) VALUES (?)", (BASE_SCHEMA_VERSION,))
            version = BASE_SCHEMA_VERSION
        while version < SCHEMA_VERSION:
            next_version = version + 1
            migration = SCHEMA_MIGRATIONS.get(next_version)
            if migration is None:
                raise RuntimeError(f"Missing database migration for schema version {next_version}")
            migration(cur)
            cur.execute("INSERT INTO schema_migrations (version) VALUES (?)", (next_version,))
            version = next_version
        if APP_ENV == "test":
            _truncate_for_tests(cur)
        seed_auth(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if lock_acquired:
            try:
                cur.execute("SELECT RELEASE_LOCK(?)", (migration_lock,))
            except Exception:
                # Closing the connection also releases a connection-scoped lock.
                pass
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
    if cur.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0:
        import bcrypt

        validate_initial_admin_credentials()
        password_hash = bcrypt.hashpw(INITIAL_ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            (INITIAL_ADMIN_USERNAME, password_hash, "Administrator", "admin"),
        )

    if cur.execute("SELECT COUNT(*) AS n FROM permissions").fetchone()["n"] == 0:
        for role, modules in DEFAULT_MATRIX.items():
            for module, (can_read, can_write, can_delete) in modules.items():
                cur.execute(
                    "INSERT INTO permissions (role, module, can_read, can_write, can_delete) VALUES (?, ?, ?, ?, ?)",
                    (role, module, can_read, can_write, can_delete),
                )
