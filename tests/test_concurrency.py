"""Race-condition tests. They need a real PostgreSQL (row locks), so they only run when
TEST_DATABASE_URL is set, e.g.
    TEST_DATABASE_URL=postgresql+psycopg2://user:pw@localhost:5432/zahanati_test pytest tests/test_concurrency.py
"""
import os
import threading

import pytest

from tests.test_appointments import AP, book, open_hours, slot

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
                                reason="needs PostgreSQL (set TEST_DATABASE_URL)")


def _race(app, jobs):
    results, barrier = [], threading.Barrier(len(jobs))

    def run(job):
        client = app.test_client()
        barrier.wait()
        results.append(job(client).status_code)

    threads = [threading.Thread(target=run, args=(j,)) for j in jobs]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return sorted(results)


def test_many_patients_one_slot(app, client, new_doctor, new_patient):
    hd, did = new_doctor()
    open_hours(client, hd)
    patients = [new_patient()[0] for _ in range(8)]
    start = slot()
    codes = _race(app, [lambda c, h=h: book(c, h, did, start) for h in patients])
    assert codes == [201] + [409] * 7, codes


def test_one_patient_two_doctors_same_time(app, client, new_doctor, new_patient):
    (h1, d1), (h2, d2) = new_doctor(), new_doctor()
    open_hours(client, h1)
    open_hours(client, h2)
    hp, _ = new_patient()
    start = slot()
    codes = _race(app, [lambda c: book(c, hp, d1, start), lambda c: book(c, hp, d2, start)])
    assert codes == [201, 409], codes


def test_accept_and_cancel_race_leaves_one_final_state(app, client, new_doctor, new_patient):
    hd, did = new_doctor()
    open_hours(client, hd)
    hp, _ = new_patient()
    aid = book(client, hp, did, slot()).get_json()["data"]["id"]
    codes = _race(app, [lambda c: c.post(f"{AP}/{aid}/accept", headers=hd),
                        lambda c: c.post(f"{AP}/{aid}/reject", headers=hd)])
    assert codes == [200, 409], codes


def test_otp_code_can_only_be_used_once_under_race(app, client, new_doctor):
    from tests.conftest import sms_code
    phone = "+255766000001"
    client.post("/api/v1/auth/otp/request", json={"phone": phone})
    code = sms_code(app, phone)
    codes = _race(app, [lambda c: c.post("/api/v1/auth/otp/verify", json={"phone": phone, "code": code, "full_name": "Asha Juma"})
                        for _ in range(6)])
    assert codes.count(201) == 1 and all(c in (400, 409) for c in codes if c != 201), codes


# ---------------- orders and payments ----------------
def _shop(client, new_pharmacy, stock=1):
    from tests.test_medicines import add
    h, pid = new_pharmacy()
    return h, add(client, h, "Last unit", 1000, stock), add(client, h, "Rx drug", 2000, 50, requires_prescription=True)


def _order(client, h, medicine_id, qty=1):
    r = client.post("/api/v1/orders", headers=h, json={"items": [{"medicine_id": medicine_id, "quantity": qty}]})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]["id"]


def test_two_customers_paying_for_the_last_unit(app, client, new_pharmacy, new_patient):
    ph, med, _ = _shop(client, new_pharmacy, stock=1)
    p1, _ = new_patient()
    p2, _ = new_patient()
    o1, o2 = _order(client, p1, med), _order(client, p2, med)                  # both orders fit: stock is only reserved on payment
    codes = _race(app, [lambda c: c.post(f"/api/v1/orders/{o1}/pay", headers=p1, json={"network": "mpesa"}),
                        lambda c: c.post(f"/api/v1/orders/{o2}/pay", headers=p2, json={"network": "mpesa"})])
    assert codes == [200, 409], codes
    from app.extensions import db
    from app.models import Medicine
    db.session.expire_all()
    assert db.session.get(Medicine, med).stock_quantity == 0                     # never negative, never oversold


def test_double_click_on_pay_creates_one_payment(app, client, new_pharmacy, new_patient):
    ph, med, _ = _shop(client, new_pharmacy, stock=10)
    hp, _ = new_patient()
    oid = _order(client, hp, med, 3)
    codes = _race(app, [lambda c: c.post(f"/api/v1/orders/{oid}/pay", headers=hp, json={"network": "mpesa"}) for _ in range(5)])
    assert codes == [200] + [409] * 4, codes
    from app.extensions import db
    from app.models import Medicine, Payment
    db.session.expire_all()
    assert Payment.query.filter_by(order_id=oid).count() == 1 and db.session.get(Medicine, med).stock_quantity == 7


def test_concurrent_callbacks_apply_once(app, client, new_pharmacy, new_patient):
    import hashlib, hmac, json
    from app.extensions import db
    from app.models import Notification, Payment
    ph, med, _ = _shop(client, new_pharmacy, stock=5)
    hp, _ = new_patient()
    oid = _order(client, hp, med)
    client.post(f"/api/v1/orders/{oid}/pay", headers=hp, json={"network": "mpesa"})
    db.session.expire_all()
    ref = Payment.query.filter_by(order_id=oid).one().provider_ref
    raw = json.dumps({"provider_ref": ref, "status": "success"}).encode()
    sig = hmac.new(b"test-callback-secret", raw, hashlib.sha256).hexdigest()
    codes = _race(app, [lambda c: c.post("/api/v1/payments/callback", data=raw, headers={"X-Signature": sig, "Content-Type": "application/json"})
                        for _ in range(5)])
    assert codes == [200] * 5, codes
    db.session.expire_all()
    assert Notification.query.filter_by(type="payment.received").count() == 1      # processed exactly once


def test_two_simultaneous_prescription_uploads(app, client, new_pharmacy, new_patient):
    import io
    ph, _, rx = _shop(client, new_pharmacy)
    hp, _ = new_patient()
    oid = _order(client, hp, rx)
    pdf = b"%PDF-1.4 race"
    codes = _race(app, [lambda c: c.post(f"/api/v1/orders/{oid}/prescription", headers=hp,
                                         data={"file": (io.BytesIO(pdf), "rx.pdf")}, content_type="multipart/form-data")
                        for _ in range(4)])
    assert codes == [200] + [409] * 3, codes
    from pathlib import Path
    assert len(list(Path(app.config["UPLOAD_DIR"]).glob("*.enc"))) == 1            # no orphaned files from the losers
