from flask import Blueprint, current_app, request
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt, get_jwt_identity, jwt_required

from app.auth import otp, services
from app.auth.schemas import (ChangePasswordSchema, ForgotPasswordSchema, LoginSchema, OtpRequestSchema,
                              OtpVerifySchema, PhoneChangeConfirmSchema, PhoneChangeRequestSchema,
                              RegisterDoctorSchema, RegisterPharmacySchema, ResetPasswordSchema, UserSchema)
from app.common.audit import log_action
from app.common.decorators import current_user, roles_required, tokens_revoked_for
from app.common.errors import APIError
from app.common.i18n import get_lang
from app.common.responses import success
from app.common.timeutils import utcnow
from app.extensions import db, limiter
from app.models import User

bp = Blueprint("auth", __name__)
user_schema = UserSchema()


def _tokens(user):
    claims = {"role": user.role}
    return {
        "access_token": create_access_token(identity=str(user.id), additional_claims=claims),
        "refresh_token": create_refresh_token(identity=str(user.id), additional_claims=claims),
        "token_type": "Bearer",
    }


def _json():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    return body


def _otp_info():
    c = current_app.config
    return {"expires_in": c["OTP_TTL_SECONDS"], "resend_after": c["OTP_RESEND_SECONDS"]}


# ---------------- patients: OTP ----------------
@bp.post("/otp/request")
@limiter.limit("20 per hour")
def otp_request():
    """Send a 6-digit code by SMS. purpose=login (patients, default) or register (doctors/pharmacies before registering).
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [phone]
          properties:
            phone: {type: string, example: "0712345678"}
            purpose: {type: string, enum: [login, register]}
    responses:
      200: {description: Request accepted (the response never reveals whether the number is registered)}
      422: {description: Invalid phone number}
      429: {description: Resend too soon, or number locked after wrong attempts}
      503: {description: SMS could not be sent}
    """
    data = OtpRequestSchema().load(_json())
    phone, purpose = data["phone"], data["purpose"]
    existing = User.query.filter_by(phone=phone).first()
    if purpose == "login":
        send = existing is None or existing.role == "patient"  # staff accounts use passwords
    else:
        send = existing is None
    if send:
        otp.issue(phone, purpose, data["lang"] or get_lang(default="sw"))
    return success(_otp_info(), "If the number can receive a code, an SMS has been sent.")


@bp.post("/otp/verify")
@limiter.limit("30 per hour")
def otp_verify():
    """Verify the code. Existing patients are logged in. For a new number the first call returns
    registration_required=true (the code is not consumed); call again with full_name to create the account.
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [phone, code]
          properties:
            phone: {type: string}
            code: {type: string, example: "123456"}
            full_name: {type: string, example: "Asha Juma"}
    responses:
      200: {description: Logged in, or registration_required}
      400: {description: Invalid or expired code}
      403: {description: Staff number (use password login) or deactivated account}
      422: {description: Validation failed}
      429: {description: Too many wrong attempts}
    """
    data = OtpVerifySchema().load(_json())
    phone = data["phone"]
    row = otp.check(phone, "login", data["code"])
    user = User.query.filter_by(phone=phone).first()
    created = False
    if user:
        if user.role != "patient":
            raise APIError("This number belongs to a professional account. Please log in with your password.", 403)
        if not user.is_active:
            raise APIError("This account has been deactivated. Contact support.", 403)
    else:
        if not data["full_name"]:
            return success({"registration_required": True},
                           "Code accepted. Please provide your full name to finish registration.")
        user, created = services.create_patient(phone, data["full_name"], get_lang(default="sw")), True
    otp.consume(row)
    user.last_login_at = utcnow()
    log_action("auth.login", user_id=user.id, entity_type="user", entity_id=user.id, commit=False)
    db.session.commit()
    return success({"user": user_schema.dump(user), "is_new_user": created, **_tokens(user)},
                   "Account created" if created else "Login successful", 201 if created else 200)


# ---------------- doctors / pharmacies ----------------
@bp.post("/register/doctor")
@limiter.limit("10 per hour")
def register_doctor():
    """Register a doctor. First call /auth/otp/request with purpose=register, then send the code as otp_code.
    Status starts as 'pending' until an admin verifies the MCT licence.
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [phone, otp_code, password, first_name, last_name, license_number, qualification]
          properties:
            phone: {type: string}
            otp_code: {type: string}
            password: {type: string}
            email: {type: string}
            first_name: {type: string}
            last_name: {type: string}
            license_number: {type: string, example: MCT-12345}
            qualification: {type: string, example: MD}
            specialisation_ids: {type: array, items: {type: string}}
    responses:
      201: {description: Doctor created, pending verification}
      400: {description: Invalid or expired code}
      409: {description: Phone, email already registered}
      422: {description: Validation failed}
    """
    user = services.register_doctor(RegisterDoctorSchema().load(_json()))
    return success({"user": user_schema.dump(user), **_tokens(user)},
                   "Doctor registered. Awaiting administrator verification.", 201)


@bp.post("/register/pharmacy")
@limiter.limit("10 per hour")
def register_pharmacy():
    """Register a pharmacy (hidden from customers until an admin approves it).
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [phone, otp_code, password, name, license_number, latitude, longitude]
          properties:
            phone: {type: string}
            otp_code: {type: string}
            password: {type: string}
            email: {type: string}
            name: {type: string}
            license_number: {type: string}
            address: {type: string}
            latitude: {type: number, example: -6.7924}
            longitude: {type: number, example: 39.2083}
    responses:
      201: {description: Pharmacy created, pending approval}
      400: {description: Invalid or expired code}
      409: {description: Phone, email or licence already registered}
      422: {description: Validation failed}
    """
    user = services.register_pharmacy(RegisterPharmacySchema().load(_json()))
    return success({"user": user_schema.dump(user), **_tokens(user)},
                   "Pharmacy registered. Awaiting administrator approval.", 201)


