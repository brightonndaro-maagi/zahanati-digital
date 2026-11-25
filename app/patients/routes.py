from flask import Blueprint, request
from app.common.access import doctor_can_access_patient
from app.common.audit import log_action
from app.common.decorators import current_user, roles_required
from app.common.errors import APIError
from app.common.responses import paginate, success
from app.extensions import db
from app.models import MedicalRecord, PatientProfile
from app.patients.schemas import MedicalRecordSchema, PatientProfileSchema

bp = Blueprint("patients", __name__)
profile_schema = PatientProfileSchema()
record_schema = MedicalRecordSchema()


def _json():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    return body


def _my_profile():
    p = current_user().patient_profile
    if not p:
        raise APIError("Patient profile not found", 404)
    return p


@bp.get("/me")
@roles_required("patient")
def get_me():
    """Get my patient profile.
    ---
    tags: [Patients]
    security: [{Bearer: []}]
    responses:
      200: {description: Profile}
      403: {description: Not a patient}
    """
    return success(profile_schema.dump(_my_profile()))


@bp.route("/me", methods=["PUT", "PATCH"])
@roles_required("patient")
def update_me():
    """Update my profile (PUT = full, PATCH = partial).
    ---
    tags: [Patients]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
      422: {description: Validation failed}
    """
    data = profile_schema.load(_json(), partial=request.method == "PATCH")
    user, profile = current_user(), _my_profile()
    for k, v in data.items():
        setattr(profile, k, v)
    log_action("patient.profile_updated", user_id=user.id, entity_type="patient_profile", entity_id=profile.id, commit=False)
    db.session.commit()
    return success(profile_schema.dump(profile), "Profile updated")


# ---------- own medical records ----------
@bp.get("/me/medical-records")
@roles_required("patient")
def list_my_records():
    """List my medical records (filter: record_type, page, per_page).
    ---
    tags: [Patients]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated records}
    """
    q = MedicalRecord.query.filter_by(patient_id=_my_profile().id)
    if request.args.get("record_type"):
        q = q.filter_by(record_type=request.args["record_type"])
    q = q.order_by(MedicalRecord.created_at.desc())
    items, meta = paginate(q, record_schema, request.args.get("page", 1, int), request.args.get("per_page", 20, int))
    return success(items, meta=meta)


@bp.post("/me/medical-records")
@roles_required("patient")
def add_my_record():
    """Add a medical history entry.
    ---
    tags: [Patients]
    security: [{Bearer: []}]
    responses:
      201: {description: Created}
      422: {description: Validation failed}
    """
    data = record_schema.load(_json())
    rec = MedicalRecord(patient_id=_my_profile().id, recorded_by_user_id=current_user().id, **data)
    db.session.add(rec)
    db.session.flush()
    log_action("medical_record.created", user_id=current_user().id, entity_type="medical_record", entity_id=rec.id, commit=False)
    db.session.commit()
    return success(record_schema.dump(rec), "Record added", 201)


def _own_record(record_id, must_be_author=False):
    rec = MedicalRecord.query.filter_by(id=record_id, patient_id=_my_profile().id).first()
    if not rec:
        raise APIError("Medical record not found", 404)
    if must_be_author and rec.recorded_by_user_id != current_user().id:
        raise APIError("Records entered by a doctor cannot be modified by the patient", 403)
    return rec


@bp.get("/me/medical-records/<uid:record_id>")
@roles_required("patient")
def get_my_record(record_id):
    """Get one of my records.
    ---
    tags: [Patients]
    security: [{Bearer: []}]
    responses:
      200: {description: Record}
      404: {description: Not found}
    """
    return success(record_schema.dump(_own_record(record_id)))


@bp.route("/me/medical-records/<uid:record_id>", methods=["PUT", "PATCH"])
@roles_required("patient")
def update_my_record(record_id):
    """Update a record I created.
    ---
    tags: [Patients]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
      403: {description: Record was entered by a doctor}
      404: {description: Not found}
    """
    rec = _own_record(record_id, must_be_author=True)
    for k, v in record_schema.load(_json(), partial=request.method == "PATCH").items():
        setattr(rec, k, v)
    log_action("medical_record.updated", user_id=current_user().id, entity_type="medical_record", entity_id=rec.id, commit=False)
    db.session.commit()
    return success(record_schema.dump(rec), "Record updated")


@bp.delete("/me/medical-records/<uid:record_id>")
@roles_required("patient")
def delete_my_record(record_id):
    """Delete a record I created.
    ---
    tags: [Patients]
    security: [{Bearer: []}]
    responses:
      200: {description: Deleted}
      403: {description: Record was entered by a doctor}
      404: {description: Not found}
    """
    rec = _own_record(record_id, must_be_author=True)
    log_action("medical_record.deleted", user_id=current_user().id, entity_type="medical_record", entity_id=rec.id, commit=False)
    db.session.delete(rec)
    db.session.commit()
    return success(message="Record deleted")


# ---------- authorised access by doctors / admins ----------
def _authorised_patient(patient_id):
    user = current_user()
    if user.role == "doctor":
        if not doctor_can_access_patient(user.doctor_profile, patient_id):
            raise APIError("You are not authorised to access this patient's information", 403)
    patient = db.session.get(PatientProfile, patient_id)
    if not patient:
        raise APIError("Patient not found", 404)
    return patient


@bp.get("/<uid:patient_id>")
@roles_required("doctor", "admin")
def get_patient(patient_id):
    """View a patient's profile (verified doctor with an accepted/completed appointment, or admin).
    ---
    tags: [Patients]
    security: [{Bearer: []}]
    responses:
      200: {description: Patient profile}
      403: {description: Not authorised}
      404: {description: Not found}
    """
    patient = _authorised_patient(patient_id)
    log_action("patient.profile_viewed", user_id=current_user().id, entity_type="patient_profile", entity_id=patient.id)
    return success(profile_schema.dump(patient))


@bp.get("/<uid:patient_id>/medical-records")
@roles_required("doctor", "admin")
def get_patient_records(patient_id):
    """View a patient's medical records (authorised access only; access is audited).
    ---
    tags: [Patients]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated records}
      403: {description: Not authorised}
      404: {description: Not found}
    """
    patient = _authorised_patient(patient_id)
    log_action("patient.records_viewed", user_id=current_user().id, entity_type="patient_profile", entity_id=patient.id)
    q = MedicalRecord.query.filter_by(patient_id=patient.id).order_by(MedicalRecord.created_at.desc())
    items, meta = paginate(q, record_schema, request.args.get("page", 1, int), request.args.get("per_page", 20, int))
    return success(items, meta=meta)
