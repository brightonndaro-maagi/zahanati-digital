# Specification compliance

Two specifications were provided: **Spec 1** (the Flask/PostgreSQL MVP backend prompt) and **Spec 2** (the Swahili "MVP
Specification, toleo la 2", of which the PDF was cut off in section 15.1). They were merged as agreed. Status:
**Done** = implemented and tested, **Partly** = implemented with a stated limit, **Not done** = open item.

## Spec 1: technical requirements
| Requirement | Status | Where / note |
|---|---|---|
| Python 3.12, Flask, PostgreSQL, SQLAlchemy, Flask-Migrate, JWT, Marshmallow, Swagger, ReportLab, pytest, Docker | Done | `requirements.txt`, `Dockerfile`, `docker-compose.yml` (Docker not executed here) |
| Application factory + blueprints, routes/schemas/services/models separated | Done | `app/` |
| Roles patient / doctor / admin with RBAC and ownership checks | Done | plus pharmacy role (Spec 2) |
| Registration, login, logout, access + refresh tokens, hashing, password recovery, activation/deactivation | Done | OTP for patients, password for others |
| Patient profile, medical history, medical records, consultation history, prescription history | Done | `/patients/me/*`, `/consultations`, `/prescriptions` |
| Doctor profile, specialisations, qualifications, licence submission, admin verification, search/filter, verified status | Done | `/doctors`, `/admin/doctors` |
| Appointments: availability, book, reschedule, cancel, accept/reject, statuses, **no double booking** | Done | tested with concurrent requests on PostgreSQL |
| Consultation records linked to appointments, notes, diagnosis, recommendations, history | Done | consultations are chat threads; appointment link optional; video excluded |
| Electronic prescriptions with medicines, dosage, frequency, duration, dates, **PDF download**, patient access, verified doctors only | Done | immutable, can be cancelled |
| Admin dashboard, user management, doctor verification, appointment monitoring, activity monitoring, audit logs | Done | `/admin/*` |
| 12 listed tables | Done | `users`, `patient_profiles`, `doctor_profiles`, `specialisations`, `doctor_specialisations`, `doctor_credentials`, `appointments`, `consultations`, `medical_records`, `prescriptions`, `prescription_items`, `audit_logs` + extra tables for later modules |
| UUIDs, uniqueness, FKs, indexes, migrations | Done | |
| `/api/v1/*`, GET/POST/PUT/PATCH/DELETE, consistent JSON, status codes, validation, pagination, filtering, errors | Done | |
| Security list (hashing, JWT, RBAC, ownership, validation, SQL injection, rate limiting, env config, audit, CORS, medical-record handling, prescription protection) | Done | [SECURITY.md](SECURITY.md) |
| Tests for every listed area | Done | 211 tests |
| Swagger/OpenAPI for every endpoint (URL, method, auth, parameters, request example, response example, errors) | Done | `/api/docs/`; a test fails if an endpoint lacks any of these |
| Deliverables: source, schema, migrations, APIs, Swagger, tests, Docker, `.env.example`, README, endpoint docs, deployment | Done | |
| Excluded: AI symptom checker, ambulance, pharmacy management (Spec 1 only), HEDHI (Spec 1 only), payments (Spec 1 only), video | Done / superseded | Spec 2 adds pharmacy, payments and HEDHI to the MVP; AI, ambulance and video remain excluded |

## Spec 2: product requirements
| Section | Status | Note |
|---|---|---|
| 3.1 OTP (6 digits, 5 min, single use, resend 60 s, 5 tries then 10 min, full name first time, token for all requests) | Done | |
| 3.2 Medicine search (2+ letters; shows price, pharmacy, distance, availability, prescription mark; order available > distance > price; finished medicine visible but not orderable) | Done | |
| 3.3 Ordering (1-20 medicines; no prescription: pay then pharmacy prepares; with prescription: cannot pay until approved; unpaid order expires after 24 h) | Done | *Interpretation:* 1-20 **different medicines** per order, quantity per medicine up to 20 (both configurable) |
| 3.4 Prescription file (PDF/JPG/PNG <= 5 MB, re-upload after rejection, only the pharmacy sees it, encrypted, deleted after 2 years) | Done | plus electronic prescriptions from doctors |
| 3.5 Payments (callback, stock held during payment, only released on failure/expiry, no prescription-less preparation before `paid`, never paid twice) | Done | real provider adapter **not yet written** (simulator only) |
| 3.6 Customer sees all orders and status; cancel before paying | Done | cancel after payment goes through a refund |
| 4.1 Pharmacy registration and approval; unapproved invisible | Done | |
| 4.2 Stock and price (whole shillings, available/finished, immediate changes, existing orders keep price) | Done | |
| 4.3 Pharmacy orders view and states (`ready` only when paid and prescription ok, `collected`, `cancelled`) | Done | |
| 4.4 Refunds handled by the pharmacy, recorded with amount, reason, date | Done | `[WAZI]` ordering through the payment provider: system only records |
| 4.5 In-app notifications (new order, prescription uploaded, payment received) | Done | plus more events; SMS for "order ready" |
| 5.1-5.3 Doctor registration (MCT number, unique), admin verification with the register name, dashboard (experience, workplace history, licence status, inbox), verified badge | Done | council field (Tanganyika/Zanzibar) per 15.1 point 5 |
| 5.2 "Prescription writing section inside chat" `[WAZI]` | Done (decision) | electronic prescription issued in an open consultation; usable for orders (auto-approved when it covers every prescription medicine) |
| 6 Chat (text only, to verified doctors, private, 24 h reply target, any doctor, 112 notice) | Done | not even admins can read chats |
| 7 First aid (searchable, public, no AI, reviewed, do / do-not / when to call emergency, editions) | Done | **content itself is empty**: needs your medical reviewers |
| 8 HEDHI (encrypted, delete all data, 2-year inactivity, estimates, doctor signs and search path) and reproductive-health education (8 stages, reviewed) | Done | estimates use textbook parameters: have your reviewers confirm them |
| 9 Admin (dashboard, approvals, licences, content review) | Done | |
| 10-11 Business rules and states (order / prescription / payment states) | Done | |
| 12 Data (customers, otp, pharmacies, medicines, orders, notifications, doctors, consultations, prescriptions, hedhi, first aid, education, refunds, audit) | Done | |
| 13 Acceptance criteria | Done | each has a test (OTP rules, paid before preparing, no purchase without approved prescription, 24 h expiry, privacy between customers, unapproved pharmacy invisible, unverified doctor has no badge, chat answers through the same thread, unreviewed content hidden, HEDHI export/delete, all tests pass) |
| 14 Non-functional: HTTPS, encrypted health data, server storage, SQLite for tests / PostgreSQL for production, Kiswahili + English | Done | HTTPS via proxy config (untested here) |
| 15.1 Closed decisions: Beem SMS; M-Pesa + Tigo first through one aggregator (Airtel later); reviewed content with one named reviewer; 2-year retention; Zanzibar doctors | Partly | Beem adapter untested live; aggregator adapter missing; others done |
| 15.2 Open: legal advice on prescription without payment / chat without prior relationship / health data protection | Not done | needs a lawyer; see SECURITY.md |
| "Mobile app screens", real SMS/payments, HTTPS hosting | Out of scope | backend only |
