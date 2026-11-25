from app.extensions import db
from app.models.base import TimestampMixin, fk, utcnow, uuid_pk

NETWORKS = ("mpesa", "tigopesa", "airtelmoney")


class Payment(TimestampMixin, db.Model):
    """One mobile-money payment attempt for an order. At most ONE pending-or-paid payment per order (DB-enforced)."""
    __tablename__ = "payments"
    __table_args__ = (
        db.CheckConstraint("status IN ('pending','paid','failed')", name="ck_payment_status"),
        db.CheckConstraint("amount_tzs > 0", name="ck_payment_amount"),
        db.Index("uq_payment_active_per_order", "order_id", unique=True,
                 postgresql_where=db.text("status IN ('pending','paid')"),
                 sqlite_where=db.text("status IN ('pending','paid')")),
    )
    id = uuid_pk()
    order_id = fk("orders.id", nullable=False, index=True)
    amount_tzs = db.Column(db.Integer, nullable=False)
    network = db.Column(db.String(15), nullable=False)
    payer_phone = db.Column(db.String(20), nullable=False)
    provider = db.Column(db.String(30), nullable=False)
    provider_ref = db.Column(db.String(100), unique=True)
    status = db.Column(db.String(10), nullable=False, default="pending", index=True)
    failure_reason = db.Column(db.String(255))
    paid_at = db.Column(db.DateTime(timezone=True))
    stock_released = db.Column(db.Boolean, nullable=False, default=False)

    order = db.relationship("Order", back_populates="payments")


class Refund(db.Model):
    """The pharmacy returns the money itself; the system records amount, reason and date (spec 4.4)."""
    __tablename__ = "refunds"
    __table_args__ = (db.CheckConstraint("amount_tzs > 0", name="ck_refund_amount"),)
    id = uuid_pk()
    order_id = fk("orders.id", nullable=False, index=True)
    payment_id = fk("payments.id", nullable=True)
    amount_tzs = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    created_by_user_id = fk("users.id", nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    order = db.relationship("Order", back_populates="refunds")
