from datetime import datetime, timezone

from app.common.audit import log_action
from app.common.errors import APIError
from app.extensions import db
from app.models import DoctorCredential, Specialisation


def require_profile(user):
    if not user.doctor_profile:
        raise APIError("Doctor profile not found", 404)
    return user.doctor_profile


def reset_verification_if_needed(profile, user_id, reason):
    """Changing licence credentials of a verified doctor sends them back to review."""
    if profile.verification_status == "verified":
        profile.verification_status = "pending"
        profile.verified_at = None
        profile.verified_by_id = None
        log_action("doctor.verification_reset", user_id=user_id, entity_type="doctor_profile",
                   entity_id=profile.id, details={"reason": reason}, commit=False)


def set_specialisations(profile, ids):
    ids = {str(i) for i in ids}
    specs = Specialisation.query.filter(Specialisation.id.in_(ids)).all() if ids else []
    if len(specs) != len(ids):
        raise APIError("One or more specialisations do not exist", 422)
    profile.specialisations = specs


def ensure_license_unique(number, exclude_credential_id=None):
    q = DoctorCredential.query.filter(DoctorCredential.credential_type == "license",
                                      db.func.lower(DoctorCredential.license_number) == number.lower())
    if exclude_credential_id:
        q = q.filter(DoctorCredential.id != exclude_credential_id)
    if q.first():
        raise APIError("This licence number is already registered to another doctor", 409)


def verify(profile, admin, verified_name=None):
    if not any(c.credential_type == "license" and c.license_number for c in profile.credentials):
        raise APIError("Doctor has no licence credential to verify", 409)
    profile.verification_status = "verified"
    profile.verified_at = datetime.now(timezone.utc)
    profile.verified_by_id = admin.id
    profile.rejection_reason = None
    profile.license_status = "active"
    if verified_name:
        profile.verified_name = verified_name
    log_action("doctor.verified", user_id=admin.id, entity_type="doctor_profile", entity_id=profile.id,
               details={"verified_name": verified_name}, commit=False)
    db.session.commit()


def reject(profile, admin, reason):
    profile.verification_status = "rejected"
    profile.verified_at = None
    profile.verified_by_id = admin.id
    profile.rejection_reason = reason
    log_action("doctor.rejected", user_id=admin.id, entity_type="doctor_profile", entity_id=profile.id,
               details={"reason": reason}, commit=False)
    db.session.commit()


def set_license_status(profile, admin, status):
    old, profile.license_status = profile.license_status, status
    log_action("doctor.license_status", user_id=admin.id, entity_type="doctor_profile", entity_id=profile.id,
               details={"from": old, "to": status}, commit=False)
    db.session.commit()
