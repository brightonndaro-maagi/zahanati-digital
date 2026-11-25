from tests.conftest import auth

P = "/api/v1/patients"


def test_patient_profile_get_and_update(client, new_patient):
    h, _ = new_patient()
    assert client.get(f"{P}/me", headers=h).get_json()["data"]["first_name"] == "Asha"
    r = client.patch(f"{P}/me", headers=h, json={"blood_group": "O+", "address": "Kinondoni", "region": "Dar es Salaam"})
    assert r.status_code == 200 and r.get_json()["data"]["blood_group"] == "O+"
    assert client.put(f"{P}/me", headers=h, json={"blood_group": "O+"}).status_code == 422  # PUT needs full body
    assert client.patch(f"{P}/me", headers=h, json={"blood_group": "Z"}).status_code == 422
    assert client.patch(f"{P}/me", headers=h, json={"date_of_birth": "2999-01-01"}).status_code == 422


def test_phone_is_read_only_here(client, new_patient):
    h, _ = new_patient()
    before = client.get(f"{P}/me", headers=h).get_json()["data"]["phone"]
    assert client.patch(f"{P}/me", headers=h, json={"phone": "+255799999999", "region": "Arusha"}).status_code == 200
    d = client.get(f"{P}/me", headers=h).get_json()["data"]
    assert d["phone"] == before and d["region"] == "Arusha"      # phone changes need an SMS code (/auth/phone/change)
    assert client.patch(f"{P}/me", headers=h, json={"emergency_contact_phone": "0712345678"}).get_json()["data"]["emergency_contact_phone"] == "+255712345678"
    assert client.patch(f"{P}/me", headers=h, json={"emergency_contact_phone": "123"}).status_code == 422


def test_role_restrictions(client, new_patient, new_doctor):
    hp, _ = new_patient()
    hd, _ = new_doctor()
    assert client.get(f"{P}/me", headers=hd).status_code == 403
    assert client.get("/api/v1/doctors/me", headers=hp).status_code == 403
    assert client.get(f"{P}/me").status_code == 401


def test_medical_record_crud_and_isolation(client, new_patient):
    h1, _ = new_patient()
    h2, _ = new_patient()
    r = client.post(f"{P}/me/medical-records", headers=h1,
                    json={"record_type": "allergy", "title": "Penicillin", "description": "Rash"})
    assert r.status_code == 201
    rid = r.get_json()["data"]["id"]
    assert client.post(f"{P}/me/medical-records", headers=h1, json={"record_type": "bogus", "title": "x"}).status_code == 422
    assert client.get(f"{P}/me/medical-records", headers=h1).get_json()["meta"]["total"] == 1
    assert client.get(f"{P}/me/medical-records?record_type=surgery", headers=h1).get_json()["meta"]["total"] == 0
    # another patient cannot see/modify/delete it (404, existence not leaked)
    assert client.get(f"{P}/me/medical-records/{rid}", headers=h2).status_code == 404
    assert client.patch(f"{P}/me/medical-records/{rid}", headers=h2, json={"title": "hack"}).status_code == 404
    assert client.delete(f"{P}/me/medical-records/{rid}", headers=h2).status_code == 404
    assert client.get(f"{P}/me/medical-records", headers=h2).get_json()["meta"]["total"] == 0
    # owner can update and delete
    assert client.patch(f"{P}/me/medical-records/{rid}", headers=h1, json={"title": "Penicillin allergy"}).status_code == 200
    assert client.delete(f"{P}/me/medical-records/{rid}", headers=h1).status_code == 200
    assert client.get(f"{P}/me/medical-records/{rid}", headers=h1).status_code == 404


def test_doctor_access_requires_relationship(client, new_patient, new_doctor, make_appointment):
    hp, pid = new_patient()
    client.post(f"{P}/me/medical-records", headers=hp, json={"record_type": "history", "title": "Asthma"})
    hd, did = new_doctor()
    # no appointment -> forbidden
    assert client.get(f"{P}/{pid}", headers=hd).status_code == 403
    assert client.get(f"{P}/{pid}/medical-records", headers=hd).status_code == 403
    # pending appointment is not enough
    make_appointment(pid, did, status="pending", hours=48)
    assert client.get(f"{P}/{pid}/medical-records", headers=hd).status_code == 403
    # accepted appointment grants access
    make_appointment(pid, did, status="accepted", hours=72)
    r = client.get(f"{P}/{pid}/medical-records", headers=hd)
    assert r.status_code == 200 and r.get_json()["meta"]["total"] == 1
    assert client.get(f"{P}/{pid}", headers=hd).status_code == 200
    # a different doctor still has no access
    hd2, _ = new_doctor()
    assert client.get(f"{P}/{pid}/medical-records", headers=hd2).status_code == 403


def test_unverified_doctor_cannot_access_even_with_appointment(client, new_patient, new_doctor, make_appointment):
    _, pid = new_patient()
    hd, did = new_doctor(verified=False)
    make_appointment(pid, did, status="accepted")
    assert client.get(f"{P}/{pid}", headers=hd).status_code == 403


def test_patient_cannot_view_other_patient_by_id(client, new_patient):
    h1, _ = new_patient()
    _, pid2 = new_patient()
    assert client.get(f"{P}/{pid2}", headers=h1).status_code == 403
    assert client.get(f"{P}/{pid2}/medical-records", headers=h1).status_code == 403


def test_admin_can_view_and_access_is_audited(client, new_patient, admin_headers, app):
    _, pid = new_patient()
    assert client.get(f"{P}/{pid}/medical-records", headers=admin_headers).status_code == 200
    assert client.get(f"{P}/does-not-exist", headers=admin_headers).status_code == 404
    from app.models import AuditLog
    assert AuditLog.query.filter_by(action="patient.records_viewed").count() == 1


def test_malformed_ids_never_cause_500(client, new_patient, new_doctor, admin_headers):
    hp, _ = new_patient()
    hd, _ = new_doctor()
    for url, h in [("/api/v1/patients/not-a-uuid", hd), ("/api/v1/patients/me/medical-records/xyz", hp),
                   ("/api/v1/doctors/123", hp), ("/api/v1/appointments/abc", hp),
                   ("/api/v1/doctors/abc/availability", hp), ("/api/v1/admin/doctors/zzz", admin_headers)]:
        assert client.get(url, headers=h).status_code == 404, url
    assert client.get("/api/v1/doctors?specialisation_id=bad", headers=hp).status_code == 422
    assert client.get("/api/v1/appointments?doctor_id=bad", headers=admin_headers).status_code == 422
