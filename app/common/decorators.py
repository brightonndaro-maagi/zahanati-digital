from functools import wraps
from flask import g
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
from app.common.errors import APIError
from app.extensions import db
from app.models.user import User


def tokens_revoked_for(user, claims):
    """Tokens issued before `tokens_valid_after` (password change/reset, deactivation) are no longer accepted."""
    from app.common.timeutils import as_utc
    if not user.tokens_valid_after:
        return False
    return claims.get("iat", 0) < int(as_utc(user.tokens_valid_after).timestamp())


def current_user():
    return g.current_user


def roles_required(*roles):
    """Require a valid JWT, an active account and one of the given roles."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            verify_jwt_in_request()
            user = db.session.get(User, get_jwt_identity())
            if not user or not user.is_active:
                raise APIError("Account not found or deactivated", 401)
            if tokens_revoked_for(user, get_jwt()):
                raise APIError("Your session has expired. Please log in again.", 401)
            if roles and user.role not in roles:
                raise APIError("You do not have permission to access this resource", 403)
            g.current_user = user
            return fn(*a, **kw)
        wrapper.required_roles = roles
        return wrapper
    return deco


def verified_doctor_required(fn):
    @wraps(fn)
    @roles_required("doctor")
    def wrapper(*a, **kw):
        profile = g.current_user.doctor_profile
        if not profile or not profile.can_practice:
            raise APIError("Only verified doctors can perform this action", 403)
        return fn(*a, **kw)
    wrapper.required_roles = ("doctor",)
    wrapper.requirement = "verified doctor with an active licence"
    return wrapper


def approved_pharmacy_required(fn):
    @wraps(fn)
    @roles_required("pharmacy")
    def wrapper(*a, **kw):
        profile = g.current_user.pharmacy_profile
        if not profile or profile.approval_status != "approved":
            raise APIError("Your pharmacy has not been approved yet", 403)
        return fn(*a, **kw)
    wrapper.required_roles = ("pharmacy",)
    wrapper.requirement = "approved pharmacy"
    return wrapper
