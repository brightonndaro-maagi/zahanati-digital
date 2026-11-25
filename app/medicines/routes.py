from flask import Blueprint, request

from app.common.decorators import approved_pharmacy_required, current_user, roles_required
from app.common.errors import APIError
from app.common.geo import location_args
from app.common.responses import paginate, paginate_list, success
from app.common.validators import uuid_arg
from app.extensions import db
from app.medicines import services
from app.medicines.schemas import MedicineSchema
from app.models import Medicine, PharmacyProfile

bp = Blueprint("medicines", __name__)            # customer-facing, /api/v1/medicines
catalogue_bp = Blueprint("catalogue", __name__)  # pharmacy-facing, /api/v1/pharmacies
schema = MedicineSchema()


def _json():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    return body


def _flag(name):
    return request.args.get(name, "").lower() in ("1", "true", "yes")


def _page():
    return request.args.get("page", 1, int), request.args.get("per_page", 20, int)


# ---------------- customers ----------------
@bp.get("")
@roles_required("patient", "doctor", "admin")
def search_medicines():
    """Search medicines in approved pharmacies. q (min 2 chars) is required. Optional: lat & lon (customer GPS),
    only_available, pharmacy_id, page, per_page. Order: available first, then nearest, then cheapest.
    Out-of-stock medicines are listed with available=false.
    ---
    tags: [Medicines]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated results}
      422: {description: q too short or invalid GPS}
    """
    term = " ".join(request.args.get("q", "").split())
    if len(term) < 2:
        raise APIError("Search text must be at least 2 characters", 422, {"q": ["Minimum 2 characters."]})
    lat, lon = location_args()
    results = services.search(term, lat, lon, _flag("only_available"), uuid_arg(request.args.get("pharmacy_id"), "pharmacy_id"))
    items, meta = paginate_list(results, *_page())
    return success(items, meta=meta)


def _visible_medicine(medicine_id):
    row = services.visible_query().filter(Medicine.id == medicine_id).first()
    if not row:
        raise APIError("Medicine not found", 404)
    return row


@bp.get("/<uid:medicine_id>")
@roles_required("patient", "doctor", "admin")
def get_medicine(medicine_id):
    """One medicine (only if it is active and its pharmacy is approved). Optional lat & lon add distance_km.
    ---
    tags: [Medicines]
    security: [{Bearer: []}]
    responses:
      200: {description: Medicine}
      404: {description: Not found or not visible}
    """
    m, p = _visible_medicine(medicine_id)
    lat, lon = location_args()
    return success(services.public_dict(m, p, lat, lon))


@catalogue_bp.get("/<uid:pharmacy_id>/medicines")
@roles_required("patient", "doctor", "admin")
def pharmacy_catalogue(pharmacy_id):
    """Catalogue of one approved pharmacy. Optional: q, lat & lon, page, per_page. Available medicines first.
    ---
    tags: [Pharmacies]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated medicines}
      404: {description: Pharmacy not found or not approved}
    """
    q = services.visible_query().filter(Medicine.pharmacy_id == pharmacy_id)
    if not q.first():
        pharm = db.session.get(PharmacyProfile, pharmacy_id)
        if not pharm or pharm.approval_status != "approved" or not pharm.user.is_active:
            raise APIError("Pharmacy not found", 404)
    term = " ".join(request.args.get("q", "").split())
    if term:
        pattern = services.like_pattern(term)
        q = q.filter(db.or_(Medicine.name.ilike(pattern, escape="\\"), Medicine.generic_name.ilike(pattern, escape="\\")))
    lat, lon = location_args()
    q = q.order_by(db.case((Medicine.stock_quantity > 0, 0), else_=1), Medicine.name)
    page, per_page = _page()
    per_page = max(1, min(per_page, 100))
    p = q.paginate(page=max(1, page), per_page=per_page, error_out=False)
    items = [services.public_dict(m, ph, lat, lon) for m, ph in p.items]
    return success(items, meta={"page": p.page, "per_page": p.per_page, "total": p.total, "pages": p.pages})


