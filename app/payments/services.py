import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from flask import current_app

from app.common.audit import log_action
from app.common.errors import APIError
from app.common.phone import normalize_phone
from app.common.timeutils import as_utc, utcnow
from app.extensions import db
from app.models import Medicine, Order, Payment, Refund
from app.notifications.services import notify
from app.orders.services import _locked, expire_due, get_visible, is_payable
from app.payments.providers import PaymentProviderError, get_provider


# ---------------- stock reservation ----------------
def _lock_medicines(order):
    ids = sorted(i.medicine_id for i in order.items)
    rows = Medicine.query.filter(Medicine.id.in_(ids)).order_by(Medicine.id).populate_existing().with_for_update().all()
    return {m.id: m for m in rows}  # locked in id order everywhere -> no deadlocks


def _reserve(order):
    meds = _lock_medicines(order)
    short = [i.medicine_name for i in order.items if i.medicine_id not in meds or not meds[i.medicine_id].is_active
             or meds[i.medicine_id].stock_quantity < i.quantity]
    if short:
        raise APIError("Some medicines are no longer available in the requested quantity", 409, {"items": short})
    for i in order.items:
        meds[i.medicine_id].stock_quantity -= i.quantity


def _release(order, payment):
    """Give the held stock back (only once per payment)."""
    if payment.stock_released:
        return
    meds = _lock_medicines(order)
    for i in order.items:
        if i.medicine_id in meds:
            meds[i.medicine_id].stock_quantity += i.quantity
    payment.stock_released = True


# ---------------- starting a payment ----------------
def start_payment(user, order_id, network, phone):
    cfg = current_app.config
    if network not in cfg["PAYMENT_NETWORKS"]:
        raise APIError(f"Payment network not supported. Use one of: {', '.join(cfg['PAYMENT_NETWORKS'])}", 422)
    payer = normalize_phone(phone) if phone else user.phone
    if not payer:
        raise APIError("A valid mobile money phone number is required", 422)
    order = get_visible(user, order_id)
    order = _locked(order.id)
    expire_due([Order.id == order.id])
    db.session.refresh(order)
    if order.payment_status == "pending":
        raise APIError("A payment for this order is already in progress", 409)
    if order.payment_status == "paid":
        raise APIError("This order has already been paid", 409)
    if not is_payable(order):
        reason = {"new": "The prescription must be approved before you can pay"}.get(order.status, f"The order is {order.status}")
        if order.status == "new" and order.prescription_status in ("required", "uploaded", "rejected"):
            reason = "The prescription must be approved before you can pay"
        raise APIError(reason, 409)
    _reserve(order)
    payment = Payment(order_id=order.id, amount_tzs=order.total_tzs, network=network, payer_phone=payer,
                      provider=cfg["PAYMENT_PROVIDER"], status="pending")
    db.session.add(payment)
    order.payment_status = "pending"
    db.session.flush()
    log_action("payment.started", user_id=user.id, entity_type="payment", entity_id=payment.id,
               details={"order_id": order.id, "amount_tzs": order.total_tzs, "network": network}, commit=False)
    db.session.commit()
    try:
        payment.provider_ref = get_provider().initiate(payment)
        db.session.commit()
    except PaymentProviderError as e:
        current_app.logger.error("Payment provider failure: %s", e)
        db.session.rollback()
        _fail(payment.id, "Provider could not start the payment")
        raise APIError("The payment service is unavailable. Please try again shortly.", 503)
    return payment


def _fail(payment_id, reason):
    payment = Payment.query.filter_by(id=payment_id).populate_existing().with_for_update().one()
    if payment.status != "pending":
        return payment
    order = _locked(payment.order_id)
    payment.status, payment.failure_reason = "failed", reason
    _release(order, payment)
    order.payment_status = "failed"
    notify(order.patient.user_id, "payment.failed", "Malipo yameshindwa. Unaweza kujaribu tena.", {"order_id": order.id, "reason": reason})
    log_action("payment.failed", entity_type="payment", entity_id=payment.id, details={"reason": reason}, commit=False)
    db.session.commit()
    return payment


# ---------------- protected callback ----------------
def sign(raw_body: bytes) -> str:
    return hmac.new(current_app.config["PAYMENT_CALLBACK_SECRET"].encode(), raw_body, hashlib.sha256).hexdigest()


def verify_signature(raw_body: bytes, header_value):
    secret = current_app.config.get("PAYMENT_CALLBACK_SECRET")
    if not secret or not header_value or not hmac.compare_digest(sign(raw_body), header_value.strip().lower()):
        raise APIError("Invalid callback signature", 401)


