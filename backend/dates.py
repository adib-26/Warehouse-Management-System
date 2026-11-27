"""Calendar-date rules shared by the shipment endpoints."""

from datetime import date, datetime, timedelta, timezone

# UTC+14 (Line Islands) is the earliest time zone to reach a new calendar day.
_EARLIEST_TIME_ZONE = timezone(timedelta(hours=14))


def business_today() -> date:
    """Today's date in UTC, the time zone every database session uses."""
    return datetime.now(timezone.utc).date()


def latest_local_today() -> date:
    """The latest date that is already "today" somewhere in the world.

    Browsers submit the user's local calendar date. Comparing it with the UTC
    date would reject same-day shipments east of UTC for part of every day, so
    shipment dates are only rejected when they are in the future everywhere.
    """
    return datetime.now(_EARLIEST_TIME_ZONE).date()
