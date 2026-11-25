import itertools
import re
from datetime import datetime, timedelta, timezone

import pytest
from app import create_app
from app.extensions import db as _db
from app.models import Appointment, OtpCode, User

DOCTOR = {"password": "Secret123", "first_name": "Neema", "last_name": "Mushi", "qualification": "MD"}
PHARMACY = {"password": "Secret123", "name": "Afya Pharmacy", "address": "Kariakoo, Dar es Salaam",
            "latitude": -6.8184, "longitude": 39.2766}

_counter = itertools.count(1)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def sms_code(app, phone):
    """Latest 6-digit code sent by SMS to `phone` (tests use the in-memory SMS gateway)."""
    for to, msg in reversed(app.extensions.get("sms_outbox", [])):
        if to == phone:
            return re.search(r"\b(\d{6})\b", msg).group(1)
    raise AssertionError(f"No SMS was sent to {phone}")


def sms_count(app, phone=None):
    box = app.extensions.get("sms_outbox", [])
    return len([1 for to, _ in box if phone is None or to == phone])


def age_otp(**fields):
    """Make OTP rows look older instead of sleeping (e.g. age_otp(created_at=..., locked_until=None))."""
    for row in OtpCode.query.all():
        for k, v in fields.items():
            setattr(row, k, v)
    _db.session.commit()


def past(seconds):
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


@pytest.fixture()
def app(tmp_path):
    app = create_app("testing")
    app.config["UPLOAD_DIR"] = str(tmp_path / "uploads")   # every test gets its own empty upload folder
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()
        _db.engine.dispose()   # hand every connection back now: each test builds its own app, and a slow garbage collector
                               # (e.g. Python 3.14) would otherwise leave hundreds open until PostgreSQL refuses new ones


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_admin(app):
    def _make(phone="+255700000001", email="admin@example.com", password="Admin12345"):
        u = User(phone=phone, email=email, role="admin")
        u.set_password(password)
        _db.session.add(u)
        _db.session.commit()
        return u
    return _make


@pytest.fixture()
def admin_headers(client, make_admin):
    make_admin()
    r = client.post("/api/v1/auth/login", json={"phone": "+255700000001", "password": "Admin12345"})
    assert r.status_code == 200, r.get_json()
    return auth(r.get_json()["data"]["access_token"])


@pytest.fixture()
def new_patient(app, client):
    """Create a patient through the real OTP flow; returns (headers, patient_profile_id)."""
    def _new(full_name="Asha Juma"):
        n = next(_counter)
        phone = f"+25571{n:07d}"
        assert client.post("/api/v1/auth/otp/request", json={"phone": phone}).status_code == 200
        r = client.post("/api/v1/auth/otp/verify", json={"phone": phone, "code": sms_code(app, phone), "full_name": full_name})
        assert r.status_code == 201, r.get_json()
        d = r.get_json()["data"]
        return auth(d["access_token"]), User.query.filter_by(phone=phone).one().patient_profile.id
    return _new


def _register_staff(app, client, kind, body):
    phone = body["phone"]
    assert client.post("/api/v1/auth/otp/request", json={"phone": phone, "purpose": "register"}).status_code == 200
    r = client.post(f"/api/v1/auth/register/{kind}", json={**body, "otp_code": sms_code(app, phone)})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


@pytest.fixture()
def register_staff(app, client):
    return lambda kind, body: _register_staff(app, client, kind, body)


@pytest.fixture()
def new_doctor(app, client, admin_headers):
    """Register a doctor; verified by default. Returns (headers, doctor_profile_id)."""
    def _new(verified=True, **over):
        n = next(_counter)
        body = {**DOCTOR, "phone": f"+25572{n:07d}", "license_number": f"MCT-{n:04d}", **over}
        d = _register_staff(app, client, "doctor", body)
        did = User.query.filter_by(phone=body["phone"]).one().doctor_profile.id
        if verified:
            assert client.post(f"/api/v1/admin/doctors/{did}/verify", headers=admin_headers).status_code == 200
        return auth(d["access_token"]), did
    return _new


@pytest.fixture()
def new_pharmacy(app, client, admin_headers):
    """Register a pharmacy; approved by default. Returns (headers, pharmacy_profile_id)."""
    def _new(approved=True, **over):
        n = next(_counter)
        body = {**PHARMACY, "phone": f"+25573{n:07d}", "license_number": f"PC-{n:04d}", **over}
        d = _register_staff(app, client, "pharmacy", body)
        pid = User.query.filter_by(phone=body["phone"]).one().pharmacy_profile.id
        if approved:
            assert client.post(f"/api/v1/admin/pharmacies/{pid}/approve", headers=admin_headers).status_code == 200
        return auth(d["access_token"]), pid
    return _new


@pytest.fixture()
def make_appointment(app):
    """Insert an appointment directly."""
    def _make(patient_id, doctor_id, status="accepted", hours=24):
        start = datetime.now(timezone.utc) + timedelta(hours=hours)
        a = Appointment(patient_id=patient_id, doctor_id=doctor_id, status=status,
                        start_time=start, end_time=start + timedelta(minutes=30))
        _db.session.add(a)
        _db.session.commit()
        return a
    return _make
