from app.extensions import db
from app.models.base import TimestampMixin, fk, uuid_pk


class PharmacyProfile(TimestampMixin, db.Model):
    __tablename__ = "pharmacy_profiles"
    __table_args__ = (db.CheckConstraint(
        "approval_status IN ('pending','approved','rejected')", name="ck_pharmacy_approval_status"),)

    id = uuid_pk()
    user_id = fk("users.id", nullable=False, unique=True)
    name = db.Column(db.String(150), nullable=False)
    license_number = db.Column(db.String(60), nullable=False, unique=True)
    address = db.Column(db.String(255))
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    approval_status = db.Column(db.String(10), nullable=False, default="pending", index=True)
    approved_at = db.Column(db.DateTime(timezone=True))
    approved_by_id = fk("users.id", nullable=True)
    rejection_reason = db.Column(db.String(255))

    user = db.relationship("User", back_populates="pharmacy_profile", foreign_keys=[user_id])
