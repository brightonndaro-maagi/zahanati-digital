"""Completes the OpenAPI spec generated from the view docstrings: who may call each endpoint, request body examples,
response examples and the error responses every endpoint can return. Used by /api/openapi.json and /api/docs/."""
import re

from flask import current_app

PHONE, UUID = "0712345678", "3f2a8c1e-5b7d-4c0a-9e21-8a6f0d4b7c15"
BODY = {
    "/api/v1/auth/change-password": {"current_password": "Secret123", "new_password": "Brand-new-77"},
    "/api/v1/auth/phone/change/request": {"phone": "0755123456"},
    "/api/v1/auth/phone/change/confirm": {"phone": "0755123456", "code": "123456"},
    "/api/v1/admin/doctors/<uid:doctor_id>/license-status": {"status": "expired"},
    "/api/v1/admin/doctors/<uid:doctor_id>/reject": {"reason": "Licence number was not found on the council register"},
    "/api/v1/admin/doctors/<uid:doctor_id>/verify": {"verified_name": "Neema A. Mushi"},
    "/api/v1/admin/pharmacies/<uid:pharmacy_id>/reject": {"reason": "Pharmacy licence has expired"},
    "/api/v1/admin/users/<uid:user_id>/deactivate": {"reason": "Repeated abusive messages"},
    "/api/v1/admin/first-aid": {"title": "Kuvuja damu", "summary": "Hatua za kwanza", "language": "sw", "keywords": "damu, jeraha",
                                "emergency_warning": "Piga 112 ikiwa damu haiachi baada ya dakika 10.",
                                "steps_to_do": ["Bonyeza jeraha kwa kitambaa safi"], "steps_to_avoid": ["Usiondoe kitu kilichobaki kwenye jeraha"]},
    "/api/v1/admin/first-aid/<uid:item_id>": {"title": "Kuvuja damu (imeboreshwa)"},
    "/api/v1/admin/health-education": {"title": "Mzunguko wa hedhi", "body": "Mzunguko wa kawaida ni siku 21 hadi 35.", "stage": 2, "language": "sw"},
    "/api/v1/admin/health-education/<uid:item_id>": {"title": "Mzunguko wa hedhi (toleo jipya)"},
    "/api/v1/admin/first-aid/<uid:item_id>/publish": {"reviewed_by_name": "Dr. Amina Salim"},
    "/api/v1/admin/health-education/<uid:item_id>/publish": {"reviewed_by_name": "Dr. Amina Salim"},
    "/api/v1/appointments/<uid:appt_id>/accept": {"note": "Karibu kliniki, fika dakika 10 mapema"},
    "/api/v1/appointments/<uid:appt_id>/reject": {"note": "Sipatikani muda huo"},
    "/api/v1/appointments/<uid:appt_id>/cancel": {"note": "Nimepata dharura"},
    "/api/v1/appointments/<uid:appt_id>/reschedule": {"start_time": "2026-11-25T10:30:00+03:00"},
    "/api/v1/consultations/<uid:consultation_id>/clinical": {"notes": "Private notes", "diagnosis": "Tension headache", "treatment_recommendations": "Rest and fluids"},
    "/api/v1/doctors/me": {"first_name": "Neema", "last_name": "Mushi", "bio": "Daktari wa watoto", "years_of_experience": 9, "practice_location": "Dar es Salaam"},
    "/api/v1/doctors/me/credentials": {"credential_type": "qualification", "title": "MMed Paediatrics", "institution": "MUHAS", "document_url": "https://example.com/cert.pdf"},
    "/api/v1/doctors/me/credentials/<uid:cred_id>": {"title": "MMed Paediatrics (updated)"},
    "/api/v1/doctors/me/specialisations": {"specialisation_ids": [UUID]},
    "/api/v1/doctors/me/workplaces": {"institution": "Muhimbili National Hospital", "role": "Consultant", "start_year": 2018, "is_current": True},
    "/api/v1/doctors/me/workplaces/<uid:workplace_id>": {"role": "Senior consultant"},
    "/api/v1/hedhi/cycles/<uid:entry_id>": {"end_date": "2026-11-06", "flow": "medium"},
    "/api/v1/orders/<uid:order_id>/cancel": {"reason": "Nimebadilisha mawazo"},
    "/api/v1/orders/<uid:order_id>/prescription/reject": {"reason": "Picha haisomeki"},
    "/api/v1/patients/me": {"first_name": "Asha", "last_name": "Juma", "region": "Dar es Salaam", "blood_group": "O+", "emergency_contact_phone": "0712345678"},
    "/api/v1/patients/me/medical-records": {"record_type": "allergy", "title": "Penicillin", "description": "Rash and itching", "record_date": "2024-05-01"},
    "/api/v1/patients/me/medical-records/<uid:record_id>": {"description": "Updated description"},
    "/api/v1/pharmacies/me": {"name": "Afya Pharmacy", "address": "Kariakoo", "latitude": -6.8184, "longitude": 39.2766},
    "/api/v1/pharmacies/me/medicines/<uid:medicine_id>": {"price_tzs": 1800, "stock_quantity": 80},
    "/api/v1/prescriptions/<uid:prescription_id>/cancel": {"reason": "Wrong dose written"},
    "/api/v1/specialisations": {"name": "Cardiology", "description": "Heart and blood vessels"},
    "/api/v1/specialisations/<uid:spec_id>": {"description": "Updated description"},
}
BODY.update({
    "/api/v1/auth/otp/request": {"phone": "0712345678", "purpose": "login", "lang": "sw"},
    "/api/v1/auth/otp/verify": {"phone": "0712345678", "code": "123456", "full_name": "Asha Juma"},
    "/api/v1/auth/register/doctor": {"phone": "0755123456", "otp_code": "123456", "password": "Secret123", "first_name": "Neema", "last_name": "Mushi",
                                     "license_number": "MCT-12345", "qualification": "MD", "council": "tanganyika", "specialisation_ids": []},
    "/api/v1/auth/register/pharmacy": {"phone": "0713000111", "otp_code": "123456", "password": "Secret123", "name": "Afya Pharmacy",
                                       "license_number": "PC-0001", "address": "Kariakoo, Dar es Salaam", "latitude": -6.8184, "longitude": 39.2766},
    "/api/v1/auth/login": {"phone": "0755123456", "password": "Secret123"},
    "/api/v1/auth/forgot-password": {"phone": "0755123456"},
    "/api/v1/auth/reset-password": {"phone": "0755123456", "code": "123456", "new_password": "Brand-new-77"},
    "/api/v1/auth/me/language": {"language": "sw"},
    "/api/v1/orders": {"items": [{"medicine_id": UUID, "quantity": 2}]},
    "/api/v1/orders/<uid:order_id>/pay": {"network": "mpesa", "phone": "0712345678"},
    "/api/v1/orders/<uid:order_id>/refund": {"amount_tzs": 1500, "reason": "Medicine was damaged"},
    "/api/v1/orders/<uid:order_id>/prescription/use": {"prescription_id": UUID},
    "/api/v1/payments/callback": {"provider_ref": "SIM-0a1b2c3d4e5f6071", "status": "success", "amount_tzs": 3000},
    "/api/v1/consultations": {"doctor_id": UUID, "subject": "Maumivu ya kichwa", "message": "Habari daktari, nina maumivu ya kichwa kwa siku tatu."},
    "/api/v1/consultations/<uid:consultation_id>/messages": {"body": "Asante daktari, nitafuata ushauri."},
    "/api/v1/consultations/<uid:consultation_id>/prescriptions": {"notes": "Pumzika na unywe maji mengi", "items": [
        {"medicine_name": "Amoxicillin 500mg", "dosage": "1 capsule", "frequency": "3 times a day", "duration_days": 7, "instructions": "After meals"}]},
    "/api/v1/appointments": {"doctor_id": UUID, "start_time": "2026-11-25T10:00:00+03:00", "reason": "Kipimo cha kawaida"},
    "/api/v1/doctors/me/availability": {"windows": [{"weekday": 0, "start_time": "09:00", "end_time": "17:00"}]},
    "/api/v1/pharmacies/me/medicines": {"name": "Paracetamol 500mg", "generic_name": "Paracetamol", "price_tzs": 1500, "stock_quantity": 100, "requires_prescription": False},
    "/api/v1/hedhi/cycles": {"start_date": "2026-11-02", "end_date": "2026-11-06", "flow": "medium", "symptoms": ["cramps"], "notes": "Maumivu kidogo"},
})
# Write endpoints that take no JSON body (the action is the URL itself)
NO_BODY = {"/api/v1/auth/logout", "/api/v1/auth/refresh", "/api/v1/consultations/<uid:consultation_id>/close", "/api/v1/notifications/read-all",
           "/api/v1/notifications/<uid:notification_id>/read", "/api/v1/orders/<uid:order_id>/collect", "/api/v1/orders/<uid:order_id>/ready",
           "/api/v1/orders/<uid:order_id>/prescription/approve", "/api/v1/appointments/<uid:appt_id>/complete",
           "/api/v1/admin/first-aid/<uid:item_id>/unpublish", "/api/v1/admin/health-education/<uid:item_id>/unpublish",
           "/api/v1/admin/pharmacies/<uid:pharmacy_id>/approve", "/api/v1/admin/users/<uid:user_id>/activate"}
