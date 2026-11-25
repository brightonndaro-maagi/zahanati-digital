from app.models import AuditLog, User
from tests.conftest import DOCTOR, age_otp, auth, past, sms_code, sms_count

A = "/api/v1/auth"
DPHONE = "+255755000111"


def _doc_body(**over):
    return {**DOCTOR, "phone": DPHONE, "license_number": "MCT-1001", **over}


def _otp(client, phone=DPHONE, purpose="register"):
    return client.post(f"{A}/otp/request", json={"phone": phone, "purpose": purpose})


def _register(client, app, **over):
    _otp(client, over.get("phone", DPHONE))
    body = _doc_body(**over)
    return client.post(f"{A}/register/doctor", json={"otp_code": sms_code(app, body["phone"]), **body})


def test_doctor_registration_requires_valid_otp(app, client):
    assert client.post(f"{A}/register/doctor", json=_doc_body()).status_code == 422            # no code
    assert client.post(f"{A}/register/doctor", json={**_doc_body(), "otp_code": "123456"}).status_code == 400  # never requested
    _otp(client)
    bad = "000000" if sms_code(app, DPHONE) != "000000" else "111111"
    assert client.post(f"{A}/register/doctor", json={**_doc_body(), "otp_code": bad}).status_code == 400
    assert User.query.count() == 0


def test_doctor_registers_pending_and_logs_in(app, client):
    r = _register(client, app, email="Doc@Example.com")
    assert r.status_code == 201
    u = r.get_json()["data"]["user"]
    assert u["role"] == "doctor" and u["verification_status"] == "pending" and u["phone"] == DPHONE
    assert u["email"] == "doc@example.com" and "password" not in u
    for ident in ({"phone": DPHONE}, {"phone": "0755000111"}, {"email": "doc@example.com"}):
        r = client.post(f"{A}/login", json={**ident, "password": "Secret123"})
        assert r.status_code == 200 and r.get_json()["data"]["access_token"], ident


def test_email_is_optional_and_password_is_hashed(app, client):
    assert _register(client, app).status_code == 201
    u = User.query.filter_by(phone=DPHONE).one()
    assert u.email is None and u.password_hash.startswith("scrypt") and u.password_hash != "Secret123"


def test_registration_uniqueness(app, client):
    assert _register(client, app, email="a@example.com").status_code == 201
    # the phone is taken: a register code is never even sent
    before = sms_count(app, DPHONE)
    assert _otp(client).status_code == 200 and sms_count(app, DPHONE) == before
    # same email, other phone
    r = _register(client, app, phone="+255755000222", email="A@example.com", license_number="MCT-2")
    assert r.status_code == 409


def test_registration_validation(app, client):
    assert _register(client, app, password="short").status_code == 422
    assert _register(client, app, email="not-an-email").status_code == 422
    assert client.post(f"{A}/register/doctor", data="x").status_code == 400


def test_patients_cannot_use_password_login_or_old_register_endpoint(app, client, new_patient):
    h, _ = new_patient()
    phone = client.get(f"{A}/me", headers=h).get_json()["data"]["phone"]
    assert client.post(f"{A}/login", json={"phone": phone, "password": "anything1"}).status_code == 401
    assert client.post(f"{A}/register/patient", json={"phone": phone}).status_code == 404


def test_login_failures(app, client):
    _register(client, app)
    assert client.post(f"{A}/login", json={"phone": DPHONE, "password": "Wrong1234"}).status_code == 401
    assert client.post(f"{A}/login", json={"phone": "+255700000000", "password": "Secret123"}).status_code == 401
    assert client.post(f"{A}/login", json={"password": "Secret123"}).status_code == 422
    assert client.post(f"{A}/login", json={"phone": DPHONE, "email": "a@b.co", "password": "x"}).status_code == 422
    assert AuditLog.query.filter_by(action="auth.login_failed").count() == 2


def test_me_requires_auth(client):
    assert client.get(f"{A}/me").status_code == 401
    assert client.get(f"{A}/me", headers=auth("garbage")).status_code == 401


