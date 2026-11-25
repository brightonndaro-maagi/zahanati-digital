import pytest

from app.extensions import db
from app.models import AuditLog, User
from tests.conftest import age_otp, auth, past, sms_code
from tests.test_content import AFA, GUIDE
from tests.test_medicines import add
from tests.test_orders import OR, place
from tests.test_payments import callback, pay, ref_of

AD = "/api/v1/admin"


@pytest.fixture()
def world(client, new_patient, new_doctor, new_pharmacy):
    hp, pid = new_patient()
    hp2, _ = new_patient("Baraka Lema")
    hd, did = new_doctor()
    pending_d, _ = new_doctor(verified=False)
    ph, phid = new_pharmacy()
    pending_ph, _ = new_pharmacy(approved=False)
    med = add(client, ph, "Paracetamol 500mg", 1500, 100)
    out = add(client, ph, "Panadol Extra", 900, 0)
    return locals()


def test_dashboard_counts(client, world, admin_headers):
    w = world
    o1 = place(client, w["hp"], (w["med"], 2))["id"]
    pay(client, w["hp"], o1)
    callback(client, ref_of(o1))
    client.post(f"{OR}/{o1}/refund", headers=w["ph"], json={"reason": "Partial return", "amount_tzs": 500})
    place(client, w["hp2"], (w["med"], 1))
    client.post("/api/v1/consultations", headers=w["hp"], json={"doctor_id": w["did"], "message": "Habari"})
    client.post(AFA, headers=admin_headers, json=GUIDE)
    client.post("/api/v1/auth/login", json={"phone": "+255700000099", "password": "wrong-pass1"})
    d = client.get(f"{AD}/dashboard", headers=admin_headers).get_json()["data"]
    assert d["users"]["by_role"] == {"patient": 2, "doctor": 2, "pharmacy": 2, "admin": 1} and d["users"]["total"] == 7
    assert d["users"]["active"] == 7 and d["users"]["deactivated"] == 0 and d["users"]["new_last_7_days"] == 7
    assert d["approvals_waiting"] == {"doctors": 1, "pharmacies": 1, "first_aid_drafts": 1, "health_education_drafts": 0}
    assert d["doctors"] == {"pending": 1, "verified": 1, "rejected": 0, "licence_expired": 0}
    assert d["pharmacies"] == {"pending": 1, "approved": 1, "rejected": 0}
    assert d["orders"]["by_status"] == {"new": 2} and d["orders"]["by_payment_status"] == {"paid": 1, "unpaid": 1}
    assert d["payments_last_30_days"] == {"paid_count": 1, "paid_total_tzs": 3000, "pending_now": 0, "refunds_count": 1, "refunds_total_tzs": 500}
    assert d["consultations"]["open"] == 1 and d["consultations"]["awaiting_reply"] == 1 and d["consultations"]["overdue_replies"] == 0
    assert d["catalogue"] == {"medicines_active": 2, "medicines_out_of_stock": 1}
    assert d["security"]["failed_logins_24h"] == 1 and d["security"]["audit_events_24h"] > 5
    assert d["appointments"]["by_status"] == {} and d["generated_at"]


def test_admin_endpoints_are_admin_only(client, world):
    w = world
    urls = [("get", "/dashboard"), ("get", "/users"), ("get", f"/users/{w['did']}"), ("get", "/payments"), ("get", "/refunds"),
            ("get", "/audit-logs"), ("get", "/audit-logs/actions")]
    for h in (w["hp"], w["hd"], w["ph"]):
        for method, url in urls:
            assert getattr(client, method)(f"{AD}{url}", headers=h).status_code == 403, url
        assert client.post(f"{AD}/users/{w['did']}/deactivate", headers=h, json={"reason": "no right"}).status_code == 403
    for _, url in urls:
        assert client.get(f"{AD}{url}").status_code == 401


