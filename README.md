# NovaLedger

A full-stack Warehouse Management System built with modern web technologies to streamline inventory operations, stock movements, supplier management, customer management, and warehouse workflows.

## Overview

NovaLedger is designed for organizations that require secure and efficient inventory management. The system provides role-based access control, product management, shipment tracking, stock adjustments, audit logging, and administrative controls within a modern web application. The backend exposes a versioned RESTful API (`/v1`) that powers the React frontend and can also be consumed independently.

## Features

* Versioned RESTful API (`/v1`) covering every module, with interactive Swagger docs
* JWT authentication with secure password hashing using bcrypt
* Role-based access control (Admin, Manager, Operator)
* Configurable permission matrix for each module
* Complete audit trail for user and system activities
* Product catalog with search, filtering, archiving, and low-stock monitoring
* Filter-aware product CSV exports for reporting and spreadsheet workflows
* Bulk product import using CSV and Excel files
* Stock movement tracking with paginated history and filtering
* Inbound shipment management
* Outbound shipment management
* Batch-level inventory with transactional FIFO/FEFO allocation, expiry handling, and product/batch reconciliation
* Supplier management
* Customer management
* File attachment support for shipment documents
* Dashboard with inventory statistics and recent activities
* Warehouse-level rolling-average and ARIMA forecasting with isolated M5 sample data, zero-demand preservation, and safe fallbacks
* User and permission management
* Docker support with an Nginx frontend, loopback-only published ports, and a persistent data volume
* GitHub Actions checks for the API tests, frontend build, and a container smoke test

---

# Project Structure

```text
PythonProject/
│
├── README.md
├── docker-compose.yml
├── .env.example
├── .github/
│   ├── dependabot.yml
│   └── workflows/ci.yml
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── forecasting_models.py
│   ├── file_utils.py
│   ├── security.py
│   ├── schemas.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pytest.ini
│   ├── tests/
│   └── routes/
│       ├── auth.py
│       ├── admin.py
│       ├── products.py
│       ├── movements.py
│       ├── suppliers.py
│       ├── customers.py
│       ├── inbound.py
│       ├── outbound.py
│       ├── warehouses.py
│       ├── batches.py
│       ├── forecasting.py
│       └── attachments.py
│
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── security-headers.conf
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    └── src/
        ├── App.jsx
        ├── api.js
        ├── Sidebar.jsx
        ├── AuthContext.jsx
        ├── main.jsx
        └── pages/
            ├── Login.jsx
            ├── Dashboard.jsx
            ├── Products.jsx
            ├── Stock.jsx
            ├── Inbound.jsx
            ├── Outbound.jsx
            ├── Suppliers.jsx
            ├── Customers.jsx
            ├── Activity.jsx
            ├── Forecasting.jsx
            ├── Users.jsx
            ├── Permissions.jsx
            └── AuditLog.jsx
```

---

# System Architecture

```text
React + Vite + TailwindCSS
            │
            │ JWT Authentication
            ▼
FastAPI REST API (/v1)
            │
            ▼
MySQL Community Edition
```

The frontend authenticates users through the backend using JWT. Every protected request includes a bearer token that is validated before access is granted. Permissions are enforced according to the user's assigned role, while all significant actions are recorded in the audit log. Every resource is exposed under a single `/v1` prefix, so the same API that drives the React frontend can be called directly by scripts, Postman, or third-party integrations.

---

# Technology Stack

| Component        | Technology                 |
| ---------------- | --------------------------- |
| Frontend         | React 19, Vite             |
| Styling          | Tailwind CSS               |
| Routing          | React Router 7             |
| Backend          | FastAPI                    |
| API Style        | RESTful, versioned (`/v1`) |
| Authentication   | JWT (PyJWT), bcrypt        |
| Database         | MySQL Community Edition    |
| File Processing  | python-multipart, openpyxl |
| Forecasting      | statsmodels ARIMA          |
| Server           | Uvicorn                    |
| Containerization | Docker                     |
| Orchestration    | Docker Compose             |
| Static web server | Nginx                      |
| Tests            | pytest                     |
| CI               | GitHub Actions             |
| Linting          | ESLint                     |

---

# User Roles

| Role     | Permissions                                                            |
| -------- | ---------------------------------------------------------------------- |
| Admin    | Full access to all modules and administrative functions                |
| Manager  | Read and write access to operational modules without delete privileges |
| Operator | Inventory operations with read-only access to selected modules         |

Deleting a product, supplier, customer, or shipment attachment requires the
module's `delete` permission. Write access to the Administration module can be
delegated to another role, but a delegated user can only manage accounts and
assign roles that have no more access than their own role. Only
administrators can change the admin role, their own role's permissions, or
grant a permission they lack. The audit report at `/v1/audit-logs` shows
sign-in history and user or permission changes only to users who can read the
Administration module.

Development administrator credentials:

```text
Username: admin
Password: admin123
```

The local development database is seeded with this account. Docker starts in
production mode and requires a unique initial administrator password in `.env`.
New user accounts and password resets require at least 12 characters. Change
the administrator password after first login as well.

---

# Installation

## Docker Installation

