from datetime import date, timedelta

from flask import Blueprint, request
from sqlalchemy.orm import joinedload

from app.appointments import services
from app.appointments.schemas import (AppointmentSchema, AvailabilitySchema, BookSchema, NoteSchema,
                                      RescheduleSchema, WindowSchema)
from app.common.audit import log_action
from app.common.decorators import current_user, roles_required, verified_doctor_required
from app.common.errors import APIError
from app.common.responses import paginate, success
from app.common.validators import uuid_arg
from app.common.timeutils import local_day_start_utc, to_utc, today_local
from app.doctors.services import require_profile
from app.extensions import db, limiter
from app.models import Appointment, DoctorProfile
from app.models.appointment import APPOINTMENT_STATUSES

bp = Blueprint("appointments", __name__)
availability_bp = Blueprint("availability", __name__)
appt_schema = AppointmentSchema()


def _json(optional=False):
    body = request.get_json(silent=True)
    if body is None and optional:
        return {}
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    return body


def _date_arg(name, default=None):
    raw = request.args.get(name)
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise APIError(f"'{name}' must be a date in YYYY-MM-DD format", 422)


# ---------------- availability ----------------
@availability_bp.get("/me/availability")
@roles_required("doctor")
def get_my_availability():
    """My weekly working hours (weekday 0=Monday ... 6=Sunday, clinic local time).
    ---
    tags: [Availability]
    security: [{Bearer: []}]
    responses:
      200: {description: Windows}
    """
    return success(WindowSchema().dump(require_profile(current_user()).availability, many=True))


@availability_bp.put("/me/availability")
@roles_required("doctor")
def set_my_availability():
    """Replace my weekly working hours. Existing appointments are not affected.
    ---
    tags: [Availability]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        schema:
          type: object
          properties:
            windows:
              type: array
              items: {type: object, properties: {weekday: {type: integer, example: 0}, start_time: {type: string, example: "09:00"}, end_time: {type: string, example: "17:00"}}}
    responses:
      200: {description: Saved}
      422: {description: Invalid or overlapping windows}
    """
    prof = require_profile(current_user())
    data = AvailabilitySchema().load(_json())
    services.set_availability(prof, data["windows"])
    log_action("doctor.availability_updated", user_id=current_user().id, entity_type="doctor_profile",
               entity_id=prof.id, commit=False)
    db.session.commit()
    return success(WindowSchema().dump(prof.availability, many=True), "Availability updated")


@availability_bp.get("/<uid:doctor_id>/availability")
@roles_required()
def doctor_slots(doctor_id):
    """Free appointment slots of a verified doctor. Query: from, to (YYYY-MM-DD, max 14 days; default next 7 days).
    ---
    tags: [Availability]
    security: [{Bearer: []}]
    responses:
      200: {description: Free slots per day}
      404: {description: Doctor not found}
      422: {description: Bad date range}
    """
    doc = db.session.get(DoctorProfile, doctor_id)
    if not doc or not doc.can_practice:
        raise APIError("Doctor not found", 404)
    d_from = _date_arg("from", today_local())
    d_to = _date_arg("to", d_from + timedelta(days=6))
    if d_to < d_from or (d_to - d_from).days > 13:
        raise APIError("Date range must be between 1 and 14 days", 422)
    return success({"doctor_id": doc.id, "slot_minutes": services.slot_minutes(),
                    "timezone": str(services.clinic_tz()), "days": services.available_slots(doc, d_from, d_to)})


# ---------------- appointments ----------------
@bp.post("")
@roles_required("patient")
@limiter.limit("20 per hour")
def book():
    """Book an appointment (status starts as 'pending' until the doctor accepts).
    ---
    tags: [Appointments]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [doctor_id, start_time]
          properties:
            doctor_id: {type: string}
            start_time: {type: string, example: "2026-11-20T10:00:00+03:00"}
            reason: {type: string}
    responses:
      201: {description: Booked}
      404: {description: Doctor not found or not verified}
      409: {description: Slot taken or you already have an overlapping appointment}
      422: {description: Outside working hours, in the past, or not on a slot boundary}
    """
    data = BookSchema().load(_json())
    appt = services.book(current_user(), data["doctor_id"], to_utc(data["start_time"]), data["reason"])
    return success(appt_schema.dump(appt), "Appointment requested", 201)