def handle_callback(data):
    payment = Payment.query.filter_by(provider_ref=data["provider_ref"]).populate_existing().with_for_update().first()
    if not payment:
        raise APIError("Unknown payment", 404)
    success = data["status"] == "success"
    if data.get("amount_tzs") is not None and data["amount_tzs"] != payment.amount_tzs:
        log_action("payment.amount_mismatch", entity_type="payment", entity_id=payment.id,
                   details={"expected": payment.amount_tzs, "got": data["amount_tzs"]})
        raise APIError("Amount does not match the payment", 422)
    if payment.status == "paid" or (payment.status == "failed" and not success and payment.paid_at is None):
        # duplicate delivery of an already-applied outcome: acknowledge without changing anything
        if (payment.status == "paid") == success:
            return payment, False
        log_action("payment.conflicting_callback", entity_type="payment", entity_id=payment.id, details={"status": data["status"]})
        raise APIError("Payment is already in a final state", 409)
    order = _locked(payment.order_id)
    if not success:
        return _fail(payment.id, data.get("reason") or "Payment was declined"), True
    # success: normal path, or a late success after our timeout marked it failed
    if payment.status == "failed":
        if order.status == "new" and payment.stock_released:
            try:
                _reserve(order)
                payment.stock_released = False
            except APIError:
                return _paid_without_order(payment, order), True
        else:
            return _paid_without_order(payment, order), True
    payment.status, payment.paid_at, payment.failure_reason = "paid", utcnow(), None
    order.payment_status = "paid"
    notify(order.pharmacy.user_id, "payment.received", "Malipo yamepokelewa. Unaweza kuandaa oda.", {"order_id": order.id})
    notify(order.patient.user_id, "payment.paid", "Malipo yako yamepokelewa.", {"order_id": order.id})
    log_action("payment.paid", entity_type="payment", entity_id=payment.id, commit=False)
    db.session.commit()
    return payment, True


def _paid_without_order(payment, order):
    """Money arrived but the order can no longer be fulfilled: keep the money visible and record a refund due."""
    payment.status, payment.paid_at, payment.failure_reason = "paid", utcnow(), "Late payment; order could not be fulfilled"
    db.session.add(Refund(order_id=order.id, payment_id=payment.id, amount_tzs=payment.amount_tzs,
                          reason="Payment arrived after the order could no longer be fulfilled"))
    notify(order.pharmacy.user_id, "refund.due", "Malipo yamefika kuchelewa kwa oda isiyoweza kutekelezwa. Rudisha fedha kwa mteja.", {"order_id": order.id})
    notify(order.patient.user_id, "refund.recorded", "Malipo yako yamefika kuchelewa. Utarudishiwa fedha.", {"order_id": order.id})
    log_action("payment.late_paid_refund_due", entity_type="payment", entity_id=payment.id, commit=False)
    db.session.commit()
    return payment


def expire_pending(limit=500):
    """Payments without any callback after PAYMENT_TIMEOUT_MINUTES are failed and their stock released."""
    cutoff = utcnow() - timedelta(minutes=current_app.config["PAYMENT_TIMEOUT_MINUTES"])
    ids = [p.id for p in Payment.query.filter(Payment.status == "pending", Payment.created_at <= cutoff).limit(limit).all()]
    for pid in ids:
        _fail(pid, "No confirmation received in time")
    return len(ids)


# ---------------- refunds ----------------
def refunded_total(order):
    return sum(r.amount_tzs for r in order.refunds)


def record_refund(user, order_id, amount, reason):
    order = get_visible(user, order_id)
    order = _locked(order.id)
    if user.pharmacy_profile.approval_status != "approved":
        raise APIError("Your pharmacy has not been approved yet", 403)
    paid = next((p for p in order.payments if p.status == "paid"), None)
    if order.payment_status != "paid" or not paid:
        raise APIError("Only paid orders can be refunded", 409)
    remaining = paid.amount_tzs - refunded_total(order)
    amount = remaining if amount is None else amount
    if amount <= 0 or amount > remaining:
        raise APIError(f"Refund must be between 1 and {remaining} TZS", 422)
    db.session.add(Refund(order_id=order.id, payment_id=paid.id, amount_tzs=amount, reason=reason, created_by_user_id=user.id))
    full = amount == remaining and refunded_total(order) == 0
    if amount == remaining and order.status in ("new", "ready"):
        # a fully refunded order that was not collected is cancelled and its stock goes back on the shelf
        meds = _lock_medicines(order)
        for i in order.items:
            if i.medicine_id in meds:
                meds[i.medicine_id].stock_quantity += i.quantity
        order.status, order.cancelled_at, order.cancelled_by_user_id, order.cancel_reason = "cancelled", utcnow(), user.id, f"Refunded: {reason}"
    notify(order.patient.user_id, "refund.recorded", f"Umerejeshewa TZS {amount}: {reason}.", {"order_id": order.id, "amount_tzs": amount})
    log_action("refund.recorded", user_id=user.id, entity_type="order", entity_id=order.id,
               details={"amount_tzs": amount, "reason": reason}, commit=False)
    db.session.commit()
    return order