Clone the repository.

```bash
git clone https://github.com/adib-26/Warehouse-Management-System.git
cd Warehouse-Management-System
```

Copy the environment template, set a unique signing key and initial
administrator password, then build and start the application. Generate the key
with `openssl rand -hex 32`; set `INITIAL_ADMIN_PASSWORD` to a unique password
with at least 16 characters.
The bcrypt-backed account password fields accept up to 72 UTF-8 bytes.

```bash
cp .env.example .env
# Edit .env: replace SECRET_KEY and INITIAL_ADMIN_PASSWORD before starting.
docker compose up --build
```

Access the application:

| Service           | URL                           |
| ----------------- | ------------------------------ |
| Frontend          | http://localhost:5173         |
| Backend           | http://localhost:8000 (local only) |
| REST API          | http://localhost:8000/v1 (local only) |
| Health check      | http://localhost:8000/health (local only) |
| API Documentation | http://localhost:8000/docs (local only) |

Docker serves a built React frontend through Nginx. MySQL Community Edition stores the inventory database in the `mysql-data` volume. Uploaded files stay in the `warehouse-data` volume. Both survive container recreation. Stop the stack with `docker compose down`. Add `-v` only when you intend to delete that data. The frontend proxies `/v1` to the backend, so it works through one browser origin by default. `VITE_API_URL` is an optional build-time override for a separately hosted public API.

Both published ports bind to `127.0.0.1` by default. If port 8000 or 5173 is
already in use, set `BACKEND_PORT` or `FRONTEND_PORT` in `.env`; the container
ports remain 8000 and 80 respectively. Deliberately change a bind address only
when a network design requires it.

The API reads `APP_ENV`, `SECRET_KEY`, `INITIAL_ADMIN_USERNAME`,
`INITIAL_ADMIN_PASSWORD`, `CORS_ORIGINS`, `DATABASE_URL`,
`DATABASE_PASSWORD`, `UPLOAD_DIR`, and `MAX_UPLOAD_BYTES` from the environment.
Docker Compose maps `MYSQL_PASSWORD` to `DATABASE_PASSWORD`, which means a
generated database password may contain URL-reserved characters without being
percent-encoded. Existing deployments that place the password in
`DATABASE_URL` continue to work. Production startup rejects the built-in
development signing key and weak first-run administrator passwords. Existing
databases keep their current users; use the administration screen to change an
existing account password. Changing `SECRET_KEY` invalidates all active JWTs.
The frontend proxy receives the same `MAX_UPLOAD_BYTES` value, so uploads are
rejected consistently at the configured limit.

### Database upgrades and backups

Schema versions are stored in the `schema_migrations` table and applied during
startup. Keep the `mysql-data` volume when updating the application image.
Before a production upgrade, dump the database:

```bash
docker compose exec -T mysql sh -c 'exec mysqldump -unovaledger -p"$MYSQL_PASSWORD" novaledger' > novaledger-pre-upgrade.sql
```

Future schema changes belong in numbered migration functions in
`backend/database.py`. Increment `SCHEMA_VERSION`, register the function in
`SCHEMA_MIGRATIONS`, and do not edit a migration that existing installations
have already applied. The current application schema version is 11.

### Production deployment notes

For an internet-facing deployment, keep the Compose ports loopback-only and
place a TLS-terminating reverse proxy (such as Caddy, Traefik, or a managed
load balancer) in front of the frontend. Serve HTTPS before exposing the app;
do not publish the backend directly. Enable HSTS only at that HTTPS boundary.

The bundled Nginx limits `POST /v1/auth/login` to a burst of 20 attempts per
client address, then one every 3 seconds; extra attempts receive HTTP 429.
Failed sign-ins are recorded in the audit log as `LOGIN_FAILED`. If another
reverse proxy forwards traffic to this Nginx, configure `set_real_ip_from` and
`real_ip_header` in `frontend/nginx.conf`; otherwise every user shares the
proxy's address and therefore one limit.

`APP_ENV=test` empties every table on startup, so the API refuses to start in
test mode unless the database name ends in `_test`.

The application database is MySQL Community Edition. Point every backend instance at the same `DATABASE_URL` and `DATABASE_PASSWORD` before running more than one API process. Do not share one MySQL data volume across hosts.

---

## Manual Installation

### Backend

```bash
cd backend

python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt

uvicorn main:app --reload --port 8000
```

Development defaults are suitable for local use. For a shared deployment, set
`APP_ENV=production`, generate a unique `SECRET_KEY`, and set the initial admin
credentials before starting Uvicorn. Production mode enforces those settings.

Optional development environment variables:

```bash
export SECRET_KEY="replace-with-a-long-random-secret"
export CORS_ORIGINS="http://localhost:5173"
```

Windows:

```bash
set SECRET_KEY=replace-with-a-long-random-secret
set CORS_ORIGINS=http://localhost:5173
```

### Isolated API integration tests

Run the API suite against a disposable MySQL container instead of the normal
application database:

```bash
PYTHON=./.venv/bin/python ./scripts/test_api_integration.sh
```

