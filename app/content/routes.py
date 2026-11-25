from flask import Blueprint, request

from app.common.decorators import current_user, roles_required
from app.common.errors import APIError
from app.common.responses import paginate_list, success
from app.common.validators import uuid_arg
from app.content import services
from app.content.schemas import SCHEMAS, PublishSchema
from app.extensions import db
from app.models import FirstAidGuide, HealthEducation

public_bp = Blueprint("content_public", __name__)   # /api/v1
admin_bp = Blueprint("content_admin", __name__)     # /api/v1/admin

TITLES = {"first-aid": "first-aid guides", "health-education": "reproductive and child health education"}


def _json():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError("Request body must be a JSON object", 400)
    return body


def _page():
    return request.args.get("page", 1, int), request.args.get("per_page", 20, int)


def _term():
    term = " ".join(request.args.get("q", "").split())
    if request.args.get("q") is not None and 0 < len(term) < 2:
        raise APIError("Search text must be at least 2 characters", 422, {"q": ["Minimum 2 characters."]})
    return term or None


def _lang():
    lang = request.args.get("language") or request.args.get("lang")
    if lang and lang not in ("sw", "en"):
        raise APIError("language must be 'sw' or 'en'", 422)
    return lang


def _stage(kind):
    if kind != "health-education" or request.args.get("stage") is None:
        return None
    try:
        stage = int(request.args["stage"])
    except ValueError:
        stage = 0
    if stage not in services.STAGES:
        raise APIError("stage must be a number from 1 to 8", 422)
    return stage


# ---------------- public ----------------
def _make_public(kind, auth_required):
    guard = roles_required("patient", "doctor", "admin") if auth_required else (lambda f: f)

    def list_items():
        rows = services.search_published(kind, _term(), _lang(), _stage(kind))
        items, meta = paginate_list([services.public_dict(r, kind) for r in rows], *_page())
        return success(items, meta=meta)

    def get_item(item_id):
        return success(services.public_dict(services.get_published(kind, item_id), kind, full=True))

    list_items.__name__, get_item.__name__ = f"{kind}_list".replace("-", "_"), f"{kind}_get".replace("-", "_")
    access = "Requires login." if auth_required else "Public: no login needed."
    list_items.__doc__ = f"""Search {TITLES[kind]} (approved content only). {access} Query: q (min 2 chars), language (sw|en),{' stage (1-8),' if kind == 'health-education' else ''} page, per_page.
    ---
    tags: [Content]
    responses:
      200: {{description: Paginated approved content}}
      422: {{description: Invalid query}}
    """
    get_item.__doc__ = f"""One approved piece of {TITLES[kind]} with its reviewer, date and edition. {access}
    ---
    tags: [Content]
    responses:
      200: {{description: Content}}
      404: {{description: Not found or not approved}}
    """
    public_bp.add_url_rule(f"/{kind}", view_func=guard(list_items), methods=["GET"])
    public_bp.add_url_rule(f"/{kind}/<uid:item_id>", view_func=guard(get_item), methods=["GET"])


_make_public("first-aid", auth_required=False)
_make_public("health-education", auth_required=True)


@public_bp.get("/health-education/stages")
@roles_required("patient", "doctor", "admin")
def stages():
    """The eight stages of the reproductive-health journey used to group education content.
    ---
    tags: [Content]
    security: [{Bearer: []}]
    responses:
      200: {description: Stages}
    """
    return success([{"stage": n, **names} for n, names in services.STAGES.items()])


# ---------------- admin ----------------
def _make_admin(kind):
    Model = services.KINDS[kind]
    schema = SCHEMAS[kind]()

    def _item(item_id):
        item = db.session.get(Model, item_id)
        if not item:
            raise APIError("Content not found", 404)
        return item

    def list_all():
        q = Model.query
        if request.args.get("status"):
            if request.args["status"] not in ("draft", "published"):
                raise APIError("Invalid status filter", 422)
            q = q.filter(Model.status == request.args["status"])
        if _lang():
            q = q.filter(Model.language == _lang())
        if _stage(kind):
            q = q.filter(Model.stage == _stage(kind))
        term = _term()
        if term:
            from app.medicines.services import like_pattern
            pat = like_pattern(term)
            q = q.filter(db.or_(Model.title.ilike(pat, escape="\\"), Model.keywords.ilike(pat, escape="\\")))
        rows = q.order_by(Model.updated_at.desc()).limit(2000).all()
        items, meta = paginate_list([services.admin_dict(r, kind) for r in rows], *_page())
        return success(items, meta=meta)

    def create():
        return success(services.admin_dict(services.create(kind, current_user(), schema.load(_json())), kind), "Draft created", 201)

    def get_one(item_id):
        return success(services.admin_dict(_item(item_id), kind))

    def edit(item_id):
        sent = _json()
        data = {k: v for k, v in schema.load(sent, partial=True).items() if k in sent}
        return success(services.admin_dict(services.update(kind, current_user(), _item(item_id), data), kind), "Saved as draft: needs review before it goes live")

    def publish(item_id):
        reviewer = PublishSchema().load(_json())["reviewed_by_name"].strip()
        return success(services.admin_dict(services.publish(kind, current_user(), _item(item_id), reviewer), kind), "Published")

    def unpublish(item_id):
        return success(services.admin_dict(services.unpublish(kind, current_user(), _item(item_id)), kind), "Unpublished")

    def delete(item_id):
        services.delete(kind, current_user(), _item(item_id))
        return success(message="Deleted")

    base = f"/{kind}"
    docs = {
        "list_all": ("List all (drafts and published). Filters: status, language, q, page, per_page.", "200: {description: Paginated content}"),
        "create": ("Create a draft. Nothing is public until a named reviewer approves it.", "201: {description: Draft created}\n      422: {description: Validation failed}"),
        "get_one": ("One item with its working copy and the approved version.", "200: {description: Content}\n      404: {description: Not found}"),
        "edit": ("Edit the working copy. The currently approved text stays live until the new version is published.", "200: {description: Saved}\n      404: {description: Not found}"),
        "publish": ("Publish after review. Body: {reviewed_by_name} = the single reviewer who approved this version.", "200: {description: Published}\n      422: {description: Reviewer name required}"),
        "unpublish": ("Take the content offline.", "200: {description: Unpublished}\n      404: {description: Not found}"),
        "delete": ("Delete content that is not published.", "200: {description: Deleted}\n      409: {description: Still published}"),
    }
    for name, fn, rule, methods in [
        ("list_all", list_all, base, ["GET"]), ("create", create, base, ["POST"]),
        ("get_one", get_one, f"{base}/<uid:item_id>", ["GET"]), ("edit", edit, f"{base}/<uid:item_id>", ["PATCH", "PUT"]),
        ("publish", publish, f"{base}/<uid:item_id>/publish", ["POST"]), ("unpublish", unpublish, f"{base}/<uid:item_id>/unpublish", ["POST"]),
        ("delete", delete, f"{base}/<uid:item_id>", ["DELETE"])]:
        text, resp = docs[name]
        fn.__name__ = f"admin_{kind}_{name}".replace("-", "_")
        fn.__doc__ = f"{text} ({TITLES[kind]})\n    ---\n    tags: [Admin content]\n    security: [{{Bearer: []}}]\n    responses:\n      {resp}\n    "
        admin_bp.add_url_rule(rule, view_func=roles_required("admin")(fn), methods=methods)


_make_admin("first-aid")
_make_admin("health-education")
