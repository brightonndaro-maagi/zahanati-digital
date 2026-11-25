from datetime import datetime, time, timedelta, timezone

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.common.audit import log_action
from app.common.errors import APIError
from app.common.timeutils import as_utc, clinic_tz, local_day_start_utc, to_local, utcnow
from app.extensions import db
from app.models import Appointment, DoctorAvailability, DoctorProfile, PatientProfile
from app.models.appointment import ACTIVE_STATUSES


def slot_minutes():
    return current_app.config["APPOINTMENT_SLOT_MINUTES"]


def _mins(t):
    return t.hour * 60 + t.minute


# ---------------- availability ----------------
def set_availability(doctor, windows):
    slot = slot_minutes()
    by_day = {}
    for w in windows:
        if _mins(w["end_time"]) - _mins(w["start_time"]) < slot:
            raise APIError(f"Each window must be at least {slot} minutes long", 422)
        by_day.setdefault(w["weekday"], []).append(w)
    for day, ws in by_day.items():
        ws.sort(key=lambda w: w["start_time"])
        for a, b in zip(ws, ws[1:]):
            if b["start_time"] < a["end_time"]:
                raise APIError(f"Overlapping availability windows on weekday {day}", 422)
    doctor.availability = [DoctorAvailability(weekday=w["weekday"], start_time=w["start_time"],
                                              end_time=w["end_time"]) for w in windows]


