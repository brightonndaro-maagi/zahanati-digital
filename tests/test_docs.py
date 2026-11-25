from app.docs import NO_BODY

METHODS = ("get", "post", "put", "patch", "delete")


def _spec(client):
    r = client.get("/api/openapi.json")
    assert r.status_code == 200
    return r.get_json()


def test_swagger_ui_and_spec_are_served(client):
    assert client.get("/api/docs/").status_code == 200
    spec = _spec(client)
    assert spec["info"]["title"] == "Zahanati Digital API" and "Bearer" in spec["securityDefinitions"]


def test_every_endpoint_is_documented(client, app):
    """Every /api/v1 route must appear in the spec with: tags, summary, authentication, error responses and, for
    write endpoints that take JSON, a request body example. Fails when a new endpoint is added without documentation."""
    spec = _spec(client)
    documented = {(m, p) for p, ops in spec["paths"].items() for m in ops if m in METHODS}
    from app.docs import _openapi_path
    expected = {(m.lower(), _openapi_path(r.rule)) for r in app.url_map.iter_rules() if r.rule.startswith("/api/v1")
               for m in r.methods - {"HEAD", "OPTIONS"}}
    assert expected - documented == set(), sorted(expected - documented)
    problems = []
    for path, ops in spec["paths"].items():
        for m, op in ops.items():
            if m not in METHODS:
                continue
            name = f"{m.upper()} {path}"
            if not op.get("tags"):
                problems.append(f"{name}: no tags")
            if not (op.get("summary") or op.get("description")):
                problems.append(f"{name}: no description")
            if "Authentication:" not in op["description"]:
                problems.append(f"{name}: authentication not stated")
            if not any(c.startswith("2") for c in op["responses"]):
                problems.append(f"{name}: no success response")
            if not any(c[0] in "45" for c in op["responses"]):
                problems.append(f"{name}: no error responses")
            if any("examples" not in r for r in op["responses"].values()):
                problems.append(f"{name}: response without example")
            if m in ("post", "put", "patch"):
                body = [p for p in op["parameters"] if p.get("in") in ("body", "formData")]
                if not body and "No request body is needed" not in op["description"]:
                    problems.append(f"{name}: no request body documented")
                for p in body:
                    if p["in"] == "body" and "example" not in p.get("schema", {}) and not p.get("schema", {}).get("properties"):
                        problems.append(f"{name}: body without example")
    assert not problems, "\n".join(problems)


def test_protected_endpoints_state_their_roles(client):
    spec = _spec(client)
    op = spec["paths"]["/api/v1/orders/{order_id}/ready"]["post"]
    assert "approved pharmacy" in op["description"] and op["x-roles"] == ["pharmacy"] and op["security"] == [{"Bearer": []}]
    pub = spec["paths"]["/api/v1/first-aid"]["get"]
    assert "none (public endpoint)" in pub["description"] and not pub.get("security")
    assert "patient" in spec["paths"]["/api/v1/orders"]["post"]["x-roles"]
    assert spec["paths"]["/api/v1/orders/{order_id}/pay"]["post"]["parameters"][-1]["in"] == "body"


def test_appointments_can_be_switched_off(monkeypatch):
    from app import create_app
    from config import TestingConfig
    monkeypatch.setattr(TestingConfig, "FEATURE_APPOINTMENTS", False)
    app = create_app("testing")
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert not any(r.startswith("/api/v1/appointments") or r.endswith("/availability") for r in rules)
    assert "/api/v1/orders" in rules and "/api/v1/consultations" in rules          # everything else is untouched
    assert app.test_client().get("/api/v1/appointments").status_code == 404
