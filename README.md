# Zahanati Digital: Backend API

REST API for **Zahanati Digital**, a digital health platform for Tanzania: patients find and order medicines from
pharmacies, talk to verified doctors by text chat, receive electronic prescriptions (PDF), read first-aid and
reproductive-health content, and track their cycle (HEDHI). Pharmacies manage stock and orders; admins approve
pharmacies and doctors and monitor the platform.

Built with **Flask 3 (application factory + blueprints), PostgreSQL, SQLAlchemy, Flask-Migrate, Flask-JWT-Extended,
Marshmallow, ReportLab, Flasgger (Swagger/OpenAPI), pytest, Docker**.

| | |
|---|---|
| Endpoints | **152**, all documented in Swagger UI (`/api/docs/`) and [docs/API_ENDPOINTS.md](docs/API_ENDPOINTS.md) |
| Tests | **211** automated tests (PostgreSQL: all pass; SQLite: 203 pass, 8 concurrency tests need PostgreSQL) |
| Roles | Patient, Doctor, Pharmacy, Administrator (role-based access control + ownership checks) |
| Languages | Kiswahili and English (API messages, notifications, SMS) |

## What it does

| Area | Highlights |
|---|---|
| **Sign-in** | Patients: phone number + SMS code (6 digits, 5 min, single use, 60 s resend, 5 wrong tries lock 10 min). Doctors, pharmacies, admins: phone + password. Refresh tokens, logout, password reset by SMS, token invalidation on password change/deactivation. |
| **Medicines & pharmacies** | Approved pharmacies only are visible. Search (2+ letters), ordered *available first, nearest, cheapest*. Stock shown as available / finished. Price changes are visible immediately; orders keep the price they were placed at. |
| **Orders** | 1-20 medicines from one pharmacy. Unpaid orders expire after 24 h. Prescription medicines need an approved prescription before payment. States: `new`, `ready`, `collected`, `cancelled`, `expired`. |
| **Prescriptions** | Upload a photo/PDF (max 5 MB, type checked by content, **encrypted**, deleted after 2 years) or attach an electronic prescription written by a doctor. Pharmacy approves or rejects. |
| **Payments** | M-Pesa / Tigo Pesa / Airtel Money flow: stock is held only while a payment is in progress, **HMAC-signed callback**, idempotent, one active payment per order (enforced by the database), timeouts, refunds recorded by the pharmacy. |
| **Doctors** | Registration with council (Tanganyika/Zanzibar) and unique licence number, admin verification, licence status, public verified badge, work history, dashboard, text consultations with a 24 h reply target and a "chat is not an emergency, call 112" notice, electronic prescriptions as PDF. |
| **Appointments** | Weekly availability, booking, rescheduling, accept/reject/cancel, **double-booking prevented** (overlap checks + row locks + unique index). Can be switched off (`FEATURE_APPOINTMENTS=false`). |
| **Content** | First-aid guides (public) and reproductive-health education: admin drafts, **one named reviewer approves each edition**, editing keeps the approved text live until re-approved. |
| **HEDHI** | Every entry encrypted at rest; estimates (next period, ovulation, fertile window), signs to see a doctor, export, delete everything, auto-delete after 2 years of inactivity. |
| **Admin** | Dashboard, user search and (de)activation, doctor and pharmacy approval, payments, refunds, content review, searchable audit log. |

## Quick start (local, terminal)

```bash
# 1. PostgreSQL
sudo apt install -y postgresql libpq-dev python3-venv
sudo -u postgres psql -c "CREATE USER zahanati WITH PASSWORD 'zahanati';"
sudo -u postgres psql -c "CREATE DATABASE zahanati OWNER zahanati;"

# 2. Python environment
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Configuration (never commit .env)
cp .env.example .env
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')|" .env
sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')|" .env
sed -i "s|^PAYMENT_CALLBACK_SECRET=.*|PAYMENT_CALLBACK_SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(24))')|" .env
export FLASK_APP=run.py
sed -i "s|^FILE_ENCRYPTION_KEYS=.*|FILE_ENCRYPTION_KEYS=$(flask generate-fernet-key)|" .env

# 4. Database
flask db init                      # first time only: creates migrations/
flask db migrate -m "initial schema"
python scripts/install_migrations.py   # adds the hand-written migrations (OTP/pharmacy, medicines, phases 8-13)
flask db upgrade
flask seed-specialisations
flask create-admin                 # asks for phone, optional email, password

# 5. Run
flask run                          # http://127.0.0.1:5000  (Swagger UI: /api/docs/)
```

