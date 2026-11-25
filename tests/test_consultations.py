from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models import AuditLog, Consultation, Notification
from tests.conftest import past

CN, AD = "/api/v1/consultations", "/api/v1/admin"


def start(client, hp, did, msg="Habari daktari, nina maumivu ya kichwa.", **kw):
    return client.post(CN, headers=hp, json={"doctor_id": did, "message": msg, **kw})


@pytest.fixture()
def chat(client, new_patient, new_doctor):
    hp, pid = new_patient()
    hd, did = new_doctor()
    r = start(client, hp, did, subject="Kichwa")
    assert r.status_code == 201, r.get_json()
    return {"hp": hp, "pid": pid, "hd": hd, "did": did, "cid": r.get_json()["data"]["id"]}


def test_start_consultation(client, chat):
    d = client.get(f"{CN}/{chat['cid']}", headers=chat["hp"]).get_json()["data"]
    assert d["status"] == "open" and d["subject"] == "Kichwa" and d["awaiting_reply"] is True and d["overdue"] is False
    assert "112" in d["notice"]["sw"] and "112" in d["notice"]["en"]
    assert d["doctor"]["verified_badge"] is True and "notes" not in d and "patient" not in d
    hours = (datetime.fromisoformat(d["reply_due_at"]) - datetime.now(timezone.utc)).total_seconds() / 3600
    assert 23.9 < hours < 24.1
    msgs = client.get(f"{CN}/{chat['cid']}/messages", headers=chat["hp"]).get_json()["data"]
    assert [m["body"] for m in msgs] == ["Habari daktari, nina maumivu ya kichwa."] and msgs[0]["sender_role"] == "patient"
    n = Notification.query.filter_by(type="consultation.new").one()
    assert n.data["consultation_id"] == chat["cid"]
    dd = client.get(f"{CN}/{chat['cid']}", headers=chat["hd"]).get_json()["data"]
    assert dd["unread_count"] == 1 and dd["patient"]["name"] == "Asha Juma" and dd["notes"] is None


