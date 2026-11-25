from datetime import timedelta

from flask import current_app
from sqlalchemy.orm import joinedload

from app.common import storage
from app.common.audit import log_action
from app.common.errors import APIError
from app.common.sms import SMSError, get_gateway
from app.common.timeutils import as_utc, to_local, utcnow
from app.extensions import db
from app.medicines.services import visible_query
from app.models import Medicine, Order, OrderItem, PrescriptionFile
from app.notifications.services import notify

UNPAID = ("unpaid", "failed")
RX_OK = ("not_required", "approved")
PDF, JPEG, PNG = b"%PDF-", b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n"


# ---------------- presentation ----------------
def is_payable(o):
    """Can the customer pay now? (used by the payment step)"""
    return (o.status == "new" and o.payment_status in UNPAID and o.prescription_status in RX_OK
            and as_utc(o.expires_at) > utcnow() and not _rx_cancelled(o))


def _rx_cancelled(o):
    return o.e_prescription is not None and o.e_prescription.status != "active"


def _iso(dt):
    return to_local(dt).isoformat() if dt else None


def _latest_file(o):
    files = [f for f in o.prescription_files]
    return files[-1] if files else None


def order_dict(o, role):
    f = _latest_file(o)
    d = {
        "id": o.id, "status": o.status, "payment_status": o.payment_status,
        "prescription_status": o.prescription_status, "total_tzs": o.total_tzs, "payable": is_payable(o),
        "expires_at": _iso(o.expires_at), "created_at": _iso(o.created_at), "ready_at": _iso(o.ready_at),
        "collected_at": _iso(o.collected_at), "cancel_reason": o.cancel_reason,
        "items": [{"medicine_id": i.medicine_id, "name": i.medicine_name, "quantity": i.quantity,
                   "unit_price_tzs": i.unit_price_tzs, "line_total_tzs": i.unit_price_tzs * i.quantity,
                   "requires_prescription": i.requires_prescription} for i in o.items],
        "pharmacy": {"id": o.pharmacy.id, "name": o.pharmacy.name, "address": o.pharmacy.address},
        "payment": next(({"id": p.id, "status": p.status, "network": p.network, "amount_tzs": p.amount_tzs,
                          "paid_at": _iso(p.paid_at), "failure_reason": p.failure_reason}
                         for p in reversed(o.payments)), None),
        "e_prescription": None if o.e_prescription is None else {
            "id": o.e_prescription.id, "status": o.e_prescription.status,
            "doctor": f"Dr. {o.e_prescription.doctor.first_name} {o.e_prescription.doctor.last_name}",
            "issued_date": o.e_prescription.issued_date.isoformat(),
            "items": [{"medicine_name": i.medicine_name, "dosage": i.dosage, "frequency": i.frequency,
                       "duration_days": i.duration_days} for i in o.e_prescription.items]},
        "refunds": [{"amount_tzs": r.amount_tzs, "reason": r.reason, "created_at": _iso(r.created_at)} for r in o.refunds],
        "prescription": None if o.prescription_status == "not_required" else {
            "status": o.prescription_status,
            "uploaded_at": _iso(f.uploaded_at) if f else None,
            "reviewed_at": _iso(f.reviewed_at) if f else None,
            "rejection_reason": f.rejection_reason if f and f.status == "rejected" else None,
            "file_available": bool(f and f.deleted_at is None),
        },
    }
    if role in ("pharmacy", "admin"):
        d["customer"] = {"id": o.patient.id, "full_name": f"{o.patient.first_name} {o.patient.last_name}"}
    return d


# ---------------- access ----------------
def get_visible(user, order_id):
    o = db.session.get(Order, order_id)
    if o:
        if user.role == "admin":
            return o
        if user.role == "patient" and user.patient_profile and o.patient_id == user.patient_profile.id:
            return o
        if user.role == "pharmacy" and user.pharmacy_profile and o.pharmacy_id == user.pharmacy_profile.id:
            return o
    raise APIError("Order not found", 404)


