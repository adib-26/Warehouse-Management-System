from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import date


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: str = Field(min_length=1, max_length=100)
    description: str = ""
    category: str = ""
    tags: str = ""
    quantity: int = Field(default=0, ge=0)
    low_stock: int = Field(default=10, ge=0)


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=0)
    low_stock: Optional[int] = Field(default=None, ge=0)
    archived: Optional[bool] = None


class MovementCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    delta: int
    reason: str = ""

    @field_validator("delta")
    @classmethod
    def validate_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("delta must not be zero")
        return value


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
    quantity: int = Field(gt=0)
    invoice_ref: str = ""
    received_date: Optional[date] = None
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
    warehouse_id: Optional[int] = Field(default=None, gt=0)
    quantity: int = Field(gt=0)
    so_ref: str = ""
    dispatch_date: Optional[date] = None
    notes: str = ""


class WarehouseCreate(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    address: str = ""
    active: bool = True


class WarehouseUpdate(BaseModel):
    warehouse_code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    address: Optional[str] = None
    active: Optional[bool] = None
