from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal, Optional
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


class RollingAverageForecastRequest(BaseModel):
    source: Literal["M5", "WMS"]
    window_days: Literal[7, 14, 30] = 7
    series_limit: int = Field(default=1000, ge=1, le=1000)
    horizon_days: int = Field(default=1, ge=1, le=90)
    as_of_date: Optional[date] = None


class ArimaForecastRequest(BaseModel):
    source: Literal["M5", "WMS"]
    history_days: Literal[90, 180, 365] = 365
    fallback_window_days: Literal[7, 14, 30] = 7
    series_limit: int = Field(default=1000, ge=1, le=1000)
    max_arima_series: int = Field(default=100, ge=1, le=250)
    horizon_days: int = Field(default=14, ge=1, le=90)
    as_of_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_series_limits(self):
        if self.max_arima_series > self.series_limit:
            # A caller that only narrows the overall sample should still get a
            # useful request. Explicitly inconsistent caps remain an error.
            if "max_arima_series" not in self.model_fields_set:
                self.max_arima_series = self.series_limit
                return self
            raise ValueError("max_arima_series cannot exceed series_limit")
        return self


class ForecastComparisonRequest(BaseModel):
    source: Literal["M5", "WMS"]
    history_days: Literal[90, 180, 365] = 365
    horizon_days: int = Field(default=14, ge=1, le=90)
    series_limit: int = Field(default=100, ge=1, le=250)
    max_arima_series: int = Field(default=100, ge=1, le=250)
    as_of_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_series_limits(self):
        if self.max_arima_series > self.series_limit:
            if "max_arima_series" not in self.model_fields_set:
                self.max_arima_series = self.series_limit
                return self
            raise ValueError("max_arima_series cannot exceed series_limit")
        return self


class M5EvaluationRequest(BaseModel):
    """Fixed M5 backtest protocol; dates and 28-day horizon are not configurable."""

    model_config = ConfigDict(extra="forbid")
    experiment: Literal["development", "final"] = "development"
    series_limit: int = Field(default=100, ge=1, le=250)
    max_arima_series: int = Field(default=100, ge=1, le=250)

    @model_validator(mode="after")
    def validate_series_limits(self):
        if self.max_arima_series > self.series_limit:
            if "max_arima_series" not in self.model_fields_set:
                self.max_arima_series = self.series_limit
                return self
            raise ValueError("max_arima_series cannot exceed series_limit")
        return self
