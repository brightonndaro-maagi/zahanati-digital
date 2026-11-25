"""All datetimes are stored in UTC. Clients may send ISO-8601 with an offset; a value without
an offset is interpreted in the clinic timezone (Africa/Dar_es_Salaam by default)."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app


def clinic_tz():
    return ZoneInfo(current_app.config["CLINIC_TIMEZONE"])


def utcnow():
    return datetime.now(timezone.utc)


def to_utc(dt):
    """Client input -> aware UTC (naive input is clinic-local)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=clinic_tz())
    return dt.astimezone(timezone.utc)


def as_utc(dt):
    """Database value -> aware UTC (SQLite returns naive values, which are already UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_local(dt):
    return as_utc(dt).astimezone(clinic_tz())


def local_day_start_utc(d: date):
    return datetime.combine(d, time.min, tzinfo=clinic_tz()).astimezone(timezone.utc)


def today_local():
    return utcnow().astimezone(clinic_tz()).date()
