from app.models import AuditLog
from tests.conftest import PHARMACY, auth, sms_code

A, P, AD = "/api/v1/auth", "/api/v1/pharmacies", "/api/v1/admin"
PHONE = "+255744123456"


def _body(**over):
    return {**PHARMACY, "phone": PHONE, "license_number": "PC-0001", **over}


def _reg(client, app, **over):
    body = _body(**over)
    client.post(f"{A}/otp/request", json={"phone": body["phone"], "purpose": "register"})
    return client.post(f"{A}/register/pharmacy", json={**body, "otp_code": sms_code(app, body["phone"])})


def test_pharmacy_registers_pending(app, client):
    r = _reg(client, app)
    assert r.status_code == 201
    d = r.get_json()["data"]
    assert d["user"]["role"] == "pharmacy" and d["user"]["approval_status"] == "pending"
    me = client.get(f"{P}/me", headers=auth(d["access_token"])).get_json()["data"]
    assert me["approval_status"] == "pending" and me["latitude"] == -6.8184 and me["phone"] == PHONE
    assert AuditLog.query.filter_by(action="pharmacy.register").count() == 1


def test_pharmacy_validation_and_uniqueness(app, client):
    assert _reg(client, app, latitude=123).status_code == 422
    assert _reg(client, app, longitude=-500).status_code == 422
    body = {k: v for k, v in _body().items() if k != "latitude"}
    client.post(f"{A}/otp/request", json={"phone": PHONE, "purpose": "register"})
    r = client.post(f"{A}/register/pharmacy", json={**body, "otp_code": sms_code(app, PHONE)})
    assert r.status_code == 422                                   # GPS is mandatory
    assert _reg(client, app).status_code == 201
    assert _reg(client, app, phone="+255744999999").status_code == 409   # same licence number
    assert _reg(client, app, phone="+255744999999", license_number="PC-0002").status_code == 201


def test_admin_approves_and_rejects(client, new_pharmacy, admin_headers):
    h, pid = new_pharmacy(approved=False)
    assert client.get(f"{AD}/pharmacies?status=pending", headers=admin_headers).get_json()["meta"]["total"] == 1
    assert client.post(f"{AD}/pharmacies/{pid}/reject", headers=admin_headers, json={}).status_code == 422
    r = client.post(f"{AD}/pharmacies/{pid}/reject", headers=admin_headers, json={"reason": "Licence not found"})
    assert r.status_code == 200
    me = client.get(f"{P}/me", headers=h).get_json()["data"]
    assert me["approval_status"] == "rejected" and me["rejection_reason"] == "Licence not found"
    r = client.post(f"{AD}/pharmacies/{pid}/approve", headers=admin_headers)
    assert r.status_code == 200 and r.get_json()["data"]["approval_status"] == "approved"
    assert client.get(f"{P}/me", headers=h).get_json()["data"]["rejection_reason"] is None
    assert AuditLog.query.filter_by(action="pharmacy.approved", entity_id=pid).count() == 1
    assert client.get(f"{AD}/pharmacies?status=bogus", headers=admin_headers).status_code == 422
    assert client.get(f"{AD}/pharmacies/not-a-uuid", headers=admin_headers).status_code == 404


def test_only_admin_can_approve(client, new_pharmacy, new_doctor, new_patient):
    h, pid = new_pharmacy(approved=False)
    hd, _ = new_doctor()
    hp, _ = new_patient()
    for other in (h, hd, hp):
        assert client.post(f"{AD}/pharmacies/{pid}/approve", headers=other).status_code == 403
        assert client.get(f"{AD}/pharmacies", headers=other).status_code == 403
    assert client.post(f"{AD}/pharmacies/{pid}/approve").status_code == 401


def test_pharmacy_profile_update_and_isolation(client, new_pharmacy, new_patient, new_doctor):
    h, _ = new_pharmacy()
    licence = client.get(f"{P}/me", headers=h).get_json()["data"]["license_number"]
    r = client.patch(f"{P}/me", headers=h, json={"name": "Afya Bora", "latitude": -6.9, "license_number": "HACK-1"})
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["name"] == "Afya Bora" and d["latitude"] == -6.9
    assert d["license_number"] == licence                      # the licence number cannot be edited
    assert client.patch(f"{P}/me", headers=h, json={"latitude": 200}).status_code == 422
    assert client.put(f"{P}/me", headers=h, json={"name": "Only name"}).status_code == 422   # PUT needs everything
    hp, _ = new_patient()
    hd, _ = new_doctor()
    assert client.get(f"{P}/me", headers=hp).status_code == 403
    assert client.get(f"{P}/me", headers=hd).status_code == 403
    assert client.get(f"{P}/me").status_code == 401


def test_pharmacy_password_login_and_reset(app, client, new_pharmacy):
    h, _ = new_pharmacy()
    phone = client.get(f"{A}/me", headers=h).get_json()["data"]["phone"]
    assert client.post(f"{A}/login", json={"phone": phone, "password": "Secret123"}).status_code == 200
    client.post(f"{A}/forgot-password", json={"phone": phone})
    r = client.post(f"{A}/reset-password", json={"phone": phone, "code": sms_code(app, phone), "new_password": "Fresh1234"})
    assert r.status_code == 200
    assert client.post(f"{A}/login", json={"phone": phone, "password": "Fresh1234"}).status_code == 200
