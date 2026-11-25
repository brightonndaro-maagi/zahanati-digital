from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import AuditLog, HedhiCycle, User
from tests.conftest import auth, past

HD = "/api/v1/hedhi"
FIX = date(2026, 3, 20)   # a fixed "today" used with ?on= so the maths is deterministic


def log(client, h, start, end=None, **kw):
    body = {"start_date": start.isoformat(), **({"end_date": end.isoformat()} if end else {}), **kw}
    return client.post(f"{HD}/cycles", headers=h, json=body)


def seed_regular(client, h):
    # three 28-day cycles: Dec 25, Jan 22, Feb 19; 5-day periods; today (on) is Mar 1
    for s in (date(2025, 12, 25), date(2026, 1, 22), date(2026, 2, 19)):
        assert log(client, h, s, s + timedelta(days=4)).status_code == 201


def insight(client, h, on):
    r = client.get(f"{HD}/insights?on={on}", headers=h)
    assert r.status_code == 200
    return r.get_json()["data"]


def test_entries_are_encrypted_at_rest(client, new_patient):
    h, _ = new_patient()
    r = log(client, h, date(2026, 2, 1), date(2026, 2, 5), flow="heavy", symptoms=["cramps"], notes="very private note")
    assert r.status_code == 201
    d = r.get_json()["data"]
    assert d["length_days"] == 5 and d["flow"] == "heavy" and d["symptoms"] == ["cramps"]
    raw = HedhiCycle.query.one().data
    for secret in ("2026", "02-01", "heavy", "cramps", "private", "start_date"):
        assert secret not in raw, secret
    got = client.get(f"{HD}/cycles/{d['id']}", headers=h).get_json()["data"]
    assert got["notes"] == "very private note" and got["start_date"] == "2026-02-01"


def test_validation(client, new_patient):
    h, _ = new_patient()
    today = date.today()
    assert log(client, h, today + timedelta(days=1)).status_code == 422
    assert log(client, h, date(2026, 2, 10), date(2026, 2, 9)).status_code == 422
    assert log(client, h, date(2026, 2, 1), date(2026, 2, 20)).status_code == 422                 # > 14 days
    assert log(client, h, date(2026, 2, 1), flow="torrential").status_code == 422
    assert log(client, h, date(2026, 2, 1), symptoms=["x"] * 11).status_code == 422
    assert log(client, h, date(2026, 2, 1), notes="n" * 501).status_code == 422
    assert client.post(f"{HD}/cycles", headers=h, json={}).status_code == 422
    assert client.post(f"{HD}/cycles", headers=h, json={"start_date": "not-a-date"}).status_code == 422
    assert HedhiCycle.query.count() == 0


def test_duplicates_overlaps_and_update(client, new_patient):
    h, _ = new_patient()
    a = log(client, h, date(2026, 2, 1), date(2026, 2, 5)).get_json()["data"]["id"]
    assert log(client, h, date(2026, 2, 1)).status_code == 409                    # same start
    assert log(client, h, date(2026, 2, 4), date(2026, 2, 8)).status_code == 409  # overlaps
    b = log(client, h, date(2026, 3, 1), date(2026, 3, 4)).get_json()["data"]["id"]
    assert client.patch(f"{HD}/cycles/{b}", headers=h, json={"start_date": "2026-02-03", "end_date": "2026-02-06"}).status_code == 409
    assert client.patch(f"{HD}/cycles/{b}", headers=h, json={"end_date": "2026-03-06", "flow": "light"}).get_json()["data"]["length_days"] == 6
    assert client.patch(f"{HD}/cycles/{b}", headers=h, json={"end_date": "2026-02-20"}).status_code == 422
    items = client.get(f"{HD}/cycles", headers=h).get_json()["data"]
    assert [x["id"] for x in items] == [b, a]                                     # newest first
    assert client.delete(f"{HD}/cycles/{a}", headers=h).status_code == 200
    assert client.delete(f"{HD}/cycles/{a}", headers=h).status_code == 404


def test_entries_are_private(client, new_patient, new_doctor, new_pharmacy, admin_headers):
    h1, _ = new_patient()
    h2, _ = new_patient()
    eid = log(client, h1, date(2026, 2, 1)).get_json()["data"]["id"]
    assert client.get(f"{HD}/cycles/{eid}", headers=h2).status_code == 404
    assert client.patch(f"{HD}/cycles/{eid}", headers=h2, json={"flow": "light"}).status_code == 404
    assert client.delete(f"{HD}/cycles/{eid}", headers=h2).status_code == 404
    assert client.get(f"{HD}/cycles", headers=h2).get_json()["data"] == []
    hd, _ = new_doctor()
    hph, _ = new_pharmacy()
    for h in (hd, hph, admin_headers):                                            # no one else, not even admins
        for url in (f"{HD}/cycles", f"{HD}/insights", f"{HD}/export"):
            assert client.get(url, headers=h).status_code == 403
    assert client.get(f"{HD}/cycles").status_code == 401
    assert client.get(f"{HD}/cycles/bad", headers=h1).status_code == 404


