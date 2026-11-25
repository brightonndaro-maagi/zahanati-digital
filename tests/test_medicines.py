import pytest

from app.common.geo import haversine_km
from app.extensions import db
from app.models import AuditLog, Medicine, PharmacyProfile
from tests.conftest import auth

PH, MED, AD = "/api/v1/pharmacies", "/api/v1/medicines", "/api/v1/admin"
# Dar es Salaam reference points
USER_LAT, USER_LON = -6.8184, 39.2766        # Kariakoo
NEAR = {"latitude": -6.8200, "longitude": 39.2780}   # ~0.2 km
MID = {"latitude": -6.7715, "longitude": 39.2216}    # Mlimani City ~7 km
FAR = {"latitude": -6.9, "longitude": 39.5}           # ~26 km


def add(client, h, name="Paracetamol 500mg", price=1500, stock=100, **kw):
    r = client.post(f"{PH}/me/medicines", headers=h, json={"name": name, "price_tzs": price, "stock_quantity": stock, **kw})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]["id"]


def search(client, h, q, **params):
    qs = "&".join(f"{k}={v}" for k, v in {"q": q, **params}.items())
    r = client.get(f"{MED}?{qs}", headers=h)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def test_haversine():
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.19, abs=0.1)
    assert haversine_km(-6.8, 39.2, -6.8, 39.2) == 0


# ---------------- pharmacy catalogue ----------------
def test_add_medicine_rules(client, new_pharmacy, new_patient, new_doctor):
    h, _ = new_pharmacy()
    mid = add(client, h, "  Amoxicillin   500mg ", 3500, 50, generic_name="Amoxicillin", requires_prescription=True)
    d = client.get(f"{PH}/me/medicines/{mid}", headers=h).get_json()["data"]
    assert d["name"] == "Amoxicillin 500mg" and d["requires_prescription"] is True and d["stock_quantity"] == 50 and d["available"]
    body = {"name": "Panadol", "price_tzs": 500, "stock_quantity": 5}
    for bad in ({"price_tzs": 0}, {"price_tzs": -100}, {"price_tzs": 500.5}, {"price_tzs": "500"}, {"price_tzs": 10 ** 9},
                {"stock_quantity": -1}, {"stock_quantity": 1.5}, {"name": "x"}):
        assert client.post(f"{PH}/me/medicines", headers=h, json={**body, **bad}).status_code == 422, bad
    assert client.post(f"{PH}/me/medicines", headers=h, json={"name": "Panadol"}).status_code == 422
    assert client.post(f"{PH}/me/medicines", headers=h, json={**body, "name": "amoxicillin 500MG"}).status_code == 409
    hp, _ = new_patient()
    hd, _ = new_doctor()
    for other in (hp, hd):
        assert client.post(f"{PH}/me/medicines", headers=other, json=body).status_code == 403
        assert client.get(f"{PH}/me/medicines", headers=other).status_code == 403
    assert client.post(f"{PH}/me/medicines", json=body).status_code == 401
    assert AuditLog.query.filter_by(action="medicine.created", entity_id=mid).count() == 1


def test_unapproved_pharmacy_cannot_sell(client, new_pharmacy):
    h, _ = new_pharmacy(approved=False)
    r = client.post(f"{PH}/me/medicines", headers=h, json={"name": "Panadol", "price_tzs": 500, "stock_quantity": 5})
    assert r.status_code == 403
    assert client.get(f"{PH}/me/medicines", headers=h).get_json()["meta"]["total"] == 0