def _locked(order_id):
    return Order.query.filter_by(id=order_id).populate_existing().with_for_update().one()


def _sms(phone, text):
    """Best effort: a failed SMS must never fail the business action."""
    try:
        get_gateway().send(phone, text)
    except SMSError as e:
        current_app.logger.warning("Order SMS failed: %s", e)


# ---------------- expiry ----------------
def expire_due(extra_filters=(), limit=500):
    """Unpaid orders older than ORDER_EXPIRY_HOURS become 'expired'. Orders with a payment in progress
    ('pending') or already paid are never expired here."""
    now = utcnow()
    rows = (Order.query.filter(Order.status == "new", Order.payment_status.in_(UNPAID), Order.expires_at <= now, *extra_filters)
            .with_for_update(skip_locked=True).limit(limit).all())
    for o in rows:
        o.status = "expired"
        notify(o.patient.user_id, "order.expired", "Oda yako imeisha muda kwa sababu haikulipwa ndani ya saa 24.", {"order_id": o.id})
        log_action("order.expired", entity_type="order", entity_id=o.id, commit=False)
    if rows:
        db.session.commit()
    return len(rows)


# ---------------- create ----------------
def create_order(user, items):
    cfg = current_app.config
    if len(items) > cfg["ORDER_MAX_ITEMS"]:
        raise APIError(f"An order can contain at most {cfg['ORDER_MAX_ITEMS']} medicines", 422)
    ids = [str(i["medicine_id"]) for i in items]
    if len(set(ids)) != len(ids):
        raise APIError("Each medicine can appear only once in an order; increase its quantity instead", 422)
    for i in items:
        if i["quantity"] > cfg["ORDER_MAX_ITEM_QUANTITY"]:
            raise APIError(f"Quantity per medicine cannot exceed {cfg['ORDER_MAX_ITEM_QUANTITY']}", 422)
    found = {m.id: (m, p) for m, p in visible_query().filter(Medicine.id.in_(ids)).all()}
    missing = [i for i in ids if i not in found]
    if missing:
        raise APIError("One or more medicines were not found", 404, {"medicine_ids": missing})
    pharmacies = {p.id for _, p in found.values()}
    if len(pharmacies) > 1:
        raise APIError("An order can only contain medicines from one pharmacy", 422)
    problems = []
    for i in items:
        m, _ = found[str(i["medicine_id"])]
        if m.stock_quantity <= 0:
            problems.append({"medicine_id": m.id, "name": m.name, "reason": "out_of_stock"})
        elif m.stock_quantity < i["quantity"]:
            problems.append({"medicine_id": m.id, "name": m.name, "reason": "quantity_not_available"})
    if problems:
        raise APIError("Some medicines cannot be ordered", 409, {"items": problems})
    pharmacy = next(iter(found.values()))[1]
    needs_rx = any(found[str(i["medicine_id"])][0].requires_prescription for i in items)
    now = utcnow()
    order = Order(patient_id=user.patient_profile.id, pharmacy_id=pharmacy.id, status="new", payment_status="unpaid",
                  prescription_status="required" if needs_rx else "not_required",
                  expires_at=now + timedelta(hours=cfg["ORDER_EXPIRY_HOURS"]), total_tzs=0)
    total = 0
    for i in items:
        m, _ = found[str(i["medicine_id"])]
        order.items.append(OrderItem(medicine_id=m.id, medicine_name=m.name, unit_price_tzs=m.price_tzs,
                                     quantity=i["quantity"], requires_prescription=m.requires_prescription))
        total += m.price_tzs * i["quantity"]
    order.total_tzs = total
    db.session.add(order)
    db.session.flush()
    notify(pharmacy.user_id, "order.created", "Oda mpya imepokelewa.", {"order_id": order.id})
    log_action("order.created", user_id=user.id, entity_type="order", entity_id=order.id,
               details={"total_tzs": total, "items": len(items)}, commit=False)
    db.session.commit()
    return order