The runner creates a Docker Compose project named `novaledger-api-test` on
`127.0.0.1:3307`, runs `backend/tests/test_api.py` with `APP_ENV=test`, then
removes only that project's database volume. It never connects to or removes
the normal `mysql-data` volume. `TEST_DATABASE_URL`, when set, is constrained
to the `novaledger` user at `127.0.0.1`, `TEST_MYSQL_PORT`, and the
`novaledger_test` database; unsafe overrides are rejected before Docker starts.
The default URL safely percent-encodes
`TEST_MYSQL_PASSWORD`. Override `TEST_MYSQL_PORT`, `TEST_MYSQL_PASSWORD`, and
`TEST_MYSQL_ROOT_PASSWORD` as needed. For parallel CI jobs, also set a distinct
test-only `TEST_COMPOSE_PROJECT` such as `novaledger-api-test-ci1` and a distinct
`TEST_MYSQL_PORT`; non-test project names are rejected.

### Frontend

```bash
cd frontend

npm ci

npm run dev
```

The frontend uses the Vite development proxy by default, so start the backend on
port 8000 before running the frontend. Set `VITE_API_URL` only when the browser
must call a separately hosted API origin:

```bash
VITE_API_URL=https://api.example.com npm run dev
```

### Development checks

Run the same checks used by CI:

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pip check
python -m compileall -q .
pytest -q
(cd .. && python -m pytest -q scripts/tests)
pip-audit -r requirements.txt
pip-audit -r requirements-dev.txt

cd ../frontend
npm ci
npm run lint
npm run build
npm audit --audit-level=high
```

Open:

```text
http://localhost:5173
```

### M5 forecasting dataset

Place the M5 CSV files under `datasets/m5/raw/m5-forecasting-accuracy/`, then run:

```bash
python3 scripts/prepare_m5.py
```

The script converts `sales_train_evaluation.csv` into
`datasets/m5/processed/m5_daily_sales.csv.gz`. It maps each `d_n` sales column
to the corresponding date in `calendar.csv` and writes one row per item, store,
and date with the columns `item_id`, `store_id`, `date`, and `daily_sales`.
Rows retain zero sales, preserve the input series order, and sort dates within
each series. The sales rows are streamed, so the full long-format dataset does
not need to fit in memory. Gzip compression defaults to level 6;
`--compression-level` adjusts the speed and output size tradeoff. Set `--output`
to a `.csv` path for an uncompressed file.

Each run also creates `m5_daily_sales.metadata.json` beside the dataset. The
manifest records the schema, date coverage, row and series counts, sales summary,
and SHA-256 checksums for the source and output files. The converter rejects
missing or nonconsecutive M5 days, invalid calendar dates, malformed records,
duplicate item/store series, and invalid sales values before replacing an
existing output. Pass `--no-metadata` to omit the manifest.

Before modeling, validate the processed file against the original sales and
calendar data:

```bash
python3 scripts/validate_m5.py
```

The validator checks the four-column schema, duplicate item/store/date keys,
calendar mapping, nonnegative integer sales, complete daily coverage for every
series, and preservation of zero-sales rows. It also verifies the manifest
checksums and summary when a manifest is present. Its reported mean includes
zero-sales observations. For per-series average demand, include every date in
the series when calculating the mean; a zero is a real demand observation and
must remain in the denominator.

With the included evaluation source, the generated dataset contains 59,181,090
rows across 30,490 item/store series from 2011-01-29 through 2016-05-22. To
prepare the validation period instead, use:

```bash
python3 scripts/prepare_m5.py \
  --sales datasets/m5/raw/m5-forecasting-accuracy/sales_train_validation.csv \
  --output datasets/m5/processed/m5_validation_daily_sales.csv.gz
