from werkzeug.security import check_password_hash, generate_password_hash
from app.extensions import db
from app.models.base import TimestampMixin, uuid_pk

ROLES = ("patient", "doctor", "pharmacy", "admin")


class User(TimestampMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (db.CheckConstraint("role IN ('patient','doctor','pharmacy','admin')", name="ck_users_role"),)

    id = uuid_pk()
    # Phone is the primary identifier (OTP login for patients, phone+password for staff). Email is optional.
    email = db.Column(db.String(255), unique=True, nullable=True, index=True)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)  # patients log in with OTP and have no password
    role = db.Column(db.String(10), nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True))
    language = db.Column(db.String(2), nullable=False, default="sw")  # sw | en (SMS and notification language)
    tokens_valid_after = db.Column(db.DateTime(timezone=True))  # tokens issued before this are rejected (password change, deactivation)

    patient_profile = db.relationship("PatientProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    pharmacy_profile = db.relationship("PharmacyProfile", back_populates="user", uselist=False, cascade="all, delete-orphan",
                                       foreign_keys="PharmacyProfile.user_id")
    doctor_profile = db.relationship("DoctorProfile", back_populates="user", uselist=False, cascade="all, delete-orphan",
                                     foreign_keys="DoctorProfile.user_id")

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw, method="scrypt")

    def check_password(self, raw):
        return bool(self.password_hash) and check_password_hash(self.password_hash, raw)


class TokenBlocklist(db.Model):
    """Revoked JWTs (logout)."""
    __tablename__ = "token_blocklist"
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), unique=True, nullable=False, index=True)
    token_type = db.Column(db.String(10), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=False)