In development the SMS codes are printed in the server terminal (`SMS_PROVIDER=console`).

### Run the tests

```bash
FLASK_ENV=testing python -m pytest -q                    # SQLite, no setup needed: 203 passed, 8 skipped
sudo -u postgres psql -c "CREATE DATABASE zahanati_test OWNER zahanati;"
TEST_DATABASE_URL=postgresql+psycopg2://zahanati:zahanati@localhost:5432/zahanati_test python -m pytest -q   # 211 passed
```

The PostgreSQL run also executes the **race-condition tests** (many people paying for the last unit, double-click on
"pay", parallel callbacks, simultaneous uploads).

### Docker

```bash
cp .env.example .env        # fill in secrets, DB_PASSWORD, FILE_ENCRYPTION_KEYS ...
docker compose up -d --build
docker compose --profile tls up -d     # optional: HTTPS with Caddy (set DOMAIN)
```
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). *The Docker files were written and syntax-checked but could not be run in the build environment (no Docker available).*

## Project structure

```
app/
  __init__.py        application factory, hooks (security headers, request id), CLI jobs, Swagger
  models/            SQLAlchemy models (users, profiles, appointments, orders, payments, content, ...)
  auth/ patients/ doctors/ pharmacies/ medicines/ appointments/ orders/ payments/
  consultations/ prescriptions/ notifications/ content/ hedhi/ admin/
                     each module: routes.py (HTTP + OpenAPI docs), schemas.py (Marshmallow), services.py (rules)
  common/            decorators (RBAC), errors, i18n (sw/en), crypto + storage (Fernet), sms, audit, validators
  docs.py            completes the OpenAPI spec (roles, examples, error responses)
migrations/          Alembic (create with `flask db init`; hand-written parts in scripts/*.template)
scripts/             install_migrations.py, generate_api_docs.py
tests/               211 tests
docs/                API_ENDPOINTS.md, DEPLOYMENT.md, ARCHITECTURE.md, SECURITY.md, SPEC_COMPLIANCE.md
deploy/              Caddyfile, nginx.conf
```

## Scheduled jobs (cron or the `jobs` container)

| Command | Every | Purpose |
|---|---|---|
| `flask expire-orders` | 5 min | unpaid orders older than 24 h become `expired` |
| `flask expire-payments` | 5 min | payments with no confirmation after 30 min fail and release their stock |
| `flask purge-prescriptions` | day | delete prescription files older than 2 years |
| `flask purge-inactive-hedhi` | day | delete HEDHI data of customers inactive for 2 years |

## Configuration

Everything is configured through environment variables; see [`.env.example`](.env.example) (every variable is explained
there). Secrets are never in the code. In production the app **refuses to start** without `SECRET_KEY`, `JWT_SECRET_KEY`,
`DATABASE_URL`, `FILE_ENCRYPTION_KEYS`, `PAYMENT_CALLBACK_SECRET` and `SMS_PROVIDER=beem`.

## Known limitations (please read)

1. **Payment provider.** The complete payment flow is implemented and tested, but only a *simulator* provider exists.
   Connecting real M-Pesa / Tigo Pesa / Airtel Money needs the chosen aggregator's API credentials and one adapter class
   (`app/payments/providers.py`, a single `initiate()` method). Production mode refuses to start with the simulator unless
   `ALLOW_PAYMENT_SIMULATOR=true` (demo only).
2. **Beem Africa SMS.** The adapter follows Beem's API format but has only been tested with simulated responses. Verify it
   with your credentials before launch.
3. **Medical content and rules need human review.** Cycle estimates (HEDHI) use common textbook parameters (14-day luteal
   phase, fertile window of 6 days); first-aid and education texts are *workflow-ready but empty*. The specification requires
   a named medical reviewer for every text.
4. **Docker and Redis rate-limit storage** were not executed in the build environment.
5. Not included, by specification: video calls, AI symptom checker, ambulance requests, doctor fees, full health records.
6. No account-deletion endpoint other than "delete all HEDHI data"; see [docs/SECURITY.md](docs/SECURITY.md) for data-protection notes.

Full requirement-by-requirement status: [docs/SPEC_COMPLIANCE.md](docs/SPEC_COMPLIANCE.md).