```

Run the converter, loader, and validator regression checks with:

```bash
python3 -m pytest -q scripts/tests
```

### Forecasting database

Migration 3 adds `warehouses`, `forecast_runs`, `forecast_m5_mappings`,
`forecast_demand_history`, `forecast_results` (unique per run, series, date,
and model), `forecast_evaluation_metrics`, and `product_reorder_settings`. It
reuses NovaLedger’s existing `products` table. Forecast tables use InnoDB,
foreign keys, nonnegative quantity checks, and product/warehouse/date
uniqueness. Migration 4 adds the `is_forecast_test` markers, the
`forecast_m5_imports` audit table, and high-volume indexes. Migration 5
isolates legacy M5 records from operational inventory, and migration 6 records
forecast request parameters. Migrations 7 and 8 bring databases created before
those tables existed up to the same per-model key and metrics table that
migration 3 now creates directly.
Migration 9 adds decimal-safe batch balances and outbound allocations,
migration 10 marks the batch-tracking cutover so historic shipments cannot be
allocated against newly tracked lot balances, and migration 11 indexes lot
traceability queries.

New outbound dispatches must select a real active warehouse. The shipment,
stock decrement, stock movement, and daily `WMS` demand are written in one
transaction. CSV/XLSX outbound imports require `warehouse_code`; blank,
inactive, test, or unknown codes are reported as row errors, and future
`dispatch_date` values are rejected. Existing outbound records stay unchanged
with a null warehouse because their original location cannot be inferred. The
current inventory count remains product-level; warehouse assignment supplies
demand attribution rather than separate warehouse stock balances.

Each accepted outbound-import row is an independent dispatch. Until the input
contract includes a stable external dispatch-line ID, do not retry a partially
successful file wholesale: `so_ref` is not a safe idempotency key, so re-send
only the corrected or unprocessed rows reported by the response.

Product, inbound, and outbound imports share these rules. Header names are
case-insensitive, so a product CSV from `GET /v1/products/export` can be edited
and imported again. CSV files must be UTF-8; a file that cannot be parsed is
rejected with HTTP 400. Blank rows are skipped. A row that names a product,
supplier, or customer matching more than one record is rejected; use the SKU
instead. If MySQL aborts the import transaction (a deadlock, a lock-wait
timeout, or a lost connection), the API returns HTTP 409 and no rows from that
file are saved, so the whole file can be retried.

Shipment dates (`dispatch_date`, `received_date`) are calendar dates in the
user's time zone. The API rejects only dates that have not yet started
anywhere in the world (later than today in UTC+14), so same-day shipments work
for users east of UTC. When the date is omitted, the UTC date is used.

Administrators can create or deactivate real warehouses from the
Administration → Warehouses page or through `/v1/warehouses`. M5 test warehouses do not appear
there and cannot be used for WMS outbound transactions.

M5 records are isolated in the same shared masters with `is_forecast_test=1`.
The loader requires every M5 mapping to target an active test product and test
warehouse, and WMS dispatches reject those test records. Imported Walmart sales
only write forecast mappings, import audit rows, and `M5` demand history; they
never write `products.quantity`, outbound shipments, or stock movements.
Zero-sales days are retained.

### Rolling-average forecast

The first model is available at `POST /v1/forecasts/rolling-average`. It uses
the latest available demand date as its default `as_of_date`, calculates the
sum of demand over the selected trailing window divided by the fixed number of
calendar days, and writes one prediction per product/warehouse/date to
`forecast_results`. Supported windows are 7, 14, and 30 days; the default is
7 days. Missing WMS dates count as zero demand. The default horizon is one day;
longer horizons repeat the same average for each future date. Each run uses a
stable, deterministic sample of up to 1,000 eligible series (configurable with
`series_limit`) so even a 90-day run remains bounded at 90,000 saved rows.

For example, run the 7-day model on the isolated M5 sample:

```json
{
  "source": "M5",
  "window_days": 7,
  "horizon_days": 1
}
```

The endpoint requires `reports` write permission. Review runs with
`GET /v1/forecasts/runs` and predictions with
`GET /v1/forecasts/runs/{run_id}/results`. M5 runs only use test products and
test warehouses; WMS runs only use active operational products and warehouses.
Users with reports read access can review forecasts from Reports → Forecasts in
the web app; generating runs requires reports write permission.

### ARIMA forecast

Model B is available at `POST /v1/forecasts/arima` and fits Statsmodels
`ARIMA(1,1,1)` independently for each product/warehouse series. The default
training window is 365 trailing calendar days; 90- and 180-day windows are also
available. The default forecast horizon is 14 days. Missing WMS dates are
filled with zero demand in the daily series, and imported M5 zero-sales days
remain in the training data. To bound the cost on large catalogs, a run fits at
most 100 eligible series with ARIMA by default (configurable from 1 to 250).
The overall deterministic forecast sample is independently bounded by
`series_limit` (1 to 1,000), and all selected series outside the ARIMA fit cap
still receive rolling-average fallback results.

ARIMA is attempted only with at least 90 calendar observations and 10 days with
nonzero demand. Short or intermittent histories, invalid model output, fit
errors, and convergence warnings use the rolling-average fallback. Negative
ARIMA predictions are clipped to zero. The API response reports how many
series used each model, and each saved prediction records its actual model and
version, including fallback rows. A missing Statsmodels installation is treated
as a failed ARIMA run rather than silently mislabeling a fallback as ARIMA. To
compare models, run both with the same
source, cutoff date, and forecast horizon, then inspect the corresponding run
results in Reports → Forecasts, or call `POST /v1/forecasts/compare` to compare
the 7-day, 14-day, and 30-day rolling averages with ARIMA(1,1,1). All four
models use the same training cutoff, product/warehouse sample, and historical
holdout dates. The comparison reports MAE, RMSE, and WAPE, and saves each
model's predictions as a forecast run. ARIMA fits are capped at 100 series by
default (configurable to at most 250); other series receive a labeled 7-day
rolling-average fallback. The comparison series sample is capped at 250 (100
by default) so large M5 imports remain bounded. These simple models are a
baseline for learning and comparison; ARIMA is not expected to outperform the
rolling average for every intermittent-demand series. The comparison endpoint
requires reports write permission. Each saved prediction includes its model
name, model version, and UTC generation timestamp.
For comparisons, `as_of_date` marks the last day of the holdout; training uses
the selected number of calendar days immediately before that holdout.

### Fixed M5 benchmark evaluation

`POST /v1/forecasts/m5-evaluations` runs one of two non-editable, 28-day M5
backtests. It accepts `experiment` (`development` or `final`), `series_limit`,
and `max_arima_series`; it does not accept a custom cutoff, training span, or
horizon.

| Experiment | Training data | Test data | Calendar dates |
| --- | --- | --- | --- |
| Development validation | `d_1`–`d_1885` (1,885 days) | `d_1886`–`d_1913` (28 days) | 2011-01-29–2016-03-27 train; 2016-03-28–2016-04-24 test |
| Final validation | `d_1`–`d_1913` (1,913 days) | `d_1914`–`d_1941` (28 days) | 2011-01-29–2016-04-24 train; 2016-04-25–2016-05-22 test |

The development split uses the M5 validation-period prefix; final validation
uses the evaluation-period range. The evaluator requires complete daily M5
coverage for every selected product/warehouse series and fails rather than
silently treating a missing imported day as zero. Zero-sale observations remain
valid observations.

For every selected product, warehouse, and model, it saves the 28 daily
predictions in `forecast_results` and an immutable metric row in
`forecast_evaluation_metrics`. `GET /v1/forecasts/runs/{run_id}/evaluation`
returns the paginated per-series report. It includes MAE, RMSE, WAPE, Bias,
and MASE, alongside actual holdout demand and model/version provenance. The
report accepts optional `product_id`, `warehouse_id`, and `model_key` filters.

Bias is mean `(prediction - actual)` in units per day, so a positive value
means overprediction. MASE scales the test MAE by the mean absolute one-step
naïve error on that series' training history; it is unavailable when that
in-sample scale is zero. Per-series WAPE is calculated as
`sum(abs(actual - prediction)) / sum(actual) * 100`; it is unavailable for a
zero-demand holdout. Those series remain in the report with MAE, RMSE, and
Bias, and are counted separately instead of being assigned a misleading
percentage. Aggregate WAPE uses the same pooled numerator and denominator;
aggregate MASE is the mean of defined per-series values.

The 7-, 14-, and 30-day rolling averages and ARIMA(1,1,1) each forecast the
same 28 test days from the full fixed training history. ARIMA still follows the
safe fallback policy for sparse, capped, invalid, or non-converged series, and
the saved model name identifies those fallback rows. The default deterministic
sample is 100 series and the maximum is 250, so a report always states when it
is a bounded sample rather than the full M5 catalog.

### Stockout risk projections

`POST /v1/forecasts/runs/{run_id}/stockout-predictions` converts a successful
run's daily predictions into product-level remaining-stock paths, first
stockout dates, risk bands, and reorder recommendations. WMS projections use
the current stock that can ship: `products.quantity`, or for batch-tracked
products the sum of unexpired, available lots in active warehouses (the same
basis as the low-stock alerts). Saved `product_reorder_settings` apply
where available; request-level fallback lead time and safety stock can be
changed for each projection. The default risk cutoffs are critical through 3
days, high through 7, warning through 14, and healthy beyond 14. They are
configurable in the request and in the Forecasts screen. Any horizon of at
least one future day can be projected. A stockout inside the horizon gets its
risk band; a product with no stockout is `healthy` only when the horizon is
longer than the warning cutoff, and `unrated` otherwise. The projection
cutoff is the day before the first forecast date, which for comparison and
benchmark runs is the end of the training period.

This application currently stores inventory quantity at product level, not by
warehouse. The projection therefore sums the selected run's daily demand across
its warehouses and compares it with that product-wide balance. It uses only
future forecast dates relative to today for WMS stock. Projections from a
capped series sample are flagged because excluded warehouses can understate
demand. The ARIMA fit cap does not set this flag, because capped series still
receive fallback predictions.

M5 contains demand but no on-hand balances, so an M5 projection requires an
explicit `simulated_starting_stock` and is labeled as a development scenario.
Incoming receipts can be included in the request with product, optional
warehouse, arrival date, quantity, and purchase-order reference. They are
applied before demand on their arrival date. NovaLedger does not yet store open
purchase orders, so receipt entries affect only that projection and do not
create or update an order. The response includes daily opening stock, demand,
receipts, unmet demand, and ending stock for each product.

### Forecast API

The forecasting service is available through the versioned `/v1/forecasts`
routes and the compatibility routes below. `POST /api/forecast/run` uses one
request shape for both sources, for example
`{"source":"WMS","model":"rolling_average","horizon_days":28}`; set
`source` to `M5` for development experiments. `model` accepts
`rolling_average` or `arima`. Product forecast listings require `model_name`
when the selected run contains multiple model outputs. Without a `run_id`,
product listings and alerts use the newest successful rolling-average or ARIMA
run; comparison and M5 benchmark runs are only read when selected by `run_id`.
Alerts keep current low-stock results available and report a forecast warning
when the projection cannot be built.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/forecast/overview?source=WMS` | Run counts and latest forecast coverage |
| GET | `/api/forecast/products?source=WMS` | Product level demand totals for the latest successful forward run, or a selected `run_id` (defaults to WMS) |
| GET | `/api/forecast/products/{id}?source=WMS` | Daily forecast rows and summary for one product (defaults to WMS) |
| POST | `/api/forecast/run` | Start an M5 or WMS forecast with a shared request shape |
| GET | `/api/forecast/runs?source=WMS` | Forecast execution history |
| GET | `/api/forecast/alerts` | Current WMS low-stock products, plus forecast risk alerts from the latest forward WMS run |
| PUT | `/api/products/{id}/reorder-settings` | Save lead time, safety stock, and review period for a product at one warehouse |

