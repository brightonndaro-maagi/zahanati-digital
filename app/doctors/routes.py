from flask import Blueprint, request
from marshmallow import Schema, fields

from app.common.audit import log_action
from app.common.decorators import current_user, roles_required
from app.common.errors import APIError
from app.common.responses import paginate, success
from app.common.validators import uuid_arg
from app.doctors import services
from app.doctors.schemas import (CredentialSchema, DoctorPrivateSchema, DoctorPublicSchema, DoctorUpdateSchema,
                                 SpecialisationSchema)
from app.extensions import db
from app.models import DoctorCredential, DoctorProfile, Specialisation, User

bp = Blueprint("doctors", __name__)
spec_bp = Blueprint("specialisations", __name__)
public_schema, private_schema = DoctorPublicSchema(), DoctorPrivateSchema()
cred_schema, spec_schema = CredentialSchema(), SpecialisationSchema()


def _json():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    return body


# ---------------- search / public view ----------------
@bp.get("")
@roles_required()
def search_doctors():
    """Search verified doctors. Filters: q (name), specialisation_id, location, min_experience, page, per_page.
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated verified doctors}
    """
    q = (DoctorProfile.query.join(User, DoctorProfile.user_id == User.id)
         .filter(DoctorProfile.verification_status == "verified", DoctorProfile.license_status == "active",
                 User.is_active.is_(True)))
    a = request.args
    if a.get("q"):
        term = f"%{a['q'].strip()}%"
        q = q.filter(db.or_(DoctorProfile.first_name.ilike(term), DoctorProfile.last_name.ilike(term)))
    if a.get("specialisation_id"):
        q = q.filter(DoctorProfile.specialisations.any(Specialisation.id == uuid_arg(a["specialisation_id"], "specialisation_id")))
    if a.get("location"):
        q = q.filter(DoctorProfile.practice_location.ilike(f"%{a['location'].strip()}%"))
    if a.get("min_experience", type=int) is not None:
        q = q.filter(DoctorProfile.years_of_experience >= a.get("min_experience", type=int))
    q = q.order_by(DoctorProfile.last_name, DoctorProfile.first_name)
    items, meta = paginate(q, public_schema, a.get("page", 1, int), a.get("per_page", 20, int))
    return success(items, meta=meta)


@bp.get("/<uid:doctor_id>")
@roles_required()
def get_doctor(doctor_id):
    """Doctor details. Non-verified doctors are only visible to themselves and admins.
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      200: {description: Doctor}
      404: {description: Not found}
    """
    user = current_user()
    doc = db.session.get(DoctorProfile, doctor_id)
    if not doc:
        raise APIError("Doctor not found", 404)
    privileged = user.role == "admin" or (user.doctor_profile and user.doctor_profile.id == doc.id)
    if privileged:
        return success(private_schema.dump(doc))
    if not doc.can_practice:
        raise APIError("Doctor not found", 404)
    return success(public_schema.dump(doc))


# ---------------- own profile ----------------
@bp.get("/me")
@roles_required("doctor")
def get_me():
    """My doctor profile (includes verification status and credentials).
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      200: {description: Profile}
    """
    return success(private_schema.dump(services.require_profile(current_user())))


@bp.route("/me", methods=["PUT", "PATCH"])
@roles_required("doctor")
def update_me():
    """Update my profile.
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
      422: {description: Validation failed}
    """
    user, prof = current_user(), services.require_profile(current_user())
    data = DoctorUpdateSchema().load(_json(), partial=request.method == "PATCH")
    for k, v in data.items():
        setattr(prof, k, v)
    log_action("doctor.profile_updated", user_id=user.id, entity_type="doctor_profile", entity_id=prof.id, commit=False)
    db.session.commit()
    return success(private_schema.dump(prof), "Profile updated")


class _SpecIds(Schema):
    specialisation_ids = fields.List(fields.UUID(), required=True)


@bp.put("/me/specialisations")
@roles_required("doctor")
def set_my_specialisations():
    """Replace my specialisations.
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
      422: {description: Unknown specialisation}
    """
    prof = services.require_profile(current_user())
    services.set_specialisations(prof, _SpecIds().load(_json())["specialisation_ids"])
    db.session.commit()
    return success(private_schema.dump(prof), "Specialisations updated")


# ---------------- credentials ----------------
def _own_cred(cred_id):
    prof = services.require_profile(current_user())
    cred = DoctorCredential.query.filter_by(id=cred_id, doctor_id=prof.id).first()
    if not cred:
        raise APIError("Credential not found", 404)
    return prof, cred


@bp.get("/me/credentials")
@roles_required("doctor")
def list_credentials():
    """List my credentials.
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      200: {description: Credentials}
    """
    return success(cred_schema.dump(services.require_profile(current_user()).credentials, many=True))


