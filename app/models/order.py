from app.extensions import db
from app.models.base import TimestampMixin, fk, uuid_pk, utcnow

ORDER_STATUSES = ("new", "ready", "collected", "cancelled", "expired")
PAYMENT_STATUSES = ("unpaid", "pending", "paid", "failed")
PRESCRIPTION_STATUSES = ("not_required", "required", "uploaded", "approved", "rejected")


class Order(TimestampMixin, db.Model):
    __tablename__ = "orders"
    __table_args__ = (
        db.CheckConstraint("status IN ('new','ready','collected','cancelled','expired')", name="ck_order_status"),
        db.CheckConstraint("payment_status IN ('unpaid','pending','paid','failed')", name="ck_order_payment_status"),
        db.CheckConstraint("prescription_status IN ('not_required','required','uploaded','approved','rejected')",
                           name="ck_order_prescription_status"),
        db.CheckConstraint("total_tzs >= 0", name="ck_order_total"),
        db.Index("ix_orders_expiry", "status", "payment_status", "expires_at"),
    )
    id = uuid_pk()
    patient_id = fk("patient_profiles.id", nullable=False, index=True)
    pharmacy_id = fk("pharmacy_profiles.id", nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False, default="new", index=True)
    payment_status = db.Column(db.String(10), nullable=False, default="unpaid")
    prescription_status = db.Column(db.String(15), nullable=False, default="not_required")
    total_tzs = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    ready_at = db.Column(db.DateTime(timezone=True))
    collected_at = db.Column(db.DateTime(timezone=True))
    cancelled_at = db.Column(db.DateTime(timezone=True))
    cancelled_by_user_id = fk("users.id", nullable=True)
    cancel_reason = db.Column(db.String(255))
    e_prescription_id = fk("prescriptions.id", nullable=True)  # doctor-issued prescription attached instead of an upload

    e_prescription = db.relationship("Prescription")
    patient = db.relationship("PatientProfile")
    pharmacy = db.relationship("PharmacyProfile")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.medicine_name")
    payments = db.relationship("Payment", back_populates="order", order_by="Payment.created_at")
    refunds = db.relationship("Refund", back_populates="order", order_by="Refund.created_at")
    prescription_files = db.relationship("PrescriptionFile", back_populates="order", order_by="PrescriptionFile.uploaded_at")


class OrderItem(db.Model):
    """Name and price are copied from the medicine when the order is placed, so later price changes never affect it."""
    __tablename__ = "order_items"
    __table_args__ = (db.CheckConstraint("quantity > 0", name="ck_order_item_qty"),
                      db.CheckConstraint("unit_price_tzs > 0", name="ck_order_item_price"))
    id = uuid_pk()
    order_id = fk("orders.id", nullable=False, index=True)
    medicine_id = fk("medicines.id", nullable=False, index=True)
    medicine_name = db.Column(db.String(150), nullable=False)
    unit_price_tzs = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    requires_prescription = db.Column(db.Boolean, nullable=False, default=False)

    order = db.relationship("Order", back_populates="items")
    medicine = db.relationship("Medicine")


class PrescriptionFile(db.Model):
    """Metadata of an encrypted prescription file. The file itself lives encrypted on disk (storage_key)
    until expires_at (2 years), then it is deleted and storage_key is cleared."""
    __tablename__ = "prescription_files"
    __table_args__ = (db.CheckConstraint("status IN ('uploaded','approved','rejected')", name="ck_rx_file_status"),)
    id = uuid_pk()
    order_id = fk("orders.id", nullable=False, index=True)
    storage_key = db.Column(db.String(80), unique=True)
    content_type = db.Column(db.String(30), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="uploaded")
    uploaded_by_user_id = fk("users.id", nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    deleted_at = db.Column(db.DateTime(timezone=True))
    reviewed_by_user_id = fk("users.id", nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True))
    rejection_reason = db.Column(db.String(255))

    order = db.relationship("Order", back_populates="prescription_files")
