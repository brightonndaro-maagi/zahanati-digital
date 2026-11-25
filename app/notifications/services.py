from app.extensions import db
from app.models import Notification


def notify(user_id, type_, message, data=None):
    """Adds a notification to the caller's transaction (the caller commits)."""
    db.session.add(Notification(user_id=user_id, type=type_, message=message, data=data or {}))
