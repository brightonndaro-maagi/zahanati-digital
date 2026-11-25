from app.extensions import db
from app.models.base import TimestampMixin, fk, uuid_pk


class Medicine(TimestampMixin, db.Model):
    """A medicine sold by one pharmacy. Customers only ever see `stock_quantity > 0` as available/finished;
    the exact quantity is internal (it is reserved while a payment is in progress)."""
    __tablename__ = "medicines"
    __table_args__ = (
        db.CheckConstraint("price_tzs > 0", name="ck_medicine_price_positive"),
        db.CheckConstraint("stock_quantity >= 0", name="ck_medicine_stock_not_negative"),
        db.Index("uq_medicine_pharmacy_name", "pharmacy_id", db.text("lower(name)"), unique=True),
    )
    id = uuid_pk()
    pharmacy_id = fk("pharmacy_profiles.id", nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    generic_name = db.Column(db.String(150))
    price_tzs = db.Column(db.Integer, nullable=False)  # whole Tanzanian shillings, never negative
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)
    requires_prescription = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    pharmacy = db.relationship("PharmacyProfile")