def test_start_validation_and_eligibility(client, new_patient, new_doctor, admin_headers):
    hp, _ = new_patient()
    pending, pid = new_doctor(verified=False)
    expired, eid = new_doctor()
    client.post(f"{AD}/doctors/{eid}/license-status", headers=admin_headers, json={"status": "expired"})
    ok, oid = new_doctor()
    assert start(client, hp, pid).status_code == 404                       # not verified
    assert start(client, hp, eid).status_code == 404                       # licence expired
    assert start(client, hp, "00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.post(CN, headers=hp, json={"doctor_id": "bad", "message": "x"}).status_code == 422
    assert start(client, hp, oid, msg="").status_code == 422
    assert start(client, hp, oid, msg="   ").status_code == 422
    assert start(client, hp, oid, msg="x" * 2001).status_code == 422
    assert start(client, ok, oid).status_code == 403                       # doctors cannot start
    assert client.post(CN, json={"doctor_id": oid, "message": "x"}).status_code == 401
    assert start(client, hp, oid).status_code == 201                       # no prior relationship needed


def test_reply_flow_read_receipts_and_order(client, chat):
    cid, hp, hd = chat["cid"], chat["hp"], chat["hd"]
    r = client.post(f"{CN}/{cid}/messages", headers=hd, json={"body": "Pole sana. Unakunywa maji ya kutosha?"})
    assert r.status_code == 201 and r.get_json()["data"]["sender_role"] == "doctor"
    d = client.get(f"{CN}/{cid}", headers=hp).get_json()["data"]
    assert d["awaiting_reply"] is False and d["reply_due_at"] is None and d["unread_count"] == 1
    assert Notification.query.filter_by(type="consultation.message").count() == 1
    msgs = client.get(f"{CN}/{cid}/messages", headers=hp).get_json()          # reading marks as read
    assert [m["sender_role"] for m in msgs["data"]] == ["patient", "doctor"]
    assert msgs["data"][1]["read_at"] is not None and msgs["data"][0]["read_at"] is None   # the doctor's message was just read; the doctor has not read the patient's yet
    assert client.get(f"{CN}/{cid}", headers=hp).get_json()["data"]["unread_count"] == 0
    client.post(f"{CN}/{cid}/messages", headers=hp, json={"body": "Ndiyo, lakini bado yanauma."})
    assert client.get(f"{CN}/{cid}", headers=hp).get_json()["data"]["awaiting_reply"] is True
    desc = client.get(f"{CN}/{cid}/messages?order=desc&per_page=2", headers=hd).get_json()
    assert desc["data"][0]["body"].startswith("Ndiyo") and desc["meta"]["total"] == 3 and desc["meta"]["pages"] == 2
    assert client.post(f"{CN}/{cid}/messages", headers=hp, json={"body": ""}).status_code == 422
    assert client.post(f"{CN}/{cid}/messages", headers=hp, json={"body": "y" * 2001}).status_code == 422


def test_conversations_are_private(client, chat, new_patient, new_doctor, admin_headers):
    cid = chat["cid"]
    other_p, _ = new_patient()
    other_d, _ = new_doctor()
    for h in (other_p, other_d):
        assert client.get(f"{CN}/{cid}", headers=h).status_code == 404
        assert client.get(f"{CN}/{cid}/messages", headers=h).status_code == 404
        assert client.post(f"{CN}/{cid}/messages", headers=h, json={"body": "hi"}).status_code == 404
        assert client.get(CN, headers=h).get_json()["meta"]["total"] == 0
    for url in (f"{CN}/{cid}", f"{CN}/{cid}/messages", CN):           # not even admins can read private chats
        assert client.get(url, headers=admin_headers).status_code == 403
    assert client.get(f"{CN}/not-a-uuid", headers=chat["hp"]).status_code == 404
    assert client.get(CN).status_code == 401


def test_closing(client, chat):
    cid = chat["cid"]
    assert client.post(f"{CN}/{cid}/close", headers=chat["hp"]).status_code == 403
    r = client.post(f"{CN}/{cid}/close", headers=chat["hd"])
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "closed" and r.get_json()["data"]["awaiting_reply"] is False
    assert client.post(f"{CN}/{cid}/close", headers=chat["hd"]).status_code == 409
    for h in (chat["hp"], chat["hd"]):
        assert client.post(f"{CN}/{cid}/messages", headers=h, json={"body": "more"}).status_code == 409
    assert start(client, chat["hp"], chat["did"]).status_code == 201     # a new consultation can be started
    assert client.get(f"{CN}?status=closed", headers=chat["hp"]).get_json()["meta"]["total"] == 1
    assert client.get(f"{CN}?status=open", headers=chat["hp"]).get_json()["meta"]["total"] == 1
    assert client.get(f"{CN}?status=bogus", headers=chat["hp"]).status_code == 422


def test_doctor_who_loses_verification_cannot_chat(client, chat, admin_headers):
    cid = chat["cid"]
    client.post(f"{AD}/doctors/{chat['did']}/license-status", headers=admin_headers, json={"status": "expired"})
    assert client.post(f"{CN}/{cid}/messages", headers=chat["hd"], json={"body": "reply"}).status_code == 403
    r = client.post(f"{CN}/{cid}/messages", headers=chat["hp"], json={"body": "hello?"})
    assert r.status_code == 409 and "unavailable" in r.get_json()["message"]
    assert client.get(f"{CN}/{cid}/messages", headers=chat["hp"]).status_code == 200   # history stays readable
    client.post(f"{AD}/doctors/{chat['did']}/license-status", headers=admin_headers, json={"status": "active"})
    assert client.post(f"{CN}/{cid}/messages", headers=chat["hd"], json={"body": "back"}).status_code == 201


def test_reply_deadline_overdue_and_filters(client, chat, new_patient):
    hp2, _ = new_patient()
    c2 = start(client, hp2, chat["did"]).get_json()["data"]["id"]
    c = db.session.get(Consultation, chat["cid"])
    c.awaiting_reply_since = past(25 * 3600)
    db.session.commit()
    d = client.get(f"{CN}/{chat['cid']}", headers=chat["hd"]).get_json()["data"]
    assert d["overdue"] is True
    ov = client.get(f"{CN}?overdue=true", headers=chat["hd"]).get_json()
    assert [x["id"] for x in ov["data"]] == [chat["cid"]] and ov["meta"]["total"] == 1
    assert client.get(f"{CN}?awaiting_reply=true", headers=chat["hd"]).get_json()["meta"]["total"] == 2
    client.post(f"{CN}/{chat['cid']}/messages", headers=chat["hd"], json={"body": "Samahani kwa kuchelewa"})
    assert client.get(f"{CN}?overdue=true", headers=chat["hd"]).get_json()["meta"]["total"] == 0
    assert c2


def test_clinical_notes_private_to_doctor(client, chat, new_doctor):
    cid = chat["cid"]
    r = client.patch(f"{CN}/{cid}/clinical", headers=chat["hd"], json={
        "notes": "Anaonekana na wasiwasi", "diagnosis": "Tension headache", "treatment_recommendations": "Pumzika, kunywa maji"})
    assert r.status_code == 200 and r.get_json()["data"]["notes"] == "Anaonekana na wasiwasi"
    p = client.get(f"{CN}/{cid}", headers=chat["hp"]).get_json()["data"]
    assert p["diagnosis"] == "Tension headache" and p["treatment_recommendations"] == "Pumzika, kunywa maji" and "notes" not in p
    assert Notification.query.filter_by(type="consultation.updated").count() == 1
    assert AuditLog.query.filter_by(action="consultation.clinical_updated").count() == 1
    client.patch(f"{CN}/{cid}/clinical", headers=chat["hd"], json={"notes": "Ameitikia vizuri"})
    assert Notification.query.filter_by(type="consultation.updated").count() == 1      # notes only: patient not pinged
    assert client.patch(f"{CN}/{cid}/clinical", headers=chat["hp"], json={"diagnosis": "self"}).status_code == 403
    other, _ = new_doctor()
    assert client.patch(f"{CN}/{cid}/clinical", headers=other, json={"diagnosis": "x"}).status_code == 404


def test_consultation_gives_doctor_authorised_access_to_patient(client, chat, new_patient, new_doctor):
    pid, hd = chat["pid"], chat["hd"]
    assert client.get(f"/api/v1/patients/{pid}", headers=hd).status_code == 200
    assert client.get(f"/api/v1/patients/{pid}/medical-records", headers=hd).status_code == 200
    stranger, _ = new_doctor()
    assert client.get(f"/api/v1/patients/{pid}", headers=stranger).status_code == 403
    _, pid2 = new_patient()
    assert client.get(f"/api/v1/patients/{pid2}", headers=hd).status_code == 403