def test_regular_cycle_predictions(client, new_patient):
    h, _ = new_patient()
    seed_regular(client, h)
    d = insight(client, h, "2026-03-01")
    assert d["has_data"] and d["average_cycle_length"] == 28 and d["average_period_length"] == 5 and d["based_on_default_cycle"] is False
    assert d["last_period_start"] == "2026-02-19" and d["next_period_start"] == "2026-03-19" and d["next_period_end"] == "2026-03-23"
    assert d["ovulation_estimate"] == "2026-03-05" and d["fertile_window"] == {"start": "2026-02-28", "end": "2026-03-06"}
    assert d["days_until_next_period"] == 18 and d["day_of_cycle"] == 11 and d["late_by_days"] == 0 and d["cycles_logged"] == 3
    assert d["phase"] == "fertile_window" and d["see_doctor"]["recommended"] is False
    assert "makadirio" in d["disclaimer"]["sw"].lower() and "not a method of contraception" in d["disclaimer"]["en"]
    phases = {on: insight(client, h, on)["phase"] for on in ("2026-02-21", "2026-02-25", "2026-03-10", "2026-03-22")}
    assert phases == {"2026-02-21": "menstruation", "2026-02-25": "follicular", "2026-03-10": "luteal", "2026-03-22": "late"}
    assert insight(client, h, "2026-02-20")["last_period_start"] == "2026-02-19"
    assert insight(client, h, "2026-01-25")["last_period_start"] == "2026-01-22"   # entries after `on` are ignored


def test_single_entry_uses_defaults(client, new_patient):
    h, _ = new_patient()
    log(client, h, date(2026, 3, 1))
    d = insight(client, h, "2026-03-10")
    assert d["based_on_default_cycle"] is True and d["average_cycle_length"] == 28 and d["average_period_length"] == 5
    assert d["next_period_start"] == "2026-03-29"


def test_no_data_and_bad_date(client, new_patient):
    h, _ = new_patient()
    d = client.get(f"{HD}/insights", headers=h).get_json()["data"]
    assert d["has_data"] is False and d["see_doctor"]["recommended"] is False and "disclaimer" in d
    assert client.get(f"{HD}/insights?on=yesterday", headers=h).status_code == 422


def test_warning_signs_point_to_doctor_search(client, new_patient):
    h, _ = new_patient()
    for s in (date(2026, 1, 1), date(2026, 1, 15), date(2026, 1, 29)):           # 14-day cycles are ignored as missed logs
        log(client, h, s, s + timedelta(days=9))                                  # 10-day periods
    d = insight(client, h, "2026-02-05")
    assert d["see_doctor"]["recommended"] is True and "long_period" in d["see_doctor"]["reasons"]
    assert d["see_doctor"]["search_path"] == "/api/v1/doctors" and d["see_doctor"]["messages"]["sw"] and d["see_doctor"]["messages"]["en"]


def test_irregular_late_and_missing_periods(client, new_patient):
    h, _ = new_patient()
    for s in (date(2025, 10, 1), date(2025, 11, 5), date(2025, 12, 20)):          # 35 then 45 day gaps
        log(client, h, s, s + timedelta(days=4))
    assert "irregular_cycle" in insight(client, h, "2025-12-25")["see_doctor"]["reasons"]
    late = insight(client, h, "2026-02-20")                                        # next was due ~Feb 4
    assert late["phase"] == "late" and late["late_by_days"] > 7 and "period_late" in late["see_doctor"]["reasons"]
    gone = insight(client, h, "2026-04-15")                                        # > 90 days since the last start
    assert "no_period_3_months" in gone["see_doctor"]["reasons"] and "period_late" not in gone["see_doctor"]["reasons"]


def test_delete_everything_and_export(client, new_patient):
    h, _ = new_patient()
    other, _ = new_patient()
    seed_regular(client, h)
    log(client, other, date(2026, 2, 1))
    ex = client.get(f"{HD}/export", headers=h).get_json()["data"]["entries"]
    assert len(ex) == 3 and ex[0]["start_date"] == "2026-02-19"
    r = client.delete(HD, headers=h)
    assert r.status_code == 200 and r.get_json()["data"]["deleted"] == 3
    assert client.get(f"{HD}/cycles", headers=h).get_json()["data"] == []
    assert insight(client, h, "2026-03-01")["has_data"] is False
    assert len(client.get(f"{HD}/cycles", headers=other).get_json()["data"]) == 1           # nobody else is affected
    log_row = AuditLog.query.filter_by(action="hedhi.deleted_all").one()
    assert log_row.details == {"entries": 3}                                      # the audit trail holds a count, never content


def test_inactive_users_data_is_purged_after_two_years(client, new_patient, app):
    h1, _ = new_patient()
    h2, _ = new_patient()
    log(client, h1, date(2026, 2, 1))
    log(client, h2, date(2026, 2, 1))
    u1 = User.query.filter_by(phone=client.get("/api/v1/auth/me", headers=h1).get_json()["data"]["phone"]).one()
    u1.last_login_at = past(731 * 86400)
    db.session.commit()
    out = app.test_cli_runner().invoke(args=["purge-inactive-hedhi"])
    assert out.exit_code == 0 and "Purged 1 HEDHI entr(y/ies) of 1 inactive user(s)." in out.output, out.output
    assert client.get(f"{HD}/cycles", headers=h1).get_json()["data"] == []
    assert len(client.get(f"{HD}/cycles", headers=h2).get_json()["data"]) == 1


def test_missing_encryption_key_refuses_to_store(client, new_patient, app):
    h, _ = new_patient()
    app.config["FILE_ENCRYPTION_KEYS"] = []
    assert log(client, h, date(2026, 2, 1)).status_code == 503
    assert HedhiCycle.query.count() == 0


def test_limit_of_entries(client, new_patient, app):
    h, _ = new_patient()
    app.config["HEDHI_MAX_ENTRIES"] = 2
    assert log(client, h, date(2026, 1, 1)).status_code == 201
    assert log(client, h, date(2026, 2, 1)).status_code == 201
    assert log(client, h, date(2026, 3, 1)).status_code == 422
