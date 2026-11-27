"""Decimal-safe helpers for inventory amounts stored at two decimal places."""

from decimal import Decimal, InvalidOperation


CENT = Decimal("0.01")
# Inventory columns are DECIMAL(12,2).
MAX_QUANTITY = Decimal("9999999999.99")


def as_quantity(value, *, allow_zero: bool = True) -> Decimal:
    try:
        quantity = Decimal(str(value if value is not None else 0))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Quantity must be a number with at most two decimal places") from exc
    if not quantity.is_finite() or quantity != quantity.quantize(CENT):
        raise ValueError("Quantity must be a finite number with at most two decimal places")
    quantity = quantity.quantize(CENT)
    if quantity > MAX_QUANTITY:
        raise ValueError(f"Quantity cannot exceed {MAX_QUANTITY}")
    if not allow_zero and quantity <= 0:
        raise ValueError("Quantity must be greater than zero")
    if allow_zero and quantity < 0:
        raise ValueError("Quantity cannot be negative")
    return quantity


def quantity_for_json(value):
    quantity = as_quantity(value)
    return int(quantity) if quantity == quantity.to_integral_value() else float(quantity)
