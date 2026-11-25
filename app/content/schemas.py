from marshmallow import EXCLUDE, Schema, fields, validate

LANG = validate.OneOf(["sw", "en"])
def steps():
    return fields.List(fields.String(validate=validate.Length(min=2, max=500)), required=True, validate=validate.Length(min=1, max=30))


class _Base(Schema):
    class Meta:
        unknown = EXCLUDE

    title = fields.String(required=True, validate=validate.Length(min=3, max=200))
    summary = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=500))
    body = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=30000))
    keywords = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=300))
    language = fields.String(load_default="sw", validate=LANG)


class FirstAidSchema(_Base):
    emergency_warning = fields.String(required=True, validate=validate.Length(min=5, max=2000))
    steps_to_do = steps()
    steps_to_avoid = steps()


class HealthEducationSchema(_Base):
    body = fields.String(required=True, validate=validate.Length(min=10, max=30000))
    stage = fields.Integer(required=True, strict=True, validate=validate.Range(min=1, max=8))


class PublishSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    reviewed_by_name = fields.String(required=True, validate=validate.Length(min=3, max=160))


SCHEMAS = {"first-aid": FirstAidSchema, "health-education": HealthEducationSchema}
