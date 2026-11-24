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
`INITIAL_ADMIN_PASSWORD`, `CORS_ORIGINS`, `DATABASE_URL`, `MYSQL_PASSWORD`,
`MYSQL_ROOT_PASSWORD`, `UPLOAD_DIR`, and `MAX_UPLOAD_BYTES` from the environment.
`MYSQL_PASSWORD` is the password inside `DATABASE_URL`. Production startup rejects the built-in
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
docker compose exec -T mysql mysqldump -unovaledger -p"$MYSQL_PASSWORD" novaledger > novaledger-pre-upgrade.sql
```

Future schema changes belong in numbered migration functions in
`backend/database.py`. Increment `SCHEMA_VERSION`, register the function in
`SCHEMA_MIGRATIONS`, and do not edit a migration that existing installations
have already applied.

### Production deployment notes

For an internet-facing deployment, keep the Compose ports loopback-only and
place a TLS-terminating reverse proxy (such as Caddy, Traefik, or a managed
load balancer) in front of the frontend. Serve HTTPS before exposing the app;
do not publish the backend directly. Enable HSTS only at that HTTPS boundary.

The application database is MySQL Community Edition. Point every backend instance at the same `DATABASE_URL` before running more than one API process. Do not share one MySQL data volume across hosts.

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

Run the converter and validator regression checks with:

```bash
python3 -m unittest discover -s scripts/tests -v
```

### Forecasting database

The version 5 migration adds `forecast_demand_history`, `forecast_results`,
`forecast_runs`, `product_reorder_settings`, `forecast_m5_mappings`, and
`forecast_m5_imports`. It reuses NovaLedger’s existing `products` table and
adds one shared `warehouses` master. Forecast tables use InnoDB, foreign keys,
nonnegative quantity checks, and product/warehouse/date uniqueness.
Version 6 adds request parameters to forecast runs so their source, cutoff,
history window, and horizon remain visible for later review. Version 7 lets one
comparison run save predictions from multiple models for the same product,
warehouse, and test date. Version 8 adds immutable per-series metric reports
for fixed M5 benchmark evaluations.

New outbound dispatches must select a real warehouse in the web app. The
shipment, stock decrement, stock movement, and daily `WMS` demand are written
in one transaction. CSV/XLSX outbound imports can include `warehouse_code`;
without it the shipment remains valid but does not contribute warehouse-level
forecast demand. Existing outbound records stay unchanged with a null
warehouse because their original location cannot be inferred. The current
inventory count remains product-level; warehouse assignment supplies demand
attribution rather than separate warehouse stock balances.

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

Forecasting and comparisons acquire the same M5 import lock as the loader. If
an M5 import is active, the API returns `409` instead of calculating from a
partially committed dataset.

For a manually maintained mapping file, run:

```bash
python3 scripts/create_m5_mapping_template.py
```

Fill `product_id` and `warehouse_id` using active records marked
`is_forecast_test=1`. Each M5 item/store series must map to its own
product/warehouse pair. After the version 5 migration has run at backend
startup, import the processed CSV with:

```bash
python3 scripts/load_m5_forecast.py \
  --input datasets/m5/processed/m5_daily_sales.csv.gz \
  --mapping datasets/m5/processed/m5_mapping.csv
```

The loader verifies the converter manifest by default, validates every source
series, preserves zero demand, validates mappings, serializes imports with a
MySQL lock, and records each attempt in `forecast_m5_imports`. Rerunning the
same successful input and mapping is idempotent. To load a different source or
mapping for a selected series, use `--replace`; it upserts the complete
replacement first, then prunes only stale dates for those affected M5 series.
An interrupted import therefore does not clear the previous series up front.

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

### Forecasting — `/v1/forecasts`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| POST   | `/v1/forecasts/rolling-average` | Generate 7-, 14-, or 30-day rolling-average predictions |
| POST   | `/v1/forecasts/arima` | Generate ARIMA(1,1,1) predictions with rolling-average fallback |
| POST   | `/v1/forecasts/compare` | Save and score four model predictions on one historical holdout sample |
| POST   | `/v1/forecasts/m5-evaluations` | Run a fixed 28-day M5 development or final backtest and save its report |
| GET    | `/v1/forecasts/runs` | List forecasting runs |
| GET    | `/v1/forecasts/runs/{run_id}/results` | List predictions for a run, optionally filtered by product or warehouse |
| GET    | `/v1/forecasts/runs/{run_id}/evaluation` | List per-product, warehouse, and model metrics for a fixed M5 evaluation |

### Attachments — `/v1/attachments`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET    | `/v1/attachments/{attachment_id}` | Download an attachment |
| DELETE | `/v1/attachments/{attachment_id}` | Delete an attachment |

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
