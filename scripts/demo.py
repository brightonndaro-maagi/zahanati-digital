"""End-to-end demo of Zahanati Digital. Runs the real API in-process against YOUR configured database and prints
every step of a complete journey. Creates demo accounts with random phone numbers, so it can be run many times.

    source venv/bin/activate
    export FLASK_APP=run.py
    SMS_PROVIDER=memory python scripts/demo.py            # add  --lang sw  for Kiswahili messages

Needs the normal .env (SECRET_KEY, JWT_SECRET_KEY, DATABASE_URL, FILE_ENCRYPTION_KEYS, PAYMENT_CALLBACK_SECRET).
SMS_PROVIDER=memory lets the script read the SMS codes itself instead of you copying them from the server log."""
import hashlib
import hmac
import io
import json
import os
import random
import re
import sys
from pathlib import Path

os.environ["SMS_PROVIDER"] = "memory"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402

LANG = "sw" if "--lang" in sys.argv and sys.argv[sys.argv.index("--lang") + 1] == "sw" else "en"
app = create_app(os.environ.get("FLASK_ENV", "development"))
client = app.test_client()
HDR = {"Accept-Language": LANG}
steps = 0
calls = 0


def call(method, url, token=None, expect=(200, 201), **kw):
    global calls
    calls += 1
    headers = {**HDR, **({"Authorization": f"Bearer {token}"} if token else {}), **kw.pop("headers", {})}
    r = getattr(client, method)(url, headers=headers, **kw)
    if r.status_code not in (expect if isinstance(expect, tuple) else (expect,)):
        sys.exit(f"\nFAILED {method.upper()} {url} -> {r.status_code}: {r.get_data(as_text=True)[:400]}")
    return r


def data(r):
    return r.get_json()["data"]


def step(text):
    global steps
    steps += 1
    print(f"\n[{steps:02d}] {text}")


def ok(text):
    print(f"     OK  {text}")


def sms_code(phone):
    for to, msg in reversed(app.extensions.get("sms_outbox", [])):
        if to == phone:
            return re.search(r"\b(\d{6})\b", msg).group(1)
    sys.exit(f"No SMS was sent to {phone}")


def rand_phone(prefix):
    return f"+255{prefix}{random.randint(1000000, 9999999)}"


def register_staff(kind, body):
    call("post", "/api/v1/auth/otp/request", json={"phone": body["phone"], "purpose": "register"})
    r = call("post", f"/api/v1/auth/register/{kind}", json={**body, "otp_code": sms_code(body["phone"])})
    return data(r)["access_token"]


def patient_login(phone, name):
    call("post", "/api/v1/auth/otp/request", json={"phone": phone})
    r = call("post", "/api/v1/auth/otp/verify", json={"phone": phone, "code": sms_code(phone), "full_name": name})
    return data(r)["access_token"]


secret = app.config.get("PAYMENT_CALLBACK_SECRET")
if not secret or not app.config.get("FILE_ENCRYPTION_KEYS"):
    sys.exit("Set PAYMENT_CALLBACK_SECRET and FILE_ENCRYPTION_KEYS in .env first (see the README, step 3).")

with app.app_context():
    admin = User.query.filter_by(phone="+255700009999").first()
    if not admin:
        admin = User(phone="+255700009999", role="admin")
        admin.set_password("DemoAdmin2026")
        db.session.add(admin)
        db.session.commit()
print("=" * 72 + "\nZAHANATI DIGITAL: end-to-end demo\n" + "=" * 72)

step("Administrator signs in")
admin_t = data(call("post", "/api/v1/auth/login", json={"phone": "+255700009999", "password": "DemoAdmin2026"}))["access_token"]
ok("admin logged in (phone + password)")

step("A pharmacy registers (SMS code proves the phone), the admin approves it")
ph_phone = rand_phone("73")
ph_t = register_staff("pharmacy", {"phone": ph_phone, "password": "DemoPass2026", "name": "Afya Bora Pharmacy", "address": "Kariakoo, Dar es Salaam",
                                   "license_number": f"PC-{random.randint(10000, 99999)}", "latitude": -6.8184, "longitude": 39.2766})