def test_update_remove_restore_and_isolation(client, new_pharmacy):
    h1, _ = new_pharmacy()
    h2, _ = new_pharmacy()
    mid = add(client, h1)
    assert client.patch(f"{PH}/me/medicines/{mid}", headers=h2, json={"price_tzs": 1}).status_code == 404
    assert client.delete(f"{PH}/me/medicines/{mid}", headers=h2).status_code == 404
    assert client.get(f"{PH}/me/medicines/{mid}", headers=h2).status_code == 404
    r = client.patch(f"{PH}/me/medicines/{mid}", headers=h1, json={"price_tzs": 1800})
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["price_tzs"] == 1800 and d["stock_quantity"] == 100 and d["requires_prescription"] is False
    assert client.put(f"{PH}/me/medicines/{mid}", headers=h1, json={"price_tzs": 1900}).status_code == 422   # PUT needs everything
    assert client.patch(f"{PH}/me/medicines/{mid}", headers=h1, json={"price_tzs": -5}).status_code == 422
    log = AuditLog.query.filter_by(action="medicine.updated", entity_id=mid).one()
    assert log.details["before"]["price_tzs"] == 1500 and log.details["after"]["price_tzs"] == 1800
    # removal is soft; the name stays reserved; restoring works
    assert client.delete(f"{PH}/me/medicines/{mid}", headers=h1).status_code == 200
    assert Medicine.query.count() == 1
    assert client.get(f"{PH}/me/medicines?is_active=false", headers=h1).get_json()["meta"]["total"] == 1
    assert client.get(f"{PH}/me/medicines?is_active=true", headers=h1).get_json()["meta"]["total"] == 0
    dup = client.post(f"{PH}/me/medicines", headers=h1, json={"name": "Paracetamol 500mg", "price_tzs": 1, "stock_quantity": 1})
    assert dup.status_code == 409 and "Restore" in dup.get_json()["message"]
    assert client.patch(f"{PH}/me/medicines/{mid}", headers=h1, json={"is_active": True}).get_json()["data"]["available"]
    # two pharmacies may sell the same medicine name
    add(client, h2)
    assert client.get(f"{PH}/me/medicines/not-a-uuid", headers=h1).status_code == 404


def test_own_list_filters(client, new_pharmacy):
    h, _ = new_pharmacy()
    add(client, h, "Panadol", 500, 10)
    add(client, h, "Panadol Extra", 700, 0)
    add(client, h, "Amoxil", 900, 5)
    assert client.get(f"{PH}/me/medicines?q=panadol", headers=h).get_json()["meta"]["total"] == 2
    assert client.get(f"{PH}/me/medicines?available=false", headers=h).get_json()["data"][0]["name"] == "Panadol Extra"
    assert client.get(f"{PH}/me/medicines?available=true", headers=h).get_json()["meta"]["total"] == 2
    assert client.get(f"{PH}/me/medicines?per_page=2&page=2", headers=h).get_json()["data"][0]["name"] == "Panadol Extra"


# ---------------- customer search ----------------
def test_search_requires_two_chars_and_login(client, new_patient, new_pharmacy):
    hp, _ = new_patient()
    ph, _ = new_pharmacy()
    assert client.get(MED, headers=hp).status_code == 422
    assert client.get(f"{MED}?q=a", headers=hp).status_code == 422
    assert client.get(f"{MED}?q=%20a%20", headers=hp).status_code == 422
    assert client.get(f"{MED}?q=pa").status_code == 401
    assert client.get(f"{MED}?q=pa", headers=ph).status_code == 403
    assert client.get(f"{MED}?q=pa&lat=1", headers=hp).status_code == 422
    assert client.get(f"{MED}?q=pa&lat=abc&lon=1", headers=hp).status_code == 422
    assert client.get(f"{MED}?q=pa&lat=95&lon=1", headers=hp).status_code == 422


def test_search_matches_name_and_generic_case_insensitive(client, new_patient, new_pharmacy):
    hp, _ = new_patient()
    h, _ = new_pharmacy()
    add(client, h, "Panadol Extra", generic_name="Paracetamol + Caffeine")
    add(client, h, "Amoxil 250mg", generic_name="Amoxicillin")
    assert [m["name"] for m in search(client, hp, "PANA")] == ["Panadol Extra"]
    assert [m["name"] for m in search(client, hp, "amoxicillin")] == ["Amoxil 250mg"]
    assert [m["name"] for m in search(client, hp, "caffeine")] == ["Panadol Extra"]
    assert search(client, hp, "zzz") == []
    assert search(client, hp, "%%") == [] and search(client, hp, "__") == []     # wildcards are literal