# ---------------- status changes ----------------
def change_status(user, order_id, action, reason=None):
    order = get_visible(user, order_id)
    order = _locked(order.id)
    expire_due([Order.id == order.id])
    db.session.refresh(order)
    if action == "cancel":
        return _cancel(user, order, reason)
    if user.role != "pharmacy":
        raise APIError("Only the pharmacy can do this", 403)
    if user.pharmacy_profile.approval_status != "approved":
        raise APIError("Your pharmacy has not been approved yet", 403)
    if action == "ready":
        if order.status != "new":
            raise APIError(f"Cannot mark an order that is {order.status} as ready", 409)
        if order.payment_status != "paid":
            raise APIError("The order has not been paid yet", 409)
        if order.prescription_status not in RX_OK:
            raise APIError("The prescription has not been approved yet", 409)
        if _rx_cancelled(order):
            raise APIError("The attached prescription was cancelled by the doctor", 409)
        order.status, order.ready_at = "ready", utcnow()
        notify(order.patient.user_id, "order.ready", "Oda yako iko tayari kuchukuliwa.", {"order_id": order.id})
        log_action("order.ready", user_id=user.id, entity_type="order", entity_id=order.id, commit=False)
        db.session.commit()
        en = order.patient.user.language == "en"
        _sms(order.patient.user.phone, f"Zahanati Digital: your order is ready for pickup at {order.pharmacy.name}." if en
             else f"Zahanati Digital: oda yako iko tayari kuchukuliwa katika {order.pharmacy.name}.")
    else:  # collect
        if order.status != "ready":
            raise APIError(f"Only a ready order can be collected (this one is {order.status})", 409)
        order.status, order.collected_at = "collected", utcnow()
        log_action("order.collected", user_id=user.id, entity_type="order", entity_id=order.id, commit=False)
        db.session.commit()
    return order


def _cancel(user, order, reason):
    if user.role not in ("patient", "pharmacy"):
        raise APIError("You cannot cancel this order", 403)
    if order.status != "new":
        raise APIError(f"Cannot cancel an order that is {order.status}", 409)
    if order.payment_status == "pending":
        raise APIError("A payment is in progress for this order. Please wait for it to finish.", 409)
    if order.payment_status == "paid":
        raise APIError("A paid order cannot be cancelled here. Paid orders are cancelled through a refund.", 409)
    order.status, order.cancelled_at, order.cancelled_by_user_id, order.cancel_reason = "cancelled", utcnow(), user.id, reason
    other = order.pharmacy.user_id if user.role == "patient" else order.patient.user_id
    notify(other, "order.cancelled", "Oda imeghairiwa.", {"order_id": order.id, "by": user.role})
    log_action("order.cancelled", user_id=user.id, entity_type="order", entity_id=order.id, commit=False)
    db.session.commit()
    return order


# ---------------- prescriptions ----------------
def detect_type(data):
    if data.startswith(PDF):
        return "application/pdf"
    if data.startswith(JPEG):
        return "image/jpeg"
    if data.startswith(PNG):
        return "image/png"
    return None