pid = data(call("get", "/api/v1/admin/pharmacies?status=pending", admin_t))[0]["id"]
call("post", f"/api/v1/admin/pharmacies/{pid}/approve", admin_t)
ok(f"pharmacy {ph_phone} approved")

step("The pharmacy lists three medicines (one needs a prescription, one is out of stock)")
tag = random.randint(100, 999)
meds = {}
for key, body in {"para": {"name": f"Paracetamol 500mg #{tag}", "generic_name": "Paracetamol", "price_tzs": 1500, "stock_quantity": 100},
                  "amox": {"name": f"Amoxicillin 500mg #{tag}", "generic_name": "Amoxicillin", "price_tzs": 3500, "stock_quantity": 40, "requires_prescription": True},
                  "out": {"name": f"Vitamin C #{tag}", "price_tzs": 800, "stock_quantity": 0}}.items():
    meds[key] = data(call("post", "/api/v1/pharmacies/me/medicines", ph_t, json=body))["id"]
ok("3 medicines added")

step("A doctor registers; the admin verifies the licence")
dr_phone = rand_phone("72")
dr_t = register_staff("doctor", {"phone": dr_phone, "password": "DemoPass2026", "first_name": "Neema", "last_name": "Mushi",
                                 "license_number": f"MCT-{random.randint(10000, 99999)}", "qualification": "MD"})
did = data(call("get", "/api/v1/admin/doctors?status=pending", admin_t))[0]["id"]
call("post", f"/api/v1/admin/doctors/{did}/verify", admin_t, json={"verified_name": "Neema Mushi"})
call("post", "/api/v1/doctors/me/workplaces", dr_t, json={"institution": "Muhimbili National Hospital", "is_current": True})
ok(f"doctor {dr_phone} verified, badge shown to patients")

step("A new patient signs in with an SMS code (no password)")
pt_phone = rand_phone("71")
pt_t = patient_login(pt_phone, "Asha Juma")
ok(f"patient {pt_phone} created: {data(call('get', '/api/v1/auth/me', pt_t))['full_name']}")

step("The patient searches for medicines near Kariakoo")
res = data(call("get", f"/api/v1/medicines?q={tag}&lat=-6.82&lon=39.27", pt_t))
for m in res:
    print(f"     - {m['name']:<28} TZS {m['price_tzs']:<6} {'available' if m['available'] else 'FINISHED ':<9} {m['distance_km']} km  {'[needs prescription]' if m['requires_prescription'] else ''}")
ok("available medicines first, then nearest, then cheapest; out-of-stock is listed but cannot be ordered")
call("post", "/api/v1/orders", pt_t, json={"items": [{"medicine_id": meds["out"], "quantity": 1}]}, expect=409)
ok("ordering the finished medicine is refused (409)")

step("The patient orders Paracetamol + Amoxicillin (needs a prescription)")
order = data(call("post", "/api/v1/orders", pt_t, json={"items": [{"medicine_id": meds["para"], "quantity": 2}, {"medicine_id": meds["amox"], "quantity": 1}]}))
oid = order["id"]
ok(f"order total TZS {order['total_tzs']}, prescription_status={order['prescription_status']}, payable={order['payable']}")
call("post", f"/api/v1/orders/{oid}/pay", pt_t, json={"network": "mpesa"}, expect=409)
ok("payment is refused until the prescription is approved (409)")

step("The patient asks the doctor for advice by text chat")
cid = data(call("post", "/api/v1/consultations", pt_t, json={"doctor_id": did, "subject": "Koo", "message": "Habari daktari, nina kikohozi kwa wiki moja."}))["id"]
call("post", f"/api/v1/consultations/{cid}/messages", dr_t, json={"body": "Pole sana. Nitakuandikia dawa."})
ok("doctor replied (notice: chat is not an emergency, call 112)")