def test_search_result_shape_hides_stock_quantity(client, new_patient, new_pharmacy):
    hp, _ = new_patient()
    h, pid = new_pharmacy(**NEAR)
    add(client, h, "Panadol", 500, 7, requires_prescription=True)
    r = search(client, hp, "pana", lat=USER_LAT, lon=USER_LON)[0]
    assert r["price_tzs"] == 500 and r["available"] is True and r["requires_prescription"] is True
    assert "stock_quantity" not in r and "is_active" not in r
    assert r["pharmacy"]["id"] == pid and r["pharmacy"]["name"] == "Afya Pharmacy"
    assert r["distance_km"] == pytest.approx(0.2, abs=0.1)
    assert search(client, hp, "pana")[0]["distance_km"] is None


def test_search_order_available_then_distance_then_price(client, new_patient, new_pharmacy):
    hp, _ = new_patient()
    far, _ = new_pharmacy(name="Far", **FAR)
    mid_cheap, _ = new_pharmacy(name="Mid cheap", **MID)
    mid_dear, _ = new_pharmacy(name="Mid dear", **MID)
    near_out, _ = new_pharmacy(name="Near but finished", **NEAR)
    add(client, far, "Panadol", 100, 10)            # cheapest of all, but far
    add(client, mid_dear, "Panadol", 900, 10)
    add(client, mid_cheap, "Panadol", 400, 10)
    add(client, near_out, "Panadol", 300, 0)        # nearest, but out of stock
    names = [r["pharmacy"]["name"] for r in search(client, hp, "panadol", lat=USER_LAT, lon=USER_LON)]
    assert names == ["Mid cheap", "Mid dear", "Far", "Near but finished"]
    res = search(client, hp, "panadol", lat=USER_LAT, lon=USER_LON)
    assert [r["available"] for r in res] == [True, True, True, False]
    # without GPS: available first, then cheapest
    names = [r["pharmacy"]["name"] for r in search(client, hp, "panadol")]
    assert names == ["Far", "Mid cheap", "Mid dear", "Near but finished"]
    # only_available hides the finished one; pharmacy filter narrows
    assert len(search(client, hp, "panadol", only_available="true")) == 3
    pid = res[0]["pharmacy"]["id"]
    assert len(search(client, hp, "panadol", pharmacy_id=pid)) == 1
    assert client.get(f"{MED}?q=panadol&pharmacy_id=bad", headers=hp).status_code == 422


def test_hidden_medicines_never_appear(client, new_patient, new_pharmacy, admin_headers):
    hp, _ = new_patient()
    approved, _ = new_pharmacy()
    pending, _ = new_pharmacy(approved=False)
    rejected, rid = new_pharmacy()
    deactivated, did = new_pharmacy()
    add(client, approved, "Visible Panadol")
    removed = add(client, approved, "Removed Panadol")
    client.delete(f"{PH}/me/medicines/{removed}", headers=approved)
    add(client, rejected, "Rejected Panadol")
    add(client, deactivated, "Deactivated Panadol")
    client.post(f"{AD}/pharmacies/{rid}/reject", headers=admin_headers, json={"reason": "Licence expired"})
    db.session.get(PharmacyProfile, did).user.is_active = False
    db.session.commit()
    assert [m["name"] for m in search(client, hp, "panadol")] == ["Visible Panadol"]
    # an approved pharmacy that adds a medicine for a pending pharmacy is impossible (403), so pending has nothing
    assert client.post(f"{PH}/me/medicines", headers=pending, json={"name": "P", "price_tzs": 1, "stock_quantity": 1}).status_code == 403