def test_me_refresh_and_token_types(app, client):
    d = _register(client, app).get_json()["data"]
    assert client.get(f"{A}/me", headers=auth(d["access_token"])).get_json()["data"]["phone"] == DPHONE
    assert client.get(f"{A}/me", headers=auth(d["refresh_token"])).status_code == 401
    r = client.post(f"{A}/refresh", headers=auth(d["refresh_token"]))
    assert r.status_code == 200 and r.get_json()["data"]["access_token"]
    assert client.post(f"{A}/refresh", headers=auth(d["access_token"])).status_code == 401


def test_logout_revokes_token(app, client):
    d = _register(client, app).get_json()["data"]
    assert client.post(f"{A}/logout", headers=auth(d["access_token"])).status_code == 200
    assert client.get(f"{A}/me", headers=auth(d["access_token"])).status_code == 401


def test_deactivated_account_blocked_everywhere(app, client):
    from app.extensions import db
    d = _register(client, app).get_json()["data"]
    User.query.filter_by(phone=DPHONE).one().is_active = False
    db.session.commit()
    assert client.get(f"{A}/me", headers=auth(d["access_token"])).status_code == 401
    assert client.post(f"{A}/login", json={"phone": DPHONE, "password": "Secret123"}).status_code == 403


def test_password_reset_by_sms(app, client):
    _register(client, app)
    assert client.post(f"{A}/forgot-password", json={"phone": DPHONE}).status_code == 200
    code = sms_code(app, DPHONE)
    r = client.post(f"{A}/reset-password", json={"phone": DPHONE, "code": code, "new_password": "NewPass123"})
    assert r.status_code == 200
    assert client.post(f"{A}/login", json={"phone": DPHONE, "password": "NewPass123"}).status_code == 200
    assert client.post(f"{A}/login", json={"phone": DPHONE, "password": "Secret123"}).status_code == 401
    # single use
    assert client.post(f"{A}/reset-password", json={"phone": DPHONE, "code": code, "new_password": "Another123"}).status_code == 400
    # weak password rejected without burning anything
    age_otp(created_at=past(120))
    client.post(f"{A}/forgot-password", json={"phone": DPHONE})
    assert client.post(f"{A}/reset-password", json={"phone": DPHONE, "code": sms_code(app, DPHONE), "new_password": "short"}).status_code == 422


def test_forgot_password_never_leaks_or_texts_strangers_and_patients(app, client, new_patient):
    h, _ = new_patient()
    pphone = client.get(f"{A}/me", headers=h).get_json()["data"]["phone"]
    before = sms_count(app)
    for phone in ("+255799000000", pphone):
        r = client.post(f"{A}/forgot-password", json={"phone": phone})
        assert r.status_code == 200
    assert sms_count(app) == before


def test_reset_code_for_one_purpose_does_not_work_for_another(app, client):
    _register(client, app)
    client.post(f"{A}/forgot-password", json={"phone": DPHONE})
    code = sms_code(app, DPHONE)
    # reset code cannot log anyone in
    assert client.post(f"{A}/otp/verify", json={"phone": DPHONE, "code": code}).status_code in (400, 403)


def test_change_password(app, client, new_patient):
    d = _register(client, app).get_json()["data"]
    h = auth(d["access_token"])
    assert client.post(f"{A}/change-password", headers=h,
                       json={"current_password": "bad", "new_password": "NewPass123"}).status_code == 400
    assert client.post(f"{A}/change-password", headers=h,
                       json={"current_password": "Secret123", "new_password": "Secret123"}).status_code == 422
    assert client.post(f"{A}/change-password", headers=h,
                       json={"current_password": "Secret123", "new_password": "NewPass123"}).status_code == 200
    hp, _ = new_patient()
    assert client.post(f"{A}/change-password", headers=hp,
                       json={"current_password": "x", "new_password": "NewPass123"}).status_code == 403


def test_admin_login_by_phone_or_email(client, make_admin):
    make_admin()
    for ident in ({"phone": "0700000001"}, {"email": "admin@example.com"}):
        r = client.post(f"{A}/login", json={**ident, "password": "Admin12345"})
        assert r.status_code == 200 and r.get_json()["data"]["user"]["role"] == "admin"
