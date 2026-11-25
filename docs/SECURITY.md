# Security and data protection

## Implemented controls
- **Authentication:** OTP (hashed with HMAC, single use, expiry, resend delay, lockout); passwords hashed with scrypt; policy
  (8+ chars, letters + digits, common passwords refused); JWT access (15 min) + refresh (7 days) tokens; logout revokes tokens;
  password change/reset and deactivation invalidate older tokens.
- **Authorization:** role checks on every endpoint (`roles_required`), ownership checks on every resource (other people's
  resources return 404, not 403, so existence is not revealed), doctors only reach patient data with an appointment or a
  consultation the patient started, only verified doctors with an active licence can chat or prescribe, only approved pharmacies sell.
- **Input:** Marshmallow validation on all bodies; SQLAlchemy parameter binding (no string-built SQL); LIKE wildcards escaped;
  strict integers for money/quantities; file type from magic bytes; 5 MB upload limit; 6 MB request limit.
- **Data at rest:** prescription files and HEDHI entries encrypted (Fernet); retention jobs delete after 2 years.
- **Transport and browser:** HTTPS terminated at the proxy (HSTS sent when secure), `nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, API `Content-Security-Policy: default-src 'none'`, `Cache-Control: no-store`, CORS allow-list.
- **Abuse:** rate limits on login, OTP, registration, ordering, paying, uploads and messages (Redis-backed in production);
  anti-enumeration on OTP/password-reset answers.
- **Payments:** signed callbacks, idempotent, amount verified, one active payment per order at the database level.
- **Operations:** secrets only from environment; app refuses unsafe production configuration; non-root container; audit log of
  important actions (never containing secrets or health content); request ids in every response; generic 500 errors.

## Data protection (Tanzania Personal Data Protection Act, 2022)
This software provides technical measures: purpose-limited collection, access control, encryption of sensitive health data,
retention limits, audit logging, export and deletion of HEDHI data. As the operator you must additionally: register as a data
controller/processor with the Personal Data Protection Commission, publish a privacy notice and obtain consent in the mobile
app, define breach-notification procedures, keep the database in the permitted jurisdiction (or comply with transfer rules) and
sign data-processing agreements with Beem and the payment provider. Get legal review before launch.

## Known gaps
- No self-service account deletion (only HEDHI "delete all"); add one with your legal advisor's retention rules.
- Doctor `document_url` credentials are links, not uploaded files.
- Rate limits are per IP (and per phone for OTP). Add a WAF for large-scale abuse.
- No two-factor authentication for administrators yet.
- Malware scanning of uploaded files is not performed (type and size are checked, files are stored encrypted and only served to the pharmacy).
