"""Writes docs/API_ENDPOINTS.md from the live OpenAPI spec (the same one Swagger UI shows).
Run from the project root:  python scripts/generate_api_docs.py"""
import json
from collections import defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402

METHODS = ("get", "post", "put", "patch", "delete")
spec = create_app("testing").test_client().get("/api/openapi.json").get_json()
by_tag = defaultdict(list)
for path, ops in spec["paths"].items():
    for method, op in ops.items():
        if method in METHODS:
            by_tag[(op.get("tags") or ["Other"])[0]].append((path, method, op))

order = [t["name"] for t in spec.get("tags", [])]
out = ["# Zahanati Digital: API endpoints", "",
       "Generated from the OpenAPI spec (`/api/openapi.json`). Interactive version: **`/api/docs/`**.", "",
       "- Base URL: `/api/v1`. Send `Authorization: Bearer <access_token>` where a role is listed.",
       "- Language: `Accept-Language: sw|en` (or `?lang=`). Success: `{success, message, data, meta?}`. Errors: `{success:false, message, errors?, request_id}`.",
       "- Pagination: `?page=&per_page=` (max 100); lists return `meta: {page, per_page, total, pages}`.", "",
       f"**{sum(len(v) for v in by_tag.values())} endpoints**", ""]
for tag in sorted(by_tag, key=lambda t: order.index(t) if t in order else 99):
    items = sorted(by_tag[tag], key=lambda x: (x[0], METHODS.index(x[1])))
    out += [f"## {tag}", "", "| Method | Path | Who |", "|---|---|---|"]
    for path, method, op in items:
        who = ", ".join(op.get("x-roles") or []) or ("any signed-in user" if op.get("security") else "public")
        out.append(f"| {method.upper()} | `{path}` | {who} |")
    out.append("")
    for path, method, op in items:
        desc = (op.get("description") or "").split("\n\n")
        out += [f"### {method.upper()} `{path}`", "", desc[0].strip().replace("\n", " "), ""]
        auth = next((d for d in desc if d.startswith("**Authentication:**")), None)
        if auth:
            out += [auth, ""]
        params = [p for p in op.get("parameters", []) if p.get("in") in ("query", "path", "formData")]
        body = [p for p in op.get("parameters", []) if p.get("in") == "body"]
        for p in body:
            ex = p.get("schema", {}).get("example")
            if ex is None and p.get("schema", {}).get("properties"):
                ex = {k: (v.get("example") or v.get("type")) for k, v in p["schema"]["properties"].items()}
            if ex is not None:
                out += ["Request body:", "", "```json", json.dumps(ex, indent=2, ensure_ascii=False), "```", ""]
        if any(p.get("in") == "formData" for p in params):
            out += ["Request: `multipart/form-data` with the file in field `file` (PDF/JPG/PNG, max 5 MB).", ""]
        out += ["Responses: " + "; ".join(f"`{c}` {r.get('description', '')}" for c, r in sorted(op["responses"].items())), ""]
Path("docs").mkdir(exist_ok=True)
Path("docs/API_ENDPOINTS.md").write_text("\n".join(out), encoding="utf-8")
print("docs/API_ENDPOINTS.md:", len(out), "lines")