@bp.post("/me/credentials")
@roles_required("doctor")
def add_credential():
    """Submit a credential (licence, qualification, certificate). Adding a licence to a verified doctor re-opens review.
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      201: {description: Created}
      422: {description: Validation failed}
    """
    prof = services.require_profile(current_user())
    data = cred_schema.load(_json())
    if data["credential_type"] == "license" and not data.get("license_number"):
        raise APIError("license_number is required for licence credentials", 422, {"license_number": ["Required."]})
    if data["credential_type"] == "license":
        services.ensure_license_unique(data["license_number"])
    cred = DoctorCredential(doctor_id=prof.id, **data)
    db.session.add(cred)
    db.session.flush()
    if cred.credential_type == "license":
        services.reset_verification_if_needed(prof, current_user().id, "licence added")
    log_action("doctor.credential_added", user_id=current_user().id, entity_type="doctor_credential", entity_id=cred.id, commit=False)
    db.session.commit()
    return success(cred_schema.dump(cred), "Credential submitted", 201)


@bp.route("/me/credentials/<uid:cred_id>", methods=["PUT", "PATCH"])
@roles_required("doctor")
def update_credential(cred_id):
    """Update a credential. Editing a licence of a verified doctor re-opens review.
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
      404: {description: Not found}
    """
    prof, cred = _own_cred(cred_id)
    changes = cred_schema.load(_json(), partial=request.method == "PATCH")
    new_type = changes.get("credential_type", cred.credential_type)
    new_number = changes.get("license_number", cred.license_number)
    if new_type == "license" and new_number:
        services.ensure_license_unique(new_number, exclude_credential_id=cred.id)
    for k, v in changes.items():
        setattr(cred, k, v)
    if cred.credential_type == "license":
        services.reset_verification_if_needed(prof, current_user().id, "licence edited")
    log_action("doctor.credential_updated", user_id=current_user().id, entity_type="doctor_credential", entity_id=cred.id, commit=False)
    db.session.commit()
    return success(cred_schema.dump(cred), "Credential updated")


@bp.delete("/me/credentials/<uid:cred_id>")
@roles_required("doctor")
def delete_credential(cred_id):
    """Delete a credential.
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      200: {description: Deleted}
      404: {description: Not found}
    """
    prof, cred = _own_cred(cred_id)
    if cred.credential_type == "license":
        services.reset_verification_if_needed(prof, current_user().id, "licence removed")
    log_action("doctor.credential_deleted", user_id=current_user().id, entity_type="doctor_credential", entity_id=cred.id, commit=False)
    db.session.delete(cred)
    db.session.commit()
    return success(message="Credential deleted")


# ---------------- specialisations ----------------
@spec_bp.get("")
@roles_required()
def list_specialisations():
    """List specialisations.
    ---
    tags: [Specialisations]
    security: [{Bearer: []}]
    responses:
      200: {description: List}
    """
    return success(spec_schema.dump(Specialisation.query.order_by(Specialisation.name).all(), many=True))


@spec_bp.post("")
@roles_required("admin")
def create_specialisation():
    """Create a specialisation (admin).
    ---
    tags: [Specialisations]
    security: [{Bearer: []}]
    responses:
      201: {description: Created}
      409: {description: Already exists}
    """
    data = spec_schema.load(_json())
    if Specialisation.query.filter(db.func.lower(Specialisation.name) == data["name"].lower()).first():
        raise APIError("Specialisation already exists", 409)
    s = Specialisation(**data)
    db.session.add(s)
    db.session.flush()
    log_action("specialisation.created", user_id=current_user().id, entity_type="specialisation", entity_id=s.id, commit=False)
    db.session.commit()
    return success(spec_schema.dump(s), "Specialisation created", 201)


@spec_bp.route("/<uid:spec_id>", methods=["PUT", "PATCH"])
@roles_required("admin")
def update_specialisation(spec_id):
    """Update a specialisation (admin).
    ---
    tags: [Specialisations]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
      404: {description: Not found}
      409: {description: Name taken}
    """
    s = db.session.get(Specialisation, spec_id)
    if not s:
        raise APIError("Specialisation not found", 404)
    data = spec_schema.load(_json(), partial=request.method == "PATCH")
    if "name" in data and Specialisation.query.filter(
            db.func.lower(Specialisation.name) == data["name"].lower(), Specialisation.id != s.id).first():
        raise APIError("Specialisation name already exists", 409)
    for k, v in data.items():
        setattr(s, k, v)
    log_action("specialisation.updated", user_id=current_user().id, entity_type="specialisation", entity_id=s.id, commit=False)
    db.session.commit()
    return success(spec_schema.dump(s), "Specialisation updated")


@spec_bp.delete("/<uid:spec_id>")
@roles_required("admin")
def delete_specialisation(spec_id):
    """Delete a specialisation that no doctor uses (admin).
    ---
    tags: [Specialisations]
    security: [{Bearer: []}]
    responses:
      200: {description: Deleted}
      404: {description: Not found}
      409: {description: In use}
    """
    s = db.session.get(Specialisation, spec_id)
    if not s:
        raise APIError("Specialisation not found", 404)
    if s.doctors:
        raise APIError("Specialisation is assigned to doctors and cannot be deleted", 409)
    log_action("specialisation.deleted", user_id=current_user().id, entity_type="specialisation", entity_id=s.id, commit=False)
    db.session.delete(s)
    db.session.commit()
    return success(message="Specialisation deleted")
