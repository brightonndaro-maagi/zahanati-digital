from app.models import AuditLog

D = "/api/v1/doctors"
A = "/api/v1/admin"


def _spec(client, admin_headers, name="Cardiology"):
    r = client.post("/api/v1/specialisations", headers=admin_headers, json={"name": name})
    assert r.status_code == 201
    return r.get_json()["data"]["id"]


def test_new_doctor_is_pending_and_hidden(client, new_patient, new_doctor):
    hp, _ = new_patient()
    _, did = new_doctor(verified=False)
    assert client.get(D, headers=hp).get_json()["meta"]["total"] == 0
    assert client.get(f"{D}/{did}", headers=hp).status_code == 404


def test_admin_verify_and_search(client, new_patient, new_doctor, admin_headers):
    hp, _ = new_patient()
    sid = _spec(client, admin_headers)
    hd, did = new_doctor(first_name="Amina", last_name="Kweka")
    client.put(f"{D}/me/specialisations", headers=hd, json={"specialisation_ids": [sid]})
    client.patch(f"{D}/me", headers=hd, json={"practice_location": "Mwanza", "years_of_experience": 8})
    new_doctor(first_name="Baraka", last_name="Lema")  # verified, no specialisation
    r = client.get(D, headers=hp)
    assert r.get_json()["meta"]["total"] == 2
    assert client.get(f"{D}?specialisation_id={sid}", headers=hp).get_json()["meta"]["total"] == 1
    assert client.get(f"{D}?q=kwe", headers=hp).get_json()["meta"]["total"] == 1
    assert client.get(f"{D}?location=mwan", headers=hp).get_json()["meta"]["total"] == 1
    assert client.get(f"{D}?min_experience=5", headers=hp).get_json()["meta"]["total"] == 1
    # public view leaks nothing sensitive
    pub = client.get(f"{D}/{did}", headers=hp).get_json()["data"]
    for k in ("email", "phone", "credentials", "verification_status"):
        assert k not in pub
    assert pub["specialisations"][0]["name"] == "Cardiology"


def test_only_admin_can_verify_or_reject(client, new_patient, new_doctor):
    hp, _ = new_patient()
    hd, did = new_doctor(verified=False)
    for h in (hp, hd):
        assert client.post(f"{A}/doctors/{did}/verify", headers=h).status_code == 403
        assert client.post(f"{A}/doctors/{did}/reject", headers=h, json={"reason": "no"}).status_code == 403
    assert client.post(f"{A}/doctors/{did}/verify").status_code == 401


def test_reject_requires_reason_and_hides_doctor(client, new_doctor, new_patient, admin_headers):
    hd, did = new_doctor(verified=False)
    assert client.post(f"{A}/doctors/{did}/reject", headers=admin_headers, json={}).status_code == 422
    r = client.post(f"{A}/doctors/{did}/reject", headers=admin_headers, json={"reason": "Invalid licence"})
    assert r.status_code == 200 and r.get_json()["data"]["verification_status"] == "rejected"
    me = client.get(f"{D}/me", headers=hd).get_json()["data"]
    assert me["verification_status"] == "rejected" and me["rejection_reason"] == "Invalid licence"
    hp, _ = new_patient()
    assert client.get(D, headers=hp).get_json()["meta"]["total"] == 0


def test_admin_pending_list_and_audit(client, new_doctor, admin_headers):
    new_doctor(verified=False)
    _, did = new_doctor(verified=True)
    r = client.get(f"{A}/doctors?status=pending", headers=admin_headers)
    assert r.get_json()["meta"]["total"] == 1
    assert client.get(f"{A}/doctors?status=weird", headers=admin_headers).status_code == 422
    assert AuditLog.query.filter_by(action="doctor.verified", entity_id=did).count() == 1


