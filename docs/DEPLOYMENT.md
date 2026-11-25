# Deployment guide

## 1. What you need
- A Linux server (2 GB RAM is enough to start), a domain name, Docker + Docker Compose **or** Python 3.12 + PostgreSQL 16.
- A [Beem Africa](https://beem.africa) account (SMS) and, later, a payment aggregator account.

## 2. Secrets (generate once, store safely)
```bash
python3 -c "import secrets;print(secrets.token_hex(32))"   # SECRET_KEY
python3 -c "import secrets;print(secrets.token_hex(32))"   # JWT_SECRET_KEY
python3 -c "import secrets;print(secrets.token_hex(24))"   # PAYMENT_CALLBACK_SECRET
flask generate-fernet-key                                   # FILE_ENCRYPTION_KEYS
```
> **Back up `FILE_ENCRYPTION_KEYS` separately from the database.** If the key is lost, prescription files and HEDHI data
> can never be read again. If it leaks, change it (see rotation below).

## 3. Docker Compose (recommended)
```bash
cp .env.example .env          # set FLASK_ENV=production, secrets, DB_PASSWORD, SMS_PROVIDER=beem + Beem keys, CORS_ORIGINS, DOMAIN
docker compose up -d --build
docker compose exec api flask create-admin
docker compose exec api flask seed-specialisations
curl http://127.0.0.1:5000/api/v1/health
docker compose --profile tls up -d        # HTTPS via Caddy (needs DNS pointing to the server, ports 80/443 open)
```
Services: `db` (PostgreSQL), `redis` (shared rate limits), `api` (gunicorn, runs `flask db upgrade` on start), `jobs`
(runs the scheduled commands every 5 minutes), `proxy` (Caddy, optional). Prescription files live in the `uploads` volume.

Migrations: the `migrations/` folder must exist in the image. Create it on your machine once
(`flask db init`, `flask db migrate`, `python scripts/install_migrations.py`) and commit it.

## 4. Without Docker
Follow the Quick start in the README, run with `gunicorn -w 3 -b 127.0.0.1:5000 run:app` behind nginx
(`deploy/nginx.conf`, TLS with certbot), and add cron lines:
```
*/5 * * * * cd /srv/zahanati && venv/bin/flask expire-orders && venv/bin/flask expire-payments
15 3 * * *  cd /srv/zahanati && venv/bin/flask purge-prescriptions && venv/bin/flask purge-inactive-hedhi
```
Set `PROXY_HOPS=1` so the app trusts the proxy's `X-Forwarded-For` (rate limits and audit IPs depend on it) and
`RATELIMIT_STORAGE_URI=redis://...` so limits are shared between workers.

## 5. Payments: connecting a real provider
The flow is complete (reserve stock, pending payment, signed callback, idempotency, timeouts, refund records). To go live:
1. Choose an aggregator that supports M-Pesa, Tigo Pesa and Airtel Money and get sandbox credentials.
2. Add a class to `app/payments/providers.py` with `initiate(payment) -> provider_ref` (call the aggregator's "request
   payment" API with `payment.amount_tzs`, `payment.network`, `payment.payer_phone`) and register it in `_PROVIDERS`.
3. Give the aggregator the callback URL `https://<domain>/api/v1/payments/callback` and the shared
   `PAYMENT_CALLBACK_SECRET`. The callback must send header `X-Signature` = hex HMAC-SHA256 of the raw body with that
   secret and a JSON body `{provider_ref, status: "success"|"failed", amount_tzs}`. If the aggregator signs differently,
   adapt `verify_signature()` in `app/payments/services.py` (one function).
4. Set `PAYMENT_PROVIDER=<your adapter name>`, test with the sandbox, then go live.

## 6. Operations
- **Health:** `GET /api/v1/health`. Every response has an `X-Request-ID`; error bodies contain it: ask users for it.
- **Logs:** gunicorn access log + application log on stdout (`docker compose logs -f api`).
- **Audit trail:** admin endpoint `/api/v1/admin/audit-logs`.
- **Backups:** `pg_dump` the database daily and snapshot the `uploads` volume; keep the encryption keys elsewhere.
- **Upgrades:** pull, rebuild, `flask db upgrade` (the compose `api` service does it automatically).
- **Key rotation:** put the new key *first*: `FILE_ENCRYPTION_KEYS=<new>,<old>`; all data stays readable and new data uses
  the new key. Remove the old key only after re-encrypting (or after the 2-year retention has passed).
- **Swagger in production:** set `SWAGGER_ENABLED=false` if you do not want to expose it.
