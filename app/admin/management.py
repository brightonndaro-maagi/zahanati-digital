from datetime import date, datetime, timedelta

from flask import Blueprint, request
from marshmallow import Schema, fields, validate

from app.common.audit import log_action
from app.common.decorators import current_user, roles_required
from app.common.errors import APIError
from app.common.responses import paginate, success
from app.common.timeutils import local_day_start_utc, to_local, utcnow
from app.common.validators import uuid_arg
from app.extensions import db
from app.medicines.services import like_pattern
from app.models import (Appointment, AuditLog, Consultation, DoctorProfile, FirstAidGuide, HealthEducation, Medicine, Order,
                        PatientProfile, Payment, PharmacyProfile, Prescription, Refund, User)

bp = Blueprint("admin_management", __name__)


def _json():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _page():
    return request.args.get("page", 1, int), request.args.get("per_page", 20, int)


def _iso(dt):
    return to_local(dt).isoformat() if dt else None


def _date_arg(name):
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise APIError(f"'{name}' must be a date in YYYY-MM-DD format", 422)


def _counts(column, query=None):
    q = db.session.query(column, db.func.count()).group_by(column)
    return {k: v for k, v in (query(q) if query else q).all()}


# ---------------- dashboard ----------------
@bp.get("/dashboard")
@roles_required("admin")
def dashboard():
    """Platform overview: users, approvals waiting, appointments, orders, payments, consultations, content and security signals.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Dashboard counters}
    """
    now = utcnow()
    d7, d30, h24 = now - timedelta(days=7), now - timedelta(days=30), now - timedelta(hours=24)
    roles = _counts(User.role)
    paid30 = db.session.query(db.func.count(Payment.id), db.func.coalesce(db.func.sum(Payment.amount_tzs), 0)).filter(
        Payment.status == "paid", Payment.paid_at >= d30).one()
    refunds30 = db.session.query(db.func.count(Refund.id), db.func.coalesce(db.func.sum(Refund.amount_tzs), 0)).filter(Refund.created_at >= d30).one()
    open_consults = Consultation.query.filter_by(status="open").all()
    from app.consultations.services import _due
    overdue = sum(1 for c in open_consults if c.awaiting_reply_since and _due(c)[1])
    return success({
        "generated_at": _iso(now),
        "users": {"total": sum(roles.values()), "by_role": {r: roles.get(r, 0) for r in ("patient", "doctor", "pharmacy", "admin")},
                  "active": User.query.filter_by(is_active=True).count(), "deactivated": User.query.filter_by(is_active=False).count(),
                  "new_last_7_days": User.query.filter(User.created_at >= d7).count()},
        "approvals_waiting": {
            "doctors": DoctorProfile.query.filter_by(verification_status="pending").count(),
            "pharmacies": PharmacyProfile.query.filter_by(approval_status="pending").count(),
            "first_aid_drafts": FirstAidGuide.query.filter_by(status="draft").count(),
            "health_education_drafts": HealthEducation.query.filter_by(status="draft").count()},
        "doctors": {**{k: DoctorProfile.query.filter_by(verification_status=k).count() for k in ("pending", "verified", "rejected")},
                    "licence_expired": DoctorProfile.query.filter_by(license_status="expired").count()},
        "pharmacies": {k: PharmacyProfile.query.filter_by(approval_status=k).count() for k in ("pending", "approved", "rejected")},
        "appointments": {"by_status": _counts(Appointment.status),
                         "upcoming_7_days": Appointment.query.filter(Appointment.status.in_(("pending", "accepted")),
                                                                      Appointment.start_time >= now, Appointment.start_time < now + timedelta(days=7)).count()},
        "orders": {"by_status": _counts(Order.status), "by_payment_status": _counts(Order.payment_status),
                   "prescriptions_waiting_review": Order.query.filter_by(prescription_status="uploaded").count()},
        "payments_last_30_days": {"paid_count": paid30[0], "paid_total_tzs": int(paid30[1]),
                                  "pending_now": Payment.query.filter_by(status="pending").count(),
                                  "refunds_count": refunds30[0], "refunds_total_tzs": int(refunds30[1])},
        "consultations": {"open": len(open_consults), "awaiting_reply": sum(1 for c in open_consults if c.awaiting_reply_since),
                          "overdue_replies": overdue, "prescriptions_issued_30d": Prescription.query.filter(Prescription.created_at >= d30).count()},
        "catalogue": {"medicines_active": Medicine.query.filter_by(is_active=True).count(),
                      "medicines_out_of_stock": Medicine.query.filter(Medicine.is_active.is_(True), Medicine.stock_quantity == 0).count()},
        "security": {"audit_events_24h": AuditLog.query.filter(AuditLog.created_at >= h24).count(),
                     "failed_logins_24h": AuditLog.query.filter(AuditLog.action == "auth.login_failed", AuditLog.created_at >= h24).count(),
                     "locked_otp_24h": AuditLog.query.filter(AuditLog.action == "otp.locked", AuditLog.created_at >= h24).count()},
    })