def test_doctor_credentials_and_reverification(client, new_doctor, admin_headers):
    hd, did = new_doctor()
    assert client.get(f"{D}/me", headers=hd).get_json()["data"]["verification_status"] == "verified"
    r = client.post(f"{D}/me/credentials", headers=hd, json={
        "credential_type": "qualification", "title": "MMed Surgery", "institution": "MUHAS"})
    assert r.status_code == 201
    # non-licence credential keeps verification
    assert client.get(f"{D}/me", headers=hd).get_json()["data"]["verification_status"] == "verified"
    assert client.post(f"{D}/me/credentials", headers=hd, json={"credential_type": "license", "title": "Licence"}).status_code == 422
    assert client.post(f"{D}/me/credentials", headers=hd, json={
        "credential_type": "certificate", "title": "ACLS", "document_url": "http://insecure.example/x.pdf"}).status_code == 422
    # editing the licence sends doctor back to review
    creds = client.get(f"{D}/me/credentials", headers=hd).get_json()["data"]
    lic = next(c for c in creds if c["credential_type"] == "license")
    assert client.patch(f"{D}/me/credentials/{lic['id']}", headers=hd, json={"license_number": "MCT-9999"}).status_code == 200
    assert client.get(f"{D}/me", headers=hd).get_json()["data"]["verification_status"] == "pending"


def test_doctors_cannot_touch_each_others_credentials(client, new_doctor):
    h1, _ = new_doctor()
    h2, _ = new_doctor()
    cid = client.get(f"{D}/me/credentials", headers=h1).get_json()["data"][0]["id"]
    assert client.patch(f"{D}/me/credentials/{cid}", headers=h2, json={"title": "Hacked"}).status_code == 404
    assert client.delete(f"{D}/me/credentials/{cid}", headers=h2).status_code == 404


def test_verify_requires_licence(client, new_doctor, admin_headers):
    hd, did = new_doctor(verified=False)
    creds = client.get(f"{D}/me/credentials", headers=hd).get_json()["data"]
    lic = next(c for c in creds if c["credential_type"] == "license")
    client.delete(f"{D}/me/credentials/{lic['id']}", headers=hd)
    assert client.post(f"{A}/doctors/{did}/verify", headers=admin_headers).status_code == 409


def test_specialisation_admin_crud(client, new_patient, new_doctor, admin_headers):
    hp, _ = new_patient()
    assert client.post("/api/v1/specialisations", headers=hp, json={"name": "Hack"}).status_code == 403
    sid = _spec(client, admin_headers, "Dermatology")
    assert client.post("/api/v1/specialisations", headers=admin_headers, json={"name": "dermatology"}).status_code == 409
    assert client.patch(f"/api/v1/specialisations/{sid}", headers=admin_headers, json={"description": "Skin"}).status_code == 200
    assert len(client.get("/api/v1/specialisations", headers=hp).get_json()["data"]) == 1
    hd, _ = new_doctor()
    client.put(f"{D}/me/specialisations", headers=hd, json={"specialisation_ids": [sid]})
    assert client.delete(f"/api/v1/specialisations/{sid}", headers=admin_headers).status_code == 409
    client.put(f"{D}/me/specialisations", headers=hd, json={"specialisation_ids": []})
    assert client.delete(f"/api/v1/specialisations/{sid}", headers=admin_headers).status_code == 200
    bad = "00000000-0000-0000-0000-000000000000"
    assert client.put(f"{D}/me/specialisations", headers=hd, json={"specialisation_ids": [bad]}).status_code == 422


def test_doctor_profile_update(client, new_doctor):
    hd, _ = new_doctor()
    r = client.patch(f"{D}/me", headers=hd, json={"bio": "Cardiologist", "years_of_experience": -1})
    assert r.status_code == 422
    r = client.patch(f"{D}/me", headers=hd, json={"bio": "Cardiologist", "years_of_experience": 10})
    assert r.status_code == 200 and r.get_json()["data"]["bio"] == "Cardiologist"
