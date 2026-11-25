from app.extensions import db
from app.models.base import TimestampMixin, fk, uuid_pk


class Prescription(TimestampMixin, db.Model):
    __tablename__ = "prescriptions"
    __table_args__ = (db.CheckConstraint("status IN ('active','cancelled')", name="ck_prescription_status"),)
    id = uuid_pk()
    consultation_id = fk("consultations.id", nullable=False, index=True)
    patient_id = fk("patient_profiles.id", nullable=False, index=True)
    doctor_id = fk("doctor_profiles.id", nullable=False, index=True)
    issued_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    status = db.Column(db.String(10), nullable=False, default="active")  # active | cancelled (prescriptions are never edited)
    cancelled_at = db.Column(db.DateTime(timezone=True))
    cancel_reason = db.Column(db.String(255))

    consultation = db.relationship("Consultation")
    patient = db.relationship("PatientProfile")
    doctor = db.relationship("DoctorProfile")
    items = db.relationship("PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan")


class PrescriptionItem(db.Model):
    __tablename__ = "prescription_items"
    id = uuid_pk()
    prescription_id = fk("prescriptions.id", nullable=False, index=True)
    medicine_name = db.Column(db.String(150), nullable=False)
    dosage = db.Column(db.String(80), nullable=False)
    frequency = db.Column(db.String(80), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    instructions = db.Column(db.String(255))

    prescription = db.relationship("Prescription", back_populates="items")
