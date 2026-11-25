from marshmallow import EXCLUDE, Schema, fields, validate


class MedicineSchema(Schema):
    """Owner (pharmacy) view and input. Prices are whole shillings; stock is the internal quantity."""
    class Meta:
        unknown = EXCLUDE

    id = fields.String(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=2, max=150))
    generic_name = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=150))
    price_tzs = fields.Integer(required=True, strict=True, validate=validate.Range(min=1, max=100_000_000))
    stock_quantity = fields.Integer(required=True, strict=True, validate=validate.Range(min=0, max=1_000_000))
    requires_prescription = fields.Boolean(load_default=False)
    is_active = fields.Boolean(load_default=True)
    available = fields.Method("_available", dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    def _available(self, m):
        return m.stock_quantity > 0
