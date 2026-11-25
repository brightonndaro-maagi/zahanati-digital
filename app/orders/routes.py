from flask import Blueprint, Response, request

from app.common.decorators import approved_pharmacy_required, current_user, roles_required
from app.common.errors import APIError
from app.common.responses import success
from app.common.validators import uuid_arg
from app.extensions import db, limiter
from app.models import Order
from app.models.order import ORDER_STATUSES, PAYMENT_STATUSES
from app.orders import services
from app.orders.schemas import OrderCreateSchema, ReasonSchema, RejectSchema

bp = Blueprint("orders", __name__)
EXT = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}


def _json(optional=False):
    body = request.get_json(silent=True)
    if body is None and optional:
        return {}
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    return body


@bp.post("")
@roles_required("patient")
@limiter.limit("30 per hour")
def create_order():
    """Place an order (1 to 20 medicines, all from one pharmacy). Prices are copied into the order.
    Medicines that are out of stock cannot be ordered. Unpaid orders expire after 24 hours.
    ---
    tags: [Orders]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [items]
          properties:
            items:
              type: array
              items: {type: object, properties: {medicine_id: {type: string}, quantity: {type: integer, example: 2}}}
    responses:
      201: {description: Order created (status new, payment unpaid)}
      404: {description: Medicine not found or not visible}
      409: {description: Out of stock or quantity not available}
      422: {description: Invalid items, duplicates, or medicines from more than one pharmacy}
    """
    data = OrderCreateSchema().load(_json())
    order = services.create_order(current_user(), data["items"])
    return success(services.order_dict(order, "patient"), "Order placed", 201)


@bp.get("")
@roles_required("patient", "pharmacy", "admin")
def list_orders():
    """My orders (customers: their own; pharmacies: orders they received; admins: all).
    Filters: status, payment_status, page, per_page.
    ---
    tags: [Orders]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated orders}
    """
    user, a = current_user(), request.args
    scope = {"patient": [Order.patient_id == getattr(user.patient_profile, "id", None)],
             "pharmacy": [Order.pharmacy_id == getattr(user.pharmacy_profile, "id", None)]}.get(user.role, [])
    services.expire_due(scope)
    q = services.list_query(user)
    if a.get("status"):
        if a["status"] not in ORDER_STATUSES:
            raise APIError("Invalid status filter", 422)
        q = q.filter(Order.status == a["status"])
    if a.get("payment_status"):
        if a["payment_status"] not in PAYMENT_STATUSES:
            raise APIError("Invalid payment_status filter", 422)
        q = q.filter(Order.payment_status == a["payment_status"])
    if user.role == "admin":
        if a.get("pharmacy_id"):
            q = q.filter(Order.pharmacy_id == uuid_arg(a["pharmacy_id"], "pharmacy_id"))
        if a.get("patient_id"):
            q = q.filter(Order.patient_id == uuid_arg(a["patient_id"], "patient_id"))
    per_page = max(1, min(a.get("per_page", 20, int), 100))
    p = q.order_by(Order.created_at.desc()).paginate(page=max(1, a.get("page", 1, int)), per_page=per_page, error_out=False)
    return success([services.order_dict(o, user.role) for o in p.items],
                   meta={"page": p.page, "per_page": p.per_page, "total": p.total, "pages": p.pages})


@bp.get("/<uid:order_id>")
@roles_required("patient", "pharmacy", "admin")
def get_order(order_id):
    """One order (its customer, its pharmacy, or an admin; everyone else gets 404).
    ---
    tags: [Orders]
    security: [{Bearer: []}]
    responses:
      200: {description: Order}
      404: {description: Not found}
    """
    user = current_user()
    services.get_visible(user, order_id)
    services.expire_due([Order.id == order_id])
    order = services.get_visible(user, order_id)
    db.session.refresh(order)
    return success(services.order_dict(order, user.role))


def _act(order_id, action, message):
    reason = ReasonSchema().load(_json(optional=True))["reason"]
    order = services.change_status(current_user(), order_id, action, reason)
    return success(services.order_dict(order, current_user().role), message)


