from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Appointment, AuditLog

TZ = ZoneInfo("Africa/Dar_es_Salaam")
AP, DR = "/api/v1/appointments", "/api/v1/doctors"


def slot(days=3, hour=10, minute=0):
    d = datetime.now(TZ).date() + timedelta(days=days)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ).isoformat()


def day(days=3):
    return (datetime.now(TZ).date() + timedelta(days=days)).isoformat()


def utc(iso):
    return datetime.fromisoformat(iso).astimezone(timezone.utc)


def open_hours(client, headers, windows=None):
    windows = windows or [{"weekday": i, "start_time": "09:00", "end_time": "17:00"} for i in range(7)]
    r = client.put(f"{DR}/me/availability", headers=headers, json={"windows": windows})
    assert r.status_code == 200, r.get_json()


def book(client, h, did, start, reason="Checkup"):
    return client.post(AP, headers=h, json={"doctor_id": did, "start_time": start, "reason": reason})


@pytest.fixture()
def setup(client, new_patient, new_doctor):
    hd, did = new_doctor()
    open_hours(client, hd)
    hp, pid = new_patient()
    return hp, pid, hd, did


# ---------- availability ----------
def test_availability_set_get_and_validation(client, new_doctor, new_patient):
    hd, _ = new_doctor()
    open_hours(client, hd, [{"weekday": 0, "start_time": "09:00", "end_time": "12:00"},
                            {"weekday": 0, "start_time": "14:00", "end_time": "17:00"}])
    w = client.get(f"{DR}/me/availability", headers=hd).get_json()["data"]
    assert len(w) == 2 and w[0]["start_time"] == "09:00"
    bad = [{"weekday": 0, "start_time": "09:00", "end_time": "12:00"}, {"weekday": 0, "start_time": "11:00", "end_time": "13:00"}]
    assert client.put(f"{DR}/me/availability", headers=hd, json={"windows": bad}).status_code == 422
    rev = [{"weekday": 0, "start_time": "12:00", "end_time": "09:00"}]
    assert client.put(f"{DR}/me/availability", headers=hd, json={"windows": rev}).status_code == 422
    short = [{"weekday": 0, "start_time": "09:00", "end_time": "09:10"}]
    assert client.put(f"{DR}/me/availability", headers=hd, json={"windows": short}).status_code == 422
    assert client.put(f"{DR}/me/availability", headers=hd, json={"windows": [{"weekday": 9, "start_time": "09:00", "end_time": "10:00"}]}).status_code == 422
    hp, _ = new_patient()
    assert client.put(f"{DR}/me/availability", headers=hp, json={"windows": []}).status_code == 403


def test_free_slots_listing(client, setup):
    hp, pid, hd, did = setup
    r = client.get(f"{DR}/{did}/availability?from={day()}&to={day()}", headers=hp).get_json()["data"]
    assert r["slot_minutes"] == 30 and len(r["days"][0]["slots"]) == 16
    assert r["days"][0]["slots"][0]["start"].startswith(f"{day()}T09:00:00+03:00")
    assert book(client, hp, did, slot()).status_code == 201
    r = client.get(f"{DR}/{did}/availability?from={day()}&to={day()}", headers=hp).get_json()["data"]
    assert len(r["days"][0]["slots"]) == 15
    assert client.get(f"{DR}/{did}/availability?from={day()}&to={day(30)}", headers=hp).status_code == 422
    assert client.get(f"{DR}/{did}/availability?from=bad", headers=hp).status_code == 422


def test_no_slots_on_non_working_day(client, new_doctor, new_patient):
    hd, did = new_doctor()
    target = datetime.now(TZ).date() + timedelta(days=3)
    other = (target.weekday() + 1) % 7
    open_hours(client, hd, [{"weekday": other, "start_time": "09:00", "end_time": "17:00"}])
    hp, _ = new_patient()
    r = client.get(f"{DR}/{did}/availability?from={target}&to={target}", headers=hp).get_json()["data"]
    assert r["days"][0]["slots"] == []


