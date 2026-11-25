import pytest

from app.models import AuditLog, FirstAidGuide

FA, HE, AFA, AHE = "/api/v1/first-aid", "/api/v1/health-education", "/api/v1/admin/first-aid", "/api/v1/admin/health-education"
GUIDE = {"title": "Kuvuja damu", "summary": "Hatua za kwanza kwa mtu anayevuja damu", "language": "sw", "keywords": "damu, jeraha, bleeding",
         "emergency_warning": "Piga 112 ikiwa damu haiachi baada ya dakika 10.",
         "steps_to_do": ["Bonyeza jeraha kwa kitambaa safi", "Inua sehemu iliyojeruhiwa"],
         "steps_to_avoid": ["Usiondoe kitu kilichobaki kwenye jeraha"]}
EDU = {"title": "Mzunguko wa hedhi", "body": "Mzunguko wa kawaida ni kati ya siku 21 hadi 35.", "stage": 2, "language": "sw"}


def publish(client, h, url, item_id, reviewer="Dr. Amina Salim"):
    return client.post(f"{url}/{item_id}/publish", headers=h, json={"reviewed_by_name": reviewer})


def test_first_aid_draft_is_invisible_until_reviewed(client, admin_headers):
    r = client.post(AFA, headers=admin_headers, json=GUIDE)
    assert r.status_code == 201
    d = r.get_json()["data"]
    assert d["status"] == "draft" and d["edition"] == 0 and d["published_version"] is None
    assert client.get(FA).get_json()["meta"]["total"] == 0                       # anonymous list: nothing yet
    assert client.get(f"{FA}/{d['id']}").status_code == 404
    assert client.post(f"{AFA}/{d['id']}/publish", headers=admin_headers, json={}).status_code == 422     # reviewer is mandatory
    assert client.post(f"{AFA}/{d['id']}/publish", headers=admin_headers, json={"reviewed_by_name": "ab"}).status_code == 422
    assert publish(client, admin_headers, AFA, d["id"]).status_code == 200
    pub = client.get(f"{FA}/{d['id']}").get_json()["data"]                       # public: no login needed
    assert pub["title"] == "Kuvuja damu" and pub["edition"] == 1 and pub["reviewed_by"] == "Dr. Amina Salim" and pub["reviewed_at"]
    assert pub["steps_to_do"][0].startswith("Bonyeza") and pub["steps_to_avoid"] and "112" in pub["emergency_warning"]
    assert "112" in pub["emergency_notice"]["sw"] and "112" in pub["emergency_notice"]["en"]
    assert client.get(FA).get_json()["data"][0]["reviewed_by"] == "Dr. Amina Salim"
    assert AuditLog.query.filter_by(action="first-aid.published").count() == 1


def test_editing_requires_new_review_and_old_text_stays_live(client, admin_headers):
    gid = client.post(AFA, headers=admin_headers, json=GUIDE).get_json()["data"]["id"]
    publish(client, admin_headers, AFA, gid)
    r = client.patch(f"{AFA}/{gid}", headers=admin_headers, json={"title": "Kuvuja damu (imeboreshwa)", "steps_to_avoid": ["Usitumie dawa za kienyeji"]})
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["status"] == "draft" and d["has_unpublished_changes"] is True and d["title"].endswith("(imeboreshwa)")
    assert client.get(f"{FA}/{gid}").get_json()["data"]["title"] == "Kuvuja damu"            # the approved version is still shown
    assert client.get(f"{FA}/{gid}").get_json()["data"]["steps_to_avoid"] == GUIDE["steps_to_avoid"]
    assert publish(client, admin_headers, AFA, gid, "Dr. John Mwakyusa").status_code == 200
    pub = client.get(f"{FA}/{gid}").get_json()["data"]
    assert pub["title"].endswith("(imeboreshwa)") and pub["edition"] == 2 and pub["reviewed_by"] == "Dr. John Mwakyusa"
    a = client.get(f"{AFA}/{gid}", headers=admin_headers).get_json()["data"]
    assert a["has_unpublished_changes"] is False and a["published_version"]["edition"] == 2


def test_unpublish_and_delete(client, admin_headers):
    gid = client.post(AFA, headers=admin_headers, json=GUIDE).get_json()["data"]["id"]
    publish(client, admin_headers, AFA, gid)
    assert client.delete(f"{AFA}/{gid}", headers=admin_headers).status_code == 409           # unpublish first
    assert client.post(f"{AFA}/{gid}/unpublish", headers=admin_headers).status_code == 200
    assert client.get(f"{FA}/{gid}").status_code == 404 and client.get(FA).get_json()["meta"]["total"] == 0
    assert client.delete(f"{AFA}/{gid}", headers=admin_headers).status_code == 200
    assert FirstAidGuide.query.count() == 0
    assert client.get(f"{AFA}/{gid}", headers=admin_headers).status_code == 404


