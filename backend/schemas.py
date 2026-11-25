from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal, Optional
from datetime import date, datetime
from decimal import Decimal


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: str = Field(min_length=1, max_length=100)
    description: str = ""
    category: str = ""
    tags: str = ""
    quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    low_stock: Decimal = Field(default=Decimal("10"), ge=0, max_digits=12, decimal_places=2)


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    quantity: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    low_stock: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    archived: Optional[bool] = None


class MovementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=100)
    delta: Decimal = Field(max_digits=12, decimal_places=2)
    reason: str = ""

    @field_validator("delta")
    @classmethod
    def validate_delta(cls, value: Decimal) -> Decimal:
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
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
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
    warehouse_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    so_ref: str = ""
    dispatch_date: Optional[date] = None
    notes: str = ""


class InventoryBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_number: str = Field(min_length=1, max_length=100)
    product_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    supplier_id: Optional[int] = Field(default=None, gt=0)
    received_quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    remaining_quantity: Optional[Decimal] = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    manufacturing_date: Optional[date] = None
    expiry_date: Optional[date] = None
    received_date: Optional[datetime] = None
    status: Literal["available", "blocked"] = "available"
    opening_balance: bool = False

    @field_validator("batch_number")
    @classmethod
    def normalize_batch_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("batch_number cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_batch_dates_and_quantities(self):
        remaining = (
            self.received_quantity
            if self.remaining_quantity is None
            else self.remaining_quantity
        )
        if remaining > self.received_quantity:
            raise ValueError("remaining_quantity cannot exceed received_quantity")
        if (
            self.manufacturing_date is not None
            and self.expiry_date is not None
            and self.expiry_date < self.manufacturing_date
        ):
            raise ValueError("expiry_date cannot be earlier than manufacturing_date")
        return self


class InventoryBatchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_number: Optional[str] = Field(default=None, min_length=1, max_length=100)
    warehouse_id: Optional[int] = Field(default=None, gt=0)
    supplier_id: Optional[int] = Field(default=None, gt=0)
    received_quantity: Optional[Decimal] = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    remaining_quantity: Optional[Decimal] = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    manufacturing_date: Optional[date] = None
    expiry_date: Optional[date] = None
    received_date: Optional[datetime] = None
    status: Optional[Literal["available", "blocked", "expired", "depleted"]] = None

    @field_validator("batch_number")
    @classmethod
    def normalize_optional_batch_number(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            raise ValueError("batch_number cannot be null")
        value = value.strip()
        if not value:
            raise ValueError("batch_number cannot be blank")
        return value


class BatchAllocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["AUTO", "FIFO", "FEFO"] = "AUTO"


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
    model_config = ConfigDict(extra="forbid")

    source: Literal["M5", "WMS"]
    window_days: Literal[7, 14, 30] = 7
    series_limit: int = Field(default=1000, ge=1, le=1000)
    horizon_days: int = Field(default=1, ge=1, le=90)
    as_of_date: Optional[date] = None


class ArimaForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class ForecastRunRequest(BaseModel):
    """Common request shape for running forecasts against either data source."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["M5", "WMS"]
    model: Literal["rolling_average", "arima"] = "rolling_average"
    window_days: Literal[7, 14, 30] = 7
    history_days: Literal[90, 180, 365] = 365
    fallback_window_days: Literal[7, 14, 30] = 7
    series_limit: int = Field(default=1000, ge=1, le=1000)
    max_arima_series: int = Field(default=100, ge=1, le=250)
    horizon_days: int = Field(default=28, ge=1, le=90)
    as_of_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_arima_series_limits(self):
        if self.model == "arima" and self.max_arima_series > self.series_limit:
            if "max_arima_series" not in self.model_fields_set:
                self.max_arima_series = self.series_limit
                return self
            raise ValueError("max_arima_series cannot exceed series_limit")
        return self


class ForecastComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class StockoutReplenishment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(gt=0)
    warehouse_id: Optional[int] = Field(default=None, gt=0)
    arrival_date: date
    quantity: float = Field(gt=0, le=1_000_000_000)
    reference: str = Field(default="", max_length=128)


class StockoutRiskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    simulated_starting_stock: Optional[float] = Field(
        default=None, ge=0, le=1_000_000_000
    )
    default_lead_time_days: int = Field(default=5, ge=0, le=365)
    default_safety_stock: float = Field(default=30, ge=0, le=1_000_000_000)
    critical_max_days: int = Field(default=3, ge=0, le=87)
    high_max_days: int = Field(default=7, ge=1, le=88)
    warning_max_days: int = Field(default=14, ge=2, le=89)
    replenishments: list[StockoutReplenishment] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def validate_risk_bands(self):
        if not self.critical_max_days < self.high_max_days < self.warning_max_days:
            raise ValueError(
                "Risk thresholds must increase: critical < high < warning days"
            )
        return self


class ProductReorderSettingsRequest(BaseModel):
    """A product's reorder policy for one specific warehouse."""

    model_config = ConfigDict(extra="forbid")

    warehouse_id: int = Field(gt=0)
    lead_time_days: int = Field(ge=0, le=365)
    safety_stock: float = Field(default=0, ge=0, le=1_000_000_000)
    review_period_days: int = Field(default=1, ge=1, le=365)
