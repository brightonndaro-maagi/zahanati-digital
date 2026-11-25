from app.common.audit import log_action
from app.common.errors import APIError
from app.common.timeutils import to_local, utcnow
from app.extensions import db
from app.models import FirstAidGuide, HealthEducation

KINDS = {"first-aid": FirstAidGuide, "health-education": HealthEducation}
STAGES = {
    1: {"sw": "Kutoona hedhi / hedhi kuchelewa", "en": "Missing or late periods"},
    2: {"sw": "Hedhi na mzunguko", "en": "Periods and the menstrual cycle"},
    3: {"sw": "Uzazi wa mpango", "en": "Family planning"},
    4: {"sw": "Ujauzito", "en": "Pregnancy"},
    5: {"sw": "Afya ya mama wakati wa ujauzito", "en": "Mother's health during pregnancy"},
    6: {"sw": "Kujifungua", "en": "Childbirth"},
    7: {"sw": "Baada ya kujifungua", "en": "After childbirth"},
    8: {"sw": "Afya ya mtoto", "en": "Child health"},
}
EMERGENCY = {"sw": "Katika dharura piga 112 mara moja. Maelekezo haya hayachukui nafasi ya huduma ya daktari.",
             "en": "In an emergency call 112 immediately. This guidance does not replace a doctor's care."}
EDIT_FIELDS = {"first-aid": ("title", "summary", "body", "keywords", "language", "emergency_warning", "steps_to_do", "steps_to_avoid"),
               "health-education": ("title", "summary", "body", "keywords", "language", "stage")}


def _iso(dt):
    return to_local(dt).isoformat() if dt else None


def _working(item, kind):
    return {f: getattr(item, f) for f in EDIT_FIELDS[kind]}


def public_dict(item, kind, full=False):
    live = item.live
    d = {"id": item.id, "title": live["title"], "summary": live["summary"], "language": live["language"],
         "edition": live["edition"], "reviewed_by": live["reviewed_by"], "reviewed_at": live["reviewed_at"],
         "published_at": live["published_at"]}
    if kind == "health-education":
        d["stage"], d["stage_name"] = live["stage"], STAGES[live["stage"]]
    if full:
        d.update(body=live["body"], keywords=live["keywords"], emergency_notice=EMERGENCY)
        if kind == "first-aid":
            d.update(emergency_warning=live["emergency_warning"], steps_to_do=live["steps_to_do"], steps_to_avoid=live["steps_to_avoid"])
    return d


def admin_dict(item, kind):
    d = {"id": item.id, "status": item.status, "edition": item.edition, **_working(item, kind),
         "has_unpublished_changes": item.status == "draft" and item.live is not None,
         "published_version": None if item.live is None else {k: item.live[k] for k in ("edition", "reviewed_by", "reviewed_at", "published_at")},
         "created_at": _iso(item.created_at), "updated_at": _iso(item.updated_at)}
    return d


def search_published(kind, term=None, language=None, stage=None):
    """Searches the approved snapshots (small collections, so this is done in Python and stays database-independent)."""
    Model = KINDS[kind]
    rows = Model.query.filter(Model.live.isnot(None)).limit(2000).all()
    out = []
    for r in rows:
        live = r.live
        if language and live["language"] != language:
            continue
        if stage and live.get("stage") != stage:
            continue
        if term:
            hay = " ".join(str(live.get(k) or "") for k in ("title", "summary", "body", "keywords")).lower()
            if term.lower() not in hay:
                continue
        out.append(r)
    out.sort(key=lambda r: r.live["title"].lower())
    return out


def get_published(kind, item_id):
    item = db.session.get(KINDS[kind], item_id)
    if not item or item.live is None:
        raise APIError("Content not found", 404)
    return item


# ---------------- admin workflow ----------------
def create(kind, user, data):
    item = KINDS[kind](created_by_user_id=user.id, status="draft", edition=0, **data)
    db.session.add(item)
    db.session.flush()
    log_action(f"{kind}.created", user_id=user.id, entity_type=kind, entity_id=item.id, commit=False)
    db.session.commit()
    return item


def update(kind, user, item, data):
    for k, v in data.items():
        setattr(item, k, v)
    item.status = "draft"  # any change needs a new review; the approved text stays live until then
    log_action(f"{kind}.updated", user_id=user.id, entity_type=kind, entity_id=item.id, details={"fields": sorted(data)}, commit=False)
    db.session.commit()
    return item


def publish(kind, user, item, reviewer):
    now = utcnow()
    item.edition += 1
    item.live = {**_working(item, kind), "edition": item.edition, "reviewed_by": reviewer,
                 "reviewed_at": _iso(now), "published_at": _iso(now)}
    item.status = "published"
    log_action(f"{kind}.published", user_id=user.id, entity_type=kind, entity_id=item.id,
               details={"edition": item.edition, "reviewed_by": reviewer}, commit=False)
    db.session.commit()
    return item


def unpublish(kind, user, item):
    item.live, item.status = None, "draft"
    log_action(f"{kind}.unpublished", user_id=user.id, entity_type=kind, entity_id=item.id, commit=False)
    db.session.commit()
    return item


def delete(kind, user, item):
    if item.live is not None:
        raise APIError("Unpublish this content before deleting it", 409)
    log_action(f"{kind}.deleted", user_id=user.id, entity_type=kind, entity_id=item.id, commit=False)
    db.session.delete(item)
    db.session.commit()
