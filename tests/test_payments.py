import hashlib
import hmac
import json

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AuditLog, Medicine, Notification, Order, Payment, Refund
from tests.conftest import past
from tests.test_medicines import add
from tests.test_orders import OR, PH, place, set_order, shop, upload  # noqa: F401  (shop is a fixture)

SECRET = b"test-callback-secret"


def pay(client, h, oid, network="mpesa", **kw):
    return client.post(f"{OR}/{oid}/pay", headers=h, json={"network": network, **kw})


def callback(client, ref, status="success", amount=None, sig="auto", raw=None, **extra):
    body = raw if raw is not None else json.dumps({"provider_ref": ref, "status": status, **({"amount_tzs": amount} if amount is not None else {}), **extra}).encode()
    headers = {"Content-Type": "application/json"}
    if sig == "auto":
        headers["X-Signature"] = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    elif sig:
        headers["X-Signature"] = sig
    return client.post("/api/v1/payments/callback", data=body, headers=headers)


def ref_of(oid):
    db.session.expire_all()
    return Payment.query.filter_by(order_id=oid).order_by(Payment.created_at.desc()).first().provider_ref


def stock(medicine_id):
    db.session.expire_all()
    return db.session.get(Medicine, medicine_id).stock_quantity


def paid_order(client, shop, hp, qty=2):
    oid = place(client, hp, (shop["para"], qty))["id"]
    assert pay(client, hp, oid).status_code == 200
    assert callback(client, ref_of(oid)).status_code == 200
    return oid


# ---------------- happy path ----------------
def test_pay_reserves_stock_and_callback_marks_paid(client, shop, new_patient):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 3))["id"]
    r = pay(client, hp, oid, "tigopesa", phone="0655123456")
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["payment_status"] == "pending" and d["payable"] is False
    assert d["payment"]["status"] == "pending" and d["payment"]["network"] == "tigopesa" and d["payment"]["amount_tzs"] == 4500
    assert stock(shop["para"]) == 97                                          # held while the payment is in progress
    assert Payment.query.one().payer_phone == "+255655123456"
    assert client.post(f"{OR}/{oid}/ready", headers=shop["h"]).status_code == 409     # pending is not paid
    r = callback(client, ref_of(oid), amount=4500)
    assert r.status_code == 200 and r.get_json()["data"] == {"payment_id": Payment.query.one().id, "status": "paid", "changed": True}
    o = client.get(f"{OR}/{oid}", headers=hp).get_json()["data"]
    assert o["payment_status"] == "paid" and o["payment"]["paid_at"]
    assert stock(shop["para"]) == 97
    assert Notification.query.filter_by(type="payment.received").count() == 1 and Notification.query.filter_by(type="payment.paid").count() == 1
    assert AuditLog.query.filter_by(action="payment.paid").count() == 1
    assert client.post(f"{OR}/{oid}/ready", headers=shop["h"]).status_code == 200


def test_prescription_must_be_approved_before_paying(client, shop, new_patient):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["amox"], 1))["id"]
    assert pay(client, hp, oid).status_code == 409
    upload(client, hp, oid)
    assert pay(client, hp, oid).status_code == 409                            # uploaded but not approved
    client.post(f"{OR}/{oid}/prescription/reject", headers=shop["h"], json={"reason": "Not readable"})
    assert pay(client, hp, oid).status_code == 409
    upload(client, hp, oid)
    client.post(f"{OR}/{oid}/prescription/approve", headers=shop["h"])
    assert pay(client, hp, oid).status_code == 200
    assert stock(shop["amox"]) == 49


def test_cannot_pay_twice(client, shop, new_patient):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 1))["id"]
    assert pay(client, hp, oid).status_code == 200
    assert pay(client, hp, oid).status_code == 409                            # in progress
    callback(client, ref_of(oid))
    assert pay(client, hp, oid).status_code == 409                            # already paid
    assert stock(shop["para"]) == 99                                          # reserved exactly once


def test_database_allows_only_one_active_payment_per_order(client, shop, new_patient):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 1))["id"]
    for ref in ("A-1", "B-2"):
        db.session.add(Payment(order_id=oid, amount_tzs=1500, network="mpesa", payer_phone="+255712345678",
                               provider="simulator", provider_ref=ref, status="pending"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_pay_validation_and_access(client, shop, new_patient, new_doctor):
    hp, _ = new_patient()
    other, _ = new_patient()
    oid = place(client, hp, (shop["para"], 1))["id"]
    assert pay(client, hp, oid, "airtelmoney").status_code == 422             # not enabled yet
    assert pay(client, hp, oid, "bitcoin").status_code == 422
    assert pay(client, hp, oid, "mpesa", phone="123").status_code == 422
    assert client.post(f"{OR}/{oid}/pay", headers=hp, json={}).status_code == 422
    assert pay(client, other, oid).status_code == 404                         # someone else's order
    assert pay(client, shop["h"], oid).status_code == 403
    hd, _ = new_doctor()
    assert pay(client, hd, oid).status_code == 403
    assert client.post(f"{OR}/{oid}/pay", json={"network": "mpesa"}).status_code == 401
    client.post(f"{OR}/{oid}/cancel", headers=hp)
    assert pay(client, hp, oid).status_code == 409                            # cancelled order
    assert Payment.query.count() == 0 and stock(shop["para"]) == 100


def test_expired_order_cannot_be_paid(client, shop, new_patient):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 1))["id"]
    set_order(oid, expires_at=past(60))
    assert pay(client, hp, oid).status_code == 409
    assert stock(shop["para"]) == 100


