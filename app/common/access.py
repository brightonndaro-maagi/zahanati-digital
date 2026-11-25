from app.extensions import db
from app.models import Appointment, Consultation


def doctor_can_access_patient(doctor, patient_id):
    """A practising doctor may see a patient's medical data only when the patient has an accepted/completed
    appointment with them or has started a consultation with them (the patient's own choice to consult)."""
    if not doctor or not doctor.can_practice:
        return False
    pid = str(patient_id)
    if db.session.query(Appointment.id).filter(
            Appointment.doctor_id == doctor.id, Appointment.patient_id == pid,
            Appointment.status.in_(("accepted", "completed"))).first():
        return True
    return db.session.query(Consultation.id).filter(Consultation.doctor_id == doctor.id, Consultation.patient_id == pid).first() is not None
