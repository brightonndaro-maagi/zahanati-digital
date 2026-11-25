from flask import request
from app.extensions import db
from app.models.audit_log import AuditLog


def log_action(action, user_id=None, entity_type=None, entity_id=None, details=None, commit=True):
    ip = request.remote_addr if request else None
    db.session.add(AuditLog(
        user_id=user_id, action=action, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None, ip_address=ip, details=details or {},
    ))
    if commit:
        db.session.commit()
