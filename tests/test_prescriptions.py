from datetime import timedelta

import pytest

from app.extensions import db
from app.models import AuditLog, Notification, Prescription
from tests.conftest import auth
from tests.test_consultations import AD, CN, chat, start  # noqa: F401  (chat is a fixture)
from tests.test_medicines import add
from tests.test_orders import OR, place, set_order, upload  # noqa: F401
from tests.test_payments import callback, pay, ref_of

RX = "/api/v1/prescriptions"
ITEM = {"medicine_name": "Amoxicillin", "dosage": "500mg", "frequency": "3 times a day", "duration_days": 7, "instructions": "After meals"}


def issue(client, chat, items=None, notes="Rest well", expect=201, **kw):
    r = client.post(f"{CN}/{chat['cid']}/prescriptions", headers=chat["hd"],
                    json={"items": items if items is not None else [ITEM], "notes": notes, **kw})
    assert r.status_code == expect, r.get_json()
    return r.get_json()["data"] if expect == 201 else r.get_json()


def test_issue_prescription(client, chat):
    d = issue(client, chat, [ITEM, {**ITEM, "medicine_name": "Paracetamol 500mg", "duration_days": 3}])
    assert d["status"] == "active" and len(d["items"]) == 2 and d["doctor"]["name"] == "Dr. Neema Mushi"
    assert d["patient"]["name"] == "Asha Juma" and d["consultation_id"] == chat["cid"]
    assert (__import__("datetime").date.fromisoformat(d["valid_until"]) - __import__("datetime").date.fromisoformat(d["issued_date"])).days == 90
    assert Notification.query.filter_by(type="prescription.issued").count() == 1
    assert AuditLog.query.filter_by(action="prescription.issued", entity_id=d["id"]).count() == 1
    assert client.get(f"{RX}/{d['id']}", headers=chat["hp"]).status_code == 200
    assert client.get(f"{RX}/{d['id']}", headers=chat["hd"]).status_code == 200


def test_issue_validation_and_authorisation(client, chat, new_doctor, admin_headers):
    cid = chat["cid"]
    issue(client, chat, [], expect=422)
    issue(client, chat, [ITEM] * 21, expect=422)
    for bad in ({"duration_days": 0}, {"duration_days": 366}, {"duration_days": 2.5}, {"duration_days": "7"},
                {"dosage": ""}, {"frequency": ""}, {"medicine_name": "x"}):
        issue(client, chat, [{**ITEM, **bad}], expect=422)
    assert client.post(f"{CN}/{cid}/prescriptions", headers=chat["hp"], json={"items": [ITEM]}).status_code == 403   # patients cannot
    other, _ = new_doctor()
    assert client.post(f"{CN}/{cid}/prescriptions", headers=other, json={"items": [ITEM]}).status_code == 404       # not their consultation
    assert client.post(f"{CN}/{cid}/prescriptions", json={"items": [ITEM]}).status_code == 401
    client.post(f"{AD}/doctors/{chat['did']}/license-status", headers=admin_headers, json={"status": "expired"})
    issue(client, chat, expect=403)                                      # expired licence cannot prescribe
    client.post(f"{AD}/doctors/{chat['did']}/license-status", headers=admin_headers, json={"status": "active"})
    client.post(f"{CN}/{cid}/close", headers=chat["hd"])
    issue(client, chat, expect=409)                                      # consultation closed
    assert Prescription.query.count() == 0


def test_unverified_doctor_cannot_prescribe(client, new_patient, new_doctor):
    hp, _ = new_patient()
    hd, did = new_doctor()
    cid = start(client, hp, did).get_json()["data"]["id"]
    # an unverified doctor never even gets a consultation (see consultation tests); the role check also blocks direct calls
    hu, _ = new_doctor(verified=False)
    assert client.post(f"{CN}/{cid}/prescriptions", headers=hu, json={"items": [ITEM]}).status_code == 403


def test_prescriptions_are_immutable(client, chat):
    pid = issue(client, chat)["id"]
    for method in (client.put, client.patch, client.delete):
        assert method(f"{RX}/{pid}", headers=chat["hd"], json={"notes": "changed"}).status_code == 405
    assert client.get(f"{RX}/{pid}", headers=chat["hd"]).get_json()["data"]["notes"] == "Rest well"


