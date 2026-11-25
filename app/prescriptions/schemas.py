from marshmallow import EXCLUDE, Schema, fields, validate


class _B(Schema):
    class Meta:
        unknown = EXCLUDE


class ItemSchema(_B):
    medicine_name = fields.String(required=True, validate=validate.Length(min=2, max=150))
    dosage = fields.String(required=True, validate=validate.Length(min=1, max=80))
    frequency = fields.String(required=True, validate=validate.Length(min=1, max=80))
    duration_days = fields.Integer(required=True, strict=True, validate=validate.Range(min=1, max=365))
    instructions = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=255))


class IssueSchema(_B):
    items = fields.List(fields.Nested(ItemSchema), required=True, validate=validate.Length(min=1, max=20))
    notes = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=1000))


class CancelSchema(_B):
    reason = fields.String(required=True, validate=validate.Length(min=3, max=255))


class UseSchema(_B):
    prescription_id = fields.UUID(required=True)
