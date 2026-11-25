# Architecture and design decisions

## Layers
`routes.py` (HTTP, validation, OpenAPI docs) -> `services.py` (business rules, transactions) -> `models/` (SQLAlchemy).
Cross-cutting code is in `app/common/`. Routes never contain business rules, so every rule is testable without HTTP.

## Decisions
| Decision | Why |
|---|---|
| UUID primary keys | Not guessable (no enumeration of `/orders/1`, `/orders/2`). Malformed ids return 404, never a database error. |
| Phone number is the identity | Customers in Tanzania use phones, not email. OTP for patients; password for professionals. Email is optional. |
| Phone ownership is proven (OTP) before a doctor/pharmacy account is created | Stops someone registering a victim's number. |
| Everything stored in UTC, shown in `Africa/Dar_es_Salaam` | One rule for times; naive client input is treated as local time. |
| Prices are integers (TZS) | No floating-point money errors; whole shillings only, as specified. |
| Order items copy name and price | Later price changes never alter an existing order. |
| Stock is reserved when payment *starts*, released when it fails/times out | Matches the specification; medicines are locked in id order (no deadlocks). |
| Double booking / double payment prevented in three layers | service check + PostgreSQL row locks + unique index (partial). Tested with real concurrent requests. |
| Callback authenticated with HMAC, idempotent, amount-checked | A forged or repeated callback can never mark an order paid twice or for the wrong amount. |
| Late payment after our timeout | Re-reserves stock if possible, otherwise the money is kept visible and a refund is recorded. Money is never silently lost. |
| Files and HEDHI encrypted with Fernet (AES-128-CBC + HMAC), keys from the environment, rotation supported | Specification; key never in code or database. File type is detected from content, not the extension. |
| Reviewed content uses a `live` snapshot | The approved text stays visible while an edited version waits for the next review. |
| Chat is private even from admins | Specification (patient and doctor only). Admins see counts, not conversations or HEDHI data. |
| Audit log stores ids and counts, never content or secrets | Verified by a test that scans the whole log. |
| `can_practice` is one rule (verified + licence active + account active) | Used everywhere a doctor is found, consulted or prescribes. |
| Hand-written migrations in `scripts/*.template` + installer | Alembic does not see CHECK constraints or functional indexes; the installer chains them onto *your* migration history. |
| Swagger spec is completed by `app/docs.py` and checked by a test | A new endpoint without documentation fails the test suite. |

## Extending later (the architecture leaves room)
Video consultation: `consultations.mode` and `external_session_ref` exist. A new payment provider: one adapter class.
Ambulance, AI symptom checker, pharmacy delivery: new modules (blueprint + models); nothing existing changes.
