from flask import jsonify

from app.common.i18n import tr, tr_deep
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException


class APIError(Exception):
    def __init__(self, message, status=400, errors=None):
        super().__init__(message)
        self.message, self.status, self.errors = message, status, errors


def error_response(message, status, errors=None):
    from flask import g
    body = {"success": False, "message": tr(message), "request_id": getattr(g, "request_id", None)}
    if errors:
        body["errors"] = tr_deep(errors)
    return jsonify(body), status


def register_error_handlers(app):
    @app.errorhandler(APIError)
    def _api(e):
        return error_response(e.message, e.status, e.errors)

    @app.errorhandler(ValidationError)
    def _val(e):
        return error_response("Validation failed", 422, e.messages)

    @app.errorhandler(IntegrityError)
    def _integrity(e):
        from app.extensions import db
        db.session.rollback()
        app.logger.warning("Integrity error: %s", e.orig)
        return error_response("This conflicts with an existing record", 409)

    @app.errorhandler(HTTPException)
    def _http(e):
        return error_response(e.description, e.code)

    @app.errorhandler(Exception)
    def _any(e):
        app.logger.exception("Unhandled error")
        return error_response("Internal server error", 500)
