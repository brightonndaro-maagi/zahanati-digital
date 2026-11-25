import uuid

from werkzeug.routing import BaseConverter, ValidationError as RoutingValidationError

from app.common.errors import APIError


def _canonical(value):
    return str(uuid.UUID(str(value)))


class UUIDConverter(BaseConverter):
    """URL converter: <uid:name>. Malformed ids give a clean 404 instead of a database error."""
    regex = r"[0-9a-fA-F-]{32,36}"

    def to_python(self, value):
        try:
            return _canonical(value)
        except ValueError:
            raise RoutingValidationError()

    def to_url(self, value):
        return str(value)


def uuid_arg(value, name):
    """Validate a UUID taken from a query string; returns canonical str or None if empty."""
    if not value:
        return None
    try:
        return _canonical(value)
    except ValueError:
        raise APIError(f"'{name}' must be a valid UUID", 422)
