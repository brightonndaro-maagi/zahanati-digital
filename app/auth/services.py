from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.auth import otp
from app.auth.schemas import split_full_name
from app.common.audit import log_action
from app.common.errors import APIError
from app.extensions import db
from app.models import (DoctorCredential, DoctorProfile, PatientProfile, PharmacyProfile, Specialisation,
                        TokenBlocklist, User)


def _ensure_unique(phone, email):
    if User.query.filter_by(phone=phone).first():
        raise APIError("Phone number is already registered", 409)
    if email and User.query.filter(db.func.lower(User.email) == email.lower()).first():
        raise APIError("Email is already registered", 409)


def _save(user, action):
    db.session.add(user)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise APIError("Phone number or email is already registered", 409)
    log_action(action, user_id=user.id, entity_type="user", entity_id=user.id, commit=False)
    db.session.commit()
    return user


def create_patient(phone, full_name, language="sw"):
    """Patients have no password: they prove phone ownership with an OTP. Caller commits."""
    first, last = split_full_name(full_name)
    user = User(phone=phone, role="patient", language=language)
    user.patient_profile = PatientProfile(first_name=first, last_name=last)
    db.session.add(user)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise APIError("Phone number is already registered", 409)
    log_action("patient.register", user_id=user.id, entity_type="user", entity_id=user.id, commit=False)
    return user


def _staff_user(data, role):
    otp_row = otp.check(data["phone"], "register", data["otp_code"])  # proves the person owns the number
    _ensure_unique(data["phone"], data.get("email"))
    user = User(phone=data["phone"], email=data["email"].lower() if data.get("email") else None, role=role)
    user.set_password(data["password"])
    otp.consume(otp_row)
    return user


def register_doctor(data):
    from app.doctors.services import ensure_license_unique
    ensure_license_unique(data["license_number"])
    user = _staff_user(data, "doctor")
    specs = []
    if data.get("specialisation_ids"):
        ids = [str(i) for i in data["specialisation_ids"]]
        specs = Specialisation.query.filter(Specialisation.id.in_(ids)).all()
        if len(specs) != len(set(ids)):
            raise APIError("One or more specialisations do not exist", 422)
    profile = DoctorProfile(first_name=data["first_name"], last_name=data["last_name"], council=data.get("council", "tanganyika"),
                            years_of_experience=data.get("years_of_experience"), specialisations=specs)
    profile.credentials.append(DoctorCredential(
        credential_type="license", title="Medical practice licence", license_number=data["license_number"]))
    profile.credentials.append(DoctorCredential(
        credential_type="qualification", title=data["qualification"], institution=data.get("institution")))
    user.doctor_profile = profile
    return _save(user, "doctor.register")


def register_pharmacy(data):
    if PharmacyProfile.query.filter_by(license_number=data["license_number"]).first():
        raise APIError("A pharmacy with this licence number is already registered", 409)
    user = _staff_user(data, "pharmacy")
    user.pharmacy_profile = PharmacyProfile(
        name=data["name"], license_number=data["license_number"], address=data.get("address"),
        latitude=data["latitude"], longitude=data["longitude"])
    return _save(user, "pharmacy.register")


def authenticate(phone=None, email=None, password=None):
    q = User.query.filter_by(phone=phone) if phone else User.query.filter(db.func.lower(User.email) == email.lower())
    user = q.first()
    if not user or not user.check_password(password):
        log_action("auth.login_failed", details={"identifier": phone or email})
        raise APIError("Invalid credentials", 401)
    if not user.is_active:
        raise APIError("This account has been deactivated. Contact support.", 403)
    user.last_login_at = datetime.now(timezone.utc)
    log_action("auth.login", user_id=user.id, entity_type="user", entity_id=user.id, commit=False)
    db.session.commit()
    return user


def revoke_token(payload):
    db.session.add(TokenBlocklist(jti=payload["jti"], token_type=payload["type"],
                                  revoked_at=datetime.now(timezone.utc)))
    db.session.commit()


def reset_password(phone, code, new_password):
    row = otp.check(phone, "password_reset", code)
    user = User.query.filter_by(phone=phone).first()
    if not user or user.role == "patient" or not user.is_active:
        raise APIError("Invalid or expired code.", 400)
    user.set_password(new_password)
    user.tokens_valid_after = datetime.now(timezone.utc)
    otp.consume(row)
    log_action("auth.password_reset", user_id=user.id, entity_type="user", entity_id=user.id, commit=False)
    db.session.commit()


def confirm_phone_change(user, phone, code):
    row = otp.check(phone, "phone_change", code)
    if User.query.filter(User.phone == phone, User.id != user.id).first():
        raise APIError("Phone number is already registered", 409)
    old = user.phone
    user.phone = phone
    otp.consume(row)
    log_action("auth.phone_changed", user_id=user.id, entity_type="user", entity_id=user.id,
               details={"old": old}, commit=False)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise APIError("Phone number is already registered", 409)
