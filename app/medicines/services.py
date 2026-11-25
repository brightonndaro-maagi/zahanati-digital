from sqlalchemy.exc import IntegrityError

from app.common.audit import log_action
from app.common.errors import APIError
from app.common.geo import haversine_km
from app.extensions import db
from app.models import Medicine, PharmacyProfile, User

MAX_SEARCH_RESULTS = 1000


def clean_name(name):
    return " ".join(name.split())


def like_pattern(term):
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def visible_query():
    """Medicines customers may see: active medicine, approved pharmacy, active pharmacy account."""
    return (db.session.query(Medicine, PharmacyProfile)
            .join(PharmacyProfile, Medicine.pharmacy_id == PharmacyProfile.id)
            .join(User, PharmacyProfile.user_id == User.id)
            .filter(Medicine.is_active.is_(True), PharmacyProfile.approval_status == "approved",
                    User.is_active.is_(True)))


def public_dict(medicine, pharmacy, lat=None, lon=None):
    """Customer view. The exact stock quantity is deliberately not exposed."""
    distance = None
    if lat is not None:
        distance = round(haversine_km(lat, lon, pharmacy.latitude, pharmacy.longitude), 1)
    return {
        "id": medicine.id, "name": medicine.name, "generic_name": medicine.generic_name,
        "price_tzs": medicine.price_tzs, "available": medicine.stock_quantity > 0,
        "requires_prescription": medicine.requires_prescription,
        "pharmacy": {"id": pharmacy.id, "name": pharmacy.name, "address": pharmacy.address,
                     "latitude": pharmacy.latitude, "longitude": pharmacy.longitude},
        "distance_km": distance,
    }


def search(term, lat=None, lon=None, only_available=False, pharmacy_id=None):
    """Order: available first, then nearest (when GPS given), then cheapest."""
    pattern = like_pattern(term)
    q = visible_query().filter(db.or_(Medicine.name.ilike(pattern, escape="\\"),
                                      Medicine.generic_name.ilike(pattern, escape="\\")))
    if only_available:
        q = q.filter(Medicine.stock_quantity > 0)
    if pharmacy_id:
        q = q.filter(Medicine.pharmacy_id == pharmacy_id)
    rows = q.limit(MAX_SEARCH_RESULTS).all()

    def key(row):
        m, p = row
        dist = haversine_km(lat, lon, p.latitude, p.longitude) if lat is not None else 0.0
        return (0 if m.stock_quantity > 0 else 1, dist, m.price_tzs, m.name.lower())

    return [public_dict(m, p, lat, lon) for m, p in sorted(rows, key=key)]


# ---------------- pharmacy-side catalogue ----------------
def _duplicate(pharmacy_id, name, exclude_id=None):
    q = Medicine.query.filter(Medicine.pharmacy_id == pharmacy_id, db.func.lower(Medicine.name) == name.lower())
    if exclude_id:
        q = q.filter(Medicine.id != exclude_id)
    return q.first()


def _conflict_message(existing):
    if existing is not None and not existing.is_active:
        return "A medicine with this name exists but was removed. Restore it with is_active=true instead."
    return "You already have a medicine with this name"


def create(pharmacy, user, data):
    name = clean_name(data["name"])
    existing = _duplicate(pharmacy.id, name)
    if existing:
        raise APIError(_conflict_message(existing), 409)
    m = Medicine(pharmacy_id=pharmacy.id, name=name, generic_name=data.get("generic_name") and clean_name(data["generic_name"]),
                 price_tzs=data["price_tzs"], stock_quantity=data["stock_quantity"],
                 requires_prescription=data["requires_prescription"], is_active=True)
    db.session.add(m)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise APIError("You already have a medicine with this name", 409)
    log_action("medicine.created", user_id=user.id, entity_type="medicine", entity_id=m.id,
               details={"price_tzs": m.price_tzs, "stock_quantity": m.stock_quantity}, commit=False)
    db.session.commit()
    return m


def update(medicine, user, data):
    before = {"price_tzs": medicine.price_tzs, "stock_quantity": medicine.stock_quantity, "is_active": medicine.is_active}
    if "name" in data:
        data["name"] = clean_name(data["name"])
        existing = _duplicate(medicine.pharmacy_id, data["name"], exclude_id=medicine.id)
        if existing:
            raise APIError(_conflict_message(existing), 409)
    if data.get("generic_name"):
        data["generic_name"] = clean_name(data["generic_name"])
    for k, v in data.items():
        setattr(medicine, k, v)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise APIError("You already have a medicine with this name", 409)
    after = {"price_tzs": medicine.price_tzs, "stock_quantity": medicine.stock_quantity, "is_active": medicine.is_active}
    log_action("medicine.updated", user_id=user.id, entity_type="medicine", entity_id=medicine.id,
               details={"before": before, "after": after}, commit=False)
    db.session.commit()
    return medicine


def delist(medicine, user):
    """Soft delete: past and future orders keep referencing the row."""
    medicine.is_active = False
    log_action("medicine.removed", user_id=user.id, entity_type="medicine", entity_id=medicine.id, commit=False)
    db.session.commit()
