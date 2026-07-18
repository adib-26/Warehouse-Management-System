from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routes import products, movements, suppliers, inbound, attachments, customers, outbound, auth, admin
import os

app = FastAPI(title="NovaLedger WMS API", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
app.include_router(attachments.router, prefix=f"{V1}/attachments", tags=["Attachments"])
app.include_router(admin.router, prefix=f"{V1}/admin", tags=["Admin"])
app.include_router(admin.audit_router, prefix=f"{V1}/audit-logs", tags=["Audit"])


@app.on_event("startup")
def on_startup():
    init_db()
    os.makedirs("uploads", exist_ok=True)


@app.get("/")
def root():
    return {"status": "NovaLedger API running", "version": "4.0.0", "api": "/v1"}
