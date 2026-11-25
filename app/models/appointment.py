from app.extensions import db
from app.models.base import TimestampMixin, fk, uuid_pk

APPOINTMENT_STATUSES = ("pending", "accepted", "rejected", "cancelled", "completed")
ACTIVE_STATUSES = ("pending", "accepted")


class Appointment(TimestampMixin, db.Model):
    __tablename__ = "appointments"
    __table_args__ = (
        db.CheckConstraint("end_time > start_time", name="ck_appt_time_order"),
        db.CheckConstraint("status IN ('pending','accepted','rejected','cancelled','completed')", name="ck_appt_status"),
        # Hard DB guarantee against double-booking the same slot start (overlaps are checked in the service layer)
        db.Index("uq_doctor_active_slot", "doctor_id", "start_time", unique=True,
                 postgresql_where=db.text("status IN ('pending','accepted')"),
                 sqlite_where=db.text("status IN ('pending','accepted')")),
    )
    id = uuid_pk()
    patient_id = fk("patient_profiles.id", nullable=False, index=True)
    doctor_id = fk("doctor_profiles.id", nullable=False, index=True)
    start_time = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    end_time = db.Column(db.DateTime(timezone=True), nullable=False)
    status = db.Column(db.String(12), nullable=False, default="pending", index=True)
    reason = db.Column(db.String(500))
    doctor_note = db.Column(db.String(500))
    cancelled_by_user_id = fk("users.id", nullable=True)
    cancel_reason = db.Column(db.String(255))

    patient = db.relationship("PatientProfile")
    doctor = db.relationship("DoctorProfile")
