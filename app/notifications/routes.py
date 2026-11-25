from flask import Blueprint, request
from marshmallow import Schema, fields

from app.common.decorators import current_user, roles_required
from app.common.i18n import get_lang, notification_message
from app.common.errors import APIError
from app.common.responses import paginate, success
from app.common.timeutils import utcnow
from app.extensions import db
from app.models import Notification

bp = Blueprint("notifications", __name__)


class NotificationSchema(Schema):
    id = fields.String()
    type = fields.String()
    message = fields.Method("_message")
    data = fields.Raw()
    is_read = fields.Boolean()
    created_at = fields.DateTime()

    def _message(self, n):
        return notification_message(n, get_lang())


schema = NotificationSchema()


@bp.get("")
@roles_required()
def list_notifications():
    """My notifications, newest first. Filter: unread=true. Pagination: page, per_page.
    ---
    tags: [Notifications]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated notifications}
    """
    q = Notification.query.filter_by(user_id=current_user().id)
    if request.args.get("unread", "").lower() in ("1", "true", "yes"):
        q = q.filter_by(is_read=False)
    items, meta = paginate(q.order_by(Notification.created_at.desc()), schema,
                           request.args.get("page", 1, int), request.args.get("per_page", 20, int))
    return success(items, meta=meta)


@bp.get("/unread-count")
@roles_required()
def unread_count():
    """Number of unread notifications.
    ---
    tags: [Notifications]
    security: [{Bearer: []}]
    responses:
      200: {description: Count}
    """
    return success({"unread": Notification.query.filter_by(user_id=current_user().id, is_read=False).count()})


@bp.post("/<uid:notification_id>/read")
@roles_required()
def mark_read(notification_id):
    """Mark one notification as read.
    ---
    tags: [Notifications]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
      404: {description: Not found}
    """
    n = Notification.query.filter_by(id=notification_id, user_id=current_user().id).first()
    if not n:
        raise APIError("Notification not found", 404)
    n.is_read = True
    db.session.commit()
    return success(schema.dump(n))


@bp.post("/read-all")
@roles_required()
def mark_all_read():
    """Mark all my notifications as read.
    ---
    tags: [Notifications]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
    """
    n = Notification.query.filter_by(user_id=current_user().id, is_read=False).update({"is_read": True})
    db.session.commit()
    return success({"updated": n})