The same endpoints are also available under `/v1/forecasts` (for example
`/v1/forecasts/alerts`). The product reorder settings body requires a
`warehouse_id`; reorder policy is stored per product and warehouse. Forecast
alerts use the live `low_stock` threshold and the stock that can ship, as in
stockout projections. When the latest forward WMS run has future dates, the
same response also includes products in critical, high, or warning risk bands
and products below their reorder point. The existing
`/api/forecast/runs/{run_id}/stockout-predictions` endpoint returns the full
daily stock path and accepts optional dated receipts.

A run that is still `running` when its API process stops (for example, a
container restart) is marked `failed` the next time the API starts. Each run
holds a MySQL named lock while it works, so runs owned by another live API
process are left alone.

Example reorder-settings body:

```json
{
  "warehouse_id": 12,
  "lead_time_days": 5,
  "safety_stock": 30,
  "review_period_days": 7
}
```

For example, for an M5 development run:

```json
{
  "simulated_starting_stock": 120,
  "default_lead_time_days": 5,
  "default_safety_stock": 30,
  "critical_max_days": 3,
  "high_max_days": 7,
  "warning_max_days": 14,
  "replenishments": [
    {
      "product_id": 101,
      "warehouse_id": 12,
      "arrival_date": "2016-05-10",
      "quantity": 50,
      "reference": "PO-1042"
    }
  ]
}
```

