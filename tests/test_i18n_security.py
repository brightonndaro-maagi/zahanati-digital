import re

import pytest

from app.common.i18n import SW, tr
from app.extensions import db
from app.models import AuditLog, Notification, User
from tests.conftest import age_otp, auth, past, sms_code
from tests.test_medicines import add
from tests.test_orders import OR, place

A = "/api/v1/auth"


# ---------------- language ----------------
def test_error_and_success_messages_in_swahili(client, new_patient):
    h, _ = new_patient()
    r = client.get("/api/v1/patients/me/medical-records/00000000-0000-0000-0000-000000000000", headers={**h, "Accept-Language": "sw"})
    assert r.status_code == 404 and r.get_json()["message"] == "Rekodi ya matibabu haipatikani"
    r = client.get("/api/v1/patients/me/medical-records/00000000-0000-0000-0000-000000000000", headers=h)
    assert r.get_json()["message"] == "Medical record not found"                     # default is English
    r = client.patch("/api/v1/patients/me?lang=sw", headers=h, json={"region": "Arusha"})
    assert r.get_json()["message"] == "Wasifu umesasishwa"
    r = client.patch("/api/v1/patients/me", headers={**h, "Accept-Language": "fr;q=1, sw;q=0.8"}, json={"region": "Arusha"})
    assert r.get_json()["message"] == "Wasifu umesasishwa"


def test_dynamic_and_validation_messages_in_swahili(client, new_patient):
    h, _ = new_patient()
    sw = {**h, "Accept-Language": "sw"}
    r = client.post("/api/v1/auth/otp/request", headers={"Accept-Language": "sw"}, json={"phone": "123"})
    assert r.status_code == 422 and "si sahihi" in r.get_json()["errors"]["phone"][0]
    r = client.post("/api/v1/orders", headers=sw, json={})
    assert r.get_json()["message"] == "Uthibitishaji umeshindwa" and r.get_json()["errors"]["items"] == ["Sehemu hii inahitajika."]
    r = client.post("/api/v1/auth/otp/request", headers={"Accept-Language": "sw"}, json={"phone": "0712345678"})
    r = client.post("/api/v1/auth/otp/request", headers={"Accept-Language": "sw"}, json={"phone": "0712345678"})
    assert r.status_code == 429 and re.fullmatch(r"Tafadhali subiri sekunde \d+ kabla ya kuomba msimbo mpya\.", r.get_json()["message"])
    assert client.get("/api/v1/auth/me", headers={"Accept-Language": "sw"}).get_json()["message"] == "Unahitaji kuingia"


def test_translation_helpers():
    assert tr("Order placed", "sw") == "Oda imewekwa" and tr("Order placed", "en") == "Order placed"
    assert tr("A message nobody translated", "sw") == "A message nobody translated"        # falls back to English
    assert tr("Must be greater than or equal to 1 and less than or equal to 20.", "sw") == "Lazima iwe kati ya 1 na 20."
    assert tr("Cannot cancel an order that is ready", "sw") == "Haiwezekani kwa oda iliyo 'ready'"
    assert len(SW) > 200


def test_every_api_message_in_the_code_has_a_swahili_translation():
    """Fails when somebody adds a new fixed message without translating it."""
    import ast, pathlib
    missing = set()
    for p in pathlib.Path("app").rglob("*.py"):
        if p.name == "i18n.py":
            continue
        for n in ast.walk(ast.parse(p.read_text())):
            if isinstance(n, ast.Call):
                name = n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
                if name == "APIError" and n.args and isinstance(n.args[0], ast.Constant):
                    if tr(n.args[0].value, "sw") == n.args[0].value:
                        missing.add(n.args[0].value)
    assert not missing, sorted(missing)


def test_notifications_follow_the_viewers_language(client, new_pharmacy, new_patient):
    ph, _ = new_pharmacy()
    mid = add(client, ph, "Paracetamol 500mg", 1500, 10)
    hp, _ = new_patient()
    place(client, hp, (mid, 1))
    sw = client.get("/api/v1/notifications?lang=sw", headers=ph).get_json()["data"][0]["message"]
    en = client.get("/api/v1/notifications?lang=en", headers=ph).get_json()["data"][0]["message"]
    assert sw == "Oda mpya imepokelewa." and en == "A new order has been received."


