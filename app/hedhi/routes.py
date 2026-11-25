from datetime import date

from flask import Blueprint, request

from app.common.audit import log_action
from app.common.decorators import current_user, roles_required
from app.common.errors import APIError
from app.common.responses import success
from app.extensions import limiter
from app.hedhi import services
from app.hedhi.schemas import CycleSchema

bp = Blueprint("hedhi", __name__)
schema = CycleSchema()


def _json():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    return body


@bp.post("/cycles")
@roles_required("patient")
@limiter.limit("60 per hour")
def add_cycle():
    """Log a period. Stored encrypted; only you can read it.
    ---
    tags: [HEDHI]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [start_date]
          properties:
            start_date: {type: string, example: "2026-11-02"}
            end_date: {type: string, example: "2026-11-06"}
            flow: {type: string, enum: [light, medium, heavy]}
            symptoms: {type: array, items: {type: string}}
            notes: {type: string}
    responses:
      201: {description: Logged}
      409: {description: Same start date or overlapping dates already logged}
      422: {description: Invalid dates}
      503: {description: Encryption not configured}
    """
    row, d = services.add(current_user(), schema.load(_json()))
    return success(services.entry_dict(row, d), "Period logged", 201)


@bp.get("/cycles")
@roles_required("patient")
def list_cycles():
    """My logged periods, newest first.
    ---
    tags: [HEDHI]
    security: [{Bearer: []}]
    responses:
      200: {description: Entries}
    """
    return success([services.entry_dict(r, d) for r, d in services.all_entries(current_user())])


@bp.get("/cycles/<uid:entry_id>")
@roles_required("patient")
def get_cycle(entry_id):
    """One logged period.
    ---
    tags: [HEDHI]
    security: [{Bearer: []}]
    responses:
      200: {description: Entry}
      404: {description: Not found}
    """
    row = services.get_row(current_user(), entry_id)
    return success(services.entry_dict(row, services._unpack(row)))


@bp.route("/cycles/<uid:entry_id>", methods=["PUT", "PATCH"])
@roles_required("patient")
def update_cycle(entry_id):
    """Change a logged period.
    ---
    tags: [HEDHI]
    security: [{Bearer: []}]
    responses:
      200: {description: Updated}
      404: {description: Not found}
      409: {description: Overlaps another period}
    """
    sent = _json()
    changes = {k: v for k, v in schema.load(sent, partial=True).items() if k in sent}
    row, d = services.update(current_user(), entry_id, changes)
    return success(services.entry_dict(row, d), "Updated")


@bp.delete("/cycles/<uid:entry_id>")
@roles_required("patient")
def delete_cycle(entry_id):
    """Delete one logged period.
    ---
    tags: [HEDHI]
    security: [{Bearer: []}]
    responses:
      200: {description: Deleted}
      404: {description: Not found}
    """
    services.delete_one(current_user(), entry_id)
    return success(message="Deleted")


@bp.get("/insights")
@roles_required("patient")
def insights():
    """Estimates from your logged periods: current phase, next period, ovulation, fertile window, and signs that
    you should see a doctor (with the doctor search path). Optional ?on=YYYY-MM-DD computes the estimates for another day.
    These are estimates only and not a contraceptive method.
    ---
    tags: [HEDHI]
    security: [{Bearer: []}]
    responses:
      200: {description: Insights}
      422: {description: Invalid date}
    """
    on = None
    if request.args.get("on"):
        try:
            on = date.fromisoformat(request.args["on"])
        except ValueError:
            raise APIError("'on' must be a date in YYYY-MM-DD format", 422)
    return success(services.insights(current_user(), on))


@bp.get("/export")
@roles_required("patient")
def export():
    """Download all my HEDHI data.
    ---
    tags: [HEDHI]
    security: [{Bearer: []}]
    responses:
      200: {description: All entries}
    """
    log_action("hedhi.exported", user_id=current_user().id, entity_type="user", entity_id=current_user().id)
    return success({"entries": [services.entry_dict(r, d) for r, d in services.all_entries(current_user())]})


@bp.delete("")
@roles_required("patient")
def delete_everything():
    """Delete ALL my HEDHI data permanently.
    ---
    tags: [HEDHI]
    security: [{Bearer: []}]
    responses:
      200: {description: Deleted}
    """
    return success({"deleted": services.delete_all(current_user())}, "All your HEDHI data has been deleted")
