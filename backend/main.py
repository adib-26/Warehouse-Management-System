from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routes import products, stock, history, suppliers, inbound, attachments
import os

app = FastAPI(title="NovaLedger WMS API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router, prefix="/products", tags=["Products"])
app.include_router(stock.router, prefix="/stock", tags=["Stock"])
app.include_router(history.router, prefix="/history", tags=["History"])
app.include_router(suppliers.router, prefix="/suppliers", tags=["Suppliers"])
app.include_router(inbound.router, prefix="/inbound", tags=["Inbound"])
app.include_router(attachments.router, prefix="/attachments", tags=["Attachments"])


@app.on_event("startup")
def on_startup():
    init_db()
    os.makedirs("uploads", exist_ok=True)


@app.get("/")
def root():
    return {"status": "NovaLedger API running", "version": "3.0.0"}
