import pytest

from app.common.phone import normalize_phone
from app.common.sms import SMSError
from app.extensions import db
from app.models import AuditLog, OtpCode, User
from tests.conftest import age_otp, auth, past, sms_code, sms_count

A = "/api/v1/auth"
PHONE = "+255712345678"


def _request(client, phone=PHONE, **kw):
    return client.post(f"{A}/otp/request", json={"phone": phone, **kw})


def _verify(client, app, code=None, phone=PHONE, **kw):
    return client.post(f"{A}/otp/verify", json={"phone": phone, "code": code or sms_code(app, phone), **kw})


def test_phone_normalisation():
    for raw in ("0712345678", "712345678", "255712345678", "+255 712 345 678", "00255712345678", "+255-712-345-678"):
        assert normalize_phone(raw) == PHONE, raw
    for bad in ("", "abc", "12345", "+254712345678", "0512345678", "+2557123456789", None, 712345678):
        assert normalize_phone(bad) is None, bad


def test_new_patient_flow_needs_full_name_and_creates_account(app, client):
    assert _request(client).status_code == 200
    # code is right but the number is new: ask for the name, create nothing, keep the code usable
    r = _verify(client, app)
    assert r.status_code == 200 and r.get_json()["data"] == {"registration_required": True}
    assert User.query.filter_by(phone=PHONE).first() is None
    r = _verify(client, app, full_name="Asha Juma Mwinyi")
    assert r.status_code == 201
    d = r.get_json()["data"]
    assert d["is_new_user"] and d["user"]["role"] == "patient" and d["user"]["full_name"] == "Asha Juma Mwinyi"
    p = User.query.filter_by(phone=PHONE).one().patient_profile
    assert (p.first_name, p.last_name) == ("Asha", "Juma Mwinyi")
    assert client.get(f"{A}/me", headers=auth(d["access_token"])).get_json()["data"]["phone"] == PHONE


def test_existing_patient_logs_in_and_code_is_single_use(app, client):
    _request(client)
    _verify(client, app, full_name="Asha Juma")
    age_otp(created_at=past(120))
    _request(client)
    code = sms_code(app, PHONE)
    r = _verify(client, app, code=code)
    assert r.status_code == 200 and not r.get_json()["data"]["is_new_user"]
    assert _verify(client, app, code=code).status_code == 400  # reuse fails
    assert AuditLog.query.filter_by(action="auth.login").count() == 2


def test_other_phone_formats_reach_the_same_account(app, client):
    _request(client, "0712345678")
    _verify(client, app, full_name="Asha Juma")
    age_otp(created_at=past(120))
    _request(client, "+255 712 345 678")
    assert _verify(client, app).status_code == 200
    assert User.query.count() == 1


def test_code_is_stored_hashed(app, client):
    _request(client)
    code = sms_code(app, PHONE)
    row = OtpCode.query.one()
    assert code not in row.code_hash and len(row.code_hash) == 64 and len(code) == 6 and code.isdigit()


def test_validation(app, client):
    assert _request(client, "123").status_code == 422
    assert _request(client, PHONE, purpose="password_reset").status_code == 422
    _request(client)
    assert client.post(f"{A}/otp/verify", json={"phone": PHONE, "code": "12ab56"}).status_code == 422
    assert _verify(client, app, full_name="Asha").status_code == 422  # one name is not a full name


def test_wrong_code_locks_number_after_five_attempts(app, client):
    _request(client)
    good = sms_code(app, PHONE)
    bad = "000000" if good != "000000" else "111111"
    for i in range(4):
        assert _verify(client, app, code=bad, full_name="Asha Juma").status_code == 400
    assert _verify(client, app, code=bad, full_name="Asha Juma").status_code == 429      # 5th wrong try locks
    assert _verify(client, app, code=good, full_name="Asha Juma").status_code == 429     # even the right code
    age_otp(created_at=past(120))
    assert _request(client).status_code == 429                                           # cannot dodge the lock with a new code
    assert AuditLog.query.filter_by(action="otp.locked").count() == 1
    age_otp(locked_until=past(1))                                                        # 10 minutes pass
    assert _verify(client, app, code=good, full_name="Asha Juma").status_code == 201


def test_expired_code_rejected(app, client):
    _request(client)
    age_otp(expires_at=past(1))
    assert _verify(client, app, full_name="Asha Juma").status_code == 400


def test_resend_cooldown_and_old_code_invalidated(app, client):
    _request(client)
    old = sms_code(app, PHONE)
    assert _request(client).status_code == 429
    age_otp(created_at=past(61))
    assert _request(client).status_code == 200
    assert sms_count(app, PHONE) == 2
    new = sms_code(app, PHONE)
    if new != old:
        assert _verify(client, app, code=old, full_name="Asha Juma").status_code == 400
    assert _verify(client, app, code=new, full_name="Asha Juma").status_code == 201


