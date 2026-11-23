from pydantic import BaseModel
from typing import Optional
from datetime import date


class ProductCreate(BaseModel):
    name: str
    sku: str
    description: str = ""
    category: str = ""
    tags: str = ""
    quantity: int = 0
    low_stock: int = 10


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    quantity: Optional[int] = None
    low_stock: Optional[int] = None
    archived: Optional[bool] = None


class MovementCreate(BaseModel):
    sku: str
    delta: int
    reason: str = ""


class SupplierCreate(BaseModel):
    name: str
    contact_person: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    notes: str = ""


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class InboundCreate(BaseModel):
    product_id: int
    supplier_id: int
    quantity: int
    invoice_ref: str = ""
    received_date: Optional[str] = None
    notes: str = ""


class CustomerCreate(BaseModel):
    name: str
    contact_person: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    notes: str = ""


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class OutboundCreate(BaseModel):
    product_id: int
    customer_id: int
    quantity: int
    so_ref: str = ""
    dispatch_date: Optional[str] = None
    notes: str = ""
