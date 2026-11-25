from flask import Blueprint, Response, request

from app.common.audit import log_action
from app.common.decorators import current_user, roles_required, verified_doctor_required
from app.common.errors import APIError
from app.common.responses import paginate, success
from app.extensions import limiter
from app.models import Prescription
from app.orders.services import order_dict
from app.prescriptions import pdf, services
from app.prescriptions.schemas import CancelSchema, IssueSchema, UseSchema

bp = Blueprint("prescriptions", __name__)


class _Dump:
    @staticmethod
    def dump(items, many=False):
        return [services.prescription_dict(i) for i in items]


def _json():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    return body


@bp.post("/consultations/<uid:consultation_id>/prescriptions")
@verified_doctor_required
@limiter.limit("60 per hour")
def issue_prescription(consultation_id):
    """Issue an electronic prescription inside an open consultation (verified doctors with an active licence only).
    Prescriptions can never be edited afterwards; they can only be cancelled.
    ---
    tags: [Prescriptions]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [items]
          properties:
            notes: {type: string}
            items:
              type: array
              items:
                type: object
                properties:
                  medicine_name: {type: string, example: "Amoxicillin 500mg"}
                  dosage: {type: string, example: "1 capsule"}
                  frequency: {type: string, example: "3 times a day"}
                  duration_days: {type: integer, example: 7}
                  instructions: {type: string}
    responses:
      201: {description: Issued}
      403: {description: Doctor not verified / licence expired}
      404: {description: Consultation not found}
      409: {description: Consultation closed}
      422: {description: Validation failed}
    """
    rx = services.issue(current_user(), consultation_id, IssueSchema().load(_json()))
    return success(services.prescription_dict(rx), "Prescription issued", 201)


@bp.get("/prescriptions")
@roles_required("patient", "doctor")
def list_prescriptions():
    """My prescriptions (patients: received; doctors: issued). Filter: status (active|cancelled), page, per_page.
    ---
    tags: [Prescriptions]
    security: [{Bearer: []}]
    responses:
      200: {description: Paginated prescriptions}
    """
    user = current_user()
    q = Prescription.query.filter(Prescription.patient_id == user.patient_profile.id if user.role == "patient"
                                  else Prescription.doctor_id == user.doctor_profile.id)
    if request.args.get("status"):
        if request.args["status"] not in ("active", "cancelled"):
            raise APIError("Invalid status filter", 422)
        q = q.filter(Prescription.status == request.args["status"])
    items, meta = paginate(q.order_by(Prescription.created_at.desc()), _Dump,
                           request.args.get("page", 1, int), request.args.get("per_page", 20, int))
    return success(items, meta=meta)


@bp.get("/prescriptions/<uid:prescription_id>")
@roles_required("patient", "doctor")
def get_prescription(prescription_id):
    """One prescription (its patient or its issuing doctor only).
    ---
    tags: [Prescriptions]
    security: [{Bearer: []}]
    responses:
      200: {description: Prescription}
      404: {description: Not found}
    """
    return success(services.prescription_dict(services.get_visible(current_user(), prescription_id)))


@bp.get("/prescriptions/<uid:prescription_id>/pdf")
@roles_required("patient", "doctor")
def download_pdf(prescription_id):
    """Download the prescription as a PDF.
    ---
    tags: [Prescriptions]
    security: [{Bearer: []}]
    produces: [application/pdf]
    responses:
      200: {description: PDF file}
      404: {description: Not found}
    """
    rx = services.get_visible(current_user(), prescription_id)
    data = pdf.render(rx, services.valid_until(rx), services.license_number(rx))
    log_action("prescription.pdf_downloaded", user_id=current_user().id, entity_type="prescription", entity_id=rx.id)
    return Response(data, mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="prescription-{rx.id[:8]}.pdf"', "Cache-Control": "no-store"})


@bp.post("/prescriptions/<uid:prescription_id>/cancel")
@roles_required("patient", "doctor")
def cancel_prescription(prescription_id):
    """Issuing doctor cancels a prescription (with a reason).
    ---
    tags: [Prescriptions]
    security: [{Bearer: []}]
    responses:
      200: {description: Cancelled}
      403: {description: Only the issuing doctor can cancel}
      404: {description: Not found}
      409: {description: Already cancelled}
    """
    rx = services.cancel(current_user(), prescription_id, CancelSchema().load(_json())["reason"])
    return success(services.prescription_dict(rx), "Prescription cancelled")


@bp.post("/orders/<uid:order_id>/prescription/use")
@roles_required("patient")
def use_prescription(order_id):
    """Attach one of MY electronic prescriptions to an order that needs a prescription (instead of uploading a file).
    Every medicine that needs a prescription must appear on it; the order's prescription is then approved automatically.
    ---
    tags: [Prescriptions]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema: {type: object, required: [prescription_id], properties: {prescription_id: {type: string}}}
    responses:
      200: {description: Attached and approved}
      404: {description: Order or prescription not found}
      409: {description: Cancelled, expired, already used, or order closed}
      422: {description: Prescription does not cover all required medicines}
    """
    order = services.attach_to_order(current_user(), order_id, UseSchema().load(_json())["prescription_id"])
    return success(order_dict(order, "patient"), "Prescription attached")