# ---------------- stock ----------------
def test_stock_is_checked_again_at_payment_time(client, shop, new_patient):
    low = add(client, shop["h"], "Low stock", 700, 5)
    h1, _ = new_patient()
    h2, _ = new_patient()
    o1 = place(client, h1, (low, 4))["id"]
    o2 = place(client, h2, (low, 4))["id"]                                    # both fit at order time (no reservation yet)
    assert pay(client, h1, o1).status_code == 200 and stock(low) == 1
    r = pay(client, h2, o2)
    assert r.status_code == 409 and "no longer available" in r.get_json()["message"]
    d = client.get(f"{OR}/{o2}", headers=h2).get_json()["data"]
    assert d["payment_status"] == "unpaid" and d["payment"] is None and stock(low) == 1


def test_failed_payment_releases_stock_and_allows_retry(client, shop, new_patient):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 5))["id"]
    pay(client, hp, oid)
    assert stock(shop["para"]) == 95
    r = callback(client, ref_of(oid), "failed", reason="Insufficient funds")
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "failed"
    d = client.get(f"{OR}/{oid}", headers=hp).get_json()["data"]
    assert stock(shop["para"]) == 100 and d["payment_status"] == "failed" and d["payable"] is True
    assert d["payment"]["failure_reason"] == "Insufficient funds"
    assert Notification.query.filter_by(type="payment.failed").count() == 1
    assert pay(client, hp, oid).status_code == 200                            # retry
    assert stock(shop["para"]) == 95 and Payment.query.count() == 2
    callback(client, ref_of(oid))
    assert client.get(f"{OR}/{oid}", headers=hp).get_json()["data"]["payment_status"] == "paid"
    assert stock(shop["para"]) == 95


# ---------------- callback protection ----------------
def test_callback_rejects_forged_requests(client, shop, new_patient):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 1))["id"]
    pay(client, hp, oid)
    ref = ref_of(oid)
    assert callback(client, ref, sig=None).status_code == 401
    assert callback(client, ref, sig="0" * 64).status_code == 401
    wrong = hmac.new(b"someone-elses-secret", b"x", hashlib.sha256).hexdigest()
    assert callback(client, ref, sig=wrong).status_code == 401
    assert client.get(f"{OR}/{oid}", headers=hp).get_json()["data"]["payment_status"] == "pending"   # untouched
    assert callback(client, "SIM-doesnotexist").status_code == 404
    assert callback(client, ref, raw=b"not json").status_code == 400
    assert callback(client, ref, raw=b'{"status": "success"}').status_code == 422
    assert callback(client, ref, "refunded").status_code == 422


def test_callback_amount_must_match(client, shop, new_patient):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 2))["id"]
    pay(client, hp, oid)
    assert callback(client, ref_of(oid), amount=1).status_code == 422
    assert client.get(f"{OR}/{oid}", headers=hp).get_json()["data"]["payment_status"] == "pending"
    assert AuditLog.query.filter_by(action="payment.amount_mismatch").count() == 1
    assert callback(client, ref_of(oid), amount=3000).status_code == 200


def test_callback_is_idempotent(client, shop, new_patient):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 1))["id"]
    pay(client, hp, oid)
    ref = ref_of(oid)
    assert callback(client, ref).get_json()["data"]["changed"] is True
    again = callback(client, ref)
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False
    assert Notification.query.filter_by(type="payment.received").count() == 1      # no duplicate notifications
    assert callback(client, ref, "failed").status_code == 409                       # conflicting outcome
    assert client.get(f"{OR}/{oid}", headers=hp).get_json()["data"]["payment_status"] == "paid"
    assert stock(shop["para"]) == 99


