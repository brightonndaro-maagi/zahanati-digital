import re

from marshmallow import fields

_TZ_MOBILE = re.compile(r"^255[67]\d{8}$")


def normalize_phone(raw):
    """Return the canonical '+255XXXXXXXXX' form of a Tanzanian mobile number, or None if invalid.
    Accepts 0712345678, 712345678, 255712345678, +255 712 345 678, 00255712345678."""
    if not isinstance(raw, str):
        return None
    s = re.sub(r"[\s\-().]", "", raw)
    if s.startswith("+"):
        s = s[1:]
    elif s.startswith("00"):
        s = s[2:]
    if not s.isdigit():
        return None
    if s.startswith("0"):
        s = "255" + s[1:]
    elif len(s) == 9:
        s = "255" + s
    return "+" + s if _TZ_MOBILE.match(s) else None


class PhoneField(fields.String):
    default_error_messages = {"invalid": "Invalid Tanzanian mobile number. Use e.g. +255712345678 or 0712345678."}

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        normalized = normalize_phone(value)
        if not normalized:
            raise self.make_error("invalid")
        return normalized
