from datetime import datetime, timezone

from app.common.audit import log_action
from app.extensions import db


def approve(pharmacy, admin):
    pharmacy.approval_status = "approved"
    pharmacy.approved_at = datetime.now(timezone.utc)
    pharmacy.approved_by_id = admin.id
    pharmacy.rejection_reason = None
    log_action("pharmacy.approved", user_id=admin.id, entity_type="pharmacy_profile", entity_id=pharmacy.id, commit=False)
    db.session.commit()


def reject(pharmacy, admin, reason):
    pharmacy.approval_status = "rejected"
    pharmacy.approved_at = None
    pharmacy.approved_by_id = admin.id
    pharmacy.rejection_reason = reason
    log_action("pharmacy.rejected", user_id=admin.id, entity_type="pharmacy_profile", entity_id=pharmacy.id,
               details={"reason": reason}, commit=False)
    db.session.commit()