def test_user_search_and_filters(client, world, admin_headers):
    r = client.get(f"{AD}/users", headers=admin_headers).get_json()
    assert r["meta"]["total"] == 7 and set(r["data"][0]) == {"id", "role", "name", "phone", "email", "is_active", "created_at", "last_login_at"}
    assert client.get(f"{AD}/users?role=doctor", headers=admin_headers).get_json()["meta"]["total"] == 2
    assert client.get(f"{AD}/users?role=bogus", headers=admin_headers).status_code == 422
    assert [u["name"] for u in client.get(f"{AD}/users?q=baraka", headers=admin_headers).get_json()["data"]] == ["Baraka Lema"]
    assert [u["role"] for u in client.get(f"{AD}/users?q=afya%20pharm", headers=admin_headers).get_json()["data"]] == ["pharmacy", "pharmacy"]
    phone = world["hp"] and client.get("/api/v1/auth/me", headers=world["hp"]).get_json()["data"]["phone"]
    assert client.get(f"{AD}/users?q={phone[-6:]}", headers=admin_headers).get_json()["meta"]["total"] == 1
    assert client.get(f"{AD}/users?q=%25", headers=admin_headers).get_json()["meta"]["total"] == 0        # wildcard is literal
    assert client.get(f"{AD}/users?is_active=maybe", headers=admin_headers).status_code == 422
    assert client.get(f"{AD}/users?per_page=3&page=3", headers=admin_headers).get_json()["data"].__len__() == 1


def test_user_detail_has_role_specific_summary_and_no_secrets(client, world, admin_headers):
    w = world
    uid = lambda h: client.get("/api/v1/auth/me", headers=h).get_json()["data"]["id"]
    p = client.get(f"{AD}/users/{uid(w['hp'])}", headers=admin_headers).get_json()["data"]
    assert p["role"] == "patient" and p["patient"] == {"id": w["pid"], "appointments": 0, "orders": 0, "consultations": 0}
    d = client.get(f"{AD}/users/{uid(w['hd'])}", headers=admin_headers).get_json()["data"]
    assert d["doctor"]["verification_status"] == "verified" and d["doctor"]["council"] == "tanganyika"
    f = client.get(f"{AD}/users/{uid(w['ph'])}", headers=admin_headers).get_json()["data"]
    assert f["pharmacy"]["medicines"] == 2 and f["pharmacy"]["approval_status"] == "approved"
    for blob in (p, d, f):
        assert "password" not in str(blob).lower() and "hash" not in str(blob).lower()
    assert client.get(f"{AD}/users/not-a-uuid", headers=admin_headers).status_code == 404
    assert client.get(f"{AD}/users/00000000-0000-0000-0000-000000000000", headers=admin_headers).status_code == 404


def test_deactivate_blocks_everything_and_activate_restores(client, app, world, admin_headers):
    w = world
    me = client.get("/api/v1/auth/me", headers=w["hd"]).get_json()["data"]
    assert client.post(f"{AD}/users/{me['id']}/deactivate", headers=admin_headers, json={}).status_code == 422
    r = client.post(f"{AD}/users/{me['id']}/deactivate", headers=admin_headers, json={"reason": "Licence fraud investigation"})
    assert r.status_code == 200 and r.get_json()["data"]["is_active"] is False
    assert client.get("/api/v1/auth/me", headers=w["hd"]).status_code == 401                           # existing token is dead
    assert client.post("/api/v1/auth/login", json={"phone": me["phone"], "password": "Secret123"}).status_code == 403
    assert client.get("/api/v1/doctors", headers=w["hp"]).get_json()["meta"]["total"] == 0              # hidden from patients
    assert client.post(f"{AD}/users/{me['id']}/deactivate", headers=admin_headers, json={"reason": "again please"}).status_code == 409
    log = AuditLog.query.filter_by(action="admin.user_deactivated").one()
    assert log.details == {"reason": "Licence fraud investigation"}
    assert client.post(f"{AD}/users/{me['id']}/activate", headers=admin_headers).status_code == 200
    assert client.post(f"{AD}/users/{me['id']}/activate", headers=admin_headers).status_code == 409
    assert client.post("/api/v1/auth/login", json={"phone": me["phone"], "password": "Secret123"}).status_code == 200
    assert client.get("/api/v1/doctors", headers=w["hp"]).get_json()["meta"]["total"] == 1


def test_deactivated_patient_cannot_log_in_with_otp(client, app, world, admin_headers):
    me = client.get("/api/v1/auth/me", headers=world["hp"]).get_json()["data"]
    client.post(f"{AD}/users/{me['id']}/deactivate", headers=admin_headers, json={"reason": "Abusive messages"})
    age_otp(created_at=past(120))                                      # skip the 60-second resend delay
    assert client.post("/api/v1/auth/otp/request", json={"phone": me["phone"]}).status_code == 200
    assert client.post("/api/v1/auth/otp/verify", json={"phone": me["phone"], "code": sms_code(app, me["phone"])}).status_code == 403


