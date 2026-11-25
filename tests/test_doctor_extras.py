from app.models import AuditLog, DoctorProfile
from tests.conftest import DOCTOR, auth, sms_code
from tests.test_consultations import AD, CN, chat, start  # noqa: F401
from tests.test_prescriptions import ITEM, issue  # noqa: F401

D = "/api/v1/doctors"
A = "/api/v1/auth"


def test_workplaces_crud_and_validation(client, new_doctor):
    hd, _ = new_doctor()
    r = client.post(f"{D}/me/workplaces", headers=hd, json={"institution": "Muhimbili National Hospital", "role": "Registrar",
                                                            "start_year": 2018, "end_year": 2021})
    assert r.status_code == 201
    wid = r.get_json()["data"]["id"]
    assert client.post(f"{D}/me/workplaces", headers=hd, json={"institution": "Aga Khan Hospital", "start_year": 2021, "is_current": True}).status_code == 201
    assert client.post(f"{D}/me/workplaces", headers=hd, json={"institution": "Mwananyamala Hospital", "is_current": True}).status_code == 201   # more than one current
    assert client.post(f"{D}/me/workplaces", headers=hd, json={"institution": "X"}).status_code == 422
    assert client.post(f"{D}/me/workplaces", headers=hd, json={"institution": "Bad Years", "start_year": 2020, "end_year": 2019}).status_code == 422
    assert client.post(f"{D}/me/workplaces", headers=hd, json={"institution": "Current With End", "is_current": True, "end_year": 2024}).status_code == 422
    assert client.post(f"{D}/me/workplaces", headers=hd, json={"institution": "Old", "start_year": 1900}).status_code == 422
    assert client.patch(f"{D}/me/workplaces/{wid}", headers=hd, json={"role": "Consultant"}).get_json()["data"]["role"] == "Consultant"
    assert client.patch(f"{D}/me/workplaces/{wid}", headers=hd, json={"end_year": 2010}).status_code == 422
    assert len(client.get(f"{D}/me/workplaces", headers=hd).get_json()["data"]) == 3
    assert client.delete(f"{D}/me/workplaces/{wid}", headers=hd).status_code == 200
    assert client.delete(f"{D}/me/workplaces/{wid}", headers=hd).status_code == 404


def test_workplaces_are_per_doctor_and_doctor_only(client, new_doctor, new_patient):
    h1, _ = new_doctor()
    h2, _ = new_doctor()
    wid = client.post(f"{D}/me/workplaces", headers=h1, json={"institution": "Hospital One"}).get_json()["data"]["id"]
    assert client.patch(f"{D}/me/workplaces/{wid}", headers=h2, json={"role": "x"}).status_code == 404
    assert client.delete(f"{D}/me/workplaces/{wid}", headers=h2).status_code == 404
    hp, _ = new_patient()
    assert client.get(f"{D}/me/workplaces", headers=hp).status_code == 403
    assert client.get(f"{D}/me/dashboard", headers=hp).status_code == 403


def test_public_profile_shows_badge_workplace_and_council(client, new_doctor, new_patient):
    hd, did = new_doctor(council="zanzibar")
    client.post(f"{D}/me/workplaces", headers=hd, json={"institution": "Mnazi Mmoja Hospital", "is_current": True})
    hp, _ = new_patient()
    d = client.get(f"{D}/{did}", headers=hp).get_json()["data"]
    assert d["verified_badge"] is True and d["council"] == "zanzibar" and d["workplaces"][0]["institution"] == "Mnazi Mmoja Hospital"
    for secret in ("email", "phone", "credentials", "license_status", "verified_name"):
        assert secret not in d
    assert client.get(D, headers=hp).get_json()["data"][0]["verified_badge"] is True


