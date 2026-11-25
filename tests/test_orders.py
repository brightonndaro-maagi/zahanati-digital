import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.extensions import db
from app.models import AuditLog, Notification, Order, PrescriptionFile
from tests.conftest import auth, past, sms_count
from tests.test_medicines import add

OR, PH, NT, AD = "/api/v1/orders", "/api/v1/pharmacies", "/api/v1/notifications", "/api/v1/admin"
PDF = b"%PDF-1.4\n%top-secret-diagnosis\n%%EOF"
JPG = b"\xff\xd8\xff\xe0" + b"jpeg-body-secret" * 10
PNG = b"\x89PNG\r\n\x1a\n" + b"png-body-secret" * 10


@pytest.fixture()
def shop(client, new_pharmacy):
    h, pid = new_pharmacy()
    return {"h": h, "pid": pid,
            "para": add(client, h, "Paracetamol 500mg", 1500, 100),
            "amox": add(client, h, "Amoxicillin 500mg", 3500, 50, requires_prescription=True),
            "out": add(client, h, "Panadol Extra", 900, 0)}


def place(client, h, *items, expect=201):
    r = client.post(OR, headers=h, json={"items": [{"medicine_id": m, "quantity": q} for m, q in items]})
    assert r.status_code == expect, r.get_json()
    return r.get_json()["data"] if expect == 201 else r.get_json()


def set_order(order_id, **fields):
    o = db.session.get(Order, order_id)
    db.session.refresh(o)
    for k, v in fields.items():
        setattr(o, k, v)
    db.session.commit()


