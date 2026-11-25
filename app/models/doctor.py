from app.extensions import db
from app.models.base import TimestampMixin, fk, uuid_pk

doctor_specialisations = db.Table(
    "doctor_specialisations",
    db.Column("doctor_id", db.Uuid(as_uuid=False), db.ForeignKey("doctor_profiles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("specialisation_id", db.Uuid(as_uuid=False), db.ForeignKey("specialisations.id", ondelete="CASCADE"), primary_key=True),
)


class Specialisation(db.Model):
    __tablename__ = "specialisations"
    id = uuid_pk()
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255))


class DoctorProfile(TimestampMixin, db.Model):
    __tablename__ = "doctor_profiles"
    __table_args__ = (db.CheckConstraint(
        "verification_status IN ('pending','verified','rejected')", name="ck_doctor_verification_status"),
        db.CheckConstraint("council IN ('tanganyika','zanzibar')", name="ck_doctor_council"),
        db.CheckConstraint("license_status IN ('active','expired')", name="ck_doctor_license_status"),)

    id = uuid_pk()
    user_id = fk("users.id", nullable=False, unique=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    bio = db.Column(db.Text)
    years_of_experience = db.Column(db.Integer)
    practice_location = db.Column(db.String(150))
    council = db.Column(db.String(12), nullable=False, default="tanganyika")  # registering council: tanganyika | zanzibar
    license_status = db.Column(db.String(10), nullable=False, default="active")  # active | expired (set by admin)
    verified_name = db.Column(db.String(160))  # name exactly as on the council register, entered by the admin
    verification_status = db.Column(db.String(10), nullable=False, default="pending", index=True)
    verified_at = db.Column(db.DateTime(timezone=True))
    verified_by_id = fk("users.id", nullable=True)
    rejection_reason = db.Column(db.String(255))

    user = db.relationship("User", back_populates="doctor_profile", foreign_keys=[user_id])
    specialisations = db.relationship("Specialisation", secondary=doctor_specialisations, backref="doctors")
    credentials = db.relationship("DoctorCredential", back_populates="doctor", cascade="all, delete-orphan")

    @property
    def can_practice(self):
        """Verified by an admin, licence not expired, account active: may be found, consulted and may prescribe."""
        return self.verification_status == "verified" and self.license_status == "active" and bool(self.user and self.user.is_active)


class DoctorCredential(TimestampMixin, db.Model):
    __tablename__ = "doctor_credentials"
    __table_args__ = (db.Index("uq_doctor_license_number", db.text("lower(license_number)"), unique=True,
                               postgresql_where=db.text("credential_type = 'license'"),
                               sqlite_where=db.text("credential_type = 'license'")),)
    id = uuid_pk()
    doctor_id = fk("doctor_profiles.id", nullable=False, index=True)
    credential_type = db.Column(db.String(20), nullable=False)  # license, qualification, certificate
    title = db.Column(db.String(150), nullable=False)
    institution = db.Column(db.String(150))
    license_number = db.Column(db.String(60))
    issued_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)
    document_url = db.Column(db.String(500))

    doctor = db.relationship("DoctorProfile", back_populates="credentials")


class DoctorAvailability(db.Model):
    """Recurring weekly working window (clinic local time). weekday: 0=Monday ... 6=Sunday."""
    __tablename__ = "doctor_availability"
    __table_args__ = (
        db.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_avail_weekday"),
        db.CheckConstraint("end_time > start_time", name="ck_avail_time_order"),
    )
    id = uuid_pk()
    doctor_id = fk("doctor_profiles.id", nullable=False, index=True)
    weekday = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    doctor = db.relationship("DoctorProfile", backref=db.backref(
        "availability", cascade="all, delete-orphan", order_by="DoctorAvailability.weekday"))


class DoctorWorkplace(db.Model):
    """Work history shown on the doctor's dashboard and public profile."""
    __tablename__ = "doctor_workplaces"
    id = uuid_pk()
    doctor_id = fk("doctor_profiles.id", nullable=False, index=True)
    institution = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(100))
    start_year = db.Column(db.Integer)
    end_year = db.Column(db.Integer)
    is_current = db.Column(db.Boolean, nullable=False, default=False)

    doctor = db.relationship("DoctorProfile", backref=db.backref(
        "workplaces", cascade="all, delete-orphan", order_by="DoctorWorkplace.start_year.desc()"))
