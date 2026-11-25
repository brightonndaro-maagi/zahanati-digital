from marshmallow import EXCLUDE, Schema, ValidationError, fields, validate, validates_schema

from app.common.timeutils import to_local


class _B(Schema):
    class Meta:
        unknown = EXCLUDE


class WindowSchema(_B):
    weekday = fields.Integer(required=True, validate=validate.Range(min=0, max=6))
    start_time = fields.Time(format="%H:%M", required=True)
    end_time = fields.Time(format="%H:%M", required=True)

    @validates_schema
    def _order(self, data, **kw):
        if "start_time" in data and "end_time" in data and data["end_time"] <= data["start_time"]:
            raise ValidationError("end_time must be after start_time.", "end_time")


class AvailabilitySchema(_B):
    windows = fields.List(fields.Nested(WindowSchema), required=True, validate=validate.Length(max=28))


class BookSchema(_B):
    doctor_id = fields.UUID(required=True)
    start_time = fields.DateTime(required=True, format="iso")
    reason = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=500))


class RescheduleSchema(_B):
    start_time = fields.DateTime(required=True, format="iso")


class NoteSchema(_B):
    note = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=255))


class AppointmentSchema(Schema):
    id = fields.String()
    status = fields.String()
    start_time = fields.Method("_start")
    end_time = fields.Method("_end")
    reason = fields.String()
    doctor_note = fields.String()
    cancel_reason = fields.String()
    doctor = fields.Method("_doctor")
    patient = fields.Method("_patient")
    created_at = fields.DateTime()

    def _start(self, a):
        return to_local(a.start_time).isoformat()

    def _end(self, a):
        return to_local(a.end_time).isoformat()

    def _doctor(self, a):
        return {"id": a.doctor.id, "first_name": a.doctor.first_name, "last_name": a.doctor.last_name}

    def _patient(self, a):
        return {"id": a.patient.id, "first_name": a.patient.first_name, "last_name": a.patient.last_name}