def test_lists_and_privacy(client, chat, new_patient, new_doctor):
    pid = issue(client, chat)["id"]
    assert client.get(RX, headers=chat["hp"]).get_json()["meta"]["total"] == 1
    assert client.get(RX, headers=chat["hd"]).get_json()["meta"]["total"] == 1
    other_p, _ = new_patient()
    other_d, _ = new_doctor()
    for h in (other_p, other_d):
        assert client.get(f"{RX}/{pid}", headers=h).status_code == 404
        assert client.get(f"{RX}/{pid}/pdf", headers=h).status_code == 404
        assert client.get(RX, headers=h).get_json()["meta"]["total"] == 0
    assert client.get(f"{RX}?status=cancelled", headers=chat["hp"]).get_json()["meta"]["total"] == 0
    assert client.get(f"{RX}?status=bogus", headers=chat["hp"]).status_code == 422
    assert client.get(f"{RX}/bad", headers=chat["hp"]).status_code == 404
    assert client.get(RX).status_code == 401


def test_pdf_download(client, chat):
    pid = issue(client, chat, [ITEM, {**ITEM, "medicine_name": "Paracetamol 500mg"}])["id"]
    r = client.get(f"{RX}/{pid}/pdf", headers=chat["hp"])
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    assert "attachment" in r.headers["Content-Disposition"] and r.headers["Cache-Control"] == "no-store"
    for text in (b"Dr. Neema Mushi", b"Asha Juma", b"Amoxicillin", b"Paracetamol 500mg", pid.encode(), b"Verified doctor", b"Tanganyika"):
        assert text in r.data, text
    assert b"CANCELLED" not in r.data
    assert client.get(f"{RX}/{pid}/pdf", headers=chat["hd"]).status_code == 200
    assert AuditLog.query.filter_by(action="prescription.pdf_downloaded").count() == 2
    client.post(f"{RX}/{pid}/cancel", headers=chat["hd"], json={"reason": "Wrong dose"})
    r = client.get(f"{RX}/{pid}/pdf", headers=chat["hp"])
    assert b"CANCELLED" in r.data and b"Wrong dose" in r.data


def test_pdf_escapes_markup(client, chat):
    pid = issue(client, chat, [{**ITEM, "medicine_name": "<b>Drug</b> & <script>", "instructions": "<i>x"}], notes="a < b")["id"]
    assert client.get(f"{RX}/{pid}/pdf", headers=chat["hp"]).status_code == 200


def test_cancel_prescription(client, chat):
    pid = issue(client, chat)["id"]
    assert client.post(f"{RX}/{pid}/cancel", headers=chat["hp"], json={"reason": "I do not want it"}).status_code == 403
    assert client.post(f"{RX}/{pid}/cancel", headers=chat["hd"], json={}).status_code == 422
    r = client.post(f"{RX}/{pid}/cancel", headers=chat["hd"], json={"reason": "Wrong dose"})
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "cancelled"
    assert client.post(f"{RX}/{pid}/cancel", headers=chat["hd"], json={"reason": "Again please"}).status_code == 409
    assert Notification.query.filter_by(type="prescription.cancelled").count() == 1


# ---------------- using an e-prescription for an order ----------------
@pytest.fixture()
def pharm(client, new_pharmacy):
    h, pid = new_pharmacy()
    return {"h": h, "pid": pid, "amox": add(client, h, "Amoxicillin 500mg", 3500, 50, requires_prescription=True, generic_name="Amoxicillin"),
            "para": add(client, h, "Paracetamol 500mg", 1500, 100)}


def use(client, hp, oid, rid):
    return client.post(f"{OR}/{oid}/prescription/use", headers=hp, json={"prescription_id": rid})


def test_prescription_replaces_upload_and_flows_to_ready(client, chat, pharm):
    hp, ph = chat["hp"], pharm["h"]
    oid = place(client, hp, (pharm["amox"], 1), (pharm["para"], 2))["id"]
    rid = issue(client, chat)["id"]
    r = use(client, hp, oid, rid)
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["prescription_status"] == "approved" and d["payable"] is True
    assert d["e_prescription"]["id"] == rid and d["e_prescription"]["items"][0]["medicine_name"] == "Amoxicillin"
    pharmacy_view = client.get(f"{OR}/{oid}", headers=ph).get_json()["data"]
    assert pharmacy_view["e_prescription"]["doctor"] == "Dr. Neema Mushi" and pharmacy_view["prescription_status"] == "approved"
    assert Notification.query.filter_by(type="prescription.attached").count() == 1
    assert upload(client, hp, oid).status_code == 409                    # nothing left to upload
    assert pay(client, hp, oid).status_code == 200
    callback(client, ref_of(oid))
    assert client.post(f"{OR}/{oid}/ready", headers=ph).status_code == 200