def upload(client, h, order_id, data=PDF, name="rx.pdf"):
    return client.post(f"{OR}/{order_id}/prescription", headers=h, data={"file": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


def stored_files(app):
    return list(Path(app.config["UPLOAD_DIR"]).glob("*.enc"))


# ---------------- create ----------------
def test_create_order_snapshots_prices_and_notifies_pharmacy(client, shop, new_patient):
    hp, _ = new_patient()
    o = place(client, hp, (shop["para"], 2))
    assert (o["status"], o["payment_status"], o["prescription_status"]) == ("new", "unpaid", "not_required")
    assert o["total_tzs"] == 3000 and o["payable"] is True and o["prescription"] is None
    assert o["items"] == [{"medicine_id": shop["para"], "name": "Paracetamol 500mg", "quantity": 2,
                           "unit_price_tzs": 1500, "line_total_tzs": 3000, "requires_prescription": False}]
    assert o["pharmacy"]["name"] == "Afya Pharmacy" and "customer" not in o
    hours = (datetime.fromisoformat(o["expires_at"]) - datetime.now(timezone.utc)).total_seconds() / 3600
    assert 23.9 < hours < 24.1
    n = client.get(NT, headers=shop["h"]).get_json()["data"]
    assert n[0]["type"] == "order.created" and n[0]["data"]["order_id"] == o["id"]
    assert AuditLog.query.filter_by(action="order.created", entity_id=o["id"]).count() == 1
    # later price changes never touch an existing order
    client.patch(f"{PH}/me/medicines/{shop['para']}", headers=shop["h"], json={"price_tzs": 9999})
    assert client.get(f"{OR}/{o['id']}", headers=hp).get_json()["data"]["total_tzs"] == 3000
    assert place(client, hp, (shop["para"], 1))["total_tzs"] == 9999


def test_prescription_medicine_makes_order_wait_for_prescription(client, shop, new_patient):
    hp, _ = new_patient()
    o = place(client, hp, (shop["para"], 1), (shop["amox"], 1))
    assert o["prescription_status"] == "required" and o["payable"] is False and o["total_tzs"] == 5000
    assert o["prescription"]["status"] == "required" and o["prescription"]["file_available"] is False


def test_create_order_validation(client, shop, new_patient, new_pharmacy, new_doctor, app):
    hp, _ = new_patient()
    para = shop["para"]
    assert client.post(OR, headers=hp, json={"items": []}).status_code == 422
    assert client.post(OR, headers=hp, json={}).status_code == 422
    for bad in (0, -1, 1.5, "2"):
        assert client.post(OR, headers=hp, json={"items": [{"medicine_id": para, "quantity": bad}]}).status_code == 422, bad
    assert client.post(OR, headers=hp, json={"items": [{"medicine_id": "bad", "quantity": 1}]}).status_code == 422
    assert place(client, hp, (para, 21), expect=422)["success"] is False          # per-item limit (20)
    assert place(client, hp, (para, 1), (para, 2), expect=422)                      # duplicate line
    app.config["ORDER_MAX_ITEMS"] = 2
    assert place(client, hp, (para, 1), (shop["amox"], 1), (shop["out"], 1), expect=422)   # 3 > 2 medicines
    app.config["ORDER_MAX_ITEMS"] = 20
    other, _ = new_pharmacy()
    other_med = add(client, other, "Ibuprofen 400mg", 800, 10)
    assert place(client, hp, (para, 1), (other_med, 1), expect=422)                 # two pharmacies
    assert place(client, hp, ("00000000-0000-0000-0000-000000000000", 1), expect=404)
    hd, _ = new_doctor()
    for h in (shop["h"], hd):
        assert client.post(OR, headers=h, json={"items": [{"medicine_id": para, "quantity": 1}]}).status_code == 403
    assert client.post(OR, json={"items": [{"medicine_id": para, "quantity": 1}]}).status_code == 401


def test_out_of_stock_and_hidden_medicines_cannot_be_ordered(client, shop, new_patient):
    hp, _ = new_patient()
    r = place(client, hp, (shop["out"], 1), expect=409)
    assert r["errors"]["items"][0] == {"medicine_id": shop["out"], "name": "Panadol Extra", "reason": "out_of_stock"}
    low = add(client, shop["h"], "Low stock", 700, 5)
    r = place(client, hp, (low, 6), expect=409)
    assert r["errors"]["items"][0]["reason"] == "quantity_not_available" and "stock_quantity" not in str(r)
    client.delete(f"{PH}/me/medicines/{shop['para']}", headers=shop["h"])
    place(client, hp, (shop["para"], 1), expect=404)
    assert Order.query.count() == 0


# ---------------- visibility ----------------
def test_orders_are_private(client, shop, new_patient, new_pharmacy, admin_headers):
    h1, _ = new_patient()
    h2, _ = new_patient()
    o = place(client, h1, (shop["para"], 1))
    oid = o["id"]
    assert client.get(f"{OR}/{oid}", headers=h2).status_code == 404
    assert client.post(f"{OR}/{oid}/cancel", headers=h2).status_code == 404
    assert upload(client, h2, oid).status_code == 404
    other_ph, _ = new_pharmacy()
    assert client.get(f"{OR}/{oid}", headers=other_ph).status_code == 404
    assert client.post(f"{OR}/{oid}/ready", headers=other_ph).status_code == 404
    assert client.get(f"{OR}/{oid}", headers=shop["h"]).get_json()["data"]["customer"]["full_name"] == "Asha Juma"
    assert client.get(f"{OR}/{oid}", headers=admin_headers).status_code == 200
    assert client.get(f"{OR}/not-a-uuid", headers=h1).status_code == 404
    assert client.get(OR, headers=h1).get_json()["meta"]["total"] == 1
    assert client.get(OR, headers=h2).get_json()["meta"]["total"] == 0
    assert client.get(OR, headers=other_ph).get_json()["meta"]["total"] == 0
    assert client.get(OR, headers=shop["h"]).get_json()["meta"]["total"] == 1
    assert client.get(OR, headers=admin_headers).get_json()["meta"]["total"] == 1
    assert client.get(f"{OR}?status=new", headers=h1).get_json()["meta"]["total"] == 1
    assert client.get(f"{OR}?status=ready", headers=h1).get_json()["meta"]["total"] == 0
    assert client.get(f"{OR}?status=bogus", headers=h1).status_code == 422
    assert client.get(f"{OR}?payment_status=bogus", headers=h1).status_code == 422
    assert client.get(OR).status_code == 401


# ---------------- cancel ----------------
def test_cancel_rules(client, shop, new_patient):
    hp, _ = new_patient()
    o1 = place(client, hp, (shop["para"], 1))["id"]
    r = client.post(f"{OR}/{o1}/cancel", headers=hp, json={"reason": "Changed my mind"})
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "cancelled" and r.get_json()["data"]["payable"] is False
    assert client.post(f"{OR}/{o1}/cancel", headers=hp).status_code == 409
    assert Notification.query.filter_by(type="order.cancelled").count() == 1
    # pharmacy may cancel an unpaid order too
    o2 = place(client, hp, (shop["para"], 1))["id"]
    assert client.post(f"{OR}/{o2}/cancel", headers=shop["h"], json={"reason": "Closing early"}).status_code == 200
    # paid / in-progress payments cannot be cancelled here (refunds come with payments)
    o3 = place(client, hp, (shop["para"], 1))["id"]
    set_order(o3, payment_status="pending")
    assert client.post(f"{OR}/{o3}/cancel", headers=hp).status_code == 409
    set_order(o3, payment_status="paid")
    assert client.post(f"{OR}/{o3}/cancel", headers=hp).status_code == 409
    assert client.post(f"{OR}/{o3}/cancel", headers=shop["h"]).status_code == 409
    set_order(o3, payment_status="failed")
    assert client.post(f"{OR}/{o3}/cancel", headers=hp).status_code == 200


# ---------------- expiry ----------------
def test_unpaid_orders_expire_after_24_hours(client, shop, new_patient, app):
    hp, _ = new_patient()
    unpaid = place(client, hp, (shop["para"], 1))["id"]
    failed = place(client, hp, (shop["para"], 1))["id"]
    paid = place(client, hp, (shop["para"], 1))["id"]
    pending = place(client, hp, (shop["para"], 1))["id"]
    fresh = place(client, hp, (shop["para"], 1))["id"]
    set_order(failed, payment_status="failed")
    set_order(paid, payment_status="paid")
    set_order(pending, payment_status="pending")
    for oid in (unpaid, failed, paid, pending):
        set_order(oid, expires_at=past(60))
    d = client.get(f"{OR}/{unpaid}", headers=hp).get_json()["data"]          # lazily expired on read
    assert d["status"] == "expired" and d["payable"] is False
    listing = {o["id"]: o["status"] for o in client.get(OR, headers=hp).get_json()["data"]}
    assert listing == {unpaid: "expired", failed: "expired", paid: "new", pending: "new", fresh: "new"}
    n = Notification.query.filter_by(type="order.expired").all()
    assert len(n) == 2
    assert client.post(f"{OR}/{unpaid}/cancel", headers=hp).status_code == 409
    assert AuditLog.query.filter_by(action="order.expired").count() == 2


def test_expire_orders_command(client, shop, new_patient, app):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 1))["id"]
    set_order(oid, expires_at=past(5))
    out = app.test_cli_runner().invoke(args=["expire-orders"])
    assert out.exit_code == 0 and "Expired 1 order(s)." in out.output, out.output
    assert db.session.get(Order, oid).status == "expired"
    assert "Expired 0 order(s)." in app.test_cli_runner().invoke(args=["expire-orders"]).output