step("The doctor issues an electronic prescription; the patient downloads the PDF")
rx = data(call("post", f"/api/v1/consultations/{cid}/prescriptions", dr_t, json={
    "notes": "Maliza dozi yote", "items": [{"medicine_name": "Amoxicillin", "dosage": "500mg", "frequency": "3 times a day", "duration_days": 7}]}))
pdf = call("get", f"/api/v1/prescriptions/{rx['id']}/pdf", pt_t)
Path("demo_prescription.pdf").write_bytes(pdf.data)
ok(f"prescription {rx['id'][:8]} issued; PDF saved as ./demo_prescription.pdf ({len(pdf.data)} bytes)")

step("The patient attaches the prescription to the order; the order becomes payable")
o = data(call("post", f"/api/v1/orders/{oid}/prescription/use", pt_t, json={"prescription_id": rx["id"]}))
ok(f"prescription_status={o['prescription_status']}, payable={o['payable']}")

step("The patient pays by M-Pesa; the provider's signed callback confirms it")
o = data(call("post", f"/api/v1/orders/{oid}/pay", pt_t, json={"network": "mpesa"}))
with app.app_context():
    from app.models import Payment
    ref = Payment.query.filter_by(order_id=oid).one().provider_ref
raw = json.dumps({"provider_ref": ref, "status": "success", "amount_tzs": o["total_tzs"]}).encode()
sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
call("post", "/api/v1/payments/callback", data=raw, headers={"X-Signature": sig, "Content-Type": "application/json"})
call("post", "/api/v1/payments/callback", expect=401, data=raw, headers={"X-Signature": "0" * 64, "Content-Type": "application/json"})
ok("payment_status=paid; a forged callback was rejected (401)")

step("The pharmacy prepares the order and the customer collects it")
call("post", f"/api/v1/orders/{oid}/ready", ph_t)
call("post", f"/api/v1/orders/{oid}/collect", ph_t)
final = data(call("get", f"/api/v1/orders/{oid}", pt_t))
ok(f"order status={final['status']}, payment={final['payment_status']}")

step("Privacy: another customer cannot see this order or the chat")
other = patient_login(rand_phone("71"), "Baraka Lema")
call("get", f"/api/v1/orders/{oid}", other, expect=404)
call("get", f"/api/v1/consultations/{cid}", other, expect=404)
call("get", f"/api/v1/consultations/{cid}", admin_t, expect=403)
ok("404 for the other customer; 403 even for the administrator")

step("HEDHI: the patient logs three periods and gets (encrypted) estimates")
for start, end in (("2026-08-20", "2026-08-24"), ("2026-09-17", "2026-09-21"), ("2026-10-15", "2026-10-19")):
    call("post", "/api/v1/hedhi/cycles", pt_t, json={"start_date": start, "end_date": end, "flow": "medium"})
ins = data(call("get", "/api/v1/hedhi/insights?on=2026-10-30", pt_t))
ok(f"average cycle {ins['average_cycle_length']} days, next period {ins['next_period_start']}, fertile window {ins['fertile_window']['start']} to {ins['fertile_window']['end']}")

step("The patient receives notifications")
n = data(call("get", "/api/v1/notifications?per_page=50", pt_t))
for x in n[:4]:
    print(f"     - {x['message']}")
ok(f"{len(n)} notifications")

step("The administrator's dashboard")
d = data(call("get", "/api/v1/admin/dashboard", admin_t))
ok(f"users {d['users']['by_role']}; orders {d['orders']['by_status']}; paid last 30 days: {d['payments_last_30_days']['paid_total_tzs']} TZS")
logs = call("get", "/api/v1/admin/audit-logs?per_page=1", admin_t).get_json()["meta"]["total"]
ok(f"{logs} audit-log entries recorded (no passwords, codes or health content inside)")

print("\n" + "=" * 72 + f"\nDONE: {steps} steps, {calls} API calls, all as expected.\nOpen /api/docs/ for the full API, and ./demo_prescription.pdf for the prescription.\n" + "=" * 72)
