import json

from flask import Blueprint, request
from marshmallow import EXCLUDE, Schema, ValidationError, fields, validate

from app.common.decorators import approved_pharmacy_required, current_user, roles_required
from app.common.errors import APIError
from app.common.phone import PhoneField
from app.common.responses import success
from app.extensions import limiter
from app.orders.services import order_dict
from app.payments import services

bp = Blueprint("payments", __name__)


class PaySchema(Schema):
    class Meta:
        unknown = EXCLUDE
    network = fields.String(required=True, validate=validate.OneOf(["mpesa", "tigopesa", "airtelmoney"]))
    phone = PhoneField(load_default=None, allow_none=True)


class CallbackSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    provider_ref = fields.String(required=True, validate=validate.Length(min=3, max=100))
    status = fields.String(required=True, validate=validate.OneOf(["success", "failed"]))
    amount_tzs = fields.Integer(load_default=None, allow_none=True, strict=True)
    reason = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=255))


class RefundSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    amount_tzs = fields.Integer(load_default=None, allow_none=True, strict=True, validate=validate.Range(min=1))
    reason = fields.String(required=True, validate=validate.Length(min=3, max=255))


def _json():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    return body


@bp.post("/orders/<uid:order_id>/pay")
@roles_required("patient")
@limiter.limit("20 per hour")
def pay(order_id):
    """Start a mobile-money payment. Stock is held for the order while the payment is in progress.
    The customer confirms on their phone; the result arrives through the protected callback.
    Not allowed before a required prescription is approved, twice for the same order, or for expired orders.
    ---
    tags: [Payments]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [network]
          properties:
            network: {type: string, enum: [mpesa, tigopesa, airtelmoney]}
            phone: {type: string, description: "payer number; defaults to your own"}
    responses:
      200: {description: Payment started (payment_status = pending)}
      404: {description: Order not found}
      409: {description: Already paid/in progress, prescription not approved, order closed, or stock no longer available}
      422: {description: Unsupported network or invalid phone}
      503: {description: Payment service unavailable}
    """
    data = PaySchema().load(_json())
    services.start_payment(current_user(), order_id, data["network"], data["phone"])
    order = services.get_visible(current_user(), order_id)
    return success(order_dict(order, "patient"), "Payment started. Confirm it on your phone.")


@bp.post("/payments/callback")
@limiter.exempt
def callback():
    """Payment result from the provider. Protected by header X-Signature = hex HMAC-SHA256 of the raw body.
    Duplicate deliveries are acknowledged without changing anything.
    ---
    tags: [Payments]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [provider_ref, status]
          properties:
            provider_ref: {type: string}
            status: {type: string, enum: [success, failed]}
            amount_tzs: {type: integer}
            reason: {type: string}
    responses:
      200: {description: Processed (or duplicate)}
      401: {description: Bad signature}
      404: {description: Unknown payment}
      409: {description: Conflicting final state}
      422: {description: Amount mismatch}
    """
    raw = request.get_data()
    services.verify_signature(raw, request.headers.get("X-Signature"))
    try:
        data = CallbackSchema().load(json.loads(raw or b"{}"))
    except (ValueError, TypeError):
        raise APIError("Invalid JSON", 400)
    payment, changed = services.handle_callback(data)
    return success({"payment_id": payment.id, "status": payment.status, "changed": changed}, "Callback processed")


@bp.post("/orders/<uid:order_id>/refund")
@approved_pharmacy_required
def refund(order_id):
    """Record a refund the pharmacy has given to the customer (amount defaults to the full remaining amount).
    A full refund of an uncollected order cancels it and puts the medicines back in stock.
    ---
    tags: [Payments]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [reason]
          properties:
            amount_tzs: {type: integer}
            reason: {type: string}
    responses:
      200: {description: Refund recorded}
      404: {description: Order not found}
      409: {description: Order not paid}
      422: {description: Invalid amount}
    """
    data = RefundSchema().load(_json())
    order = services.record_refund(current_user(), order_id, data["amount_tzs"], data["reason"])
    return success(order_dict(order, "pharmacy"), "Refund recorded")
