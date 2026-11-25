from datetime import timedelta

from flask import current_app

from app.common.audit import log_action
from app.common.errors import APIError
from app.common.timeutils import as_utc, to_local, utcnow
from app.extensions import db
from app.models import Consultation, ConsultationMessage, DoctorProfile
from app.notifications.services import notify

NOTICE = {"sw": "Chat si huduma ya dharura. Kwa dharura piga 112.",
          "en": "Chat is not an emergency service. In an emergency call 112."}


def _iso(dt):
    return to_local(dt).isoformat() if dt else None


def get_visible(user, consultation_id):
    """Only the patient and the doctor of a consultation can see it - not even admins (private health conversation)."""
    c = db.session.get(Consultation, consultation_id)
    if c:
        if user.role == "patient" and user.patient_profile and c.patient_id == user.patient_profile.id:
            return c
        if user.role == "doctor" and user.doctor_profile and c.doctor_id == user.doctor_profile.id:
            return c
    raise APIError("Consultation not found", 404)


def _locked(consultation_id):
    return Consultation.query.filter_by(id=consultation_id).populate_existing().with_for_update().one()


def _due(c):
    if not c.awaiting_reply_since:
        return None, False
    due = as_utc(c.awaiting_reply_since) + timedelta(hours=current_app.config["CHAT_REPLY_TARGET_HOURS"])
    return due, due < utcnow()


def unread_count(c, user):
    return sum(1 for m in c.messages if m.sender_user_id != user.id and m.read_at is None)


def consultation_dict(c, user):
    due, overdue = _due(c)
    d = {
        "id": c.id, "status": c.status, "subject": c.subject, "appointment_id": c.appointment_id,
        "doctor": {"id": c.doctor.id, "name": f"Dr. {c.doctor.first_name} {c.doctor.last_name}", "verified_badge": c.doctor.can_practice},
        "created_at": _iso(c.created_at), "last_message_at": _iso(c.last_message_at), "closed_at": _iso(c.closed_at),
        "awaiting_reply": c.awaiting_reply_since is not None, "reply_due_at": _iso(due), "overdue": overdue,
        "unread_count": unread_count(c, user), "notice": NOTICE,
        "diagnosis": c.diagnosis, "treatment_recommendations": c.treatment_recommendations,
    }
    if user.role == "doctor":
        d["patient"] = {"id": c.patient.id, "name": f"{c.patient.first_name} {c.patient.last_name}"}
        d["notes"] = c.notes  # private doctor notes are never shown to the patient
    return d


def message_dict(m):
    return {"id": m.id, "sender_role": m.sender_role, "body": m.body, "created_at": _iso(m.created_at), "read_at": _iso(m.read_at)}


def _clean_body(body):
    body = body.strip()
    limit = current_app.config["CHAT_MAX_MESSAGE_CHARS"]
    if not body:
        raise APIError("The message cannot be empty", 422)
    if len(body) > limit:
        raise APIError(f"The message is too long (maximum {limit} characters)", 422)
    return body


def start(user, doctor_id, subject, message):
    doctor = db.session.get(DoctorProfile, str(doctor_id))
    if not doctor or not doctor.can_practice:
        raise APIError("Doctor not found", 404)
    body, now = _clean_body(message), utcnow()
    c = Consultation(patient_id=user.patient_profile.id, doctor_id=doctor.id, status="open", subject=subject, mode="chat",
                     last_message_at=now, awaiting_reply_since=now)
    c.messages.append(ConsultationMessage(sender_user_id=user.id, sender_role="patient", body=body, created_at=now))
    db.session.add(c)
    db.session.flush()
    notify(doctor.user_id, "consultation.new", "Una ujumbe mpya kutoka kwa mgonjwa.", {"consultation_id": c.id})
    log_action("consultation.started", user_id=user.id, entity_type="consultation", entity_id=c.id, details={"doctor_id": doctor.id}, commit=False)
    db.session.commit()
    return c


def send(user, consultation_id, body):
    c = get_visible(user, consultation_id)
    c = _locked(c.id)
    body, now = _clean_body(body), utcnow()
    if c.status != "open":
        raise APIError("This consultation is closed. Start a new consultation to continue.", 409)
    if not c.doctor.can_practice:
        if user.role == "doctor":
            raise APIError("Only verified doctors with an active licence can reply", 403)
        raise APIError("This doctor is currently unavailable", 409)
    c.messages.append(ConsultationMessage(sender_user_id=user.id, sender_role=user.role, body=body, created_at=now))
    c.last_message_at = now
    if user.role == "patient":
        c.awaiting_reply_since = c.awaiting_reply_since or now
        notify(c.doctor.user_id, "consultation.message", "Una ujumbe mpya kutoka kwa mgonjwa.", {"consultation_id": c.id})
    else:
        c.awaiting_reply_since = None
        notify(c.patient.user_id, "consultation.message", "Daktari amejibu ujumbe wako.", {"consultation_id": c.id})
    db.session.commit()
    return c.messages[-1]


def read_messages(user, c, page, per_page, newest_first):
    q = ConsultationMessage.query.filter_by(consultation_id=c.id)
    q = q.order_by(ConsultationMessage.created_at.desc() if newest_first else ConsultationMessage.created_at.asc())
    per_page = max(1, min(per_page, 100))
    p = q.paginate(page=max(1, page), per_page=per_page, error_out=False)
    now, touched = utcnow(), False
    for m in p.items:
        if m.sender_user_id != user.id and m.read_at is None:
            m.read_at, touched = now, True
    if touched:
        db.session.commit()
    return p


def update_clinical(user, consultation_id, data):
    c = _locked(get_visible(user, consultation_id).id)
    if not c.doctor.can_practice:
        raise APIError("Only verified doctors with an active licence can record clinical information", 403)
    changed = [k for k, v in data.items() if getattr(c, k) != v]
    for k, v in data.items():
        setattr(c, k, v)
    if "diagnosis" in changed or "treatment_recommendations" in changed:
        notify(c.patient.user_id, "consultation.updated", "Daktari ameongeza maelezo ya matibabu.", {"consultation_id": c.id})
    log_action("consultation.clinical_updated", user_id=user.id, entity_type="consultation", entity_id=c.id,
               details={"fields": changed}, commit=False)
    db.session.commit()
    return c


def close(user, consultation_id):
    c = _locked(get_visible(user, consultation_id).id)
    if c.status == "closed":
        raise APIError("The consultation is already closed", 409)
    c.status, c.closed_at, c.awaiting_reply_since = "closed", utcnow(), None
    notify(c.patient.user_id, "consultation.closed", "Daktari amefunga mazungumzo.", {"consultation_id": c.id})
    log_action("consultation.closed", user_id=user.id, entity_type="consultation", entity_id=c.id, commit=False)
    db.session.commit()
    return c