def test_unverified_doctor_availability_hidden(client, new_doctor, new_patient):
    hd, did = new_doctor(verified=False)
    hp, _ = new_patient()
    assert client.get(f"{DR}/{did}/availability", headers=hp).status_code == 404


# ---------- booking ----------
def test_book_success_and_rules(client, setup, new_doctor):
    hp, pid, hd, did = setup
    r = book(client, hp, did, slot())
    assert r.status_code == 201
    d = r.get_json()["data"]
    assert d["status"] == "pending" and d["start_time"].endswith("+03:00") and d["patient"]["id"] == pid
    assert AuditLog.query.filter_by(action="appointment.booked").count() == 1
    assert book(client, hp, did, slot(hour=8)).status_code == 422          # before opening
    assert book(client, hp, did, slot(hour=17)).status_code == 422         # at closing
    assert book(client, hp, did, slot(hour=16, minute=30)).status_code == 201  # last slot ok
    assert book(client, hp, did, slot(hour=11, minute=15)).status_code == 422  # off the grid
    assert book(client, hp, did, slot(days=-1)).status_code == 422         # past
    assert book(client, hp, did, slot(days=200)).status_code == 422        # too far ahead
    assert client.post(AP, headers=hp, json={"doctor_id": did}).status_code == 422
    assert client.post(AP, headers=hp, json={"doctor_id": "x", "start_time": slot()}).status_code == 422
    hu, uid = new_doctor(verified=False)
    open_hours(client, hu)
    assert book(client, hp, uid, slot(hour=12)).status_code == 404         # unverified doctor
    assert book(client, hd, did, slot(hour=13)).status_code == 403         # doctors cannot book
    assert client.post(AP, json={"doctor_id": did, "start_time": slot()}).status_code == 401


def test_naive_time_is_clinic_local(client, setup):
    hp, _, _, did = setup
    naive = slot(hour=10).replace("+03:00", "")
    r = book(client, hp, did, naive)
    assert r.status_code == 201 and r.get_json()["data"]["start_time"].endswith("T10:00:00+03:00")


def test_double_booking_prevented(client, setup, new_patient):
    hp, pid, hd, did = setup
    assert book(client, hp, did, slot()).status_code == 201
    hp2, _ = new_patient()
    r = book(client, hp2, did, slot())
    assert r.status_code == 409
    # same patient cannot book the same slot twice either
    assert book(client, hp, did, slot()).status_code == 409


def test_overlapping_appointment_prevented(client, setup, new_patient):
    hp, pid, hd, did = setup
    start = utc(slot(hour=10))
    db.session.add(Appointment(patient_id=pid, doctor_id=did, status="accepted",
                               start_time=start, end_time=start + timedelta(minutes=60)))
    db.session.commit()
    hp2, _ = new_patient()
    assert book(client, hp2, did, slot(hour=10, minute=30)).status_code == 409   # inside the 60-min block
    assert book(client, hp2, did, slot(hour=11)).status_code == 201              # right after is fine
    assert book(client, hp2, did, slot(hour=9, minute=30)).status_code == 201    # right before is fine


def test_patient_cannot_be_in_two_places(client, setup, new_doctor):
    hp, _, _, did = setup
    hd2, did2 = new_doctor()
    open_hours(client, hd2)
    assert book(client, hp, did, slot()).status_code == 201
    assert book(client, hp, did2, slot()).status_code == 409


def test_db_unique_index_backstop(client, setup):
    hp, pid, hd, did = setup
    start = utc(slot())
    for _ in range(2):
        db.session.add(Appointment(patient_id=pid, doctor_id=did, status="pending",
                                   start_time=start, end_time=start + timedelta(minutes=30)))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# ---------- cancel / accept / reject ----------