# ---------------- prescriptions ----------------
def test_upload_is_encrypted_validated_and_pharmacy_only(client, shop, new_patient, new_pharmacy, new_doctor, admin_headers, app):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["amox"], 1))["id"]
    r = upload(client, hp, oid)
    assert r.status_code == 200
    d = r.get_json()["data"]
    assert d["prescription_status"] == "uploaded" and d["prescription"]["file_available"] and d["payable"] is False
    # on disk it is encrypted: neither the content nor the format marker is visible
    files = stored_files(app)
    assert len(files) == 1
    raw = files[0].read_bytes()
    assert b"top-secret" not in raw and b"%PDF" not in raw and raw != PDF
    # the pharmacy reads it back unchanged; the response is not cacheable
    r = client.get(f"{OR}/{oid}/prescription", headers=shop["h"])
    assert r.status_code == 200 and r.data == PDF and r.mimetype == "application/pdf"
    assert r.headers["Cache-Control"] == "no-store" and r.headers["X-Content-Type-Options"] == "nosniff"
    assert AuditLog.query.filter_by(action="prescription.viewed", entity_id=oid).count() == 1
    assert Notification.query.filter_by(type="prescription.uploaded").count() == 1
    # nobody else can read it: not the customer, another pharmacy, a doctor, an admin, an anonymous caller
    other_ph, _ = new_pharmacy()
    hd, _ = new_doctor()
    assert client.get(f"{OR}/{oid}/prescription", headers=hp).status_code == 403
    assert client.get(f"{OR}/{oid}/prescription", headers=other_ph).status_code == 404
    assert client.get(f"{OR}/{oid}/prescription", headers=hd).status_code == 403
    assert client.get(f"{OR}/{oid}/prescription", headers=admin_headers).status_code == 403
    assert client.get(f"{OR}/{oid}/prescription").status_code == 401