def test_first_aid_search(client, admin_headers):
    ids = []
    for title, kw, lang in (("Kuvuja damu", "damu jeraha", "sw"), ("Burns", "moto kuungua burn", "en"), ("Kuungua na moto", "moto", "sw")):
        gid = client.post(AFA, headers=admin_headers, json={**GUIDE, "title": title, "keywords": kw, "language": lang, "summary": None}).get_json()["data"]["id"]
        publish(client, admin_headers, AFA, gid)
        ids.append(gid)
    client.post(AFA, headers=admin_headers, json={**GUIDE, "title": "Haijachapishwa moto"})          # draft with the same word
    assert {g["title"] for g in client.get(f"{FA}?q=moto").get_json()["data"]} == {"Burns", "Kuungua na moto"}
    assert [g["title"] for g in client.get(f"{FA}?q=DAMU").get_json()["data"]] == ["Kuvuja damu"]
    assert [g["title"] for g in client.get(f"{FA}?language=en").get_json()["data"]] == ["Burns"]
    assert client.get(f"{FA}?q=m").status_code == 422 and client.get(f"{FA}?language=fr").status_code == 422
    assert client.get(f"{FA}?q=zzz").get_json()["data"] == []
    assert client.get(f"{FA}?per_page=2&page=2").get_json()["meta"] == {"page": 2, "per_page": 2, "total": 3, "pages": 2}
    assert client.get(f"{FA}/not-a-uuid").status_code == 404


def test_first_aid_validation(client, admin_headers):
    for missing in ("title", "emergency_warning", "steps_to_do", "steps_to_avoid"):
        body = {k: v for k, v in GUIDE.items() if k != missing}
        assert client.post(AFA, headers=admin_headers, json=body).status_code == 422, missing
    assert client.post(AFA, headers=admin_headers, json={**GUIDE, "steps_to_do": []}).status_code == 422
    assert client.post(AFA, headers=admin_headers, json={**GUIDE, "language": "fr"}).status_code == 422
    assert client.post(AFA, headers=admin_headers, json={**GUIDE, "steps_to_do": ["x" * 501]}).status_code == 422
    assert client.get(f"{AFA}?status=bogus", headers=admin_headers).status_code == 422


def test_only_admins_manage_content(client, new_patient, new_doctor, admin_headers):
    gid = client.post(AFA, headers=admin_headers, json=GUIDE).get_json()["data"]["id"]
    hp, _ = new_patient()
    hd, _ = new_doctor()
    for h in (hp, hd):
        assert client.post(AFA, headers=h, json=GUIDE).status_code == 403
        assert client.get(AFA, headers=h).status_code == 403
        assert client.patch(f"{AFA}/{gid}", headers=h, json={"title": "Hacked"}).status_code == 403
        assert publish(client, h, AFA, gid).status_code == 403
        assert client.delete(f"{AFA}/{gid}", headers=h).status_code == 403
    assert client.post(AFA, json=GUIDE).status_code == 401
    assert client.get(AHE, headers=hp).status_code == 403


def test_health_education_needs_login_and_supports_stages(client, new_patient, admin_headers):
    ids = {}
    for stage, title in ((2, "Mzunguko wa hedhi"), (4, "Dalili za ujauzito"), (8, "Chanjo za mtoto")):
        ids[stage] = client.post(AHE, headers=admin_headers, json={**EDU, "title": title, "stage": stage}).get_json()["data"]["id"]
        publish(client, admin_headers, AHE, ids[stage])
    client.post(AHE, headers=admin_headers, json={**EDU, "title": "Draft only", "stage": 3})
    assert client.get(HE).status_code == 401                                   # education requires login (first aid does not)
    hp, _ = new_patient()
    r = client.get(HE, headers=hp).get_json()
    assert r["meta"]["total"] == 3 and r["data"][0]["stage_name"]["sw"] and "body" not in r["data"][0]
    assert [x["title"] for x in client.get(f"{HE}?stage=4", headers=hp).get_json()["data"]] == ["Dalili za ujauzito"]
    assert client.get(f"{HE}?stage=9", headers=hp).status_code == 422 and client.get(f"{HE}?stage=x", headers=hp).status_code == 422
    full = client.get(f"{HE}/{ids[2]}", headers=hp).get_json()["data"]
    assert full["body"].startswith("Mzunguko") and full["reviewed_by"] == "Dr. Amina Salim" and full["stage"] == 2
    st = client.get(f"{HE}/stages", headers=hp).get_json()["data"]
    assert len(st) == 8 and st[0]["stage"] == 1 and st[7]["en"] == "Child health"
    assert client.post(AHE, headers=admin_headers, json={**EDU, "stage": 0}).status_code == 422
    assert client.post(AHE, headers=admin_headers, json={**EDU, "stage": 9}).status_code == 422
    assert client.post(AHE, headers=admin_headers, json={**EDU, "stage": 2.5}).status_code == 422
    assert client.post(AHE, headers=admin_headers, json={**EDU, "body": "short"}).status_code == 422
    assert client.get(f"{AHE}?stage=3", headers=admin_headers).get_json()["data"][0]["title"] == "Draft only"