# ---------------- timeouts ----------------
def test_stuck_payment_times_out_then_late_success_recovers(client, shop, new_patient, app):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 2))["id"]
    pay(client, hp, oid)
    Payment.query.one().created_at = past(60 * 31)
    db.session.commit()
    out = app.test_cli_runner().invoke(args=["expire-payments"])
    assert out.exit_code == 0 and "Failed 1 stuck payment(s)." in out.output, out.output
    assert stock(shop["para"]) == 100
    assert client.get(f"{OR}/{oid}", headers=hp).get_json()["data"]["payment_status"] == "failed"
    # the money did arrive after all: stock is taken again and the order becomes paid
    assert callback(client, ref_of(oid)).status_code == 200
    assert client.get(f"{OR}/{oid}", headers=hp).get_json()["data"]["payment_status"] == "paid"
    assert stock(shop["para"]) == 98 and Refund.query.count() == 0


def test_late_success_without_stock_records_refund_due(client, shop, new_patient, app):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 2))["id"]
    pay(client, hp, oid)
    Payment.query.one().created_at = past(60 * 31)
    db.session.commit()
    app.test_cli_runner().invoke(args=["expire-payments"])
    client.patch(f"{PH}/me/medicines/{shop['para']}", headers=shop["h"], json={"stock_quantity": 0})   # sold out meanwhile
    assert callback(client, ref_of(oid)).status_code == 200
    r = Refund.query.one()
    assert r.amount_tzs == 3000 and "no longer be fulfilled" in r.reason
    assert Payment.query.one().status == "paid" and stock(shop["para"]) == 0
    assert Notification.query.filter_by(type="refund.due").count() == 1
    assert client.get(f"{OR}/{oid}", headers=hp).get_json()["data"]["refunds"][0]["amount_tzs"] == 3000


# ---------------- refunds ----------------
def test_full_refund_cancels_uncollected_order_and_restores_stock(client, shop, new_patient, new_pharmacy):
    hp, _ = new_patient()
    oid = paid_order(client, shop, hp, 4)
    assert stock(shop["para"]) == 96
    other_ph, _ = new_pharmacy()
    assert client.post(f"{OR}/{oid}/refund", headers=other_ph, json={"reason": "x" * 5}).status_code == 404
    assert client.post(f"{OR}/{oid}/refund", headers=hp, json={"reason": "Changed my mind"}).status_code == 403
    assert client.post(f"{OR}/{oid}/refund", headers=shop["h"], json={}).status_code == 422          # reason required
    assert client.post(f"{OR}/{oid}/refund", headers=shop["h"], json={"reason": "Too much", "amount_tzs": 6001}).status_code == 422
    assert client.post(f"{OR}/{oid}/refund", headers=shop["h"], json={"reason": "Bad", "amount_tzs": 0}).status_code == 422
    r = client.post(f"{OR}/{oid}/refund", headers=shop["h"], json={"reason": "Medicine out of date"})
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["status"] == "cancelled" and d["refunds"][0]["amount_tzs"] == 6000
    assert stock(shop["para"]) == 100
    assert Notification.query.filter_by(type="refund.recorded").count() == 1
    assert client.post(f"{OR}/{oid}/refund", headers=shop["h"], json={"reason": "Again please"}).status_code == 422   # nothing left


def test_partial_refunds_then_remainder(client, shop, new_patient):
    hp, _ = new_patient()
    oid = paid_order(client, shop, hp, 2)                                     # 3000
    client.post(f"{OR}/{oid}/ready", headers=shop["h"])
    r = client.post(f"{OR}/{oid}/refund", headers=shop["h"], json={"reason": "One box damaged", "amount_tzs": 1500})
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["status"] == "ready" and stock(shop["para"]) == 98     # partial: order stays
    assert client.post(f"{OR}/{oid}/refund", headers=shop["h"], json={"reason": "Too much", "amount_tzs": 1501}).status_code == 422
    d = client.post(f"{OR}/{oid}/refund", headers=shop["h"], json={"reason": "Rest returned"}).get_json()["data"]
    assert [x["amount_tzs"] for x in d["refunds"]] == [1500, 1500] and d["status"] == "cancelled" and stock(shop["para"]) == 100


def test_refund_after_collection_keeps_order_and_stock(client, shop, new_patient):
    hp, _ = new_patient()
    oid = paid_order(client, shop, hp, 1)
    client.post(f"{OR}/{oid}/ready", headers=shop["h"])
    client.post(f"{OR}/{oid}/collect", headers=shop["h"])
    d = client.post(f"{OR}/{oid}/refund", headers=shop["h"], json={"reason": "Customer complaint"}).get_json()["data"]
    assert d["status"] == "collected" and d["refunds"][0]["amount_tzs"] == 1500 and stock(shop["para"]) == 99


def test_only_paid_orders_can_be_refunded(client, shop, new_patient):
    hp, _ = new_patient()
    oid = place(client, hp, (shop["para"], 1))["id"]
    assert client.post(f"{OR}/{oid}/refund", headers=shop["h"], json={"reason": "Nothing paid"}).status_code == 409
    pay(client, hp, oid)
    assert client.post(f"{OR}/{oid}/refund", headers=shop["h"], json={"reason": "Still pending"}).status_code == 409
