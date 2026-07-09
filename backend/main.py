from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routes import products, stock, history

app = FastAPI(title="NovaLedger WMS API", version="2.0.0")

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


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def root():
    return {"status": "NovaLedger API running", "version": "2.0.0"}
