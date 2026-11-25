from app.extensions import db
from app.models.base import TimestampMixin, fk, uuid_pk


class PatientProfile(TimestampMixin, db.Model):
    __tablename__ = "patient_profiles"
    id = uuid_pk()
    user_id = fk("users.id", nullable=False, unique=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(10))
    address = db.Column(db.String(255))
    region = db.Column(db.String(80))
    blood_group = db.Column(db.String(5))
    emergency_contact_name = db.Column(db.String(120))
    emergency_contact_phone = db.Column(db.String(20))

    user = db.relationship("User", back_populates="patient_profile")
    medical_records = db.relationship("MedicalRecord", back_populates="patient", cascade="all, delete-orphan")


class MedicalRecord(TimestampMixin, db.Model):
    __tablename__ = "medical_records"
    id = uuid_pk()
    patient_id = fk("patient_profiles.id", nullable=False, index=True)
    recorded_by_user_id = fk("users.id", nullable=True)
    record_type = db.Column(db.String(30), nullable=False)  # history, allergy, chronic_condition, surgery, immunisation, lab_result
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    record_date = db.Column(db.Date)

    patient = db.relationship("PatientProfile", back_populates="medical_records")
