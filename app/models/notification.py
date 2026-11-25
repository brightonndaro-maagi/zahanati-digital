from app.extensions import db
from app.models.base import fk, uuid_pk, utcnow


class Notification(db.Model):
    """In-app notification. `type` + `data` are machine-readable; `message` is the Swahili text shown to the user."""
    __tablename__ = "notifications"
    __table_args__ = (db.Index("ix_notifications_user_unread", "user_id", "is_read", "created_at"),)
    id = uuid_pk()
    user_id = fk("users.id", nullable=False)
    type = db.Column(db.String(40), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    data = db.Column(db.JSON, default=dict)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