def test_cancel_frees_slot(client, setup, new_patient):
    hp, pid, hd, did = setup
    aid = book(client, hp, did, slot()).get_json()["data"]["id"]
    hp2, _ = new_patient()
    assert client.post(f"{AP}/{aid}/cancel", headers=hp2).status_code == 404   # not yours
    r = client.post(f"{AP}/{aid}/cancel", headers=hp, json={"note": "Travelling"})
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "cancelled"
    assert r.get_json()["data"]["cancel_reason"] == "Travelling"
    assert client.post(f"{AP}/{aid}/cancel", headers=hp).status_code == 409   # already cancelled
    assert book(client, hp2, did, slot()).status_code == 201                  # slot is free again


def test_doctor_accept_reject_flow(client, setup, new_doctor, new_patient):
    hp, pid, hd, did = setup
    a1 = book(client, hp, did, slot(hour=10)).get_json()["data"]["id"]
    a2 = book(client, hp, did, slot(hour=11)).get_json()["data"]["id"]
    other, _ = new_doctor()
    assert client.post(f"{AP}/{a1}/accept", headers=other).status_code == 404  # not their appointment
    assert client.post(f"{AP}/{a1}/accept", headers=hp).status_code == 403     # patients cannot accept
    r = client.post(f"{AP}/{a1}/accept", headers=hd, json={"note": "See you"})
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "accepted"
    assert client.post(f"{AP}/{a1}/accept", headers=hd).status_code == 409     # not pending any more
    assert client.post(f"{AP}/{a1}/reject", headers=hd).status_code == 409
    r = client.post(f"{AP}/{a2}/reject", headers=hd, json={"note": "Fully booked"})
    assert r.get_json()["data"]["status"] == "rejected" and r.get_json()["data"]["doctor_note"] == "Fully booked"
    hp2, _ = new_patient()
    assert book(client, hp2, did, slot(hour=11)).status_code == 201            # rejected frees slot
    # the doctor can cancel an accepted appointment too
    assert client.post(f"{AP}/{a1}/cancel", headers=hd).status_code == 200


def test_unverified_doctor_cannot_manage_appointments(client, setup, admin_headers):
    hp, pid, hd, did = setup
    aid = book(client, hp, did, slot()).get_json()["data"]["id"]
    client.post(f"/api/v1/admin/doctors/{did}/reject", headers=admin_headers, json={"reason": "Licence expired"})
    assert client.post(f"{AP}/{aid}/accept", headers=hd).status_code == 403
    assert client.post(f"{AP}/{aid}/cancel", headers=hd).status_code == 200    # cancelling is still allowed


# ---------- reschedule ----------
def test_reschedule(client, setup, new_patient):
    hp, pid, hd, did = setup
    aid = book(client, hp, did, slot(hour=10)).get_json()["data"]["id"]
    client.post(f"{AP}/{aid}/accept", headers=hd)
    r = client.patch(f"{AP}/{aid}/reschedule", headers=hp, json={"start_time": slot(hour=14)})
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["status"] == "pending" and "T14:00:00" in d["start_time"]
    # old slot is free, new one is taken
    hp2, _ = new_patient()
    assert book(client, hp2, did, slot(hour=10)).status_code == 201
    assert book(client, hp2, did, slot(hour=14)).status_code == 409
    # cannot move onto someone else's slot, nor to invalid times
    assert client.patch(f"{AP}/{aid}/reschedule", headers=hp, json={"start_time": slot(hour=10)}).status_code == 409
    assert client.patch(f"{AP}/{aid}/reschedule", headers=hp, json={"start_time": slot(hour=20)}).status_code == 422
    # moving to the same time is allowed (does not conflict with itself)
    assert client.patch(f"{AP}/{aid}/reschedule", headers=hp, json={"start_time": slot(hour=14)}).status_code == 200
    # other patients and doctors cannot reschedule
    assert client.patch(f"{AP}/{aid}/reschedule", headers=hp2, json={"start_time": slot(hour=15)}).status_code == 404
    assert client.patch(f"{AP}/{aid}/reschedule", headers=hd, json={"start_time": slot(hour=15)}).status_code == 403
    # cancelled appointments cannot be rescheduled
    client.post(f"{AP}/{aid}/cancel", headers=hp)
    assert client.patch(f"{AP}/{aid}/reschedule", headers=hp, json={"start_time": slot(hour=15)}).status_code == 409


