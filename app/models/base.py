import uuid
from datetime import datetime, timezone
from sqlalchemy import Uuid
from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


def uuid_pk():
    return db.Column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))


def fk(target, **kw):
    return db.Column(Uuid(as_uuid=False), db.ForeignKey(target), **kw)


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