def test_code_for_other_number_or_purpose_is_useless(app, client):
    _request(client)
    code = sms_code(app, PHONE)
    assert _verify(client, app, code=code, phone="+255722222222", full_name="Asha Juma").status_code == 400
    # a login code cannot be used to register a doctor
    r = client.post(f"{A}/register/doctor", json={
        "phone": PHONE, "otp_code": code, "password": "Secret123", "first_name": "A", "last_name": "B",
        "license_number": "MCT-1", "qualification": "MD"})
    assert r.status_code == 400


def test_staff_number_gets_no_sms_and_cannot_use_otp(app, client, new_doctor):
    hd, _ = new_doctor()
    phone = client.get(f"{A}/me", headers=hd).get_json()["data"]["phone"]
    before = sms_count(app)
    r = _request(client, phone)
    assert r.status_code == 200 and sms_count(app) == before   # same answer, nothing sent
    assert _request(client, PHONE, purpose="register").status_code == 200  # unrelated number is fine


def test_deactivated_patient_cannot_log_in(app, client):
    _request(client)
    _verify(client, app, full_name="Asha Juma")
    User.query.filter_by(phone=PHONE).one().is_active = False
    db.session.commit()
    age_otp(created_at=past(120))
    _request(client)
    assert _verify(client, app).status_code == 403


def test_sms_failure_returns_503_and_does_not_block_retry(app, client, monkeypatch):
    from app.common import sms

    class Broken:
        def send(self, phone, message):
            raise SMSError("down")

    monkeypatch.setitem(sms._GATEWAYS, "memory", Broken)
    assert _request(client).status_code == 503
    assert OtpCode.query.count() == 0
    monkeypatch.undo()
    assert _request(client).status_code == 200  # no resend delay was imposed


def test_beem_gateway_request_format_and_errors(app, monkeypatch):
    import requests
    from app.common.sms import BeemGateway

    app.config.update(BEEM_API_KEY="k", BEEM_SECRET_KEY="s", BEEM_SOURCE_ADDR="ZAHANATI")
    seen = {}

    class Resp:
        status_code, text = 200, ""
        def json(self): return {"successful": True}

    def fake_post(url, json=None, auth=None, timeout=None):
        seen.update(url=url, json=json, auth=auth, timeout=timeout)
        return Resp()

    monkeypatch.setattr(requests, "post", fake_post)
    BeemGateway().send("+255712345678", "hello")
    assert seen["url"].startswith("https://apisms.beem.africa") and seen["auth"] == ("k", "s")
    assert seen["json"]["recipients"][0]["dest_addr"] == "255712345678" and seen["json"]["message"] == "hello"
    Resp.status_code = 401
    with pytest.raises(SMSError):
        BeemGateway().send("+255712345678", "hello")
    Resp.status_code = 200
    Resp.json = lambda self: {"successful": False, "message": "no balance"}
    with pytest.raises(SMSError):
        BeemGateway().send("+255712345678", "hello")
    app.config["BEEM_API_KEY"] = None
    with pytest.raises(SMSError):
        BeemGateway().send("+255712345678", "hello")


def test_phone_change_flow(app, client, new_patient, new_doctor):
    h, _ = new_patient()
    new = "+255788888888"
    assert client.post(f"{A}/phone/change/request", json={"phone": new}).status_code == 401
    assert client.post(f"{A}/phone/change/request", headers=h, json={"phone": new}).status_code == 200
    assert client.post(f"{A}/phone/change/confirm", headers=h, json={"phone": new, "code": "000000"}).status_code in (400,)
    r = client.post(f"{A}/phone/change/confirm", headers=h, json={"phone": new, "code": sms_code(app, new)})
    assert r.status_code == 200 and r.get_json()["data"]["phone"] == new
    assert client.get("/api/v1/patients/me", headers=h).get_json()["data"]["phone"] == new
    # a number that already belongs to someone else cannot be taken
    hd, _ = new_doctor()
    taken = client.get(f"{A}/me", headers=hd).get_json()["data"]["phone"]
    assert client.post(f"{A}/phone/change/request", headers=h, json={"phone": taken}).status_code == 409
    # the patient can no longer change the number through the profile endpoint
    client.patch("/api/v1/patients/me", headers=h, json={"phone": "+255799999999"})
    assert client.get("/api/v1/patients/me", headers=h).get_json()["data"]["phone"] == new
