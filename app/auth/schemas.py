import re
from marshmallow import EXCLUDE, Schema, ValidationError, fields, validate, validates_schema

from app.common.phone import PhoneField


from app.common.passwords import check_password as _password


def split_full_name(value):
    parts = value.split()
    if len(parts) < 2:
        raise ValidationError("Please enter your full name (first and last name).")
    first, last = parts[0], " ".join(parts[1:])
    if len(first) > 80 or len(last) > 80:
        raise ValidationError("Name is too long.")
    return first, last


def _full_name(value):
    split_full_name(value)


class _Base(Schema):
    class Meta:
        unknown = EXCLUDE


CODE = dict(validate=validate.Regexp(r"^\d{6}$", error="Code must be 6 digits."))


class OtpRequestSchema(_Base):
    phone = PhoneField(required=True)
    purpose = fields.String(load_default="login", validate=validate.OneOf(["login", "register"]))
    lang = fields.String(load_default=None, allow_none=True, validate=validate.OneOf(["sw", "en"]))


class OtpVerifySchema(_Base):
    phone = PhoneField(required=True)
    code = fields.String(required=True, **CODE)
    full_name = fields.String(load_default=None, allow_none=True, validate=_full_name)


class RegisterBase(_Base):
    phone = PhoneField(required=True)
    otp_code = fields.String(required=True, **CODE)
    email = fields.Email(load_default=None, allow_none=True)
    password = fields.String(required=True, load_only=True, validate=_password)


class RegisterDoctorSchema(RegisterBase):
    first_name = fields.String(required=True, validate=validate.Length(min=1, max=80))
    last_name = fields.String(required=True, validate=validate.Length(min=1, max=80))
    license_number = fields.String(required=True, validate=validate.Length(min=3, max=60))
    qualification = fields.String(required=True, validate=validate.Length(min=2, max=150))
    institution = fields.String(load_default=None)
    council = fields.String(load_default="tanganyika", validate=validate.OneOf(["tanganyika", "zanzibar"]))
    years_of_experience = fields.Integer(load_default=None, validate=validate.Range(min=0, max=70))
    specialisation_ids = fields.List(fields.UUID(), load_default=list)


class RegisterPharmacySchema(RegisterBase):
    name = fields.String(required=True, validate=validate.Length(min=2, max=150))
    license_number = fields.String(required=True, validate=validate.Length(min=3, max=60))
    address = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=255))
    latitude = fields.Float(required=True, validate=validate.Range(min=-90, max=90))
    longitude = fields.Float(required=True, validate=validate.Range(min=-180, max=180))


class LoginSchema(_Base):
    phone = PhoneField(load_default=None)
    email = fields.Email(load_default=None)
    password = fields.String(required=True)

    @validates_schema
    def _one_identifier(self, data, **kw):
        if bool(data.get("phone")) == bool(data.get("email")):
            raise ValidationError("Provide your phone number (or email) together with the password.", "phone")


class ForgotPasswordSchema(_Base):
    phone = PhoneField(required=True)


class ResetPasswordSchema(_Base):
    phone = PhoneField(required=True)
    code = fields.String(required=True, **CODE)
    new_password = fields.String(required=True, validate=_password)


class ChangePasswordSchema(_Base):
    current_password = fields.String(required=True)
    new_password = fields.String(required=True, validate=_password)

    @validates_schema
    def _differ(self, data, **kw):
        if data.get("current_password") == data.get("new_password"):
            raise ValidationError("New password must differ from the current one.", "new_password")


class PhoneChangeRequestSchema(_Base):
    phone = PhoneField(required=True)


class PhoneChangeConfirmSchema(_Base):
    phone = PhoneField(required=True)
    code = fields.String(required=True, **CODE)


class UserSchema(Schema):
    id = fields.String()
    phone = fields.String()
    email = fields.String()
    role = fields.String()
    is_active = fields.Boolean()
    language = fields.String()
    created_at = fields.DateTime()
    full_name = fields.Method("_name")
    verification_status = fields.Method("_vs")
    approval_status = fields.Method("_as")

    def _vs(self, u):
        return u.doctor_profile.verification_status if u.doctor_profile else None

    def _as(self, u):
        return u.pharmacy_profile.approval_status if u.pharmacy_profile else None

    def _name(self, u):
        if u.pharmacy_profile:
            return u.pharmacy_profile.name
        p = u.patient_profile or u.doctor_profile
        return f"{p.first_name} {p.last_name}" if p else None