@bp.get("")
@roles_required()
def list_appointments():
    """List appointments visible to me. Query: status, from_date, to_date, order (asc|desc), page, per_page; admin also doctor_id, patient_id.
    ---
    tags: [Appointments]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated appointments}
    """
    user, a = current_user(), request.args
    q = Appointment.query.options(joinedload(Appointment.doctor), joinedload(Appointment.patient))
    if user.role == "patient":
        q = q.filter(Appointment.patient_id == user.patient_profile.id)
    elif user.role == "doctor":
        q = q.filter(Appointment.doctor_id == user.doctor_profile.id)
    else:
        if a.get("doctor_id"):
            q = q.filter(Appointment.doctor_id == uuid_arg(a["doctor_id"], "doctor_id"))
        if a.get("patient_id"):
            q = q.filter(Appointment.patient_id == uuid_arg(a["patient_id"], "patient_id"))
    if a.get("status"):
        if a["status"] not in APPOINTMENT_STATUSES:
            raise APIError("Invalid status filter", 422)
        q = q.filter(Appointment.status == a["status"])
    if _date_arg("from_date"):
        q = q.filter(Appointment.start_time >= local_day_start_utc(_date_arg("from_date")))
    if _date_arg("to_date"):
        q = q.filter(Appointment.start_time < local_day_start_utc(_date_arg("to_date") + timedelta(days=1)))
    q = q.order_by(Appointment.start_time.asc() if a.get("order") == "asc" else Appointment.start_time.desc())
    items, meta = paginate(q, appt_schema, a.get("page", 1, int), a.get("per_page", 20, int))
    return success(items, meta=meta)


@bp.get("/<uid:appt_id>")
@roles_required()
def get_appointment(appt_id):
    """Appointment details (participants and admins only).
    ---
    tags: [Appointments]
    security: [{Bearer: []}]
    responses:
      200: {description: Appointment}
      404: {description: Not found}
    """
    return success(appt_schema.dump(services.get_visible(current_user(), appt_id)))


@bp.patch("/<uid:appt_id>/reschedule")
@roles_required("patient")
def reschedule(appt_id):
    """Reschedule my appointment; it returns to 'pending' for the doctor to confirm.
    ---
    tags: [Appointments]
    security: [{Bearer: []}]
    responses:
      200: {description: Rescheduled}
      404: {description: Not found}
      409: {description: Slot taken or appointment not reschedulable}
      422: {description: Invalid time}
    """
    data = RescheduleSchema().load(_json())
    appt = services.reschedule(current_user(), appt_id, to_utc(data["start_time"]))
    return success(appt_schema.dump(appt), "Appointment rescheduled")


def _action(appt_id, action, message):
    note = NoteSchema().load(_json(optional=True))["note"]
    appt = services.change_status(current_user(), appt_id, action, note)
    return success(appt_schema.dump(appt), message)


@bp.post("/<uid:appt_id>/accept")
@verified_doctor_required
def accept(appt_id):
    """Accept a pending request (assigned verified doctor). Optional body: {note}.
    ---
    tags: [Appointments]
    security: [{Bearer: []}]
    responses:
      200: {description: Accepted}
      404: {description: Not found}
      409: {description: Not pending / time passed}
    """
    return _action(appt_id, "accept", "Appointment accepted")


@bp.post("/<uid:appt_id>/reject")
@verified_doctor_required
def reject(appt_id):
    """Reject a pending request. Optional body: {note}.
    ---
    tags: [Appointments]
    security: [{Bearer: []}]
    responses:
      200: {description: Rejected}
      404: {description: Not found}
      409: {description: Not pending}
    """
    return _action(appt_id, "reject", "Appointment rejected")


@bp.post("/<uid:appt_id>/cancel")
@roles_required()
def cancel(appt_id):
    """Cancel a pending/accepted appointment (patient, doctor or admin). Optional body: {note}.
    ---
    tags: [Appointments]
    security: [{Bearer: []}]
    responses:
      200: {description: Cancelled}
      404: {description: Not found}
      409: {description: Not cancellable}
    """
    return _action(appt_id, "cancel", "Appointment cancelled")


@bp.post("/<uid:appt_id>/complete")
@verified_doctor_required
def complete(appt_id):
    """Mark an accepted appointment as completed once it has started.
    ---
    tags: [Appointments]
    security: [{Bearer: []}]
    responses:
      200: {description: Completed}
      404: {description: Not found}
      409: {description: Not accepted / not started}
    """
    return _action(appt_id, "complete", "Appointment completed")