def test_upload_rejects_bad_files(client, shop, new_patient, app):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["amox"], 1))["id"]
    assert upload(client, hp, oid, b"just text pretending", "rx.pdf").status_code == 422       # extension lies
    assert upload(client, hp, oid, b"MZ\x90\x00executable", "rx.png").status_code == 422
    assert upload(client, hp, oid, b"", "rx.pdf").status_code == 422
    assert client.post(f"{OR}/{oid}/prescription", headers=hp, data={}, content_type="multipart/form-data").status_code == 422
    assert upload(client, hp, oid, PDF + b"x" * (5 * 1024 * 1024), "big.pdf").status_code == 413
    assert upload(client, hp, oid, PDF + b"x" * (7 * 1024 * 1024), "huge.pdf").status_code == 413
    assert stored_files(app) == []
    assert db.session.get(Order, oid).prescription_status == "required"
    # the real type comes from the content, not the file name
    r = upload(client, hp, oid, JPG, "scan.txt")
    assert r.status_code == 200
    r = client.get(f"{OR}/{oid}/prescription", headers=shop["h"])
    assert r.mimetype == "image/jpeg" and r.data == JPG


def test_upload_state_rules(client, shop, new_patient):
    hp, _ = new_patient()
    plain = place(client, hp, (shop["para"], 1))["id"]
    assert upload(client, hp, plain).status_code == 409                 # no prescription needed
    oid = place(client, hp, (shop["amox"], 1))["id"]
    assert upload(client, shop["h"], oid).status_code == 403            # pharmacies do not upload
    assert upload(client, hp, oid, PNG, "a.png").status_code == 200
    assert upload(client, hp, oid, PNG, "a.png").status_code == 409     # already waiting for review
    client.post(f"{OR}/{oid}/prescription/approve", headers=shop["h"])
    assert upload(client, hp, oid, PNG, "a.png").status_code == 409     # already approved
    client.post(f"{OR}/{plain}/cancel", headers=hp)
    other = place(client, hp, (shop["amox"], 1))["id"]
    client.post(f"{OR}/{other}/cancel", headers=hp)
    assert upload(client, hp, other).status_code == 409                 # order is cancelled