def test_changes_are_visible_immediately(client, new_patient, new_pharmacy):
    hp, _ = new_patient()
    h, _ = new_pharmacy()
    mid = add(client, h, "Panadol", 500, 3)
    assert search(client, hp, "pana")[0]["price_tzs"] == 500
    client.patch(f"{PH}/me/medicines/{mid}", headers=h, json={"price_tzs": 650})
    assert search(client, hp, "pana")[0]["price_tzs"] == 650
    client.patch(f"{PH}/me/medicines/{mid}", headers=h, json={"stock_quantity": 0})
    assert search(client, hp, "pana")[0]["available"] is False       # still listed, cannot be ordered
    assert search(client, hp, "pana", only_available="true") == []


def test_search_pagination(client, new_patient, new_pharmacy):
    hp, _ = new_patient()
    h, _ = new_pharmacy()
    for i in range(5):
        add(client, h, f"Panadol {i}", 100 + i)
    r = client.get(f"{MED}?q=panadol&per_page=2&page=3", headers=hp).get_json()
    assert r["meta"] == {"page": 3, "per_page": 2, "total": 5, "pages": 3} and len(r["data"]) == 1


def test_medicine_detail_visibility(client, new_patient, new_pharmacy):
    hp, _ = new_patient()
    h, _ = new_pharmacy(**NEAR)
    mid = add(client, h, "Panadol")
    r = client.get(f"{MED}/{mid}?lat={USER_LAT}&lon={USER_LON}", headers=hp)
    assert r.status_code == 200 and r.get_json()["data"]["distance_km"] is not None
    client.delete(f"{PH}/me/medicines/{mid}", headers=h)
    assert client.get(f"{MED}/{mid}", headers=hp).status_code == 404
    assert client.get(f"{MED}/not-a-uuid", headers=hp).status_code == 404


# ---------------- customer-facing pharmacies ----------------
def test_pharmacy_list_and_detail_for_customers(client, new_patient, new_pharmacy):
    hp, _ = new_patient()
    _, far_id = new_pharmacy(name="Far Pharmacy", **FAR)
    _, near_id = new_pharmacy(name="Near Pharmacy", **NEAR)
    _, pending_id = new_pharmacy(name="Pending Pharmacy", approved=False)
    r = client.get(f"{PH}?lat={USER_LAT}&lon={USER_LON}", headers=hp).get_json()
    assert [p["name"] for p in r["data"]] == ["Near Pharmacy", "Far Pharmacy"] and r["meta"]["total"] == 2
    assert "license_number" not in r["data"][0] and "phone" not in r["data"][0]
    assert [p["name"] for p in client.get(f"{PH}?q=far", headers=hp).get_json()["data"]] == ["Far Pharmacy"]
    assert client.get(f"{PH}/{near_id}", headers=hp).status_code == 200
    assert client.get(f"{PH}/{pending_id}", headers=hp).status_code == 404       # not approved: invisible
    assert client.get(f"{PH}/{pending_id}/medicines", headers=hp).status_code == 404


def test_pharmacy_catalogue_for_customers(client, new_patient, new_pharmacy):
    hp, _ = new_patient()
    h, pid = new_pharmacy()
    add(client, h, "Panadol", 500, 0)
    add(client, h, "Amoxil", 900, 5)
    gone = add(client, h, "Gone", 100, 5)
    client.delete(f"{PH}/me/medicines/{gone}", headers=h)
    r = client.get(f"{PH}/{pid}/medicines", headers=hp).get_json()
    assert [m["name"] for m in r["data"]] == ["Amoxil", "Panadol"] and r["meta"]["total"] == 2    # available first
    assert "stock_quantity" not in r["data"][0]
    assert [m["name"] for m in client.get(f"{PH}/{pid}/medicines?q=pana", headers=hp).get_json()["data"]] == ["Panadol"]
    assert client.get(f"{PH}/{pid}/medicines").status_code == 401