def test_dashboard(client, chat, new_patient):
    hd = chat["hd"]
    client.post(f"{D}/me/workplaces", headers=hd, json={"institution": "Aga Khan", "is_current": True})
    client.post(f"{D}/me/workplaces", headers=hd, json={"institution": "Muhimbili", "start_year": 2015, "end_year": 2020})
    client.patch(f"{D}/me", headers=hd, json={"years_of_experience": 9})
    issue(client, chat)
    hp2, _ = new_patient()
    start(client, hp2, chat["did"])
    d = client.get(f"{D}/me/dashboard", headers=hd).get_json()["data"]
    assert d["verified_badge"] is True and d["license_status"] == "active" and d["council"] == "tanganyika"
    assert d["years_of_experience"] == 9 and d["current_workplaces"][0]["institution"] == "Aga Khan"
    assert d["experience_history"][0]["institution"] == "Muhimbili"
    assert d["stats"] == {"open_consultations": 2, "awaiting_reply": 2, "overdue_replies": 0, "unread_messages": 2,
                          "prescriptions_issued_total": 1, "prescriptions_issued_30d": 1, "pending_appointment_requests": 0}
    assert len(d["inbox"]) == 2 and d["inbox"][0]["unread_count"] == 1


def test_admin_verifies_with_register_name_and_manages_licence_status(client, new_doctor, new_patient, admin_headers):
    hd, did = new_doctor(verified=False)
    hp, _ = new_patient()
    r = client.post(f"{AD}/doctors/{did}/verify", headers=admin_headers, json={"verified_name": "Neema A. Mushi"})
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["verified_name"] == "Neema A. Mushi" and d["license_status"] == "active"
    assert client.get(f"{D}/me", headers=hd).get_json()["data"]["verified_name"] == "Neema A. Mushi"
    assert client.get(f"{D}/{did}", headers=hp).status_code == 200
    # expiring the licence hides the doctor everywhere and blocks professional actions
    assert client.post(f"{AD}/doctors/{did}/license-status", headers=hp, json={"status": "expired"}).status_code == 403
    assert client.post(f"{AD}/doctors/{did}/license-status", headers=admin_headers, json={"status": "weird"}).status_code == 422
    r = client.post(f"{AD}/doctors/{did}/license-status", headers=admin_headers, json={"status": "expired"})
    assert r.status_code == 200 and r.get_json()["data"]["license_status"] == "expired"
    assert client.get(D, headers=hp).get_json()["meta"]["total"] == 0
    assert client.get(f"{D}/{did}", headers=hp).status_code == 404
    assert client.get(f"{D}/{did}/availability", headers=hp).status_code == 404
    assert client.get(f"{D}/me/dashboard", headers=hd).get_json()["data"]["verified_badge"] is False
    assert AuditLog.query.filter_by(action="doctor.license_status").count() == 1
    client.post(f"{AD}/doctors/{did}/license-status", headers=admin_headers, json={"status": "active"})
    assert client.get(D, headers=hp).get_json()["meta"]["total"] == 1


def test_licence_numbers_are_unique(client, app, new_doctor):
    hd1, _ = new_doctor(license_number="MCT-7777")
    phone = "+255744555666"
    client.post(f"{A}/otp/request", json={"phone": phone, "purpose": "register"})
    body = {**DOCTOR, "phone": phone, "otp_code": sms_code(app, phone), "license_number": "mct-7777"}
    r = client.post(f"{A}/register/doctor", json=body)
    assert r.status_code == 409 and "licence" in r.get_json()["message"]
    hd2, _ = new_doctor()
    assert client.post(f"{D}/me/credentials", headers=hd2, json={"credential_type": "license", "title": "Second", "license_number": "MCT-7777"}).status_code == 409
    creds = client.get(f"{D}/me/credentials", headers=hd2).get_json()["data"]
    lic = next(c for c in creds if c["credential_type"] == "license")
    assert client.patch(f"{D}/me/credentials/{lic['id']}", headers=hd2, json={"license_number": "MCT-7777"}).status_code == 409
    assert client.patch(f"{D}/me/credentials/{lic['id']}", headers=hd2, json={"license_number": lic["license_number"]}).status_code == 200  # own number is fine


def test_council_on_registration(client, app, new_doctor):
    hd, did = new_doctor(council="zanzibar")
    assert db_doctor(did).council == "zanzibar"
    phone = "+255744111222"
    client.post(f"{A}/otp/request", json={"phone": phone, "purpose": "register"})
    r = client.post(f"{A}/register/doctor", json={**DOCTOR, "phone": phone, "otp_code": sms_code(app, phone), "license_number": "MCT-8888", "council": "mars"})
    assert r.status_code == 422


def db_doctor(did):
    from app.extensions import db
    return db.session.get(DoctorProfile, did)