def test_admin_cannot_lock_everyone_out(client, make_admin, admin_headers):
    me = client.get("/api/v1/auth/me", headers=admin_headers).get_json()["data"]
    assert client.post(f"{AD}/users/{me['id']}/deactivate", headers=admin_headers, json={"reason": "myself"}).status_code == 409
    second = make_admin(phone="+255700000002", email="second@example.com")
    h2 = auth(client.post("/api/v1/auth/login", json={"phone": "+255700000002", "password": "Admin12345"}).get_json()["data"]["access_token"])
    assert client.post(f"{AD}/users/{second.id}/deactivate", headers=admin_headers, json={"reason": "rotation"}).status_code == 200
    # the first admin is now the only active one: nobody can deactivate it, not even a stale call
    assert client.post(f"{AD}/users/{me['id']}/deactivate", headers=h2, json={"reason": "coup"}).status_code == 401


def test_payments_and_refunds_lists(client, world, admin_headers):
    w = world
    o1 = place(client, w["hp"], (w["med"], 1))["id"]
    pay(client, w["hp"], o1)
    callback(client, ref_of(o1))
    o2 = place(client, w["hp2"], (w["med"], 1))["id"]
    pay(client, w["hp2"], o2)
    callback(client, ref_of(o2), "failed")
    client.post(f"{OR}/{o1}/refund", headers=w["ph"], json={"reason": "Customer complaint"})
    assert client.get(f"{AD}/payments", headers=admin_headers).get_json()["meta"]["total"] == 2
    assert client.get(f"{AD}/payments?status=paid", headers=admin_headers).get_json()["data"][0]["amount_tzs"] == 1500
    assert client.get(f"{AD}/payments?status=failed", headers=admin_headers).get_json()["data"][0]["failure_reason"] == "Payment was declined"
    assert client.get(f"{AD}/payments?order_id={o1}", headers=admin_headers).get_json()["meta"]["total"] == 1
    assert client.get(f"{AD}/payments?status=bogus", headers=admin_headers).status_code == 422
    assert client.get(f"{AD}/payments?from_date=2999-01-01", headers=admin_headers).get_json()["meta"]["total"] == 0
    assert client.get(f"{AD}/payments?from_date=nonsense", headers=admin_headers).status_code == 422
    assert client.get(f"{AD}/refunds", headers=admin_headers).get_json()["data"][0]["amount_tzs"] == 1500


def test_audit_log_filters_and_no_secrets(client, world, admin_headers):
    w = world
    o = place(client, w["hp"], (w["med"], 1))["id"]
    client.post(f"{OR}/{o}/cancel", headers=w["hp"])
    r = client.get(f"{AD}/audit-logs?action=order.created", headers=admin_headers).get_json()
    assert r["meta"]["total"] == 1 and r["data"][0]["entity_id"] == o and r["data"][0]["details"]["items"] == 1
    assert client.get(f"{AD}/audit-logs?action=order.*", headers=admin_headers).get_json()["meta"]["total"] == 2
    assert client.get(f"{AD}/audit-logs?entity_type=order&entity_id={o}", headers=admin_headers).get_json()["meta"]["total"] == 2
    uid = client.get("/api/v1/auth/me", headers=w["hp"]).get_json()["data"]["id"]
    mine = client.get(f"{AD}/audit-logs?user_id={uid}", headers=admin_headers).get_json()["data"]
    assert mine and all(x["user_id"] == uid for x in mine)
    assert client.get(f"{AD}/audit-logs?user_id=bad", headers=admin_headers).status_code == 422
    assert client.get(f"{AD}/audit-logs?from_date=2999-01-01", headers=admin_headers).get_json()["meta"]["total"] == 0
    assert client.get(f"{AD}/audit-logs?to_date=2000-01-01", headers=admin_headers).get_json()["meta"]["total"] == 0
    assert client.get(f"{AD}/audit-logs?per_page=2", headers=admin_headers).get_json()["meta"]["per_page"] == 2
    assert "order.created" in client.get(f"{AD}/audit-logs/actions", headers=admin_headers).get_json()["data"]
    # nothing secret ever lands in the audit trail
    everything = str([(l.action, l.details) for l in AuditLog.query.all()]).lower()
    for forbidden in ("password", "otp_code", "secret", "hedhi_data", "token"):
        assert forbidden not in everything, forbidden
    newest = client.get(f"{AD}/audit-logs", headers=admin_headers).get_json()["data"]
    assert [x["created_at"] for x in newest] == sorted((x["created_at"] for x in newest), reverse=True)
