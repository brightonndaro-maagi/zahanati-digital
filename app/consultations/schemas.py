from marshmallow import EXCLUDE, Schema, fields, validate


class _B(Schema):
    class Meta:
        unknown = EXCLUDE


class StartSchema(_B):
    doctor_id = fields.UUID(required=True)
    subject = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=150))
    message = fields.String(required=True, validate=validate.Length(min=1))


class MessageSchema(_B):
    body = fields.String(required=True, validate=validate.Length(min=1))


class ClinicalSchema(_B):
    notes = fields.String(allow_none=True, validate=validate.Length(max=10000))
    diagnosis = fields.String(allow_none=True, validate=validate.Length(max=5000))
    treatment_recommendations = fields.String(allow_none=True, validate=validate.Length(max=5000))