@bp.post("/login")
@limiter.limit("10 per minute")
def login():
    """Password login for doctors, pharmacies and admins (patients use /auth/otp/*).
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [password]
          properties:
            phone: {type: string}
            email: {type: string, description: "alternative to phone"}
            password: {type: string}
    responses:
      200: {description: Logged in}
      401: {description: Invalid credentials}
      403: {description: Account deactivated}
    """
    data = LoginSchema().load(_json())
    user = services.authenticate(data["phone"], data["email"], data["password"])
    return success({"user": user_schema.dump(user), **_tokens(user)}, "Login successful")


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    """Exchange a refresh token for a new access token.
    ---
    tags: [Auth]
    security: [{Bearer: []}]
    responses:
      200: {description: New access token}
      401: {description: Invalid, expired or revoked refresh token}
    """
    user = db.session.get(User, get_jwt_identity())
    if not user or not user.is_active or tokens_revoked_for(user, get_jwt()):
        raise APIError("Account not found, deactivated, or the session has expired", 401)
    token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    return success({"access_token": token, "token_type": "Bearer"}, "Token refreshed")


@bp.post("/logout")
@jwt_required(verify_type=False)
def logout():
    """Revoke the presented token (send the refresh token too to fully log out).
    ---
    tags: [Auth]
    security: [{Bearer: []}]
    responses:
      200: {description: Token revoked}
    """
    services.revoke_token(get_jwt())
    return success(message="Logged out")


@bp.post("/forgot-password")
@limiter.limit("5 per hour")
def forgot_password():
    """Send a reset code by SMS to a doctor/pharmacy/admin account (always answers 200 to avoid account enumeration).
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        required: true
        schema: {type: object, required: [phone], properties: {phone: {type: string}}}
    responses:
      200: {description: Request accepted}
    """
    phone = ForgotPasswordSchema().load(_json())["phone"]
    user = User.query.filter_by(phone=phone).first()
    if user and user.role != "patient" and user.is_active:
        try:
            otp.issue(phone, "password_reset")
        except APIError as e:
            if e.status != 429:
                raise
    return success(_otp_info(), "If the account exists, a reset code has been sent by SMS.")


@bp.post("/reset-password")
@limiter.limit("10 per hour")
def reset_password():
    """Set a new password using the SMS code.
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [phone, code, new_password]
          properties: {phone: {type: string}, code: {type: string}, new_password: {type: string}}
    responses:
      200: {description: Password updated}
      400: {description: Invalid or expired code}
      429: {description: Too many wrong attempts}
    """
    data = ResetPasswordSchema().load(_json())
    services.reset_password(data["phone"], data["code"], data["new_password"])
    return success(message="Password has been reset")


@bp.get("/me")
@roles_required()
def me():
    """Current authenticated user.
    ---
    tags: [Auth]
    security: [{Bearer: []}]
    responses:
      200: {description: Current user}
      401: {description: Unauthenticated}
    """
    return success(user_schema.dump(current_user()))


@bp.post("/change-password")
@roles_required("doctor", "pharmacy", "admin")
@limiter.limit("5 per minute")
def change_password():
    """Change password (doctors, pharmacies, admins).
    ---
    tags: [Auth]
    security: [{Bearer: []}]
    responses:
      200: {description: Password changed}
      400: {description: Current password incorrect}
      403: {description: Patients have no password}
    """
    data = ChangePasswordSchema().load(_json())
    user = current_user()
    if not user.check_password(data["current_password"]):
        raise APIError("Current password is incorrect", 400)
    user.set_password(data["new_password"])
    user.tokens_valid_after = utcnow()   # every other session must log in again
    log_action("auth.password_changed", user_id=user.id, entity_type="user", entity_id=user.id, commit=False)
    db.session.commit()
    return success({**_tokens(user)}, "Password changed. All other sessions have been signed out.")


# ---------------- change phone number ----------------
@bp.post("/phone/change/request")
@roles_required()
@limiter.limit("5 per hour")
def phone_change_request():
    """Send a code to a NEW phone number to prove you own it.
    ---
    tags: [Auth]
    security: [{Bearer: []}]
    responses:
      200: {description: Code sent}
      409: {description: Number already registered}
    """
    phone = PhoneChangeRequestSchema().load(_json())["phone"]
    if User.query.filter_by(phone=phone).first():
        raise APIError("Phone number is already registered", 409)
    otp.issue(phone, "phone_change")
    return success(_otp_info(), "A code has been sent to the new number.")


@bp.post("/phone/change/confirm")
@roles_required()
@limiter.limit("10 per hour")
def phone_change_confirm():
    """Confirm the new phone number with the SMS code.
    ---
    tags: [Auth]
    security: [{Bearer: []}]
    responses:
      200: {description: Phone number changed}
      400: {description: Invalid or expired code}
      409: {description: Number already registered}
    """
    data = PhoneChangeConfirmSchema().load(_json())
    services.confirm_phone_change(current_user(), data["phone"], data["code"])
    return success(user_schema.dump(current_user()), "Phone number updated")


@bp.patch("/me/language")
@roles_required()
def set_language():
    """Choose the language of your SMS messages and notifications (sw|en).
    ---
    tags: [Auth]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema: {type: object, required: [language], properties: {language: {type: string, enum: [sw, en]}}}
    responses:
      200: {description: Saved}
      422: {description: Unsupported language}
    """
    lang = _json().get("language")
    if lang not in ("sw", "en"):
        raise APIError("language must be 'sw' or 'en'", 422)
    current_user().language = lang
    db.session.commit()
    return success(user_schema.dump(current_user()), "Updated")
