from app.extensions import db
from app.models.base import uuid_pk, utcnow


class OtpCode(db.Model):
    """One-time codes. Only an HMAC of the code is stored, never the code itself."""
    __tablename__ = "otp_codes"
    __table_args__ = (db.Index("ix_otp_lookup", "phone", "purpose", "created_at"),)

    id = uuid_pk()
    phone = db.Column(db.String(20), nullable=False)
    purpose = db.Column(db.String(20), nullable=False)  # login | register | password_reset | phone_change
    code_hash = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True))
    attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
