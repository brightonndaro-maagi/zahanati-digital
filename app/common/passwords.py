import re

from marshmallow import ValidationError

COMMON = {"12345678", "123456789", "1234567890", "password", "password1", "password123", "qwerty123", "qwertyuiop", "11111111",
          "00000000", "iloveyou1", "abc12345", "admin123", "admin1234", "welcome1", "letmein123", "zahanati1", "zahanati123",
          "12341234", "1q2w3e4r", "asdf1234", "pass1234", "test1234"}


def check_password(value):
    """Shared password policy: 8+ characters with letters and digits, and not a well-known weak password."""
    if len(value) < 8 or not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValidationError("Password must be at least 8 characters and contain letters and digits.")
    if value.lower() in COMMON or len(set(value)) < 4:
        raise ValidationError("This password is too easy to guess. Choose a different one.")
