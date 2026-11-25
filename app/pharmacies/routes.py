from flask import Blueprint, request

from app.common.audit import log_action
from app.common.decorators import current_user, roles_required
from app.common.errors import APIError
from app.common.geo import haversine_km, location_args
from app.common.responses import paginate_list, success
from app.medicines.services import like_pattern
from app.extensions import db
from app.models import PharmacyProfile, User
from app.pharmacies.schemas import PharmacyPublicSchema, PharmacySchema

bp = Blueprint("pharmacies", __name__)
schema = PharmacySchema()


def _mine():
    p = current_user().pharmacy_profile
    if not p:
        raise APIError("Pharmacy profile not found", 404)
    return p


@bp.get("/me")
@roles_required("pharmacy")
def get_me():
    """My pharmacy profile and approval status.
    ---
    tags: [Pharmacies]
    security: [{Bearer: []}]
    responses:
      200: {description: Profile}
      403: {description: Not a pharmacy}
    """
    return success(schema.dump(_mine()))


@bp.route("/me", methods=["PUT", "PATCH"])
@roles_required("pharmacy")
def update_me():
    """Update name, address or GPS location (the licence number cannot be changed).
    ---
    tags: [Pharmacies]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
      422: {description: Validation failed}
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    p = _mine()
    for k, v in schema.load(body, partial=request.method == "PATCH").items():
        setattr(p, k, v)
    log_action("pharmacy.profile_updated", user_id=current_user().id, entity_type="pharmacy_profile", entity_id=p.id, commit=False)
    db.session.commit()
    return success(schema.dump(p), "Profile updated")


# ---------------- customers ----------------
public_schema = PharmacyPublicSchema()


def _approved():
    return (PharmacyProfile.query.join(User, PharmacyProfile.user_id == User.id)
            .filter(PharmacyProfile.approval_status == "approved", User.is_active.is_(True)))


def _public(p, lat, lon):
    d = public_schema.dump(p)
    d["distance_km"] = round(haversine_km(lat, lon, p.latitude, p.longitude), 1) if lat is not None else None
    return d


@bp.get("")
@roles_required("patient", "doctor", "admin")
def list_pharmacies():
    """Approved pharmacies. Optional: q (name), lat & lon (nearest first), page, per_page.
    ---
    tags: [Pharmacies]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated pharmacies}
    """
    lat, lon = location_args()
    q = _approved()
    term = " ".join(request.args.get("q", "").split())
    if term:
        q = q.filter(PharmacyProfile.name.ilike(like_pattern(term), escape="\\"))
    rows = q.limit(1000).all()
    rows.sort(key=lambda p: (haversine_km(lat, lon, p.latitude, p.longitude) if lat is not None else 0.0, p.name.lower()))
    items, meta = paginate_list([_public(p, lat, lon) for p in rows], request.args.get("page", 1, int), request.args.get("per_page", 20, int))
    return success(items, meta=meta)


@bp.get("/<uid:pharmacy_id>")
@roles_required("patient", "doctor", "admin")
def get_pharmacy(pharmacy_id):
    """One approved pharmacy (unapproved ones are not visible to customers).
    ---
    tags: [Pharmacies]
    security: [{Bearer: []}]
    responses:
      200: {description: Pharmacy}
      404: {description: Not found or not approved}
    """
    p = _approved().filter(PharmacyProfile.id == pharmacy_id).first()
    if not p:
        raise APIError("Pharmacy not found", 404)
    lat, lon = location_args()
    return success(_public(p, lat, lon))
