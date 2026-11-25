from datetime import timedelta

from flask import Blueprint, request

from app.common.decorators import current_user, roles_required
from app.common.errors import APIError
from app.common.responses import success
from app.common.timeutils import to_local, utcnow
from app.consultations import services as chat
from app.doctors.schemas import WorkplaceSchema
from app.doctors.services import require_profile
from app.extensions import db
from app.models import Appointment, Consultation, DoctorWorkplace, Prescription

bp = Blueprint("doctor_extras", __name__)
schema = WorkplaceSchema()
MAX_WORKPLACES = 20


def _json():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    return body


def _check_years(data):
    if data.get("start_year") and data.get("end_year") and data["end_year"] < data["start_year"]:
        raise APIError("end_year cannot be before start_year", 422, {"end_year": ["Must not be before start_year."]})
    if data.get("is_current") and data.get("end_year"):
        raise APIError("A current workplace cannot have an end_year", 422, {"end_year": ["Leave empty for a current workplace."]})


def _own(workplace_id):
    w = DoctorWorkplace.query.filter_by(id=workplace_id, doctor_id=require_profile(current_user()).id).first()
    if not w:
        raise APIError("Workplace not found", 404)
    return w


@bp.get("/me/workplaces")
@roles_required("doctor")
def list_workplaces():
    """My work history (institutions, current workplace(s)).
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      200: {description: Workplaces}
    """
    return success(schema.dump(require_profile(current_user()).workplaces, many=True))


@bp.post("/me/workplaces")
@roles_required("doctor")
def add_workplace():
    """Add an institution (set is_current=true for where you work now; you may have more than one).
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      201: {description: Added}
      422: {description: Validation failed}
    """
    prof = require_profile(current_user())
    data = schema.load(_json())
    _check_years(data)
    if len(prof.workplaces) >= MAX_WORKPLACES:
        raise APIError(f"You can list at most {MAX_WORKPLACES} workplaces", 422)
    w = DoctorWorkplace(doctor_id=prof.id, **data)
    db.session.add(w)
    db.session.commit()
    return success(schema.dump(w), "Workplace added", 201)


@bp.route("/me/workplaces/<uid:workplace_id>", methods=["PUT", "PATCH"])
@roles_required("doctor")
def update_workplace(workplace_id):
    """Update a workplace.
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
      404: {description: Not found}
    """
    w = _own(workplace_id)
    sent = _json()
    data = {k: v for k, v in schema.load(sent, partial=request.method == "PATCH").items() if request.method == "PUT" or k in sent}
    merged = {"start_year": w.start_year, "end_year": w.end_year, "is_current": w.is_current, **data}
    _check_years(merged)
    for k, v in data.items():
        setattr(w, k, v)
    db.session.commit()
    return success(schema.dump(w), "Workplace updated")


@bp.delete("/me/workplaces/<uid:workplace_id>")
@roles_required("doctor")
def delete_workplace(workplace_id):
    """Remove a workplace.
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      200: {description: Removed}
      404: {description: Not found}
    """
    db.session.delete(_own(workplace_id))
    db.session.commit()
    return success(message="Workplace removed")


@bp.get("/me/dashboard")
@roles_required("doctor")
def dashboard():
    """Doctor dashboard: experience, licence status, current workplace, inbox and workload.
    ---
    tags: [Doctors]
    security: [{Bearer: []}]
    responses:
      200: {description: Dashboard}
    """
    user, prof = current_user(), require_profile(current_user())
    consults = Consultation.query.filter_by(doctor_id=prof.id).order_by(Consultation.last_message_at.desc()).all()
    dicts = [chat.consultation_dict(c, user) for c in consults]
    since = utcnow() - timedelta(days=30)
    return success({
        "name": f"Dr. {prof.first_name} {prof.last_name}",
        "verified_badge": prof.can_practice, "verification_status": prof.verification_status,
        "license_status": prof.license_status, "council": prof.council, "verified_name": prof.verified_name,
        "years_of_experience": prof.years_of_experience,
        "current_workplaces": schema.dump([w for w in prof.workplaces if w.is_current], many=True),
        "experience_history": schema.dump([w for w in prof.workplaces if not w.is_current], many=True),
        "stats": {
            "open_consultations": sum(1 for d in dicts if d["status"] == "open"),
            "awaiting_reply": sum(1 for d in dicts if d["awaiting_reply"]),
            "overdue_replies": sum(1 for d in dicts if d["overdue"]),
            "unread_messages": sum(d["unread_count"] for d in dicts),
            "prescriptions_issued_total": Prescription.query.filter_by(doctor_id=prof.id).count(),
            "prescriptions_issued_30d": Prescription.query.filter(Prescription.doctor_id == prof.id, Prescription.created_at >= since).count(),
            "pending_appointment_requests": Appointment.query.filter_by(doctor_id=prof.id, status="pending").count(),
        },
        "inbox": dicts[:5],
    })
