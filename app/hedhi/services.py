"""HEDHI menstrual tracker. Every entry is encrypted (Fernet/AES) before it is stored; predictions are computed
on the server from the decrypted entries of the logged-in customer only, and nothing is logged about their content."""
import json
from datetime import date, timedelta
from statistics import mean

from flask import current_app

from app.common import crypto
from app.common.audit import log_action
from app.common.errors import APIError
from app.common.timeutils import to_local, utcnow
from app.extensions import db
from app.models import HedhiCycle, User

DEFAULT_CYCLE, DEFAULT_PERIOD, LUTEAL_DAYS = 28, 5, 14
DISCLAIMER = {
    "sw": "Haya ni makadirio tu. Si uhakika na si njia ya kuzuia mimba. Kwa ushauri wa afya muone daktari.",
    "en": "These are estimates only. They are not certain and are not a method of contraception. See a doctor for health advice.",
}


def _pack(d):
    return crypto.encrypt(json.dumps({**d, "start_date": d["start_date"].isoformat(),
                                      "end_date": d["end_date"].isoformat() if d.get("end_date") else None}).encode()).decode()


def _unpack(row):
    d = json.loads(crypto.decrypt(row.data.encode()))
    d["start_date"] = date.fromisoformat(d["start_date"])
    d["end_date"] = date.fromisoformat(d["end_date"]) if d.get("end_date") else None
    return d


def entry_dict(row, d):
    return {"id": row.id, "start_date": d["start_date"].isoformat(), "end_date": d["end_date"].isoformat() if d["end_date"] else None,
            "flow": d.get("flow"), "symptoms": d.get("symptoms", []), "notes": d.get("notes"),
            "length_days": (d["end_date"] - d["start_date"]).days + 1 if d["end_date"] else None}


def all_entries(user):
    rows = HedhiCycle.query.filter_by(user_id=user.id).all()
    items = [(r, _unpack(r)) for r in rows]
    items.sort(key=lambda x: x[1]["start_date"], reverse=True)
    return items


def _check_overlap(items, d, exclude_id=None):
    s, e = d["start_date"], d["end_date"] or d["start_date"]
    for row, x in items:
        if row.id == exclude_id:
            continue
        if x["start_date"] == d["start_date"]:
            raise APIError("You already logged a period starting on this date", 409)
        xs, xe = x["start_date"], x["end_date"] or x["start_date"]
        if s <= xe and xs <= e:
            raise APIError("These dates overlap another logged period", 409)


def add(user, d):
    items = all_entries(user)
    if len(items) >= current_app.config["HEDHI_MAX_ENTRIES"]:
        raise APIError("You have reached the maximum number of logged periods. Delete old entries first.", 422)
    _check_overlap(items, d)
    now = utcnow()
    row = HedhiCycle(user_id=user.id, data=_pack(d), created_at=now, updated_at=now)
    db.session.add(row)
    db.session.commit()
    return row, d


def get_row(user, entry_id):
    row = HedhiCycle.query.filter_by(id=entry_id, user_id=user.id).first()
    if not row:
        raise APIError("Entry not found", 404)
    return row


def update(user, entry_id, changes):
    row = get_row(user, entry_id)
    d = {**_unpack(row), **changes}
    s, e = d["start_date"], d["end_date"]
    if e and (e < s or (e - s).days + 1 > 14):
        raise APIError("Check the dates: the end cannot be before the start and a period lasts at most 14 days", 422)
    _check_overlap(all_entries(user), d, exclude_id=row.id)
    row.data, row.updated_at = _pack(d), utcnow()
    db.session.commit()
    return row, d


def delete_one(user, entry_id):
    db.session.delete(get_row(user, entry_id))
    db.session.commit()


def delete_all(user):
    n = HedhiCycle.query.filter_by(user_id=user.id).delete()
    log_action("hedhi.deleted_all", user_id=user.id, entity_type="user", entity_id=user.id, details={"entries": n}, commit=False)
    db.session.commit()
    return n