# ---------------- users ----------------
def _name(u):
    if u.pharmacy_profile:
        return u.pharmacy_profile.name
    p = u.patient_profile or u.doctor_profile
    return f"{p.first_name} {p.last_name}" if p else None


class _UserDump:
    @staticmethod
    def dump(users, many=False):
        return [{"id": u.id, "role": u.role, "name": _name(u), "phone": u.phone, "email": u.email, "is_active": u.is_active,
                 "created_at": _iso(u.created_at), "last_login_at": _iso(u.last_login_at)} for u in users]


@bp.get("/users")
@roles_required("admin")
def list_users():
    """Search and filter accounts. Query: role (patient|doctor|pharmacy|admin), is_active, q (phone, email or name), page, per_page.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated users}
      422: {description: Invalid filter}
    """
    a = request.args
    q = (User.query.outerjoin(PatientProfile, PatientProfile.user_id == User.id)
         .outerjoin(DoctorProfile, DoctorProfile.user_id == User.id).outerjoin(PharmacyProfile, PharmacyProfile.user_id == User.id))
    if a.get("role"):
        if a["role"] not in ("patient", "doctor", "pharmacy", "admin"):
            raise APIError("Invalid role filter", 422)
        q = q.filter(User.role == a["role"])
    if a.get("is_active") is not None:
        if a["is_active"].lower() not in ("true", "false", "1", "0"):
            raise APIError("is_active must be true or false", 422)
        q = q.filter(User.is_active.is_(a["is_active"].lower() in ("true", "1")))
    term = " ".join(a.get("q", "").split())
    if term:
        pat = like_pattern(term)
        cols = (User.phone, User.email, PatientProfile.first_name, PatientProfile.last_name, DoctorProfile.first_name,
                DoctorProfile.last_name, PharmacyProfile.name)
        q = q.filter(db.or_(*[c.ilike(pat, escape="\\") for c in cols]))
    items, meta = paginate(q.order_by(User.created_at.desc()), _UserDump, *_page())
    return success(items, meta=meta)


@bp.get("/users/<uid:user_id>")
@roles_required("admin")
def get_user(user_id):
    """One account with role-specific details (no passwords, chats or HEDHI data are ever exposed).
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: User}
      404: {description: Not found}
    """
    u = db.session.get(User, user_id)
    if not u:
        raise APIError("User not found", 404)
    d = _UserDump.dump([u])[0]
    if u.patient_profile:
        pid = u.patient_profile.id
        d["patient"] = {"id": pid, "appointments": Appointment.query.filter_by(patient_id=pid).count(),
                        "orders": Order.query.filter_by(patient_id=pid).count(), "consultations": Consultation.query.filter_by(patient_id=pid).count()}
    if u.doctor_profile:
        p = u.doctor_profile
        d["doctor"] = {"id": p.id, "verification_status": p.verification_status, "license_status": p.license_status, "council": p.council,
                       "consultations": Consultation.query.filter_by(doctor_id=p.id).count(), "prescriptions": Prescription.query.filter_by(doctor_id=p.id).count()}
    if u.pharmacy_profile:
        p = u.pharmacy_profile
        d["pharmacy"] = {"id": p.id, "approval_status": p.approval_status, "license_number": p.license_number,
                         "medicines": Medicine.query.filter_by(pharmacy_id=p.id).count(), "orders": Order.query.filter_by(pharmacy_id=p.id).count()}
    return success(d)


class _Reason(Schema):
    reason = fields.String(required=True, validate=validate.Length(min=3, max=255))


@bp.post("/users/<uid:user_id>/deactivate")
@roles_required("admin")
def deactivate(user_id):
    """Deactivate an account (blocks login and every token). Body: {reason}. You cannot deactivate yourself or the last active admin.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Deactivated}
      404: {description: Not found}
      409: {description: Not allowed (self / last admin / already deactivated)}
      422: {description: Reason required}
    """
    reason = _Reason().load(_json())["reason"]
    u = db.session.get(User, user_id)
    if not u:
        raise APIError("User not found", 404)
    if u.id == current_user().id:
        raise APIError("You cannot deactivate your own account", 409)
    if not u.is_active:
        raise APIError("The account is already deactivated", 409)
    if u.role == "admin" and User.query.filter(User.role == "admin", User.is_active.is_(True), User.id != u.id).count() == 0:
        raise APIError("You cannot deactivate the last active administrator", 409)
    u.is_active, u.tokens_valid_after = False, utcnow()
    log_action("admin.user_deactivated", user_id=current_user().id, entity_type="user", entity_id=u.id, details={"reason": reason}, commit=False)
    db.session.commit()
    return success(_UserDump.dump([u])[0], "Account deactivated")


