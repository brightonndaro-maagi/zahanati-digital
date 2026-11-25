"""One-time passwords: 6 digits, valid 5 min, single use, resend after 60 s,
5 wrong attempts lock the number for 10 min (all configurable)."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from flask import current_app

from app.common.audit import log_action
from app.common.errors import APIError
from app.common.sms import SMSError, get_gateway
from app.common.timeutils import as_utc, utcnow
from app.extensions import db
from app.models import OtpCode

PURPOSES = ("login", "register", "password_reset", "phone_change")
MESSAGES = {
    "login": "Zahanati Digital: msimbo wako wa kuingia ni {code}. Unaisha baada ya dakika {m}. Usimpe mtu yeyote.",
    "register": "Zahanati Digital: msimbo wako wa usajili ni {code}. Unaisha baada ya dakika {m}. Usimpe mtu yeyote.",
    "password_reset": "Zahanati Digital: msimbo wa kubadilisha nenosiri ni {code}. Unaisha baada ya dakika {m}. Usimpe mtu yeyote.",
    "phone_change": "Zahanati Digital: msimbo wa kuthibitisha namba mpya ni {code}. Unaisha baada ya dakika {m}. Usimpe mtu yeyote.",
}


MESSAGES_EN = {
    "login": "Zahanati Digital: your login code is {code}. It expires in {m} minutes. Do not share it.",
    "register": "Zahanati Digital: your registration code is {code}. It expires in {m} minutes. Do not share it.",
    "password_reset": "Zahanati Digital: your password reset code is {code}. It expires in {m} minutes. Do not share it.",
    "phone_change": "Zahanati Digital: your code to confirm the new number is {code}. It expires in {m} minutes. Do not share it.",
}


def _hash(phone, purpose, code):
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, f"{phone}|{purpose}|{code}".encode(), hashlib.sha256).hexdigest()


def _minutes_left(until, now):
    return max(1, int((as_utc(until) - now).total_seconds() // 60) + 1)


def issue(phone, purpose, lang="sw"):
    cfg, now = current_app.config, utcnow()
    last = (OtpCode.query.filter_by(phone=phone, purpose=purpose)
            .order_by(OtpCode.created_at.desc()).first())
    if last:
        if last.locked_until and as_utc(last.locked_until) > now:
            raise APIError(f"Too many wrong attempts. Try again in {_minutes_left(last.locked_until, now)} minute(s).", 429)
        wait = (as_utc(last.created_at) + timedelta(seconds=cfg["OTP_RESEND_SECONDS"]) - now).total_seconds()
        if wait > 0:
            raise APIError(f"Please wait {int(wait) + 1} seconds before requesting a new code.", 429)
    code = f"{secrets.randbelow(10 ** 6):06d}"
    row = OtpCode(phone=phone, purpose=purpose, code_hash=_hash(phone, purpose, code),
                  created_at=now, expires_at=now + timedelta(seconds=cfg["OTP_TTL_SECONDS"]))
    db.session.add(row)
    db.session.commit()
    try:
        get_gateway().send(phone, (MESSAGES_EN if lang == "en" else MESSAGES)[purpose].format(code=code, m=cfg["OTP_TTL_SECONDS"] // 60))
    except SMSError as e:
        current_app.logger.error("SMS delivery failed: %s", e)
        db.session.delete(row)  # do not penalise the user with the resend delay
        db.session.commit()
        raise APIError("We could not send the SMS right now. Please try again shortly.", 503)
    log_action("otp.requested", entity_type="otp", entity_id=row.id, details={"purpose": purpose})


def check(phone, purpose, code):
    """Validate a code WITHOUT consuming it; call consume() once the action succeeds."""
    cfg, now = current_app.config, utcnow()
    row = (OtpCode.query.filter_by(phone=phone, purpose=purpose, used_at=None)
           .order_by(OtpCode.created_at.desc()).populate_existing().with_for_update().first())
    if not row:
        raise APIError("Invalid or expired code.", 400)
    if row.locked_until and as_utc(row.locked_until) > now:
        raise APIError(f"Too many wrong attempts. Try again in {_minutes_left(row.locked_until, now)} minute(s).", 429)
    if as_utc(row.expires_at) < now:
        raise APIError("Invalid or expired code.", 400)
    if not hmac.compare_digest(row.code_hash, _hash(phone, purpose, code)):
        row.attempts += 1
        locked = row.attempts >= cfg["OTP_MAX_ATTEMPTS"]
        if locked:
            row.locked_until = now + timedelta(seconds=cfg["OTP_LOCK_SECONDS"])
            log_action("otp.locked", entity_type="otp", entity_id=row.id, details={"purpose": purpose}, commit=False)
        db.session.commit()
        if locked:
            raise APIError(f"Too many wrong attempts. Try again in {cfg['OTP_LOCK_SECONDS'] // 60} minutes.", 429)
        raise APIError("Invalid or expired code.", 400)
    return row


def consume(row):
    row.used_at = utcnow()