# ---------------- pharmacy owner ----------------
def _own_medicine(medicine_id):
    m = Medicine.query.filter_by(id=medicine_id, pharmacy_id=current_user().pharmacy_profile.id).first()
    if not m:
        raise APIError("Medicine not found", 404)
    return m


@catalogue_bp.get("/me/medicines")
@roles_required("pharmacy")
def list_my_medicines():
    """My catalogue, including removed items. Filters: q, is_active, available, page, per_page.
    ---
    tags: [Pharmacy catalogue]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated medicines with stock quantities}
    """
    q = Medicine.query.filter_by(pharmacy_id=current_user().pharmacy_profile.id)
    term = " ".join(request.args.get("q", "").split())
    if term:
        pattern = services.like_pattern(term)
        q = q.filter(db.or_(Medicine.name.ilike(pattern, escape="\\"), Medicine.generic_name.ilike(pattern, escape="\\")))
    if request.args.get("is_active") is not None:
        q = q.filter(Medicine.is_active.is_(_flag("is_active")))
    if request.args.get("available") is not None:
        q = q.filter(Medicine.stock_quantity > 0 if _flag("available") else Medicine.stock_quantity == 0)
    items, meta = paginate(q.order_by(Medicine.name), schema, *_page())
    return success(items, meta=meta)


@catalogue_bp.post("/me/medicines")
@approved_pharmacy_required
def add_medicine():
    """Add a medicine (approved pharmacies only). Price is a whole number of shillings.
    ---
    tags: [Pharmacy catalogue]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [name, price_tzs, stock_quantity]
          properties:
            name: {type: string, example: "Paracetamol 500mg"}
            generic_name: {type: string, example: Paracetamol}
            price_tzs: {type: integer, example: 1500}
            stock_quantity: {type: integer, example: 200}
            requires_prescription: {type: boolean}
    responses:
      201: {description: Created}
      403: {description: Pharmacy not approved}
      409: {description: Duplicate name}
      422: {description: Validation failed (price must be a positive whole number)}
    """
    m = services.create(current_user().pharmacy_profile, current_user(), schema.load(_json()))
    return success(schema.dump(m), "Medicine added", 201)


@catalogue_bp.get("/me/medicines/<uid:medicine_id>")
@roles_required("pharmacy")
def get_my_medicine(medicine_id):
    """One of my medicines.
    ---
    tags: [Pharmacy catalogue]
    security: [{Bearer: []}]
    responses:
      200: {description: Medicine}
      404: {description: Not found}
    """
    return success(schema.dump(_own_medicine(medicine_id)))


@catalogue_bp.route("/me/medicines/<uid:medicine_id>", methods=["PUT", "PATCH"])
@approved_pharmacy_required
def update_my_medicine(medicine_id):
    """Change price, stock, name, prescription flag, or restore a removed medicine (is_active=true).
    Customers see the change immediately; existing orders keep their price.
    ---
    tags: [Pharmacy catalogue]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
      404: {description: Not found}
      409: {description: Duplicate name}
      422: {description: Validation failed}
    """
    m = _own_medicine(medicine_id)
    data = schema.load(_json(), partial=request.method == "PATCH")
    if request.method == "PATCH":  # load_default must not overwrite fields that were not sent
        sent = _json()
        data = {k: v for k, v in data.items() if k in sent}
    return success(schema.dump(services.update(m, current_user(), data)), "Medicine updated")


@catalogue_bp.delete("/me/medicines/<uid:medicine_id>")
@approved_pharmacy_required
def remove_my_medicine(medicine_id):
    """Remove a medicine from sale (kept in the database; can be restored).
    ---
    tags: [Pharmacy catalogue]
    security: [{Bearer: []}]
    responses:
      200: {description: Removed}
      404: {description: Not found}
    """
    services.delist(_own_medicine(medicine_id), current_user())
    return success(message="Medicine removed from sale")