@bp.post("/users/<uid:user_id>/activate")
@roles_required("admin")
def activate(user_id):
    """Reactivate an account (tokens issued before the deactivation stay invalid).
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Activated}
      404: {description: Not found}
      409: {description: Already active}
    """
    u = db.session.get(User, user_id)
    if not u:
        raise APIError("User not found", 404)
    if u.is_active:
        raise APIError("The account is already active", 409)
    u.is_active = True
    log_action("admin.user_activated", user_id=current_user().id, entity_type="user", entity_id=u.id, commit=False)
    db.session.commit()
    return success(_UserDump.dump([u])[0], "Account activated")


# ---------------- payments ----------------
class _PayDump:
    @staticmethod
    def dump(rows, many=False):
        return [{"id": p.id, "order_id": p.order_id, "amount_tzs": p.amount_tzs, "network": p.network, "payer_phone": p.payer_phone,
                 "status": p.status, "provider": p.provider, "provider_ref": p.provider_ref, "failure_reason": p.failure_reason,
                 "created_at": _iso(p.created_at), "paid_at": _iso(p.paid_at)} for p in rows]


@bp.get("/payments")
@roles_required("admin")
def list_payments():
    """All payments. Filters: status (pending|paid|failed), from_date, to_date, order_id, page, per_page.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated payments}
    """
    a, q = request.args, Payment.query
    if a.get("status"):
        if a["status"] not in ("pending", "paid", "failed"):
            raise APIError("Invalid status filter", 422)
        q = q.filter(Payment.status == a["status"])
    if a.get("order_id"):
        q = q.filter(Payment.order_id == uuid_arg(a["order_id"], "order_id"))
    if _date_arg("from_date"):
        q = q.filter(Payment.created_at >= local_day_start_utc(_date_arg("from_date")))
    if _date_arg("to_date"):
        q = q.filter(Payment.created_at < local_day_start_utc(_date_arg("to_date") + timedelta(days=1)))
    items, meta = paginate(q.order_by(Payment.created_at.desc()), _PayDump, *_page())
    return success(items, meta=meta)


class _RefundDump:
    @staticmethod
    def dump(rows, many=False):
        return [{"id": r.id, "order_id": r.order_id, "amount_tzs": r.amount_tzs, "reason": r.reason, "created_at": _iso(r.created_at),
                 "recorded_by": r.created_by_user_id} for r in rows]


@bp.get("/refunds")
@roles_required("admin")
def list_refunds():
    """All recorded refunds. Pagination: page, per_page.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated refunds}
    """
    items, meta = paginate(Refund.query.order_by(Refund.created_at.desc()), _RefundDump, *_page())
    return success(items, meta=meta)


# ---------------- audit log ----------------
class _AuditDump:
    @staticmethod
    def dump(rows, many=False):
        return [{"id": r.id, "action": r.action, "user_id": r.user_id, "entity_type": r.entity_type, "entity_id": r.entity_id,
                 "ip_address": r.ip_address, "details": r.details, "created_at": _iso(r.created_at)} for r in rows]


@bp.get("/audit-logs")
@roles_required("admin")
def audit_logs():
    """Audit trail of important operations, newest first. Filters: action (exact, or prefix with a trailing *), user_id,
    entity_type, entity_id, from_date, to_date, page, per_page.
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated audit entries}
      422: {description: Invalid filter}
    """
    a, q = request.args, AuditLog.query
    if a.get("action"):
        q = q.filter(AuditLog.action.like(a["action"][:-1].replace("%", "") + "%")) if a["action"].endswith("*") else q.filter(AuditLog.action == a["action"])
    if a.get("user_id"):
        q = q.filter(AuditLog.user_id == uuid_arg(a["user_id"], "user_id"))
    if a.get("entity_type"):
        q = q.filter(AuditLog.entity_type == a["entity_type"])
    if a.get("entity_id"):
        q = q.filter(AuditLog.entity_id == a["entity_id"])
    if _date_arg("from_date"):
        q = q.filter(AuditLog.created_at >= local_day_start_utc(_date_arg("from_date")))
    if _date_arg("to_date"):
        q = q.filter(AuditLog.created_at < local_day_start_utc(_date_arg("to_date") + timedelta(days=1)))
    items, meta = paginate(q.order_by(AuditLog.created_at.desc()), _AuditDump, *_page())
    return success(items, meta=meta)


@bp.get("/audit-logs/actions")
@roles_required("admin")
def audit_actions():
    """Distinct action names present in the audit log (for building filters).
    ---
    tags: [Admin]
    security: [{Bearer: []}]
    responses:
      200: {description: Action names}
    """
    return success(sorted(r[0] for r in db.session.query(AuditLog.action).distinct().all()))