# ---------- visibility ----------
def test_listing_and_privacy(client, setup, new_patient, new_doctor, admin_headers):
    hp, pid, hd, did = setup
    hp2, pid2 = new_patient()
    a1 = book(client, hp, did, slot(hour=10)).get_json()["data"]["id"]
    book(client, hp2, did, slot(hour=11))
    client.post(f"{AP}/{a1}/accept", headers=hd)
    assert client.get(AP, headers=hp).get_json()["meta"]["total"] == 1
    assert client.get(AP, headers=hp2).get_json()["meta"]["total"] == 1
    assert client.get(AP, headers=hd).get_json()["meta"]["total"] == 2
    other, _ = new_doctor()
    assert client.get(AP, headers=other).get_json()["meta"]["total"] == 0
    assert client.get(AP, headers=admin_headers).get_json()["meta"]["total"] == 2
    assert client.get(f"{AP}?status=accepted", headers=hd).get_json()["meta"]["total"] == 1
    assert client.get(f"{AP}?status=bogus", headers=hd).status_code == 422
    assert client.get(f"{AP}?from_date={day()}&to_date={day()}", headers=hd).get_json()["meta"]["total"] == 2
    assert client.get(f"{AP}?from_date={day(10)}", headers=hd).get_json()["meta"]["total"] == 0
    assert client.get(f"{AP}?patient_id={pid2}", headers=admin_headers).get_json()["meta"]["total"] == 1
    assert client.get(f"{AP}?patient_id={pid2}", headers=hp).get_json()["meta"]["total"] == 1  # filter ignored for patients
    # details: participants and admin only
    assert client.get(f"{AP}/{a1}", headers=hp).status_code == 200
    assert client.get(f"{AP}/{a1}", headers=hd).status_code == 200
    assert client.get(f"{AP}/{a1}", headers=admin_headers).status_code == 200
    assert client.get(f"{AP}/{a1}", headers=hp2).status_code == 404
    assert client.get(f"{AP}/{a1}", headers=other).status_code == 404
    assert client.get(f"{AP}/{a1}").status_code == 401


def test_accepted_appointment_unlocks_patient_record_access(client, setup):
    hp, pid, hd, did = setup
    aid = book(client, hp, did, slot()).get_json()["data"]["id"]
    assert client.get(f"/api/v1/patients/{pid}", headers=hd).status_code == 403   # pending: no access
    client.post(f"{AP}/{aid}/accept", headers=hd)
    assert client.get(f"/api/v1/patients/{pid}", headers=hd).status_code == 200


# ---------- complete ----------
def test_complete_requires_started(client, setup):
    hp, pid, hd, did = setup
    aid = book(client, hp, did, slot()).get_json()["data"]["id"]
    assert client.post(f"{AP}/{aid}/complete", headers=hd).status_code == 409    # not accepted
    client.post(f"{AP}/{aid}/accept", headers=hd)
    assert client.post(f"{AP}/{aid}/complete", headers=hd).status_code == 409    # in the future
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    a = Appointment(patient_id=pid, doctor_id=did, status="accepted", start_time=past, end_time=past + timedelta(minutes=30))
    db.session.add(a)
    db.session.commit()
    r = client.post(f"{AP}/{a.id}/complete", headers=hd)
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "completed"
    assert client.post(f"{AP}/{a.id}/cancel", headers=hp).status_code == 409     # completed is final


def test_cannot_accept_past_pending(client, setup):
    hp, pid, hd, did = setup
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    a = Appointment(patient_id=pid, doctor_id=did, status="pending", start_time=past, end_time=past + timedelta(minutes=30))
    db.session.add(a)
    db.session.commit()
    assert client.post(f"{AP}/{a.id}/accept", headers=hd).status_code == 409
