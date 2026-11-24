from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import DatabaseError, get_db, init_db
from config import get_cors_origins, UPLOAD_DIR, validate_runtime_config
from routes import products, movements, suppliers, inbound, attachments, customers, outbound, auth, admin, warehouses


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_runtime_config()
    init_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="NovaLedger WMS API", version="4.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Location"],
)

V1 = "/v1"

app.include_router(auth.router, prefix=f"{V1}/auth", tags=["Auth"])
app.include_router(products.router, prefix=f"{V1}/products", tags=["Products"])
app.include_router(movements.router, prefix=f"{V1}/movements", tags=["Movements"])
app.include_router(movements.stats_router, prefix=f"{V1}/stats", tags=["Stats"])
app.include_router(suppliers.router, prefix=f"{V1}/suppliers", tags=["Suppliers"])
app.include_router(customers.router, prefix=f"{V1}/customers", tags=["Customers"])
app.include_router(inbound.router, prefix=f"{V1}/inbound-shipments", tags=["Inbound Shipments"])
app.include_router(outbound.router, prefix=f"{V1}/outbound-shipments", tags=["Outbound Shipments"])
app.include_router(warehouses.router, prefix=f"{V1}/warehouses", tags=["Warehouses"])
app.include_router(attachments.router, prefix=f"{V1}/attachments", tags=["Attachments"])
app.include_router(admin.router, prefix=f"{V1}/admin", tags=["Admin"])
app.include_router(admin.audit_router, prefix=f"{V1}/audit-logs", tags=["Audit"])


@app.get("/")
def root():
    return {"status": "NovaLedger API running", "version": "4.0.0", "api": "/v1"}


@app.get("/health")
def health():
    conn = None
    try:
        conn = get_db()
        conn.execute("SELECT 1").fetchone()
    except (OSError, DatabaseError):
        raise HTTPException(status_code=503, detail="Database unavailable")
    finally:
        if conn is not None:
            conn.close()
    return {"status": "ok", "database": "ok"}


@app.get(f"{V1}")
def v1_root():
    return {
        "status": "NovaLedger API v1",
        "version": "4.0.0",
        "docs": "/docs",
        "resources": {
            "auth": f"{V1}/auth",
            "products": f"{V1}/products",
            "movements": f"{V1}/movements",
            "stats": f"{V1}/stats",
            "suppliers": f"{V1}/suppliers",
            "customers": f"{V1}/customers",
            "inbound_shipments": f"{V1}/inbound-shipments",
            "outbound_shipments": f"{V1}/outbound-shipments",
            "warehouses": f"{V1}/warehouses",
            "attachments": f"{V1}/attachments",
            "admin": f"{V1}/admin",
            "audit_logs": f"{V1}/audit-logs",
        },
    }
