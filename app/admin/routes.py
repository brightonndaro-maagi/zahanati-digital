from flask import Blueprint, request
from marshmallow import Schema, fields, validate

from app.common.decorators import current_user, roles_required
from app.common.errors import APIError
from app.common.responses import paginate, success
from app.doctors import services
from app.doctors.schemas import DoctorPrivateSchema
from app.extensions import db
from app.models import DoctorProfile, PharmacyProfile
from app.pharmacies import services as pharmacy_services
from app.pharmacies.schemas import PharmacySchema

bp = Blueprint("admin", __name__)
schema = DoctorPrivateSchema()


def _doctor(doctor_id):
    d = db.session.get(DoctorProfile, doctor_id)
    if not d:
        raise APIError("Doctor not found", 404)
    return d


@bp.get("/doctors")
@roles_required("admin")
def list_doctors():
    """List doctors for review. Filter: status (pending|verified|rejected), page, per_page.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated doctors}
    """
    q = DoctorProfile.query
    status = request.args.get("status")
    if status:
        if status not in ("pending", "verified", "rejected"):
            raise APIError("Invalid status filter", 422)
        q = q.filter_by(verification_status=status)
    items, meta = paginate(q.order_by(DoctorProfile.created_at.desc()), schema,
                           request.args.get("page", 1, int), request.args.get("per_page", 20, int))
    return success(items, meta=meta)


@bp.get("/doctors/<uid:doctor_id>")
@roles_required("admin")
def get_doctor(doctor_id):
    """Full doctor record with credentials.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Doctor}
      404: {description: Not found}
    """
    return success(schema.dump(_doctor(doctor_id)))


@bp.post("/doctors/<uid:doctor_id>/verify")
@roles_required("admin")
def verify_doctor(doctor_id):
    """Verify a doctor. Optional body: {verified_name} = the name exactly as on the council register.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Verified}
      409: {description: No licence credential}
    """
    body = request.get_json(silent=True)
    name = (body.get("verified_name") or "").strip()[:160] if isinstance(body, dict) else ""
    d = _doctor(doctor_id)
    services.verify(d, current_user(), name or None)
    return success(schema.dump(d), "Doctor verified")


class _Reject(Schema):
    reason = fields.String(required=True, validate=validate.Length(min=3, max=255))


@bp.post("/doctors/<uid:doctor_id>/reject")
@roles_required("admin")
def reject_doctor(doctor_id):
    """Reject a doctor registration with a reason.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Rejected}
      422: {description: Reason required}
    """
    body = request.get_json(silent=True)
    data = _Reject().load(body if isinstance(body, dict) else {})
    d = _doctor(doctor_id)
    services.reject(d, current_user(), data["reason"])
    return success(schema.dump(d), "Doctor rejected")


# ---------------- pharmacies ----------------
pharmacy_schema = PharmacySchema()


def _pharmacy(pharmacy_id):
    p = db.session.get(PharmacyProfile, pharmacy_id)
    if not p:
        raise APIError("Pharmacy not found", 404)
    return p


@bp.get("/pharmacies")
@roles_required("admin")
def list_pharmacies():
    """List pharmacies for review. Filter: status (pending|approved|rejected), page, per_page.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated pharmacies}
    """
    q = PharmacyProfile.query
    status = request.args.get("status")
    if status:
        if status not in ("pending", "approved", "rejected"):
            raise APIError("Invalid status filter", 422)
        q = q.filter_by(approval_status=status)
    items, meta = paginate(q.order_by(PharmacyProfile.created_at.desc()), pharmacy_schema,
                           request.args.get("page", 1, int), request.args.get("per_page", 20, int))
    return success(items, meta=meta)


@bp.get("/pharmacies/<uid:pharmacy_id>")
@roles_required("admin")
def get_pharmacy(pharmacy_id):
    """Pharmacy details.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Pharmacy}
      404: {description: Not found}
    """
    return success(pharmacy_schema.dump(_pharmacy(pharmacy_id)))


@bp.post("/pharmacies/<uid:pharmacy_id>/approve")
@roles_required("admin")
def approve_pharmacy(pharmacy_id):
    """Approve a pharmacy so customers can see it.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Approved}
      404: {description: Not found}
    """
    p = _pharmacy(pharmacy_id)
    pharmacy_services.approve(p, current_user())
    return success(pharmacy_schema.dump(p), "Pharmacy approved")


@bp.post("/pharmacies/<uid:pharmacy_id>/reject")
@roles_required("admin")
def reject_pharmacy(pharmacy_id):
    """Reject a pharmacy registration with a reason.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Rejected}
      422: {description: Reason required}
    """
    body = request.get_json(silent=True)
    data = _Reject().load(body if isinstance(body, dict) else {})
    p = _pharmacy(pharmacy_id)
    pharmacy_services.reject(p, current_user(), data["reason"])
    return success(pharmacy_schema.dump(p), "Pharmacy rejected")


class _LicenseStatus(Schema):
    status = fields.String(required=True, validate=validate.OneOf(["active", "expired"]))


@bp.post("/doctors/<uid:doctor_id>/license-status")
@roles_required("admin")
def set_license_status(doctor_id):
    """Set the licence status (active|expired). An expired licence hides the doctor and blocks chat and prescribing.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
      404: {description: Not found}
      422: {description: Invalid status}
    """
    body = request.get_json(silent=True)
    data = _LicenseStatus().load(body if isinstance(body, dict) else {})
    d = _doctor(doctor_id)
    services.set_license_status(d, current_user(), data["status"])
    return success(schema.dump(d), "Licence status updated")
