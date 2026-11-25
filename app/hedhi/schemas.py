from datetime import date

from marshmallow import EXCLUDE, Schema, ValidationError, fields, validate, validates, validates_schema


class CycleSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    start_date = fields.Date(required=True)
    end_date = fields.Date(allow_none=True, load_default=None)
    flow = fields.String(allow_none=True, load_default=None, validate=validate.OneOf(["light", "medium", "heavy"]))
    symptoms = fields.List(fields.String(validate=validate.Length(min=1, max=40)), load_default=list, validate=validate.Length(max=10))
    notes = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=500))

    @validates("start_date")
    def _start(self, v, **kw):
        if v > date.today():
            raise ValidationError("The start date cannot be in the future.")

    @validates_schema
    def _range(self, data, **kw):
        s, e = data.get("start_date"), data.get("end_date")
        if s and e:
            if e < s:
                raise ValidationError("The end date cannot be before the start date.", "end_date")
            if e > date.today():
                raise ValidationError("The end date cannot be in the future.", "end_date")
            if (e - s).days + 1 > 14:
                raise ValidationError("A period cannot last more than 14 days. Please check the dates.", "end_date")