def test_sms_language_and_user_language(client, app):
    phone = "+255712000111"
    client.post(f"{A}/otp/request", json={"phone": phone, "lang": "en"})
    from tests.conftest import sms_count
    assert "your login code is" in app.extensions["sms_outbox"][-1][1]
    r = client.post(f"{A}/otp/verify", headers={"Accept-Language": "en"}, json={"phone": phone, "code": sms_code(app, phone), "full_name": "Asha Juma"})
    h = auth(r.get_json()["data"]["access_token"])
    assert r.get_json()["data"]["user"]["language"] == "en"
    app.extensions["sms_outbox"].clear()
    age_otp(created_at=past(120))
    client.post(f"{A}/otp/request", json={"phone": phone})
    assert "msimbo wako wa kuingia" in app.extensions["sms_outbox"][-1][1]                 # default SMS language is Swahili
    assert client.patch(f"{A}/me/language", headers=h, json={"language": "fr"}).status_code == 422
    assert client.patch(f"{A}/me/language", headers=h, json={"language": "sw"}).get_json()["data"]["language"] == "sw"


# ---------------- security ----------------
def test_security_headers_and_request_id(client):
    r = client.get("/api/v1/health")
    h = r.headers
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY" and h["Referrer-Policy"] == "no-referrer"
    assert h["Cache-Control"] == "no-store" and "default-src 'none'" in h["Content-Security-Policy"] and "Strict-Transport-Security" not in h
    assert len(h["X-Request-ID"]) >= 8
    assert client.get("/api/v1/health", headers={"X-Request-ID": "trace-12345678"}).headers["X-Request-ID"] == "trace-12345678"
    assert client.get("/api/v1/health", headers={"X-Request-ID": "bad id with spaces!"}).headers["X-Request-ID"] != "bad id with spaces!"
    e = client.get("/api/v1/auth/me")
    assert e.get_json()["request_id"] == e.headers["X-Request-ID"]
    s = client.get("/api/v1/health", base_url="https://example.com")
    assert "max-age=31536000" in s.headers["Strict-Transport-Security"]


def test_audit_ip_cannot_be_forged_with_x_forwarded_for(client):
    client.post(f"{A}/login", json={"phone": "+255700000077", "password": "Wrong12345"}, headers={"X-Forwarded-For": "6.6.6.6"})
    assert AuditLog.query.filter_by(action="auth.login_failed").one().ip_address == "127.0.0.1"


def test_unknown_routes_and_methods_return_json(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404 and r.get_json()["success"] is False
    r = client.delete("/api/v1/health")
    assert r.status_code == 405 and r.get_json()["success"] is False


def test_password_change_and_reset_sign_out_other_sessions(app, client, new_doctor):
    hd, _ = new_doctor()
    me = client.get(f"{A}/me", headers=hd).get_json()["data"]
    import time
    time.sleep(1.1)                                              # tokens carry whole-second timestamps
    other = client.post(f"{A}/login", json={"phone": me["phone"], "password": "Secret123"}).get_json()["data"]
    time.sleep(1.1)
    r = client.post(f"{A}/change-password", headers=auth(other["access_token"]), json={"current_password": "Secret123", "new_password": "Brand-new-77"})
    assert r.status_code == 200
    fresh = r.get_json()["data"]["access_token"]
    assert client.get(f"{A}/me", headers=hd).status_code == 401                              # the old session is dead
    assert client.get(f"{A}/me", headers=auth(other["access_token"])).status_code == 401
    assert client.get(f"{A}/me", headers=auth(fresh)).status_code == 200                      # the new token works
    assert client.post(f"{A}/refresh", headers=auth(other["refresh_token"])).status_code == 401
    # a password reset by SMS does the same
    time.sleep(1.1)
    keep = client.post(f"{A}/login", json={"phone": me["phone"], "password": "Brand-new-77"}).get_json()["data"]
    time.sleep(1.1)
    client.post(f"{A}/forgot-password", json={"phone": me["phone"]})
    client.post(f"{A}/reset-password", json={"phone": me["phone"], "code": sms_code(app, me["phone"]), "new_password": "Another-pass-5"})
    assert client.get(f"{A}/me", headers=auth(keep["access_token"])).status_code == 401


@pytest.mark.parametrize("weak", ["12345678", "password1", "Password123", "aaaaaaa1", "qwerty123", "11111111"])
def test_weak_passwords_are_refused(client, weak):
    r = client.post(f"{A}/forgot-password", json={"phone": "+255700000001"})
    r = client.post(f"{A}/reset-password", json={"phone": "+255700000001", "code": "123456", "new_password": weak})
    assert r.status_code == 422 and "new_password" in r.get_json()["errors"]
