from flask import jsonify

from app.common.i18n import tr


def success(data=None, message="OK", status=200, meta=None):
    body = {"success": True, "message": tr(message), "data": data}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status


def paginate(query, schema, page=1, per_page=20):
    per_page = max(1, min(per_page, 100))
    p = query.paginate(page=max(1, page), per_page=per_page, error_out=False)
    return schema.dump(p.items, many=True), {
        "page": p.page, "per_page": p.per_page, "total": p.total, "pages": p.pages,
    }


def paginate_list(items, page=1, per_page=20):
    """Paginate an already-sorted Python list (used where ordering needs computed values, e.g. distance)."""
    per_page = max(1, min(per_page, 100))
    page = max(1, page)
    total = len(items)
    pages = max(1, -(-total // per_page))
    start = (page - 1) * per_page
    return items[start:start + per_page], {"page": page, "per_page": per_page, "total": total, "pages": pages}