def available_slots(doctor, d_from, d_to):
    tz, slot, cfg = clinic_tz(), slot_minutes(), current_app.config
    now = utcnow()
    earliest = now + timedelta(minutes=cfg["APPOINTMENT_MIN_LEAD_MINUTES"])
    latest = now + timedelta(days=cfg["APPOINTMENT_MAX_ADVANCE_DAYS"])
    lo, hi = local_day_start_utc(d_from), local_day_start_utc(d_to + timedelta(days=1))
    busy = [(as_utc(a.start_time), as_utc(a.end_time)) for a in Appointment.query.filter(
        Appointment.doctor_id == doctor.id, Appointment.status.in_(ACTIVE_STATUSES),
        Appointment.start_time < hi, Appointment.end_time > lo)]
    windows = {}
    for w in doctor.availability:
        windows.setdefault(w.weekday, []).append(w)
    days, d = [], d_from
    while d <= d_to:
        slots = []
        for w in sorted(windows.get(d.weekday(), []), key=lambda w: w.start_time):
            m, end_m = _mins(w.start_time), _mins(w.end_time)
            while m + slot <= end_m:
                s_local = datetime.combine(d, time(m // 60, m % 60), tzinfo=tz)
                s_utc = s_local.astimezone(timezone.utc)
                e_utc = s_utc + timedelta(minutes=slot)
                if earliest <= s_utc <= latest and not any(bs < e_utc and be > s_utc for bs, be in busy):
                    slots.append({"start": s_local.isoformat(),
                                  "end": (s_local + timedelta(minutes=slot)).isoformat()})
                m += slot
        days.append({"date": d.isoformat(), "slots": slots})
        d += timedelta(days=1)
    return days


# ---------------- booking rules ----------------
def _validate_slot(doctor, start_utc):
    cfg, now = current_app.config, utcnow()
    if start_utc < now + timedelta(minutes=cfg["APPOINTMENT_MIN_LEAD_MINUTES"]):
        raise APIError(f"Appointments must be booked at least {cfg['APPOINTMENT_MIN_LEAD_MINUTES']} minutes ahead", 422)
    if start_utc > now + timedelta(days=cfg["APPOINTMENT_MAX_ADVANCE_DAYS"]):
        raise APIError(f"Appointments cannot be booked more than {cfg['APPOINTMENT_MAX_ADVANCE_DAYS']} days ahead", 422)
    local, slot = to_local(start_utc), slot_minutes()
    start_m = local.hour * 60 + local.minute
    for w in doctor.availability:
        if w.weekday != local.weekday():
            continue
        offset = start_m - _mins(w.start_time)
        if (local.second == 0 and local.microsecond == 0 and offset >= 0
                and offset % slot == 0 and start_m + slot <= _mins(w.end_time)):
            return
    raise APIError("The doctor is not available at the requested time. Check the doctor's availability slots.", 422)


def _overlaps(column, value, start, end, exclude_id=None):
    q = Appointment.query.filter(column == value, Appointment.status.in_(ACTIVE_STATUSES),
                                 Appointment.start_time < end, Appointment.end_time > start)
    if exclude_id:
        q = q.filter(Appointment.id != exclude_id)
    return q.first() is not None


def _check_conflicts(doctor_id, patient_id, start, end, exclude_id=None):
    if _overlaps(Appointment.doctor_id, doctor_id, start, end, exclude_id):
        raise APIError("This time slot is no longer available for the doctor", 409)
    if _overlaps(Appointment.patient_id, patient_id, start, end, exclude_id):
        raise APIError("You already have an appointment that overlaps this time", 409)


def _lock_parties(doctor_id, patient_id):
    """Row locks (always doctor first, then patient) serialise concurrent bookings on PostgreSQL."""
    doctor = DoctorProfile.query.filter_by(id=doctor_id).populate_existing().with_for_update().one_or_none()
    patient = PatientProfile.query.filter_by(id=patient_id).populate_existing().with_for_update().one_or_none()
    return doctor, patient


def _flush_or_conflict():
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise APIError("This time slot was just taken. Please choose another.", 409)


def book(user, doctor_id, start_utc, reason):
    patient_id = user.patient_profile.id
    doctor, _ = _lock_parties(str(doctor_id), patient_id)
    if not doctor or not doctor.can_practice:
        raise APIError("Doctor not found", 404)
    _validate_slot(doctor, start_utc)
    end = start_utc + timedelta(minutes=slot_minutes())
    _check_conflicts(doctor.id, patient_id, start_utc, end)
    appt = Appointment(patient_id=patient_id, doctor_id=doctor.id, start_time=start_utc, end_time=end,
                       status="pending", reason=reason)
    db.session.add(appt)
    _flush_or_conflict()
    log_action("appointment.booked", user_id=user.id, entity_type="appointment", entity_id=appt.id,
               details={"doctor_id": doctor.id}, commit=False)
    db.session.commit()
    return appt


def get_visible(user, appt_id):
    appt = db.session.get(Appointment, appt_id)
    if appt:
        if user.role == "admin":
            return appt
        if user.role == "patient" and user.patient_profile and appt.patient_id == user.patient_profile.id:
            return appt
        if user.role == "doctor" and user.doctor_profile and appt.doctor_id == user.doctor_profile.id:
            return appt
    raise APIError("Appointment not found", 404)


def reschedule(user, appt_id, new_start_utc):
    appt = get_visible(user, appt_id)
    doctor, _ = _lock_parties(appt.doctor_id, appt.patient_id)
    db.session.refresh(appt)
    if appt.status not in ACTIVE_STATUSES:
        raise APIError(f"Cannot reschedule an appointment that is {appt.status}", 409)
    if as_utc(appt.start_time) <= utcnow():
        raise APIError("Past appointments cannot be rescheduled", 409)
    if not doctor.can_practice:
        raise APIError("This doctor is not currently available for appointments", 409)
    _validate_slot(doctor, new_start_utc)
    end = new_start_utc + timedelta(minutes=slot_minutes())
    _check_conflicts(appt.doctor_id, appt.patient_id, new_start_utc, end, exclude_id=appt.id)
    old = to_local(appt.start_time).isoformat()
    appt.start_time, appt.end_time = new_start_utc, end
    appt.status, appt.doctor_note = "pending", None  # the doctor must confirm the new time
    _flush_or_conflict()
    log_action("appointment.rescheduled", user_id=user.id, entity_type="appointment", entity_id=appt.id,
               details={"from": old}, commit=False)
    db.session.commit()
    return appt


RULES = {
    "accept": ({"pending"}, "accepted"),
    "reject": ({"pending"}, "rejected"),
    "cancel": ({"pending", "accepted"}, "cancelled"),
    "complete": ({"accepted"}, "completed"),
}


def change_status(user, appt_id, action, note=None):
    appt = get_visible(user, appt_id)
    appt = Appointment.query.filter_by(id=appt.id).populate_existing().with_for_update().one()
    allowed, new_status = RULES[action]
    if appt.status not in allowed:
        raise APIError(f"Cannot {action} an appointment that is {appt.status}", 409)
    started = as_utc(appt.start_time) <= utcnow()
    if action == "accept" and started:
        raise APIError("The appointment time has already passed", 409)
    if action == "complete" and not started:
        raise APIError("An appointment can only be completed once it has started", 409)
    appt.status = new_status
    if action in ("accept", "reject"):
        appt.doctor_note = note
    if action == "cancel":
        appt.cancelled_by_user_id, appt.cancel_reason = user.id, note
    log_action(f"appointment.{action}", user_id=user.id, entity_type="appointment", entity_id=appt.id, commit=False)
    db.session.commit()
    return appt