def test_prescription_must_cover_the_medicines(client, chat, pharm, new_patient):
    hp = chat["hp"]
    oid = place(client, hp, (pharm["amox"], 1))["id"]
    wrong = issue(client, chat, [{**ITEM, "medicine_name": "Ibuprofen"}])["id"]
    r = use(client, hp, oid, wrong)
    assert r.status_code == 422 and r.get_json()["errors"]["unmatched_medicines"] == ["Amoxicillin 500mg"]
    assert client.get(f"{OR}/{oid}", headers=hp).get_json()["data"]["prescription_status"] == "required"
    strength = issue(client, chat, [{**ITEM, "medicine_name": "Amoxicillin 250mg"}])["id"]
    assert use(client, hp, oid, strength).status_code == 422             # wrong strength does not match
    exact = issue(client, chat, [{**ITEM, "medicine_name": "amoxicillin 500MG"}])["id"]
    assert use(client, hp, oid, exact).status_code == 200


def test_prescription_ownership_and_state_rules(client, chat, pharm, new_patient):
    hp = chat["hp"]
    rid = issue(client, chat)["id"]
    oid = place(client, hp, (pharm["amox"], 1))["id"]
    plain = place(client, hp, (pharm["para"], 1))["id"]
    other_p, _ = new_patient()
    other_order = place(client, other_p, (pharm["amox"], 1))["id"]
    assert use(client, other_p, other_order, rid).status_code == 404     # someone else's prescription
    assert use(client, hp, plain, rid).status_code == 409                # order needs none
    assert use(client, hp, oid, "00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.post(f"{OR}/{oid}/prescription/use", headers=hp, json={}).status_code == 422
    assert use(client, chat["hd"], oid, rid).status_code == 403
    # a prescription can serve only one live order
    assert use(client, hp, oid, rid).status_code == 200
    second = place(client, hp, (pharm["amox"], 1))["id"]
    assert use(client, hp, second, rid).status_code == 409
    client.post(f"{OR}/{oid}/cancel", headers=hp)
    assert use(client, hp, second, rid).status_code == 200               # first order was cancelled: free again


def test_cancelled_or_expired_prescription_is_refused(client, chat, pharm):
    hp = chat["hp"]
    oid = place(client, hp, (pharm["amox"], 1))["id"]
    cancelled = issue(client, chat)["id"]
    client.post(f"{RX}/{cancelled}/cancel", headers=chat["hd"], json={"reason": "Mistake"})
    assert use(client, hp, oid, cancelled).status_code == 409
    old = issue(client, chat)["id"]
    rx = db.session.get(Prescription, old)
    rx.issued_date = rx.issued_date - timedelta(days=100)
    db.session.commit()
    assert use(client, hp, oid, old).status_code == 409


def test_cancelling_attached_prescription_blocks_payment_and_handover(client, chat, pharm):
    hp, ph = chat["hp"], pharm["h"]
    oid = place(client, hp, (pharm["amox"], 1))["id"]
    rid = issue(client, chat)["id"]
    use(client, hp, oid, rid)
    client.post(f"{RX}/{rid}/cancel", headers=chat["hd"], json={"reason": "Patient allergy found"})
    d = client.get(f"{OR}/{oid}", headers=hp).get_json()["data"]
    assert d["payable"] is False and d["e_prescription"]["status"] == "cancelled"
    assert pay(client, hp, oid).status_code == 409
    oid2 = place(client, hp, (pharm["amox"], 1))["id"]
    rid2 = issue(client, chat)["id"]
    use(client, hp, oid2, rid2)
    pay(client, hp, oid2)
    callback(client, ref_of(oid2))
    client.post(f"{RX}/{rid2}/cancel", headers=chat["hd"], json={"reason": "Patient allergy found"})
    assert client.post(f"{OR}/{oid2}/ready", headers=ph).status_code == 409