The reorder point uses the forecast's cumulative lead-time demand plus safety
stock. Incoming quantities due by the end of lead time are included in the
inventory position. A stockout date is the first forecast date when available
stock cannot meet that day's predicted demand.

Forecasting and comparisons acquire the same M5 import lock as the loader. If
an M5 import is active, the API returns `409` instead of calculating from a
partially committed dataset.

For a manually maintained mapping file, run:

```bash
python3 scripts/create_m5_mapping_template.py
```

Fill `product_id` and `warehouse_id` using active records marked
`is_forecast_test=1`. Each M5 item/store series must map to its own
product/warehouse pair. After backend startup has applied the forecasting
schema migrations, import the processed CSV with:

```bash
python3 scripts/load_m5_forecast.py \
  --input datasets/m5/processed/m5_daily_sales.csv.gz \
  --mapping datasets/m5/processed/m5_mapping.csv
```

The loader verifies the converter manifest by default, validates every source
series (including skipped ones), preserves zero demand, validates mappings,
serializes imports with a MySQL lock, and records each activated attempt in
`forecast_m5_imports`. It hashes the artifact during that validation pass and
stages only selected rows in a connection-private InnoDB table, so a sparse
selection does not require a second scan of the full M5 file. Rerunning the
same successful input and mapping is idempotent.

For `--replace`, the staged rows are upserted, verified, and—only then—stale
dates for the selected series are pruned in one transaction together with the
success audit update. An interruption or verification failure leaves the prior
selected demand history intact; the private staging table disappears with the
connection. `--batch-size` controls staging commits only (default: 5,000 rows),
not the atomic publish step.

The host-side bootstrap and loader scripts read the repository `.env` file when
it exists, matching the Docker Compose credentials. Explicit shell environment
variables take precedence. The dependency-free loader supports ordinary
`KEY=value` entries, optional `export`, single or double quoted values, and
comments. Double quotes support common backslash escapes (`\\`, `\"`, `\n`,
`\r`, and `\t`); use the shell environment for Compose interpolation or
multi-line values. Keep `DATABASE_URL` pointed at `127.0.0.1` for host-side
scripts; Compose supplies its internal `mysql` hostname to the backend
container. Set `DATABASE_PASSWORD` to the same value as `MYSQL_PASSWORD` when
using the included `.env` template. It is passed directly to the database
driver, so it safely supports URL-reserved characters without encoding.

A GitHub clone includes that same multiwarehouse sample, without the unused
full sales and price files. The committed files are:

- `datasets/m5/sample/m5_sample_1000_series.csv` — 100 evenly spaced items in all 10 stores (1,000 series)
- `datasets/m5/sample/m5_sample_1000_daily_sales.csv.gz` — 1,941,000 daily rows from 2011-01-29 through 2016-05-22, including every zero-sales day
- `datasets/m5/sample/m5_sample_1000_daily_sales.metadata.json` — row counts and checksum for the loader

Recreate the test catalog and demand history on a fresh database:

```bash
python3 scripts/bootstrap_m5_test_catalog.py \
  --sales datasets/m5/sample/m5_sample_1000_series.csv \
  --output datasets/m5/processed/m5_mapping.csv \
  --force
python3 scripts/load_m5_forecast.py \
  --input datasets/m5/sample/m5_sample_1000_daily_sales.csv.gz \
  --mapping datasets/m5/processed/m5_mapping.csv \
  --replace
```

