from marshmallow import EXCLUDE, Schema, fields, validate


class _B(Schema):
    class Meta:
        unknown = EXCLUDE


class SpecialisationSchema(_B):
    id = fields.String(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=2, max=100))
    description = fields.String(allow_none=True, validate=validate.Length(max=255))


class CredentialSchema(_B):
    id = fields.String(dump_only=True)
    credential_type = fields.String(required=True, validate=validate.OneOf(["license", "qualification", "certificate"]))
    title = fields.String(required=True, validate=validate.Length(min=2, max=150))
    institution = fields.String(allow_none=True, validate=validate.Length(max=150))
    license_number = fields.String(allow_none=True, validate=validate.Length(min=3, max=60))
    issued_date = fields.Date(allow_none=True)
    expiry_date = fields.Date(allow_none=True)
    document_url = fields.Url(allow_none=True, schemes={"https"}, validate=validate.Length(max=500))
    created_at = fields.DateTime(dump_only=True)


class DoctorUpdateSchema(_B):
    first_name = fields.String(required=True, validate=validate.Length(min=1, max=80))
    last_name = fields.String(required=True, validate=validate.Length(min=1, max=80))
    bio = fields.String(allow_none=True, validate=validate.Length(max=3000))
    years_of_experience = fields.Integer(allow_none=True, validate=validate.Range(min=0, max=70))
    practice_location = fields.String(allow_none=True, validate=validate.Length(max=150))


class WorkplaceSchema(_B):
    id = fields.String(dump_only=True)
    institution = fields.String(required=True, validate=validate.Length(min=2, max=150))
    role = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=100))
    start_year = fields.Integer(allow_none=True, load_default=None, strict=True, validate=validate.Range(min=1950, max=2100))
    end_year = fields.Integer(allow_none=True, load_default=None, strict=True, validate=validate.Range(min=1950, max=2100))
    is_current = fields.Boolean(load_default=False)


class DoctorPublicSchema(_B):
    """What patients see: no credentials, no contact details, no verification internals."""
    id = fields.String()
    first_name = fields.String()
    last_name = fields.String()
    bio = fields.String()
    years_of_experience = fields.Integer()
    practice_location = fields.String()
    specialisations = fields.Nested(SpecialisationSchema, many=True)
    council = fields.String()
    verified_badge = fields.Method("_badge")
    workplaces = fields.Nested(WorkplaceSchema, many=True)

    def _badge(self, d):
        return d.can_practice


class DoctorPrivateSchema(DoctorPublicSchema):
    """What the doctor themself and admins see."""
    email = fields.String(attribute="user.email", allow_none=True)
    phone = fields.String(attribute="user.phone")
    is_active = fields.Boolean(attribute="user.is_active")
    verification_status = fields.String()
    license_status = fields.String()
    verified_name = fields.String()
    verified_at = fields.DateTime()
    rejection_reason = fields.String()
    credentials = fields.Nested(CredentialSchema, many=True)
