from marshmallow import EXCLUDE, Schema, fields, validate


class _B(Schema):
    class Meta:
        unknown = EXCLUDE


class OrderItemInput(_B):
    medicine_id = fields.UUID(required=True)
    quantity = fields.Integer(required=True, strict=True, validate=validate.Range(min=1, max=1000))


class OrderCreateSchema(_B):
    items = fields.List(fields.Nested(OrderItemInput), required=True, validate=validate.Length(min=1, max=200))


class ReasonSchema(_B):
    reason = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=255))


class RejectSchema(_B):
    reason = fields.String(required=True, validate=validate.Length(min=3, max=255))