Bootstrap creates only `is_forecast_test=1` products and warehouses. If the 40
legacy M5 demo products are already in the database, it reuses them, marks them
test-only, and leaves their quantities unchanged. The loader writes forecast
mappings, the import audit row, and `M5` demand history. It does not change
product quantities, outbound shipments, or stock movements. A fresh clone has
no operational products until you add them in the app.

To opt in to the full M5 data set, generate a full-catalog mapping and import
all 30,490 series (59,181,090 rows):

```bash
python3 scripts/bootstrap_m5_test_catalog.py --output datasets/m5/processed/m5_mapping.csv --force
python3 scripts/load_m5_forecast.py --input datasets/m5/processed/m5_daily_sales.csv.gz --mapping datasets/m5/processed/m5_mapping.csv --replace
```

The full import stages every selected row in a private MySQL table before its
atomic publish. Make room for the existing forecast history, a temporary staged
copy, and indexes; test the included sample first on the target database and
monitor available disk throughout the import.

The bootstrap uses the existing product and warehouse tables, creates only
zero-stock records marked `is_forecast_test=1`, and writes a populated mapping
CSV. It reuses legacy M5 demo products when present and preserves their stored
quantities while marking them as test records. `scripts/import_m5.py` is retired
because it created separate untracked M5 tables outside the NovaLedger
forecast schema.

---

# RESTful API Reference

All endpoints are served under the base path `/v1`. Interactive, always-up-to-date documentation (Swagger UI) is available at `http://localhost:8000/docs`.

Unless noted otherwise, every endpoint requires a valid JWT bearer token in the `Authorization` header, and access is additionally gated by the caller's role permissions for that module.

### Authentication — `/v1/auth`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| POST   | `/v1/auth/login` | Authenticate with username and password, returns a JWT and user profile |
| GET    | `/v1/auth/me` | Retrieve the currently authenticated user |

### Products — `/v1/products`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/products` | List products, with search, filtering, and pagination |
| GET    | `/v1/products/export` | Download the current product filters as CSV |
| GET    | `/v1/products/facets` | List category and tag values used by the catalog filters |
| GET    | `/v1/products/{product_id}` | Retrieve a single product |
| POST   | `/v1/products` | Create a new product |
| PATCH  | `/v1/products/{product_id}` | Update an existing product |
| DELETE | `/v1/products/{product_id}` | Archive/delete a product |
| POST   | `/v1/products/imports` | Bulk import products from a CSV or Excel file |

### Stock Movements — `/v1/movements`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/movements` | List stock movements, filterable by product and action type, paginated |
| POST   | `/v1/movements` | Record a stock adjustment (in, out, or correction) |
| DELETE | `/v1/movements/{movement_id}` | Undo/reverse a stock movement |

### Stats — `/v1/stats`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/stats` | Retrieve dashboard/inventory statistics |

### Suppliers — `/v1/suppliers`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/suppliers` | List suppliers, with search and pagination |
| GET    | `/v1/suppliers/{supplier_id}` | Retrieve a single supplier |
| POST   | `/v1/suppliers` | Create a new supplier |
| PATCH  | `/v1/suppliers/{supplier_id}` | Update an existing supplier |
| DELETE | `/v1/suppliers/{supplier_id}` | Delete a supplier |

### Customers — `/v1/customers`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/customers` | List customers, with search and pagination |
| GET    | `/v1/customers/{customer_id}` | Retrieve a single customer |
| POST   | `/v1/customers` | Create a new customer |
| PATCH  | `/v1/customers/{customer_id}` | Update an existing customer |
| DELETE | `/v1/customers/{customer_id}` | Delete a customer |

### Inbound Shipments — `/v1/inbound-shipments`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| POST   | `/v1/inbound-shipments` | Create a new inbound shipment |
| GET    | `/v1/inbound-shipments` | List inbound shipments, with filtering and pagination |
| GET    | `/v1/inbound-shipments/{shipment_id}/attachments` | List attachments for a shipment |
| POST   | `/v1/inbound-shipments/{shipment_id}/attachments` | Upload an attachment to a shipment |
| POST   | `/v1/inbound-shipments/imports` | Bulk import inbound shipments from a file |

### Outbound Shipments — `/v1/outbound-shipments`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| POST   | `/v1/outbound-shipments` | Create a new outbound shipment |
| GET    | `/v1/outbound-shipments` | List outbound shipments, with filtering and pagination |
| GET    | `/v1/outbound-shipments/{shipment_id}/attachments` | List attachments for a shipment |
| POST   | `/v1/outbound-shipments/{shipment_id}/attachments` | Upload an attachment to a shipment |
| POST   | `/v1/outbound-shipments/imports` | Bulk import outbound shipments from a file |

### Warehouses — `/v1/warehouses`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/warehouses` | List real active warehouses for outbound attribution |
| POST   | `/v1/warehouses` | Create a real warehouse (administrator) |
| PATCH  | `/v1/warehouses/{warehouse_id}` | Update or activate/deactivate a real warehouse (administrator) |

