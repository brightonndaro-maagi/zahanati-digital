from app.extensions import db
from app.models.base import fk, uuid_pk, utcnow


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = uuid_pk()
    user_id = fk("users.id", nullable=True, index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.String(64))
    ip_address = db.Column(db.String(64))
    details = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