def upload_prescription(user, order_id, file_storage):
    order = get_visible(user, order_id)
    order = _locked(order.id)
    expire_due([Order.id == order.id])
    db.session.refresh(order)
    if order.status != "new":
        raise APIError(f"Cannot upload a prescription for an order that is {order.status}", 409)
    if order.prescription_status == "not_required":
        raise APIError("This order does not need a prescription", 409)
    if order.prescription_status == "uploaded":
        raise APIError("A prescription is already waiting for the pharmacy's review", 409)
    if order.prescription_status == "approved":
        raise APIError("The prescription has already been approved", 409)
    if file_storage is None or not file_storage.filename:
        raise APIError("Attach the prescription as form field 'file'", 422, {"file": ["Required."]})
    limit = current_app.config["PRESCRIPTION_MAX_BYTES"]
    data = file_storage.stream.read(limit + 1)
    if len(data) > limit:
        raise APIError(f"The file is too large (maximum {limit // (1024 * 1024)} MB)", 413)
    if not data:
        raise APIError("The file is empty", 422)
    content_type = detect_type(data)
    if not content_type:
        raise APIError("Only PDF, JPG or PNG files are accepted", 422, {"file": ["Unsupported file type."]})
    key = storage.save_encrypted(data)
    try:
        now = utcnow()
        db.session.add(PrescriptionFile(
            order_id=order.id, storage_key=key, content_type=content_type, size_bytes=len(data),
            uploaded_by_user_id=user.id, uploaded_at=now,
            expires_at=now + timedelta(days=current_app.config["PRESCRIPTION_RETENTION_DAYS"])))
        order.prescription_status = "uploaded"
        notify(order.pharmacy.user_id, "prescription.uploaded", "Agizo la daktari limepakiwa. Tafadhali lihakiki.", {"order_id": order.id})
        log_action("prescription.uploaded", user_id=user.id, entity_type="order", entity_id=order.id,
                   details={"content_type": content_type, "size_bytes": len(data)}, commit=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        storage.delete(key)
        raise
    return order


def read_prescription(user, order_id):
    """Only the pharmacy that received the order may read the prescription. Every read is audited."""
    order = get_visible(user, order_id)
    f = next((f for f in reversed(order.prescription_files) if f.deleted_at is None), None)
    if not f:
        raise APIError("No prescription file is available for this order", 404)
    data = storage.read_decrypted(f.storage_key)
    log_action("prescription.viewed", user_id=user.id, entity_type="order", entity_id=order.id)
    return data, f.content_type


def review_prescription(user, order_id, approve, reason=None):
    order = get_visible(user, order_id)
    order = _locked(order.id)
    if user.pharmacy_profile.approval_status != "approved":
        raise APIError("Your pharmacy has not been approved yet", 403)
    if order.status != "new":
        raise APIError(f"Cannot review a prescription for an order that is {order.status}", 409)
    if order.prescription_status != "uploaded":
        raise APIError("There is no prescription waiting for review", 409)
    f = next(f for f in reversed(order.prescription_files) if f.status == "uploaded")
    f.status = "approved" if approve else "rejected"
    f.reviewed_by_user_id, f.reviewed_at = user.id, utcnow()
    f.rejection_reason = None if approve else reason
    order.prescription_status = f.status
    if approve:
        notify(order.patient.user_id, "prescription.approved", "Agizo lako la daktari limeidhinishwa. Sasa unaweza kulipa.", {"order_id": order.id})
    else:
        notify(order.patient.user_id, "prescription.rejected", f"Agizo lako la daktari limekataliwa: {reason}. Tafadhali pakia tena.",
               {"order_id": order.id, "reason": reason})
    log_action("prescription.approved" if approve else "prescription.rejected", user_id=user.id,
               entity_type="order", entity_id=order.id, commit=False)
    db.session.commit()
    return order


def purge_expired_prescriptions():
    """Retention: files older than PRESCRIPTION_RETENTION_DAYS are removed from disk."""
    now = utcnow()
    rows = PrescriptionFile.query.filter(PrescriptionFile.deleted_at.is_(None), PrescriptionFile.expires_at <= now).all()
    for f in rows:
        storage.delete(f.storage_key)
        f.deleted_at, f.storage_key = now, None
        log_action("prescription.purged", entity_type="order", entity_id=f.order_id, commit=False)
    if rows:
        db.session.commit()
    return len(rows)


def list_query(user):
    q = Order.query.options(joinedload(Order.items), joinedload(Order.pharmacy), joinedload(Order.patient))
    if user.role == "patient":
        return q.filter(Order.patient_id == user.patient_profile.id)
    if user.role == "pharmacy":
        return q.filter(Order.pharmacy_id == user.pharmacy_profile.id)
    return q