BODY["/api/v1/admin/health-education/<uid:item_id>"] = BODY["/api/v1/admin/health-education/<uid:item_id>"]

ERRORS = {
    "400": ("Malformed request (for example the body is not a JSON object)", "Request body must be a JSON object"),
    "401": ("Missing, invalid or expired token", "Authentication required"),
    "403": ("Your role is not allowed to use this endpoint", "You do not have permission to access this resource"),
    "404": ("The resource does not exist, or it is not yours", "Not found"),
    "422": ("Validation failed", "Validation failed"),
    "429": ("Too many requests, slow down", "429 Too Many Requests"),
    "500": ("Unexpected server error (see request_id when contacting support)", "Internal server error"),
}


def _openapi_path(rule):
    return re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", rule)


def _success_example(op, code, description):
    return {"success": True, "message": description or "OK", "data": {}}


def enrich(spec, app):
    if spec.get("x-enriched"):
        return spec
    views = {}
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/v1"):
            for m in rule.methods - {"HEAD", "OPTIONS"}:
                views[(m.lower(), _openapi_path(rule.rule))] = (rule.rule, app.view_functions[rule.endpoint])
    for path, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            rule, view = views.get((method, path), (None, None))
            roles = getattr(view, "required_roles", None)
            note = getattr(view, "requirement", None)
            secured = bool(op.get("security")) or roles is not None
            if secured:
                op.setdefault("security", [{"Bearer": []}])
            auth = "none (public endpoint)" if not secured else "Bearer access token" + (
                f"; allowed roles: {', '.join(roles)}" if roles else "; any signed-in user") + (f" ({note})" if note else "")
            op["description"] = ((op.get("description") or op.get("summary") or "").strip() + f"\n\n**Authentication:** {auth}.").strip()
            op["x-roles"] = list(roles or [])
            # request body example
            params = op.setdefault("parameters", [])
            if method in ("post", "put", "patch") and rule in BODY and not any(p.get("in") in ("body", "formData") for p in params):
                params.append({"in": "body", "name": "body", "required": method == "post", "schema": {"type": "object", "example": BODY[rule]}})
            elif method in ("post", "put", "patch") and rule in NO_BODY:
                op["description"] += "\n\nNo request body is needed."
            for p in params:
                if p.get("in") == "body" and "schema" in p and rule in BODY:
                    p["schema"]["example"] = BODY[rule]   # concrete values beat the generic ones in the docstring
            # responses: examples + the errors every endpoint can return
            resp = op.setdefault("responses", {})
            if secured:
                resp.setdefault("401", {"description": ERRORS["401"][0]})
            if roles:
                resp.setdefault("403", {"description": ERRORS["403"][0]})
            if method in ("post", "put", "patch") and rule not in NO_BODY:
                resp.setdefault("422", {"description": ERRORS["422"][0]})
            if "{" in path:
                resp.setdefault("404", {"description": ERRORS["404"][0]})
            resp.setdefault("429", {"description": ERRORS["429"][0]})
            resp.setdefault("500", {"description": ERRORS["500"][0]})
            for code, r in resp.items():
                if "examples" in r:
                    continue
                if code.startswith("2"):
                    r["examples"] = {"application/json": _success_example(op, code, r.get("description"))}
                else:
                    r["examples"] = {"application/json": {"success": False, "message": ERRORS.get(code, (None, r.get("description")))[1] if code in ERRORS else r.get("description"),
                                                         "request_id": "9b1deb4d3b7d4bad9bdd2b0d7b3dcb6d"}}
    spec["x-enriched"] = True
    return spec