### Batch inventory — `/api`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| POST | `/api/batches` | Receive a real lot, or enable tracking with an opening balance matching existing product stock |
| GET | `/api/batches` | Filter and page through lots, including expiry and reconciliation fields |
| GET | `/api/batches/{id}` | Read one lot |
| PUT | `/api/batches/{id}` | Correct lot details, status, or remaining balance |
| GET | `/api/products/{id}/batches` | List a product's lots and its stock reconciliation summary |
| GET | `/api/batches/reconciliation` | Report products whose total batch balance differs from product on-hand |
| POST | `/api/products/{id}/batches/reconcile` | Set product on-hand to the sum of remaining lot balances and record the adjustment |
| POST | `/api/outbound/{id}/allocate` | Allocate an outbound shipment using `AUTO`, `FIFO`, or `FEFO` |
| GET | `/api/outbound/{id}/allocations` | Read the lot allocations for one outbound shipment |

`AUTO` uses FEFO when eligible lots have expiry dates and FIFO otherwise. The
InnoDB transaction locks the product and eligible lot rows; product on-hand,
remaining lot balances, allocation rows, and stock movements commit together.
Expired, blocked, and depleted lots are never allocated. If eligible stock
cannot cover the full order, the transaction rolls back without a partial
dispatch.

`inventory_batches.remaining_quantity` is the source of truth for tracked
products. Product edits, manual stock movements, and ordinary inbound receipts
cannot change a tracked product's quantity; receive an actual supplier lot
through `POST /api/batches`. When converting a product with existing stock, set
`opening_balance: true` and make both `received_quantity` and
`remaining_quantity` equal its current on-hand balance. Later receipts add the
new remaining quantity to product on-hand. Use the reconciliation report to
find older mismatches, then apply the explicit reconciliation endpoint before
allocating stock.

M5 contains no lot or expiry facts, so it is never used to infer operational
batches. For development only, the sample script can create clearly marked
synthetic lots on forecast-test products and warehouses. It previews by default
and writes only with `--apply`:

```bash
python3 scripts/seed_m5_sample_batches.py --count 10
python3 scripts/seed_m5_sample_batches.py --count 10 --apply
```

### Forecasting — `/v1/forecasts`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| POST   | `/v1/forecasts/rolling-average` | Generate 7-, 14-, or 30-day rolling-average predictions |
| POST   | `/v1/forecasts/arima` | Generate ARIMA(1,1,1) predictions with rolling-average fallback |
| POST   | `/v1/forecasts/compare` | Save and score four model predictions on one historical holdout sample |
| POST   | `/v1/forecasts/m5-evaluations` | Run a fixed 28-day M5 development or final backtest and save its report |
| POST   | `/v1/forecasts/runs/{run_id}/stockout-predictions` | Project stockout dates, risk bands, daily balances, and reorder recommendations from a saved run |
| GET    | `/v1/forecasts/runs` | List forecasting runs |
| GET    | `/v1/forecasts/runs/{run_id}/results` | List predictions for a run, optionally filtered by product or warehouse |
| GET    | `/v1/forecasts/runs/{run_id}/evaluation` | List per-product, warehouse, and model metrics for a fixed M5 evaluation |
| POST   | `/v1/forecasts/run` | Start a rolling-average or ARIMA run with one shared request shape |
| GET    | `/v1/forecasts/overview` | Run counts and the latest forecast's coverage |
| GET    | `/v1/forecasts/products` | Product demand totals for the latest forward run, or a selected `run_id` |
| GET    | `/v1/forecasts/products/{product_id}` | Daily forecast rows for one product |
| GET    | `/v1/forecasts/alerts` | Live low-stock products plus forecast stockout risk |

### Attachments — `/v1/attachments`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/attachments/{attachment_id}` | Download an attachment |
| DELETE | `/v1/attachments/{attachment_id}` | Delete an attachment (requires the shipment module's delete permission) |

### Administration — `/v1/admin`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/admin/users` | List all users |
| POST   | `/v1/admin/users` | Create a new user |
| PATCH  | `/v1/admin/users/{user_id}` | Update a user (role, password, active status) |
| GET    | `/v1/admin/permissions` | Retrieve the role permission matrix |
| PUT    | `/v1/admin/permissions` | Update the role permission matrix |
| GET    | `/v1/admin/audit-logs` | Retrieve audit logs from the admin panel |

### Audit — `/v1/audit-logs`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/audit-logs` | Retrieve a filterable, paginated audit log report |

---

# Application Modules

| Module      | Description                      |
| ----------- | --------------------------------- |
| Login       | User authentication              |
| Dashboard   | Inventory summary and statistics |
| Products    | Product catalog management       |
| Stock       | Inventory adjustments            |
| Inbound     | Incoming shipments               |
| Outbound    | Outgoing shipments               |
| Suppliers   | Supplier directory               |
| Customers   | Customer directory               |
| Activity    | Inventory history                |
| Forecasting | Rolling-average and ARIMA models |
| Users       | User administration              |
| Permissions | Role permission management       |
| Audit Log   | System activity records          |

Navigation is generated dynamically based on the authenticated user's permissions.

---

# Author

Mahbub

Warehouse Management System
