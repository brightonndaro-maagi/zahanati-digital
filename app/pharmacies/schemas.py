from marshmallow import EXCLUDE, Schema, fields, validate


class PharmacySchema(Schema):
    id = fields.String(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=2, max=150))
    license_number = fields.String(dump_only=True)
    address = fields.String(allow_none=True, validate=validate.Length(max=255))
    latitude = fields.Float(required=True, validate=validate.Range(min=-90, max=90))
    longitude = fields.Float(required=True, validate=validate.Range(min=-180, max=180))
    approval_status = fields.String(dump_only=True)
    rejection_reason = fields.String(dump_only=True)
    approved_at = fields.DateTime(dump_only=True)
    phone = fields.String(attribute="user.phone", dump_only=True)
    email = fields.String(attribute="user.email", dump_only=True)
    created_at = fields.DateTime(dump_only=True)

    class Meta:
        unknown = EXCLUDE


class PharmacyPublicSchema(Schema):
    """What customers see about an approved pharmacy."""
    id = fields.String()
    name = fields.String()
    address = fields.String()
    latitude = fields.Float()
    longitude = fields.Float()