@bp.post("/<uid:order_id>/cancel")
@roles_required("patient", "pharmacy")
def cancel_order(order_id):
    """Cancel an unpaid order (customer or pharmacy). Optional body: {reason}.
    ---
    tags: [Orders]
    security: [{Bearer: []}]
    responses:
      200: {description: Cancelled}
      404: {description: Not found}
      409: {description: Paid, payment in progress, or already closed}
    """
    return _act(order_id, "cancel", "Order cancelled")


@bp.post("/<uid:order_id>/ready")
@approved_pharmacy_required
def mark_ready(order_id):
    """Pharmacy: the order is prepared. Requires payment 'paid' and prescription not_required/approved.
    The customer is notified in the app and by SMS.
    ---
    tags: [Orders]
    security: [{Bearer: []}]
    responses:
      200: {description: Ready}
      404: {description: Not found}
      409: {description: Not paid, prescription not approved, or wrong status}
    """
    return _act(order_id, "ready", "Order marked as ready")


@bp.post("/<uid:order_id>/collect")
@approved_pharmacy_required
def mark_collected(order_id):
    """Pharmacy: the customer picked the order up.
    ---
    tags: [Orders]
    security: [{Bearer: []}]
    responses:
      200: {description: Collected}
      404: {description: Not found}
      409: {description: Order is not ready}
    """
    return _act(order_id, "collect", "Order collected")


# ---------------- prescriptions ----------------
@bp.post("/<uid:order_id>/prescription")
@roles_required("patient")
@limiter.limit("20 per hour")
def upload_prescription(order_id):
    """Upload the doctor's prescription (multipart/form-data, field 'file'; PDF, JPG or PNG up to 5 MB).
    Allowed when the order needs a prescription and none is waiting or approved (first upload or after a rejection).
    ---
    tags: [Prescriptions]
    security: [{Bearer: []}]
    consumes: [multipart/form-data]
    parameters:
      - in: formData
        name: file
        type: file
        required: true
    responses:
      200: {description: Uploaded, waiting for the pharmacy}
      404: {description: Order not found}
      409: {description: Not needed, already uploaded/approved, or order closed}
      413: {description: File larger than 5 MB}
      422: {description: Not a PDF/JPG/PNG}
    """
    order = services.upload_prescription(current_user(), order_id, request.files.get("file"))
    return success(services.order_dict(order, "patient"), "Prescription uploaded")


@bp.get("/<uid:order_id>/prescription")
@roles_required("pharmacy")
def download_prescription(order_id):
    """Pharmacy: read the prescription file of one of its orders (decrypted on the fly, access is audited).
    ---
    tags: [Prescriptions]
    security: [{Bearer: []}]
    produces: [application/pdf, image/jpeg, image/png]
    responses:
      200: {description: The file}
      404: {description: No order or no file}
    """
    data, content_type = services.read_prescription(current_user(), order_id)
    return Response(data, mimetype=content_type, headers={
        "Content-Disposition": f'inline; filename="prescription.{EXT[content_type]}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@bp.post("/<uid:order_id>/prescription/approve")
@approved_pharmacy_required
def approve_prescription(order_id):
    """Pharmacy: approve the uploaded prescription (the customer can then pay).
    ---
    tags: [Prescriptions]
    security: [{Bearer: []}]
    responses:
      200: {description: Approved}
      404: {description: Not found}
      409: {description: Nothing to review}
    """
    order = services.review_prescription(current_user(), order_id, True)
    return success(services.order_dict(order, "pharmacy"), "Prescription approved")


@bp.post("/<uid:order_id>/prescription/reject")
@approved_pharmacy_required
def reject_prescription(order_id):
    """Pharmacy: reject the prescription with a reason; the customer may upload a new one.
    ---
    tags: [Prescriptions]
    security: [{Bearer: []}]
    responses:
      200: {description: Rejected}
      404: {description: Not found}
      409: {description: Nothing to review}
      422: {description: Reason required}
    """
    data = RejectSchema().load(_json())
    order = services.review_prescription(current_user(), order_id, False, data["reason"])
    return success(services.order_dict(order, "pharmacy"), "Prescription rejected")
