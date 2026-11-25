from datetime import date
from marshmallow import EXCLUDE, Schema, ValidationError, fields, validate, validates

from app.common.phone import PhoneField

RECORD_TYPES = ["history", "allergy", "chronic_condition", "surgery", "immunisation", "lab_result", "other"]


class PatientProfileSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.String(dump_only=True)
    email = fields.String(attribute="user.email", dump_only=True)
    phone = fields.String(attribute="user.phone", dump_only=True)  # change it via /auth/phone/change/*
    first_name = fields.String(required=True, validate=validate.Length(min=1, max=80))
    last_name = fields.String(required=True, validate=validate.Length(min=1, max=80))
    date_of_birth = fields.Date(allow_none=True)
    gender = fields.String(allow_none=True, validate=validate.OneOf(["male", "female", "other"]))
    address = fields.String(allow_none=True, validate=validate.Length(max=255))
    region = fields.String(allow_none=True, validate=validate.Length(max=80))
    blood_group = fields.String(allow_none=True, validate=validate.OneOf(["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]))
    emergency_contact_name = fields.String(allow_none=True, validate=validate.Length(max=120))
    emergency_contact_phone = PhoneField(allow_none=True)
    created_at = fields.DateTime(dump_only=True)

    @validates("date_of_birth")
    def _dob(self, v, **kw):
        if v and v > date.today():
            raise ValidationError("Date of birth cannot be in the future.")


class MedicalRecordSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.String(dump_only=True)
    record_type = fields.String(required=True, validate=validate.OneOf(RECORD_TYPES))
    title = fields.String(required=True, validate=validate.Length(min=1, max=150))
    description = fields.String(allow_none=True, validate=validate.Length(max=5000))
    record_date = fields.Date(allow_none=True)
    recorded_by_user_id = fields.String(dump_only=True)
    created_at = fields.DateTime(dump_only=True)

    @validates("record_date")
    def _d(self, v, **kw):
        if v and v > date.today():
            raise ValidationError("Record date cannot be in the future.")