def purge_inactive():
    """Spec 8.1: data is kept until the customer deletes it, or 2 years without opening the app."""
    cutoff = utcnow() - timedelta(days=current_app.config["HEDHI_INACTIVITY_DAYS"])
    users = (db.session.query(User.id).join(HedhiCycle, HedhiCycle.user_id == User.id)
             .filter(db.func.coalesce(User.last_login_at, User.created_at) < cutoff).distinct().all())
    total = 0
    for (uid,) in users:
        n = HedhiCycle.query.filter_by(user_id=uid).delete()
        total += n
        log_action("hedhi.purged_inactive", user_id=uid, entity_type="user", entity_id=uid, details={"entries": n}, commit=False)
    db.session.commit()
    return len(users), total


# ---------------- insights ----------------
def _see_doctor(cycle_lengths, period_lengths, on, last_start, next_start):
    reasons = []
    if any(c < 21 or c > 35 for c in cycle_lengths[:3]):
        reasons.append(("irregular_cycle", "Mzunguko wako umekuwa mfupi (chini ya siku 21) au mrefu (zaidi ya siku 35).",
                        "Your cycle has been shorter than 21 days or longer than 35 days."))
    if any(p > 7 for p in period_lengths[:3]):
        reasons.append(("long_period", "Hedhi yako imechukua zaidi ya siku 7.", "Your period lasted more than 7 days."))
    since = (on - last_start).days
    if since > 90:
        reasons.append(("no_period_3_months", "Hujaona hedhi kwa zaidi ya miezi 3.", "You have not had a period for more than 3 months."))
    elif next_start and (on - next_start).days >= 7:
        reasons.append(("period_late", "Hedhi yako imechelewa wiki moja au zaidi.", "Your period is a week or more late."))
    return {"recommended": bool(reasons), "reasons": [r[0] for r in reasons], "messages": {"sw": [r[1] for r in reasons], "en": [r[2] for r in reasons]},
            "search_path": "/api/v1/doctors"}


def insights(user, on=None):
    on = on or to_local(utcnow()).date()
    items = [x for _, x in all_entries(user) if x["start_date"] <= on]
    base = {"as_of": on.isoformat(), "disclaimer": DISCLAIMER}
    if not items:
        return {**base, "has_data": False, "message": {"sw": "Weka tarehe ya kuanza kwa hedhi yako ya mwisho ili kupata makadirio.",
                                                        "en": "Log the start date of your last period to get estimates."},
                "see_doctor": {"recommended": False, "reasons": [], "messages": {"sw": [], "en": []}, "search_path": "/api/v1/doctors"}}
    starts = [x["start_date"] for x in items]                    # newest first
    gaps = [(a - b).days for a, b in zip(starts, starts[1:])]
    cycle_lengths = [g for g in gaps if 15 <= g <= 90]           # gaps outside this range are most likely missed logs
    recent = cycle_lengths[:6]
    avg_cycle = round(mean(recent)) if recent else DEFAULT_CYCLE
    plens = [(x["end_date"] - x["start_date"]).days + 1 for x in items if x["end_date"]]
    avg_period = round(mean(plens[:6])) if plens else DEFAULT_PERIOD
    last_start = starts[0]
    next_start = last_start + timedelta(days=avg_cycle)
    ovulation = next_start - timedelta(days=LUTEAL_DAYS)
    fertile = (ovulation - timedelta(days=5), ovulation + timedelta(days=1))
    period_end = last_start + timedelta(days=(((items[0]["end_date"] - last_start).days) if items[0]["end_date"] else avg_period - 1))
    day = (on - last_start).days + 1
    if on <= period_end:
        phase = "menstruation"
    elif on > next_start:
        phase = "late"
    elif fertile[0] <= on <= fertile[1]:
        phase = "fertile_window"
    elif on < fertile[0]:
        phase = "follicular"
    else:
        phase = "luteal"
    return {**base, "has_data": True, "phase": phase, "day_of_cycle": day,
            "last_period_start": last_start.isoformat(), "average_cycle_length": avg_cycle,
            "average_period_length": avg_period, "based_on_default_cycle": not recent,
            "cycles_logged": len(items), "next_period_start": next_start.isoformat(),
            "next_period_end": (next_start + timedelta(days=avg_period - 1)).isoformat(),
            "days_until_next_period": (next_start - on).days,
            "late_by_days": max(0, (on - next_start).days),
            "ovulation_estimate": ovulation.isoformat(),
            "fertile_window": {"start": fertile[0].isoformat(), "end": fertile[1].isoformat()},
            "see_doctor": _see_doctor(cycle_lengths, plens, on, last_start, next_start)}
