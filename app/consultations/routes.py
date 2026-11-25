from flask import Blueprint, request

from app.common.decorators import current_user, roles_required, verified_doctor_required
from app.common.errors import APIError
from app.common.responses import paginate, success
from app.consultations import services
from app.consultations.schemas import ClinicalSchema, MessageSchema, StartSchema
from app.extensions import db, limiter
from app.models import Consultation

bp = Blueprint("consultations", __name__)


def _json():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    return body


def _flag(name):
    return request.args.get(name, "").lower() in ("1", "true", "yes")


@bp.post("")
@roles_required("patient")
@limiter.limit("10 per hour")
def start_consultation():
    """Start a text consultation with any verified doctor (no prior relationship needed).
    Every consultation carries a notice that chat is not an emergency service (call 112).
    ---
    tags: [Consultations]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [doctor_id, message]
          properties:
            doctor_id: {type: string}
            subject: {type: string}
            message: {type: string, example: "Habari daktari, nina maumivu ya kichwa kwa siku tatu."}
    responses:
      201: {description: Consultation created with the first message}
      404: {description: Doctor not found or not verified}
      422: {description: Empty or too long message}
    """
    data = StartSchema().load(_json())
    c = services.start(current_user(), data["doctor_id"], data["subject"], data["message"])
    return success(services.consultation_dict(c, current_user()), "Consultation started", 201)


@bp.get("")
@roles_required("patient", "doctor")
def list_consultations():
    """My consultations, most recent activity first. Filters: status, awaiting_reply=true, overdue=true (doctors), page, per_page.
    ---
    tags: [Consultations]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated consultations}
    """
    user, a = current_user(), request.args
    q = Consultation.query
    q = q.filter(Consultation.patient_id == user.patient_profile.id) if user.role == "patient" else q.filter(Consultation.doctor_id == user.doctor_profile.id)
    if a.get("status"):
        if a["status"] not in ("open", "closed"):
            raise APIError("Invalid status filter", 422)
        q = q.filter(Consultation.status == a["status"])
    if _flag("awaiting_reply") or _flag("overdue"):
        q = q.filter(Consultation.awaiting_reply_since.isnot(None))
    items = q.order_by(Consultation.last_message_at.desc()).all()
    rows = [services.consultation_dict(c, user) for c in items]
    if _flag("overdue"):
        rows = [r for r in rows if r["overdue"]]
    per_page = max(1, min(a.get("per_page", 20, int), 100))
    page = max(1, a.get("page", 1, int))
    total = len(rows)
    return success(rows[(page - 1) * per_page: page * per_page],
                   meta={"page": page, "per_page": per_page, "total": total, "pages": max(1, -(-total // per_page))})


@bp.get("/<uid:consultation_id>")
@roles_required("patient", "doctor")
def get_consultation(consultation_id):
    """One consultation (only its patient and doctor; private notes are visible to the doctor only).
    ---
    tags: [Consultations]
    security: [{Bearer: []}]
    responses:
      200: {description: Consultation}
      404: {description: Not found}
    """
    return success(services.consultation_dict(services.get_visible(current_user(), consultation_id), current_user()))


@bp.get("/<uid:consultation_id>/messages")
@roles_required("patient", "doctor")
def get_messages(consultation_id):
    """Messages of a consultation (reading marks the other person's messages as read). Query: order=asc|desc, page, per_page.
    ---
    tags: [Consultations]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated messages}
      404: {description: Not found}
    """
    c = services.get_visible(current_user(), consultation_id)
    p = services.read_messages(current_user(), c, request.args.get("page", 1, int), request.args.get("per_page", 50, int),
                               request.args.get("order") == "desc")
    return success([services.message_dict(m) for m in p.items],
                   meta={"page": p.page, "per_page": p.per_page, "total": p.total, "pages": p.pages})


@bp.post("/<uid:consultation_id>/messages")
@roles_required("patient", "doctor")
@limiter.limit("120 per hour")
def send_message(consultation_id):
    """Send a text message (max 2000 characters). Closed consultations and unverified doctors cannot receive messages.
    ---
    tags: [Consultations]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema: {type: object, required: [body], properties: {body: {type: string}}}
    responses:
      201: {description: Sent}
      404: {description: Not found}
      409: {description: Closed, or doctor unavailable}
      422: {description: Empty or too long}
    """
    m = services.send(current_user(), consultation_id, MessageSchema().load(_json())["body"])
    return success(services.message_dict(m), "Message sent", 201)


@bp.route("/<uid:consultation_id>/clinical", methods=["PUT", "PATCH"])
@verified_doctor_required
def update_clinical(consultation_id):
    """Doctor: record private notes, diagnosis and treatment recommendations. The patient sees diagnosis and
    recommendations but never the private notes.
    ---
    tags: [Consultations]
    security: [{Bearer: []}]
    responses:
      200: {description: Saved}
      404: {description: Not found}
    """
    data = ClinicalSchema().load(_json(), partial=True)
    return success(services.consultation_dict(services.update_clinical(current_user(), consultation_id, data), current_user()), "Saved")


@bp.post("/<uid:consultation_id>/close")
@verified_doctor_required
def close_consultation(consultation_id):
    """Doctor: close the consultation (no more messages).
    ---
    tags: [Consultations]
    security: [{Bearer: []}]
    responses:
      200: {description: Closed}
      404: {description: Not found}
      409: {description: Already closed}
    """
    return success(services.consultation_dict(services.close(current_user(), consultation_id), current_user()), "Consultation closed")