def test_review_approve_reject_and_reupload(client, shop, new_patient, app):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["amox"], 1))["id"]
    ph = shop["h"]
    assert client.post(f"{OR}/{oid}/prescription/approve", headers=ph).status_code == 409   # nothing uploaded yet
    upload(client, hp, oid)
    assert client.post(f"{OR}/{oid}/prescription/reject", headers=ph, json={}).status_code == 422
    r = client.post(f"{OR}/{oid}/prescription/reject", headers=ph, json={"reason": "Image is blurry"})
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["prescription_status"] == "rejected" and d["prescription"]["rejection_reason"] == "Image is blurry"
    n = Notification.query.filter_by(type="prescription.rejected").one()
    assert "blurry" in n.message and n.data["reason"] == "Image is blurry"
    assert client.post(f"{OR}/{oid}/prescription/reject", headers=ph, json={"reason": "again"}).status_code == 409
    # the customer uploads a new one; the old file is kept until retention expires
    assert upload(client, hp, oid, PNG, "better.png").status_code == 200
    assert PrescriptionFile.query.count() == 2 and len(stored_files(app)) == 2
    assert client.get(f"{OR}/{oid}/prescription", headers=ph).data == PNG          # latest file is served
    r = client.post(f"{OR}/{oid}/prescription/approve", headers=ph)
    d = r.get_json()["data"]
    assert d["prescription_status"] == "approved" and d["payable"] is True and d["prescription"]["rejection_reason"] is None
    assert Notification.query.filter_by(type="prescription.approved").count() == 1
    assert client.post(f"{OR}/{oid}/prescription/reject", headers=ph, json={"reason": "late"}).status_code == 409
    # only the receiving pharmacy and only pharmacies may review
    assert client.post(f"{OR}/{oid}/prescription/approve", headers=hp).status_code == 403


def test_other_pharmacy_cannot_review(client, shop, new_patient, new_pharmacy):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["amox"], 1))["id"]
    upload(client, hp, oid)
    other, _ = new_pharmacy()
    assert client.post(f"{OR}/{oid}/prescription/approve", headers=other).status_code == 404
    assert client.post(f"{OR}/{oid}/prescription/reject", headers=other, json={"reason": "not yours"}).status_code == 404


def test_retention_purge_deletes_files_after_two_years(client, shop, new_patient, app):
    hp, _ = new_patient()
    old = place(client, hp, (shop["amox"], 1))["id"]
    new = place(client, hp, (shop["amox"], 1))["id"]
    upload(client, hp, old)
    upload(client, hp, new, PNG, "n.png")
    f = PrescriptionFile.query.filter_by(order_id=old).one()
    assert (f.expires_at - f.uploaded_at).days >= 729
    f.expires_at = past(5)
    db.session.commit()
    out = app.test_cli_runner().invoke(args=["purge-prescriptions"])
    assert out.exit_code == 0 and "Purged 1 prescription file(s)." in out.output, out.output
    assert len(stored_files(app)) == 1
    assert client.get(f"{OR}/{old}/prescription", headers=shop["h"]).status_code == 404
    assert client.get(f"{OR}/{new}/prescription", headers=shop["h"]).status_code == 200
    assert client.get(f"{OR}/{old}", headers=hp).get_json()["data"]["prescription"]["file_available"] is False
    assert AuditLog.query.filter_by(action="prescription.purged").count() == 1


def test_encryption_key_rotation_and_missing_key(client, shop, new_patient, app):
    from cryptography.fernet import Fernet
    from app.common import crypto
    old_keys = list(app.config["FILE_ENCRYPTION_KEYS"])
    token = crypto.encrypt(b"hello")
    app.config["FILE_ENCRYPTION_KEYS"] = [Fernet.generate_key().decode()] + old_keys      # new key first, old still readable
    assert crypto.decrypt(token) == b"hello"
    assert crypto.decrypt(crypto.encrypt(b"new")) == b"new"
    app.config["FILE_ENCRYPTION_KEYS"] = [Fernet.generate_key().decode()]                 # unrelated key: cannot read
    from app.common.errors import APIError
    with pytest.raises(APIError):
        crypto.decrypt(token)
    app.config["FILE_ENCRYPTION_KEYS"] = []
    hp, _ = new_patient()
    oid = place(client, hp, (shop["amox"], 1))["id"]
    r = upload(client, hp, oid)
    assert r.status_code == 503 and stored_files(app) == []
    assert db.session.get(Order, oid).prescription_status == "required"


