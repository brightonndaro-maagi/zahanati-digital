from app.extensions import db
from app.models.base import TimestampMixin, fk, utcnow, uuid_pk


class Consultation(TimestampMixin, db.Model):
    __tablename__ = "consultations"
    __table_args__ = (db.CheckConstraint("status IN ('open','closed')", name="ck_consultation_status"),)
    id = uuid_pk()
    appointment_id = fk("appointments.id", nullable=True, unique=True)  # optional link (chat consultations have none)
    status = db.Column(db.String(10), nullable=False, default="open", index=True)  # open | closed
    subject = db.Column(db.String(150))
    last_message_at = db.Column(db.DateTime(timezone=True))
    awaiting_reply_since = db.Column(db.DateTime(timezone=True))  # set by a patient message, cleared by the doctor's reply
    closed_at = db.Column(db.DateTime(timezone=True))
    patient_id = fk("patient_profiles.id", nullable=False, index=True)
    doctor_id = fk("doctor_profiles.id", nullable=False, index=True)
    notes = db.Column(db.Text)
    diagnosis = db.Column(db.Text)
    treatment_recommendations = db.Column(db.Text)
    # Extension points for future video consultation (not used in MVP)
    mode = db.Column(db.String(20), nullable=False, default="in_person")
    external_session_ref = db.Column(db.String(255))

    appointment = db.relationship("Appointment")
    messages = db.relationship("ConsultationMessage", back_populates="consultation", order_by="ConsultationMessage.created_at")
    patient = db.relationship("PatientProfile")
    doctor = db.relationship("DoctorProfile")


class ConsultationMessage(db.Model):
    """Text-only chat message. Visible to the patient and the doctor of the consultation only."""
    __tablename__ = "consultation_messages"
    __table_args__ = (db.Index("ix_msg_consultation_created", "consultation_id", "created_at"),)
    id = uuid_pk()
    consultation_id = fk("consultations.id", nullable=False)
    sender_user_id = fk("users.id", nullable=False)
    sender_role = db.Column(db.String(10), nullable=False)  # patient | doctor
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    read_at = db.Column(db.DateTime(timezone=True))

    consultation = db.relationship("Consultation", back_populates="messages")
