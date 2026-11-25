import re
from datetime import timedelta

from flask import current_app

from app.common.audit import log_action
from app.common.errors import APIError
from app.common.timeutils import as_utc, to_local, utcnow
from app.consultations.services import get_visible as get_consultation
from app.extensions import db
from app.models import Order, Prescription, PrescriptionItem
from app.notifications.services import notify


def _iso(dt):
    return to_local(dt).isoformat() if dt else None


def valid_until(rx):
    return rx.issued_date + timedelta(days=current_app.config["PRESCRIPTION_VALID_DAYS"])


def license_number(rx):
    return next((c.license_number for c in rx.doctor.credentials if c.credential_type == "license" and c.license_number), None)


def prescription_dict(rx):
    return {
        "id": rx.id, "status": rx.status, "issued_date": rx.issued_date.isoformat(), "valid_until": valid_until(rx).isoformat(),
        "notes": rx.notes, "cancel_reason": rx.cancel_reason, "consultation_id": rx.consultation_id,
        "doctor": {"id": rx.doctor.id, "name": f"Dr. {rx.doctor.first_name} {rx.doctor.last_name}"},
        "patient": {"id": rx.patient.id, "name": f"{rx.patient.first_name} {rx.patient.last_name}"},
        "items": [{"medicine_name": i.medicine_name, "dosage": i.dosage, "frequency": i.frequency,
                   "duration_days": i.duration_days, "instructions": i.instructions} for i in rx.items],
        "created_at": _iso(rx.created_at),
    }


def get_visible(user, prescription_id):
    rx = db.session.get(Prescription, prescription_id)
    if rx:
        if user.role == "patient" and user.patient_profile and rx.patient_id == user.patient_profile.id:
            return rx
        if user.role == "doctor" and user.doctor_profile and rx.doctor_id == user.doctor_profile.id:
            return rx
    raise APIError("Prescription not found", 404)


def issue(user, consultation_id, data):
    c = get_consultation(user, consultation_id)
    c = db.session.query(type(c)).filter_by(id=c.id).populate_existing().with_for_update().one()
    if c.status != "open":
        raise APIError("Prescriptions can only be issued in an open consultation", 409)
    if not c.doctor.can_practice:
        raise APIError("Only verified doctors with an active licence can issue prescriptions", 403)
    rx = Prescription(consultation_id=c.id, patient_id=c.patient_id, doctor_id=c.doctor_id,
                      issued_date=to_local(utcnow()).date(), notes=data["notes"], status="active")
    for i in data["items"]:
        rx.items.append(PrescriptionItem(medicine_name=i["medicine_name"].strip(), dosage=i["dosage"].strip(),
                                         frequency=i["frequency"].strip(), duration_days=i["duration_days"],
                                         instructions=i["instructions"]))
    db.session.add(rx)
    db.session.flush()
    notify(c.patient.user_id, "prescription.issued", "Daktari amekuandikia agizo la dawa.", {"prescription_id": rx.id})
    log_action("prescription.issued", user_id=user.id, entity_type="prescription", entity_id=rx.id,
               details={"items": len(rx.items), "patient_id": rx.patient_id}, commit=False)
    db.session.commit()
    return rx


def cancel(user, prescription_id, reason):
    rx = get_visible(user, prescription_id)
    rx = db.session.query(Prescription).filter_by(id=rx.id).populate_existing().with_for_update().one()
    if user.role != "doctor":
        raise APIError("Only the issuing doctor can cancel a prescription", 403)
    if rx.status == "cancelled":
        raise APIError("The prescription is already cancelled", 409)
    rx.status, rx.cancelled_at, rx.cancel_reason = "cancelled", utcnow(), reason
    notify(rx.patient.user_id, "prescription.cancelled", "Daktari amefuta agizo la dawa.", {"prescription_id": rx.id, "reason": reason})
    log_action("prescription.cancelled", user_id=user.id, entity_type="prescription", entity_id=rx.id,
               details={"reason": reason}, commit=False)
    db.session.commit()
    return rx


# ---------------- using a prescription for an order ----------------
def _norm(text):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def _matches(rx_name, item_name, generic):
    """A prescription line covers an order item when the doctor wrote
    - the same name, or a less specific name contained in the item/generic name ("Amoxicillin" covers "Amoxicillin 500mg"), or
    - a more specific name that includes the item's full name ("Amoxicillin 500mg capsules" covers "Amoxicillin 500mg").
    A different strength never matches ("Amoxicillin 250mg" does not cover "Amoxicillin 500mg"), and the generic
    name alone is never allowed to widen a more specific prescription line."""
    r, name, gen = _norm(rx_name), _norm(item_name), _norm(generic)
    if not r:
        return False
    return r == name or r in name or (gen and r in gen) or (name and name in r)


def attach_to_order(user, order_id, prescription_id):
    from app.orders.services import _locked, expire_due, get_visible as get_order
    order = get_order(user, order_id)
    order = _locked(order.id)
    expire_due([Order.id == order.id])
    db.session.refresh(order)
    if order.status != "new":
        raise APIError(f"Cannot attach a prescription to an order that is {order.status}", 409)
    if order.prescription_status == "not_required":
        raise APIError("This order does not need a prescription", 409)
    if order.prescription_status in ("uploaded", "approved"):
        raise APIError("A prescription is already attached or waiting for review", 409)
    rx = get_visible(user, str(prescription_id))
    if rx.status != "active":
        raise APIError("This prescription has been cancelled", 409)
    if to_local(utcnow()).date() > valid_until(rx):
        raise APIError("This prescription has expired", 409)
    if not rx.doctor.can_practice:
        raise APIError("The issuing doctor is no longer verified", 409)
    taken = Order.query.filter(Order.e_prescription_id == rx.id, Order.id != order.id,
                               Order.status.notin_(("cancelled", "expired"))).first()
    if taken:
        raise APIError("This prescription has already been used for another order", 409)
    unmatched = [i.medicine_name for i in order.items if i.requires_prescription and not any(
        _matches(x.medicine_name, i.medicine_name, i.medicine.generic_name) for x in rx.items)]
    if unmatched:
        raise APIError("The prescription does not cover all medicines that need one", 422, {"unmatched_medicines": unmatched})
    order.e_prescription_id, order.prescription_status = rx.id, "approved"
    notify(order.pharmacy.user_id, "prescription.attached", "Agizo la kielektroniki la daktari limeambatishwa kwenye oda.", {"order_id": order.id})
    log_action("prescription.attached", user_id=user.id, entity_type="order", entity_id=order.id,
               details={"prescription_id": rx.id}, commit=False)
    db.session.commit()
    return order