# ---------------- ready / collected ----------------
def test_ready_and_collect_flow(client, shop, new_patient, app):
    hp, _ = new_patient()
    ph = shop["h"]
    phone = client.get("/api/v1/auth/me", headers=hp).get_json()["data"]["phone"]
    oid = place(client, hp, (shop["para"], 1))["id"]
    assert client.post(f"{OR}/{oid}/ready", headers=ph).status_code == 409          # not paid yet
    assert client.post(f"{OR}/{oid}/collect", headers=ph).status_code == 409        # not ready
    set_order(oid, payment_status="paid")
    assert client.post(f"{OR}/{oid}/ready", headers=hp).status_code == 403          # customers cannot
    before = sms_count(app, phone)
    r = client.post(f"{OR}/{oid}/ready", headers=ph)
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "ready" and r.get_json()["data"]["ready_at"]
    assert Notification.query.filter_by(type="order.ready").count() == 1
    assert sms_count(app, phone) == before + 1
    assert client.post(f"{OR}/{oid}/ready", headers=ph).status_code == 409
    assert client.post(f"{OR}/{oid}/cancel", headers=hp).status_code == 409         # ready orders cannot be cancelled
    r = client.post(f"{OR}/{oid}/collect", headers=ph)
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "collected"
    assert client.post(f"{OR}/{oid}/collect", headers=ph).status_code == 409


def test_prescription_order_needs_approval_before_ready(client, shop, new_patient):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["amox"], 1))["id"]
    set_order(oid, payment_status="paid")
    assert client.post(f"{OR}/{oid}/ready", headers=shop["h"]).status_code == 409
    upload(client, hp, oid)
    assert client.post(f"{OR}/{oid}/ready", headers=shop["h"]).status_code == 409   # uploaded but not approved
    client.post(f"{OR}/{oid}/prescription/approve", headers=shop["h"])
    assert client.post(f"{OR}/{oid}/ready", headers=shop["h"]).status_code == 200


def test_unapproved_pharmacy_cannot_progress_orders(client, shop, new_patient, admin_headers):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 1))["id"]
    set_order(oid, payment_status="paid")
    client.post(f"{AD}/pharmacies/{shop['pid']}/reject", headers=admin_headers, json={"reason": "Licence expired"})
    assert client.post(f"{OR}/{oid}/ready", headers=shop["h"]).status_code == 403
    assert client.post(f"{OR}/{oid}/prescription/approve", headers=shop["h"]).status_code == 403


# ---------------- notifications ----------------
def test_notifications_api(client, shop, new_patient):
    hp, _ = new_patient()
    other, _ = new_patient()
    place(client, hp, (shop["para"], 1))
    place(client, hp, (shop["para"], 1))
    ph = shop["h"]
    assert client.get(f"{NT}/unread-count", headers=ph).get_json()["data"]["unread"] == 2
    items = client.get(NT, headers=ph).get_json()["data"]
    assert len(items) == 2 and items[0]["is_read"] is False
    assert client.post(f"{NT}/{items[0]['id']}/read", headers=other).status_code == 404     # not yours
    assert client.post(f"{NT}/{items[0]['id']}/read", headers=ph).status_code == 200
    assert client.get(f"{NT}?unread=true", headers=ph).get_json()["meta"]["total"] == 1
    assert client.post(f"{NT}/read-all", headers=ph).get_json()["data"]["updated"] == 1
    assert client.get(f"{NT}/unread-count", headers=ph).get_json()["data"]["unread"] == 0
    assert client.get(NT, headers=hp).get_json()["meta"]["total"] == 0
    assert client.get(NT).status_code == 401
    assert client.post(f"{NT}/not-a-uuid/read", headers=ph).status_code == 404
