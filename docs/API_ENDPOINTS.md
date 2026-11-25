# Zahanati Digital: API endpoints

Generated from the OpenAPI spec (`/api/openapi.json`). Interactive version: **`/api/docs/`**.

- Base URL: `/api/v1`. Send `Authorization: Bearer <access_token>` where a role is listed.
- Language: `Accept-Language: sw|en` (or `?lang=`). Success: `{success, message, data, meta?}`. Errors: `{success:false, message, errors?, request_id}`.
- Pagination: `?page=&per_page=` (max 100); lists return `meta: {page, per_page, total, pages}`.

**152 endpoints**

## Auth

| Method | Path | Who |
|---|---|---|
| POST | `/api/v1/auth/change-password` | doctor, pharmacy, admin |
| POST | `/api/v1/auth/forgot-password` | public |
| POST | `/api/v1/auth/login` | public |
| POST | `/api/v1/auth/logout` | any signed-in user |
| GET | `/api/v1/auth/me` | any signed-in user |
| PATCH | `/api/v1/auth/me/language` | any signed-in user |
| POST | `/api/v1/auth/otp/request` | public |
| POST | `/api/v1/auth/otp/verify` | public |
| POST | `/api/v1/auth/phone/change/confirm` | any signed-in user |
| POST | `/api/v1/auth/phone/change/request` | any signed-in user |
| POST | `/api/v1/auth/refresh` | any signed-in user |
| POST | `/api/v1/auth/register/doctor` | public |
| POST | `/api/v1/auth/register/pharmacy` | public |
| POST | `/api/v1/auth/reset-password` | public |
| GET | `/api/v1/health` | public |

### POST `/api/v1/auth/change-password`

Change password (doctors, pharmacies, admins).

**Authentication:** Bearer access token; allowed roles: doctor, pharmacy, admin.

Request body:

```json
{
  "current_password": "Secret123",
  "new_password": "Brand-new-77"
}
```

Responses: `200` Password changed; `400` Current password incorrect; `401` Missing, invalid or expired token; `403` Patients have no password; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/auth/forgot-password`

Send a reset code by SMS to a doctor/pharmacy/admin account (always answers 200 to avoid account enumeration).

**Authentication:** none (public endpoint).

Request body:

```json
{
  "phone": "0755123456"
}
```

Responses: `200` Request accepted; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/auth/login`

Password login for doctors, pharmacies and admins (patients use /auth/otp/*).

**Authentication:** none (public endpoint).

Request body:

```json
{
  "password": "Secret123",
  "phone": "0755123456"
}
```

Responses: `200` Logged in; `401` Invalid credentials; `403` Account deactivated; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/auth/logout`

Revoke the presented token (send the refresh token too to fully log out).

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` Token revoked; `401` Missing, invalid or expired token; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/auth/me`

Current authenticated user.

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` Current user; `401` Unauthenticated; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/auth/me/language`

Choose the language of your SMS messages and notifications (sw|en).

**Authentication:** Bearer access token; any signed-in user.

Request body:

```json
{
  "language": "sw"
}
```

Responses: `200` Saved; `401` Missing, invalid or expired token; `422` Unsupported language; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/auth/otp/request`

Send a 6-digit code by SMS. purpose=login (patients, default) or register (doctors/pharmacies before registering).

**Authentication:** none (public endpoint).

Request body:

```json
{
  "lang": "sw",
  "phone": "0712345678",
  "purpose": "login"
}
```

Responses: `200` Request accepted (the response never reveals whether the number is registered); `422` Invalid phone number; `429` Resend too soon; `500` Unexpected server error (see request_id when contacting support); `503` SMS could not be sent

### POST `/api/v1/auth/otp/verify`

registration_required=true (the code is not consumed); call again with full_name to create the account.<br/>

**Authentication:** none (public endpoint).

Request body:

```json
{
  "code": "123456",
  "full_name": "Asha Juma",
  "phone": "0712345678"
}
```

Responses: `200` Logged in; `400` Invalid or expired code; `403` Staff number (use password login) or deactivated account; `422` Validation failed; `429` Too many wrong attempts; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/auth/phone/change/confirm`

Confirm the new phone number with the SMS code.

**Authentication:** Bearer access token; any signed-in user.

Request body:

```json
{
  "code": "123456",
  "phone": "0755123456"
}
```

Responses: `200` Phone number changed; `400` Invalid or expired code; `401` Missing, invalid or expired token; `409` Number already registered; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/auth/phone/change/request`

Send a code to a NEW phone number to prove you own it.

**Authentication:** Bearer access token; any signed-in user.

Request body:

```json
{
  "phone": "0755123456"
}
```

Responses: `200` Code sent; `401` Missing, invalid or expired token; `409` Number already registered; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/auth/refresh`

Exchange a refresh token for a new access token.

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` New access token; `401` Invalid; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/auth/register/doctor`

Status starts as 'pending' until an admin verifies the MCT licence.<br/>

**Authentication:** none (public endpoint).

Request body:

```json
{
  "council": "tanganyika",
  "first_name": "Neema",
  "last_name": "Mushi",
  "license_number": "MCT-12345",
  "otp_code": "123456",
  "password": "Secret123",
  "phone": "0755123456",
  "qualification": "MD",
  "specialisation_ids": []
}
```

Responses: `201` Doctor created; `400` Invalid or expired code; `409` Phone; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/auth/register/pharmacy`

Register a pharmacy (hidden from customers until an admin approves it).

**Authentication:** none (public endpoint).

Request body:

```json
{
  "address": "Kariakoo, Dar es Salaam",
  "latitude": -6.8184,
  "license_number": "PC-0001",
  "longitude": 39.2766,
  "name": "Afya Pharmacy",
  "otp_code": "123456",
  "password": "Secret123",
  "phone": "0713000111"
}
```

Responses: `201` Pharmacy created; `400` Invalid or expired code; `409` Phone; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/auth/reset-password`

Set a new password using the SMS code.

**Authentication:** none (public endpoint).

Request body:

```json
{
  "code": "123456",
  "new_password": "Brand-new-77",
  "phone": "0755123456"
}
```

Responses: `200` Password updated; `400` Invalid or expired code; `422` Validation failed; `429` Too many wrong attempts; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/health`

Health check for load balancers and uptime monitors.

**Authentication:** none (public endpoint).

Responses: `200` The API is running; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Patients

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/patients/me` | patient |
| PUT | `/api/v1/patients/me` | patient |
| PATCH | `/api/v1/patients/me` | patient |
| GET | `/api/v1/patients/me/medical-records` | patient |
| POST | `/api/v1/patients/me/medical-records` | patient |
| GET | `/api/v1/patients/me/medical-records/{record_id}` | patient |
| PUT | `/api/v1/patients/me/medical-records/{record_id}` | patient |
| PATCH | `/api/v1/patients/me/medical-records/{record_id}` | patient |
| DELETE | `/api/v1/patients/me/medical-records/{record_id}` | patient |
| GET | `/api/v1/patients/{patient_id}` | doctor, admin |
| GET | `/api/v1/patients/{patient_id}/medical-records` | doctor, admin |

### GET `/api/v1/patients/me`

Get my patient profile.

**Authentication:** Bearer access token; allowed roles: patient.

Responses: `200` Profile; `401` Missing, invalid or expired token; `403` Not a patient; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/patients/me`

Update my profile (PUT = full, PATCH = partial).

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "blood_group": "O+",
  "emergency_contact_phone": "0712345678",
  "first_name": "Asha",
  "last_name": "Juma",
  "region": "Dar es Salaam"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/patients/me`

Update my profile (PUT = full, PATCH = partial).

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "blood_group": "O+",
  "emergency_contact_phone": "0712345678",
  "first_name": "Asha",
  "last_name": "Juma",
  "region": "Dar es Salaam"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/patients/me/medical-records`

List my medical records (filter: record_type, page, per_page).

**Authentication:** Bearer access token; allowed roles: patient.

Responses: `200` Paginated records; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/patients/me/medical-records`

Add a medical history entry.

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "description": "Rash and itching",
  "record_date": "2024-05-01",
  "record_type": "allergy",
  "title": "Penicillin"
}
```

Responses: `201` Created; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/patients/me/medical-records/{record_id}`

Get one of my records.

**Authentication:** Bearer access token; allowed roles: patient.

Responses: `200` Record; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/patients/me/medical-records/{record_id}`

Update a record I created.

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "description": "Updated description"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Record was entered by a doctor; `404` Not found; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/patients/me/medical-records/{record_id}`

Update a record I created.

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "description": "Updated description"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Record was entered by a doctor; `404` Not found; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### DELETE `/api/v1/patients/me/medical-records/{record_id}`

Delete a record I created.

**Authentication:** Bearer access token; allowed roles: patient.

Responses: `200` Deleted; `401` Missing, invalid or expired token; `403` Record was entered by a doctor; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/patients/{patient_id}`

View a patient's profile (verified doctor with an accepted/completed appointment, or admin).

**Authentication:** Bearer access token; allowed roles: doctor, admin.

Responses: `200` Patient profile; `401` Missing, invalid or expired token; `403` Not authorised; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/patients/{patient_id}/medical-records`

View a patient's medical records (authorised access only; access is audited).

**Authentication:** Bearer access token; allowed roles: doctor, admin.

Responses: `200` Paginated records; `401` Missing, invalid or expired token; `403` Not authorised; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Doctors

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/doctors` | any signed-in user |
| GET | `/api/v1/doctors/me` | doctor |
| PUT | `/api/v1/doctors/me` | doctor |
| PATCH | `/api/v1/doctors/me` | doctor |
| GET | `/api/v1/doctors/me/credentials` | doctor |
| POST | `/api/v1/doctors/me/credentials` | doctor |
| PUT | `/api/v1/doctors/me/credentials/{cred_id}` | doctor |
| PATCH | `/api/v1/doctors/me/credentials/{cred_id}` | doctor |
| DELETE | `/api/v1/doctors/me/credentials/{cred_id}` | doctor |
| GET | `/api/v1/doctors/me/dashboard` | doctor |
| PUT | `/api/v1/doctors/me/specialisations` | doctor |
| GET | `/api/v1/doctors/me/workplaces` | doctor |
| POST | `/api/v1/doctors/me/workplaces` | doctor |
| PUT | `/api/v1/doctors/me/workplaces/{workplace_id}` | doctor |
| PATCH | `/api/v1/doctors/me/workplaces/{workplace_id}` | doctor |
| DELETE | `/api/v1/doctors/me/workplaces/{workplace_id}` | doctor |
| GET | `/api/v1/doctors/{doctor_id}` | any signed-in user |

### GET `/api/v1/doctors`

Search verified doctors. Filters: q (name), specialisation_id, location, min_experience, page, per_page.

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` Paginated verified doctors; `401` Missing, invalid or expired token; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/doctors/me`

My doctor profile (includes verification status and credentials).

**Authentication:** Bearer access token; allowed roles: doctor.

Responses: `200` Profile; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/doctors/me`

Update my profile.

**Authentication:** Bearer access token; allowed roles: doctor.

Request body:

```json
{
  "bio": "Daktari wa watoto",
  "first_name": "Neema",
  "last_name": "Mushi",
  "practice_location": "Dar es Salaam",
  "years_of_experience": 9
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/doctors/me`

Update my profile.

**Authentication:** Bearer access token; allowed roles: doctor.

Request body:

```json
{
  "bio": "Daktari wa watoto",
  "first_name": "Neema",
  "last_name": "Mushi",
  "practice_location": "Dar es Salaam",
  "years_of_experience": 9
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/doctors/me/credentials`

List my credentials.

**Authentication:** Bearer access token; allowed roles: doctor.

Responses: `200` Credentials; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/doctors/me/credentials`

Submit a credential (licence, qualification, certificate). Adding a licence to a verified doctor re-opens review.

**Authentication:** Bearer access token; allowed roles: doctor.

Request body:

```json
{
  "credential_type": "qualification",
  "document_url": "https://example.com/cert.pdf",
  "institution": "MUHAS",
  "title": "MMed Paediatrics"
}
```

Responses: `201` Created; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/doctors/me/credentials/{cred_id}`

Update a credential. Editing a licence of a verified doctor re-opens review.

**Authentication:** Bearer access token; allowed roles: doctor.

Request body:

```json
{
  "title": "MMed Paediatrics (updated)"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/doctors/me/credentials/{cred_id}`

Update a credential. Editing a licence of a verified doctor re-opens review.

**Authentication:** Bearer access token; allowed roles: doctor.

Request body:

```json
{
  "title": "MMed Paediatrics (updated)"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### DELETE `/api/v1/doctors/me/credentials/{cred_id}`

Delete a credential.

**Authentication:** Bearer access token; allowed roles: doctor.

Responses: `200` Deleted; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/doctors/me/dashboard`

Doctor dashboard: experience, licence status, current workplace, inbox and workload.

**Authentication:** Bearer access token; allowed roles: doctor.

Responses: `200` Dashboard; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/doctors/me/specialisations`

Replace my specialisations.

**Authentication:** Bearer access token; allowed roles: doctor.

Request body:

```json
{
  "specialisation_ids": [
    "3f2a8c1e-5b7d-4c0a-9e21-8a6f0d4b7c15"
  ]
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Unknown specialisation; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/doctors/me/workplaces`

My work history (institutions, current workplace(s)).

**Authentication:** Bearer access token; allowed roles: doctor.

Responses: `200` Workplaces; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/doctors/me/workplaces`

Add an institution (set is_current=true for where you work now; you may have more than one).

**Authentication:** Bearer access token; allowed roles: doctor.

Request body:

```json
{
  "institution": "Muhimbili National Hospital",
  "is_current": true,
  "role": "Consultant",
  "start_year": 2018
}
```

Responses: `201` Added; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/doctors/me/workplaces/{workplace_id}`

Update a workplace.

**Authentication:** Bearer access token; allowed roles: doctor.

Request body:

```json
{
  "role": "Senior consultant"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/doctors/me/workplaces/{workplace_id}`

Update a workplace.

**Authentication:** Bearer access token; allowed roles: doctor.

Request body:

```json
{
  "role": "Senior consultant"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### DELETE `/api/v1/doctors/me/workplaces/{workplace_id}`

Remove a workplace.

**Authentication:** Bearer access token; allowed roles: doctor.

Responses: `200` Removed; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/doctors/{doctor_id}`

Doctor details. Non-verified doctors are only visible to themselves and admins.

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` Doctor; `401` Missing, invalid or expired token; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Availability

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/doctors/me/availability` | doctor |
| PUT | `/api/v1/doctors/me/availability` | doctor |
| GET | `/api/v1/doctors/{doctor_id}/availability` | any signed-in user |

### GET `/api/v1/doctors/me/availability`

My weekly working hours (weekday 0=Monday ... 6=Sunday, clinic local time).

**Authentication:** Bearer access token; allowed roles: doctor.

Responses: `200` Windows; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/doctors/me/availability`

Replace my weekly working hours. Existing appointments are not affected.

**Authentication:** Bearer access token; allowed roles: doctor.

Request body:

```json
{
  "windows": [
    {
      "end_time": "17:00",
      "start_time": "09:00",
      "weekday": 0
    }
  ]
}
```

Responses: `200` Saved; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Invalid or overlapping windows; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/doctors/{doctor_id}/availability`

Free appointment slots of a verified doctor. Query: from, to (YYYY-MM-DD, max 14 days; default next 7 days).

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` Free slots per day; `401` Missing, invalid or expired token; `404` Doctor not found; `422` Bad date range; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Specialisations

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/specialisations` | any signed-in user |
| POST | `/api/v1/specialisations` | admin |
| PUT | `/api/v1/specialisations/{spec_id}` | admin |
| PATCH | `/api/v1/specialisations/{spec_id}` | admin |
| DELETE | `/api/v1/specialisations/{spec_id}` | admin |

### GET `/api/v1/specialisations`

List specialisations.

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` List; `401` Missing, invalid or expired token; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/specialisations`

Create a specialisation (admin).

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "description": "Heart and blood vessels",
  "name": "Cardiology"
}
```

Responses: `201` Created; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `409` Already exists; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/specialisations/{spec_id}`

Update a specialisation (admin).

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "description": "Updated description"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Name taken; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/specialisations/{spec_id}`

Update a specialisation (admin).

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "description": "Updated description"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Name taken; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### DELETE `/api/v1/specialisations/{spec_id}`

Delete a specialisation that no doctor uses (admin).

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Deleted; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` In use; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Appointments

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/appointments` | any signed-in user |
| POST | `/api/v1/appointments` | patient |
| GET | `/api/v1/appointments/{appt_id}` | any signed-in user |
| POST | `/api/v1/appointments/{appt_id}/accept` | doctor |
| POST | `/api/v1/appointments/{appt_id}/cancel` | any signed-in user |
| POST | `/api/v1/appointments/{appt_id}/complete` | doctor |
| POST | `/api/v1/appointments/{appt_id}/reject` | doctor |
| PATCH | `/api/v1/appointments/{appt_id}/reschedule` | patient |

### GET `/api/v1/appointments`

List appointments visible to me. Query: status, from_date, to_date, order (asc|desc), page, per_page; admin also doctor_id, patient_id.

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` Paginated appointments; `401` Missing, invalid or expired token; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/appointments`

Book an appointment (status starts as 'pending' until the doctor accepts).

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "doctor_id": "3f2a8c1e-5b7d-4c0a-9e21-8a6f0d4b7c15",
  "reason": "Kipimo cha kawaida",
  "start_time": "2026-11-25T10:00:00+03:00"
}
```

Responses: `201` Booked; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Doctor not found or not verified; `409` Slot taken or you already have an overlapping appointment; `422` Outside working hours; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/appointments/{appt_id}`

Appointment details (participants and admins only).

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` Appointment; `401` Missing, invalid or expired token; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/appointments/{appt_id}/accept`

Accept a pending request (assigned verified doctor). Optional body: {note}.

**Authentication:** Bearer access token; allowed roles: doctor (verified doctor with an active licence).

Request body:

```json
{
  "note": "Karibu kliniki, fika dakika 10 mapema"
}
```

Responses: `200` Accepted; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Not pending / time passed; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/appointments/{appt_id}/cancel`

Cancel a pending/accepted appointment (patient, doctor or admin). Optional body: {note}.

**Authentication:** Bearer access token; any signed-in user.

Request body:

```json
{
  "note": "Nimepata dharura"
}
```

Responses: `200` Cancelled; `401` Missing, invalid or expired token; `404` Not found; `409` Not cancellable; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/appointments/{appt_id}/complete`

Mark an accepted appointment as completed once it has started.

**Authentication:** Bearer access token; allowed roles: doctor (verified doctor with an active licence).

Responses: `200` Completed; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Not accepted / not started; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/appointments/{appt_id}/reject`

Reject a pending request. Optional body: {note}.

**Authentication:** Bearer access token; allowed roles: doctor (verified doctor with an active licence).

Request body:

```json
{
  "note": "Sipatikani muda huo"
}
```

Responses: `200` Rejected; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Not pending; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/appointments/{appt_id}/reschedule`

Reschedule my appointment; it returns to 'pending' for the doctor to confirm.

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "start_time": "2026-11-25T10:30:00+03:00"
}
```

Responses: `200` Rescheduled; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Slot taken or appointment not reschedulable; `422` Invalid time; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Pharmacies

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/pharmacies` | patient, doctor, admin |
| GET | `/api/v1/pharmacies/me` | pharmacy |
| PUT | `/api/v1/pharmacies/me` | pharmacy |
| PATCH | `/api/v1/pharmacies/me` | pharmacy |
| GET | `/api/v1/pharmacies/{pharmacy_id}` | patient, doctor, admin |
| GET | `/api/v1/pharmacies/{pharmacy_id}/medicines` | patient, doctor, admin |

### GET `/api/v1/pharmacies`

Approved pharmacies. Optional: q (name), lat & lon (nearest first), page, per_page.

**Authentication:** Bearer access token; allowed roles: patient, doctor, admin.

Responses: `200` Paginated pharmacies; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/pharmacies/me`

My pharmacy profile and approval status.

**Authentication:** Bearer access token; allowed roles: pharmacy.

Responses: `200` Profile; `401` Missing, invalid or expired token; `403` Not a pharmacy; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/pharmacies/me`

Update name, address or GPS location (the licence number cannot be changed).

**Authentication:** Bearer access token; allowed roles: pharmacy.

Request body:

```json
{
  "address": "Kariakoo",
  "latitude": -6.8184,
  "longitude": 39.2766,
  "name": "Afya Pharmacy"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/pharmacies/me`

Update name, address or GPS location (the licence number cannot be changed).

**Authentication:** Bearer access token; allowed roles: pharmacy.

Request body:

```json
{
  "address": "Kariakoo",
  "latitude": -6.8184,
  "longitude": 39.2766,
  "name": "Afya Pharmacy"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/pharmacies/{pharmacy_id}`

One approved pharmacy (unapproved ones are not visible to customers).

**Authentication:** Bearer access token; allowed roles: patient, doctor, admin.

Responses: `200` Pharmacy; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found or not approved; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/pharmacies/{pharmacy_id}/medicines`

Catalogue of one approved pharmacy. Optional: q, lat & lon, page, per_page. Available medicines first.

**Authentication:** Bearer access token; allowed roles: patient, doctor, admin.

Responses: `200` Paginated medicines; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Pharmacy not found or not approved; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Medicines

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/medicines` | patient, doctor, admin |
| GET | `/api/v1/medicines/{medicine_id}` | patient, doctor, admin |

### GET `/api/v1/medicines`

only_available, pharmacy_id, page, per_page. Order: available first, then nearest, then cheapest.<br/>Out-of-stock medicines are listed with available=false.<br/>

**Authentication:** Bearer access token; allowed roles: patient, doctor, admin.

Responses: `200` Paginated results; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` q too short or invalid GPS; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/medicines/{medicine_id}`

One medicine (only if it is active and its pharmacy is approved). Optional lat & lon add distance_km.

**Authentication:** Bearer access token; allowed roles: patient, doctor, admin.

Responses: `200` Medicine; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found or not visible; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Pharmacy catalogue

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/pharmacies/me/medicines` | pharmacy |
| POST | `/api/v1/pharmacies/me/medicines` | pharmacy |
| GET | `/api/v1/pharmacies/me/medicines/{medicine_id}` | pharmacy |
| PUT | `/api/v1/pharmacies/me/medicines/{medicine_id}` | pharmacy |
| PATCH | `/api/v1/pharmacies/me/medicines/{medicine_id}` | pharmacy |
| DELETE | `/api/v1/pharmacies/me/medicines/{medicine_id}` | pharmacy |

### GET `/api/v1/pharmacies/me/medicines`

My catalogue, including removed items. Filters: q, is_active, available, page, per_page.

**Authentication:** Bearer access token; allowed roles: pharmacy.

Responses: `200` Paginated medicines with stock quantities; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/pharmacies/me/medicines`

Add a medicine (approved pharmacies only). Price is a whole number of shillings.

**Authentication:** Bearer access token; allowed roles: pharmacy (approved pharmacy).

Request body:

```json
{
  "generic_name": "Paracetamol",
  "name": "Paracetamol 500mg",
  "price_tzs": 1500,
  "requires_prescription": false,
  "stock_quantity": 100
}
```

Responses: `201` Created; `401` Missing, invalid or expired token; `403` Pharmacy not approved; `409` Duplicate name; `422` Validation failed (price must be a positive whole number); `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/pharmacies/me/medicines/{medicine_id}`

One of my medicines.

**Authentication:** Bearer access token; allowed roles: pharmacy.

Responses: `200` Medicine; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/pharmacies/me/medicines/{medicine_id}`

Customers see the change immediately; existing orders keep their price.<br/>

**Authentication:** Bearer access token; allowed roles: pharmacy (approved pharmacy).

Request body:

```json
{
  "price_tzs": 1800,
  "stock_quantity": 80
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Duplicate name; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/pharmacies/me/medicines/{medicine_id}`

Customers see the change immediately; existing orders keep their price.<br/>

**Authentication:** Bearer access token; allowed roles: pharmacy (approved pharmacy).

Request body:

```json
{
  "price_tzs": 1800,
  "stock_quantity": 80
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Duplicate name; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### DELETE `/api/v1/pharmacies/me/medicines/{medicine_id}`

Remove a medicine from sale (kept in the database; can be restored).

**Authentication:** Bearer access token; allowed roles: pharmacy (approved pharmacy).

Responses: `200` Removed; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Orders

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/orders` | patient, pharmacy, admin |
| POST | `/api/v1/orders` | patient |
| GET | `/api/v1/orders/{order_id}` | patient, pharmacy, admin |
| POST | `/api/v1/orders/{order_id}/cancel` | patient, pharmacy |
| POST | `/api/v1/orders/{order_id}/collect` | pharmacy |
| POST | `/api/v1/orders/{order_id}/ready` | pharmacy |

### GET `/api/v1/orders`

Filters: status, payment_status, page, per_page.<br/>

**Authentication:** Bearer access token; allowed roles: patient, pharmacy, admin.

Responses: `200` Paginated orders; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/orders`

Medicines that are out of stock cannot be ordered. Unpaid orders expire after 24 hours.<br/>

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "items": [
    {
      "medicine_id": "3f2a8c1e-5b7d-4c0a-9e21-8a6f0d4b7c15",
      "quantity": 2
    }
  ]
}
```

Responses: `201` Order created (status new; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Medicine not found or not visible; `409` Out of stock or quantity not available; `422` Invalid items; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/orders/{order_id}`

One order (its customer, its pharmacy, or an admin; everyone else gets 404).

**Authentication:** Bearer access token; allowed roles: patient, pharmacy, admin.

Responses: `200` Order; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/orders/{order_id}/cancel`

Cancel an unpaid order (customer or pharmacy). Optional body: {reason}.

**Authentication:** Bearer access token; allowed roles: patient, pharmacy.

Request body:

```json
{
  "reason": "Nimebadilisha mawazo"
}
```

Responses: `200` Cancelled; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Paid; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/orders/{order_id}/collect`

Pharmacy: the customer picked the order up.

**Authentication:** Bearer access token; allowed roles: pharmacy (approved pharmacy).

Responses: `200` Collected; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Order is not ready; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/orders/{order_id}/ready`

The customer is notified in the app and by SMS.<br/>

**Authentication:** Bearer access token; allowed roles: pharmacy (approved pharmacy).

Responses: `200` Ready; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Not paid; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Payments

| Method | Path | Who |
|---|---|---|
| POST | `/api/v1/orders/{order_id}/pay` | patient |
| POST | `/api/v1/orders/{order_id}/refund` | pharmacy |
| POST | `/api/v1/payments/callback` | public |

### POST `/api/v1/orders/{order_id}/pay`

The customer confirms on their phone; the result arrives through the protected callback.<br/>Not allowed before a required prescription is approved, twice for the same order, or for expired orders.<br/>

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "network": "mpesa",
  "phone": "0712345678"
}
```

Responses: `200` Payment started (payment_status = pending); `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Order not found; `409` Already paid/in progress; `422` Unsupported network or invalid phone; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support); `503` Payment service unavailable

### POST `/api/v1/orders/{order_id}/refund`

A full refund of an uncollected order cancels it and puts the medicines back in stock.<br/>

**Authentication:** Bearer access token; allowed roles: pharmacy (approved pharmacy).

Request body:

```json
{
  "amount_tzs": 1500,
  "reason": "Medicine was damaged"
}
```

Responses: `200` Refund recorded; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Order not found; `409` Order not paid; `422` Invalid amount; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/payments/callback`

Duplicate deliveries are acknowledged without changing anything.<br/>

**Authentication:** none (public endpoint).

Request body:

```json
{
  "amount_tzs": 3000,
  "provider_ref": "SIM-0a1b2c3d4e5f6071",
  "status": "success"
}
```

Responses: `200` Processed (or duplicate); `401` Bad signature; `404` Unknown payment; `409` Conflicting final state; `422` Amount mismatch; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Prescriptions

| Method | Path | Who |
|---|---|---|
| POST | `/api/v1/consultations/{consultation_id}/prescriptions` | doctor |
| GET | `/api/v1/orders/{order_id}/prescription` | pharmacy |
| POST | `/api/v1/orders/{order_id}/prescription` | patient |
| POST | `/api/v1/orders/{order_id}/prescription/approve` | pharmacy |
| POST | `/api/v1/orders/{order_id}/prescription/reject` | pharmacy |
| POST | `/api/v1/orders/{order_id}/prescription/use` | patient |
| GET | `/api/v1/prescriptions` | patient, doctor |
| GET | `/api/v1/prescriptions/{prescription_id}` | patient, doctor |
| POST | `/api/v1/prescriptions/{prescription_id}/cancel` | patient, doctor |
| GET | `/api/v1/prescriptions/{prescription_id}/pdf` | patient, doctor |

### POST `/api/v1/consultations/{consultation_id}/prescriptions`

Prescriptions can never be edited afterwards; they can only be cancelled.<br/>

**Authentication:** Bearer access token; allowed roles: doctor (verified doctor with an active licence).

Request body:

```json
{
  "items": [
    {
      "dosage": "1 capsule",
      "duration_days": 7,
      "frequency": "3 times a day",
      "instructions": "After meals",
      "medicine_name": "Amoxicillin 500mg"
    }
  ],
  "notes": "Pumzika na unywe maji mengi"
}
```

Responses: `201` Issued; `401` Missing, invalid or expired token; `403` Doctor not verified / licence expired; `404` Consultation not found; `409` Consultation closed; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/orders/{order_id}/prescription`

Pharmacy: read the prescription file of one of its orders (decrypted on the fly, access is audited).

**Authentication:** Bearer access token; allowed roles: pharmacy.

Responses: `200` The file; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` No order or no file; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/orders/{order_id}/prescription`

Allowed when the order needs a prescription and none is waiting or approved (first upload or after a rejection).<br/>

**Authentication:** Bearer access token; allowed roles: patient.

Request: `multipart/form-data` with the file in field `file` (PDF/JPG/PNG, max 5 MB).

Responses: `200` Uploaded; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Order not found; `409` Not needed; `413` File larger than 5 MB; `422` Not a PDF/JPG/PNG; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/orders/{order_id}/prescription/approve`

Pharmacy: approve the uploaded prescription (the customer can then pay).

**Authentication:** Bearer access token; allowed roles: pharmacy (approved pharmacy).

Responses: `200` Approved; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Nothing to review; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/orders/{order_id}/prescription/reject`

Pharmacy: reject the prescription with a reason; the customer may upload a new one.

**Authentication:** Bearer access token; allowed roles: pharmacy (approved pharmacy).

Request body:

```json
{
  "reason": "Picha haisomeki"
}
```

Responses: `200` Rejected; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Nothing to review; `422` Reason required; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/orders/{order_id}/prescription/use`

Every medicine that needs a prescription must appear on it; the order's prescription is then approved automatically.<br/>

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "prescription_id": "3f2a8c1e-5b7d-4c0a-9e21-8a6f0d4b7c15"
}
```

Responses: `200` Attached and approved; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Order or prescription not found; `409` Cancelled; `422` Prescription does not cover all required medicines; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/prescriptions`

My prescriptions (patients: received; doctors: issued). Filter: status (active|cancelled), page, per_page.

**Authentication:** Bearer access token; allowed roles: patient, doctor.

Responses: `200` Paginated prescriptions; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/prescriptions/{prescription_id}`

One prescription (its patient or its issuing doctor only).

**Authentication:** Bearer access token; allowed roles: patient, doctor.

Responses: `200` Prescription; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/prescriptions/{prescription_id}/cancel`

Issuing doctor cancels a prescription (with a reason).

**Authentication:** Bearer access token; allowed roles: patient, doctor.

Request body:

```json
{
  "reason": "Wrong dose written"
}
```

Responses: `200` Cancelled; `401` Missing, invalid or expired token; `403` Only the issuing doctor can cancel; `404` Not found; `409` Already cancelled; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/prescriptions/{prescription_id}/pdf`

Download the prescription as a PDF.

**Authentication:** Bearer access token; allowed roles: patient, doctor.

Responses: `200` PDF file; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Consultations

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/consultations` | patient, doctor |
| POST | `/api/v1/consultations` | patient |
| GET | `/api/v1/consultations/{consultation_id}` | patient, doctor |
| PUT | `/api/v1/consultations/{consultation_id}/clinical` | doctor |
| PATCH | `/api/v1/consultations/{consultation_id}/clinical` | doctor |
| POST | `/api/v1/consultations/{consultation_id}/close` | doctor |
| GET | `/api/v1/consultations/{consultation_id}/messages` | patient, doctor |
| POST | `/api/v1/consultations/{consultation_id}/messages` | patient, doctor |

### GET `/api/v1/consultations`

My consultations, most recent activity first. Filters: status, awaiting_reply=true, overdue=true (doctors), page, per_page.

**Authentication:** Bearer access token; allowed roles: patient, doctor.

Responses: `200` Paginated consultations; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/consultations`

Every consultation carries a notice that chat is not an emergency service (call 112).<br/>

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "doctor_id": "3f2a8c1e-5b7d-4c0a-9e21-8a6f0d4b7c15",
  "message": "Habari daktari, nina maumivu ya kichwa kwa siku tatu.",
  "subject": "Maumivu ya kichwa"
}
```

Responses: `201` Consultation created with the first message; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Doctor not found or not verified; `422` Empty or too long message; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/consultations/{consultation_id}`

One consultation (only its patient and doctor; private notes are visible to the doctor only).

**Authentication:** Bearer access token; allowed roles: patient, doctor.

Responses: `200` Consultation; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/consultations/{consultation_id}/clinical`

recommendations but never the private notes.<br/>

**Authentication:** Bearer access token; allowed roles: doctor (verified doctor with an active licence).

Request body:

```json
{
  "diagnosis": "Tension headache",
  "notes": "Private notes",
  "treatment_recommendations": "Rest and fluids"
}
```

Responses: `200` Saved; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/consultations/{consultation_id}/clinical`

recommendations but never the private notes.<br/>

**Authentication:** Bearer access token; allowed roles: doctor (verified doctor with an active licence).

Request body:

```json
{
  "diagnosis": "Tension headache",
  "notes": "Private notes",
  "treatment_recommendations": "Rest and fluids"
}
```

Responses: `200` Saved; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/consultations/{consultation_id}/close`

Doctor: close the consultation (no more messages).

**Authentication:** Bearer access token; allowed roles: doctor (verified doctor with an active licence).

Responses: `200` Closed; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Already closed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/consultations/{consultation_id}/messages`

Messages of a consultation (reading marks the other person's messages as read). Query: order=asc|desc, page, per_page.

**Authentication:** Bearer access token; allowed roles: patient, doctor.

Responses: `200` Paginated messages; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/consultations/{consultation_id}/messages`

Send a text message (max 2000 characters). Closed consultations and unverified doctors cannot receive messages.

**Authentication:** Bearer access token; allowed roles: patient, doctor.

Request body:

```json
{
  "body": "Asante daktari, nitafuata ushauri."
}
```

Responses: `201` Sent; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Closed; `422` Empty or too long; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Notifications

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/notifications` | any signed-in user |
| POST | `/api/v1/notifications/read-all` | any signed-in user |
| GET | `/api/v1/notifications/unread-count` | any signed-in user |
| POST | `/api/v1/notifications/{notification_id}/read` | any signed-in user |

### GET `/api/v1/notifications`

My notifications, newest first. Filter: unread=true. Pagination: page, per_page.

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` Paginated notifications; `401` Missing, invalid or expired token; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/notifications/read-all`

Mark all my notifications as read.

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` Updated; `401` Missing, invalid or expired token; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/notifications/unread-count`

Number of unread notifications.

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` Count; `401` Missing, invalid or expired token; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/notifications/{notification_id}/read`

Mark one notification as read.

**Authentication:** Bearer access token; any signed-in user.

Responses: `200` Updated; `401` Missing, invalid or expired token; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Content

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/first-aid` | public |
| GET | `/api/v1/first-aid/{item_id}` | public |
| GET | `/api/v1/health-education` | patient, doctor, admin |
| GET | `/api/v1/health-education/stages` | patient, doctor, admin |
| GET | `/api/v1/health-education/{item_id}` | patient, doctor, admin |

### GET `/api/v1/first-aid`

Search first-aid guides (approved content only). Public: no login needed. Query: q (min 2 chars), language (sw|en), page, per_page.

**Authentication:** none (public endpoint).

Responses: `200` Paginated approved content; `422` Invalid query; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/first-aid/{item_id}`

One approved piece of first-aid guides with its reviewer, date and edition. Public: no login needed.

**Authentication:** none (public endpoint).

Responses: `200` Content; `404` Not found or not approved; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/health-education`

Search reproductive and child health education (approved content only). Requires login. Query: q (min 2 chars), language (sw|en), stage (1-8), page, per_page.

**Authentication:** Bearer access token; allowed roles: patient, doctor, admin.

Responses: `200` Paginated approved content; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Invalid query; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/health-education/stages`

The eight stages of the reproductive-health journey used to group education content.

**Authentication:** Bearer access token; allowed roles: patient, doctor, admin.

Responses: `200` Stages; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/health-education/{item_id}`

One approved piece of reproductive and child health education with its reviewer, date and edition. Requires login.

**Authentication:** Bearer access token; allowed roles: patient, doctor, admin.

Responses: `200` Content; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found or not approved; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## HEDHI

| Method | Path | Who |
|---|---|---|
| DELETE | `/api/v1/hedhi` | patient |
| GET | `/api/v1/hedhi/cycles` | patient |
| POST | `/api/v1/hedhi/cycles` | patient |
| GET | `/api/v1/hedhi/cycles/{entry_id}` | patient |
| PUT | `/api/v1/hedhi/cycles/{entry_id}` | patient |
| PATCH | `/api/v1/hedhi/cycles/{entry_id}` | patient |
| DELETE | `/api/v1/hedhi/cycles/{entry_id}` | patient |
| GET | `/api/v1/hedhi/export` | patient |
| GET | `/api/v1/hedhi/insights` | patient |

### DELETE `/api/v1/hedhi`

Delete ALL my HEDHI data permanently.

**Authentication:** Bearer access token; allowed roles: patient.

Responses: `200` Deleted; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/hedhi/cycles`

My logged periods, newest first.

**Authentication:** Bearer access token; allowed roles: patient.

Responses: `200` Entries; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/hedhi/cycles`

Log a period. Stored encrypted; only you can read it.

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "end_date": "2026-11-06",
  "flow": "medium",
  "notes": "Maumivu kidogo",
  "start_date": "2026-11-02",
  "symptoms": [
    "cramps"
  ]
}
```

Responses: `201` Logged; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `409` Same start date or overlapping dates already logged; `422` Invalid dates; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support); `503` Encryption not configured

### GET `/api/v1/hedhi/cycles/{entry_id}`

One logged period.

**Authentication:** Bearer access token; allowed roles: patient.

Responses: `200` Entry; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/hedhi/cycles/{entry_id}`

Change a logged period.

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "end_date": "2026-11-06",
  "flow": "medium"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Overlaps another period; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/hedhi/cycles/{entry_id}`

Change a logged period.

**Authentication:** Bearer access token; allowed roles: patient.

Request body:

```json
{
  "end_date": "2026-11-06",
  "flow": "medium"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Overlaps another period; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### DELETE `/api/v1/hedhi/cycles/{entry_id}`

Delete one logged period.

**Authentication:** Bearer access token; allowed roles: patient.

Responses: `200` Deleted; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/hedhi/export`

Download all my HEDHI data.

**Authentication:** Bearer access token; allowed roles: patient.

Responses: `200` All entries; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/hedhi/insights`

you should see a doctor (with the doctor search path). Optional ?on=YYYY-MM-DD computes the estimates for another day.<br/>These are estimates only and not a contraceptive method.<br/>

**Authentication:** Bearer access token; allowed roles: patient.

Responses: `200` Insights; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Invalid date; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Admin

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/admin/audit-logs` | admin |
| GET | `/api/v1/admin/audit-logs/actions` | admin |
| GET | `/api/v1/admin/dashboard` | admin |
| GET | `/api/v1/admin/doctors` | admin |
| GET | `/api/v1/admin/doctors/{doctor_id}` | admin |
| POST | `/api/v1/admin/doctors/{doctor_id}/license-status` | admin |
| POST | `/api/v1/admin/doctors/{doctor_id}/reject` | admin |
| POST | `/api/v1/admin/doctors/{doctor_id}/verify` | admin |
| GET | `/api/v1/admin/payments` | admin |
| GET | `/api/v1/admin/pharmacies` | admin |
| GET | `/api/v1/admin/pharmacies/{pharmacy_id}` | admin |
| POST | `/api/v1/admin/pharmacies/{pharmacy_id}/approve` | admin |
| POST | `/api/v1/admin/pharmacies/{pharmacy_id}/reject` | admin |
| GET | `/api/v1/admin/refunds` | admin |
| GET | `/api/v1/admin/users` | admin |
| GET | `/api/v1/admin/users/{user_id}` | admin |
| POST | `/api/v1/admin/users/{user_id}/activate` | admin |
| POST | `/api/v1/admin/users/{user_id}/deactivate` | admin |

### GET `/api/v1/admin/audit-logs`

entity_type, entity_id, from_date, to_date, page, per_page.<br/>

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Paginated audit entries; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Invalid filter; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/audit-logs/actions`

Distinct action names present in the audit log (for building filters).

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Action names; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/dashboard`

Platform overview: users, approvals waiting, appointments, orders, payments, consultations, content and security signals.

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Dashboard counters; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/doctors`

List doctors for review. Filter: status (pending|verified|rejected), page, per_page.

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Paginated doctors; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/doctors/{doctor_id}`

Full doctor record with credentials.

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Doctor; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/doctors/{doctor_id}/license-status`

Set the licence status (active|expired). An expired licence hides the doctor and blocks chat and prescribing.

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "status": "expired"
}
```

Responses: `200` Updated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `422` Invalid status; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/doctors/{doctor_id}/reject`

Reject a doctor registration with a reason.

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "reason": "Licence number was not found on the council register"
}
```

Responses: `200` Rejected; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` The resource does not exist, or it is not yours; `422` Reason required; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/doctors/{doctor_id}/verify`

Verify a doctor. Optional body: {verified_name} = the name exactly as on the council register.

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "verified_name": "Neema A. Mushi"
}
```

Responses: `200` Verified; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` The resource does not exist, or it is not yours; `409` No licence credential; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/payments`

All payments. Filters: status (pending|paid|failed), from_date, to_date, order_id, page, per_page.

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Paginated payments; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/pharmacies`

List pharmacies for review. Filter: status (pending|approved|rejected), page, per_page.

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Paginated pharmacies; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/pharmacies/{pharmacy_id}`

Pharmacy details.

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Pharmacy; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/pharmacies/{pharmacy_id}/approve`

Approve a pharmacy so customers can see it.

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Approved; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/pharmacies/{pharmacy_id}/reject`

Reject a pharmacy registration with a reason.

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "reason": "Pharmacy licence has expired"
}
```

Responses: `200` Rejected; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` The resource does not exist, or it is not yours; `422` Reason required; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/refunds`

All recorded refunds. Pagination: page, per_page.

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Paginated refunds; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/users`

Search and filter accounts. Query: role (patient|doctor|pharmacy|admin), is_active, q (phone, email or name), page, per_page.

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Paginated users; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Invalid filter; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/users/{user_id}`

One account with role-specific details (no passwords, chats or HEDHI data are ever exposed).

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` User; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/users/{user_id}/activate`

Reactivate an account (tokens issued before the deactivation stay invalid).

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Activated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Already active; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/users/{user_id}/deactivate`

Deactivate an account (blocks login and every token). Body: {reason}. You cannot deactivate yourself or the last active admin.

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "reason": "Repeated abusive messages"
}
```

Responses: `200` Deactivated; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `409` Not allowed (self / last admin / already deactivated); `422` Reason required; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

## Admin content

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/admin/first-aid` | admin |
| POST | `/api/v1/admin/first-aid` | admin |
| GET | `/api/v1/admin/first-aid/{item_id}` | admin |
| PUT | `/api/v1/admin/first-aid/{item_id}` | admin |
| PATCH | `/api/v1/admin/first-aid/{item_id}` | admin |
| DELETE | `/api/v1/admin/first-aid/{item_id}` | admin |
| POST | `/api/v1/admin/first-aid/{item_id}/publish` | admin |
| POST | `/api/v1/admin/first-aid/{item_id}/unpublish` | admin |
| GET | `/api/v1/admin/health-education` | admin |
| POST | `/api/v1/admin/health-education` | admin |
| GET | `/api/v1/admin/health-education/{item_id}` | admin |
| PUT | `/api/v1/admin/health-education/{item_id}` | admin |
| PATCH | `/api/v1/admin/health-education/{item_id}` | admin |
| DELETE | `/api/v1/admin/health-education/{item_id}` | admin |
| POST | `/api/v1/admin/health-education/{item_id}/publish` | admin |
| POST | `/api/v1/admin/health-education/{item_id}/unpublish` | admin |

### GET `/api/v1/admin/first-aid`

List all (drafts and published). Filters: status, language, q, page, per_page. (first-aid guides)

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Paginated content; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/first-aid`

Create a draft. Nothing is public until a named reviewer approves it. (first-aid guides)

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "emergency_warning": "Piga 112 ikiwa damu haiachi baada ya dakika 10.",
  "keywords": "damu, jeraha",
  "language": "sw",
  "steps_to_avoid": [
    "Usiondoe kitu kilichobaki kwenye jeraha"
  ],
  "steps_to_do": [
    "Bonyeza jeraha kwa kitambaa safi"
  ],
  "summary": "Hatua za kwanza",
  "title": "Kuvuja damu"
}
```

Responses: `201` Draft created; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/first-aid/{item_id}`

One item with its working copy and the approved version. (first-aid guides)

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Content; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/admin/first-aid/{item_id}`

Edit the working copy. The currently approved text stays live until the new version is published. (first-aid guides)

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "title": "Kuvuja damu (imeboreshwa)"
}
```

Responses: `200` Saved; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/admin/first-aid/{item_id}`

Edit the working copy. The currently approved text stays live until the new version is published. (first-aid guides)

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "title": "Kuvuja damu (imeboreshwa)"
}
```

Responses: `200` Saved; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### DELETE `/api/v1/admin/first-aid/{item_id}`

Delete content that is not published. (first-aid guides)

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Deleted; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` The resource does not exist, or it is not yours; `409` Still published; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/first-aid/{item_id}/publish`

Publish after review. Body: {reviewed_by_name} = the single reviewer who approved this version. (first-aid guides)

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "reviewed_by_name": "Dr. Amina Salim"
}
```

Responses: `200` Published; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` The resource does not exist, or it is not yours; `422` Reviewer name required; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/first-aid/{item_id}/unpublish`

Take the content offline. (first-aid guides)

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Unpublished; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/health-education`

List all (drafts and published). Filters: status, language, q, page, per_page. (reproductive and child health education)

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Paginated content; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/health-education`

Create a draft. Nothing is public until a named reviewer approves it. (reproductive and child health education)

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "body": "Mzunguko wa kawaida ni siku 21 hadi 35.",
  "language": "sw",
  "stage": 2,
  "title": "Mzunguko wa hedhi"
}
```

Responses: `201` Draft created; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### GET `/api/v1/admin/health-education/{item_id}`

One item with its working copy and the approved version. (reproductive and child health education)

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Content; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PUT `/api/v1/admin/health-education/{item_id}`

Edit the working copy. The currently approved text stays live until the new version is published. (reproductive and child health education)

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "title": "Mzunguko wa hedhi (toleo jipya)"
}
```

Responses: `200` Saved; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### PATCH `/api/v1/admin/health-education/{item_id}`

Edit the working copy. The currently approved text stays live until the new version is published. (reproductive and child health education)

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "title": "Mzunguko wa hedhi (toleo jipya)"
}
```

Responses: `200` Saved; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `422` Validation failed; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### DELETE `/api/v1/admin/health-education/{item_id}`

Delete content that is not published. (reproductive and child health education)

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Deleted; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` The resource does not exist, or it is not yours; `409` Still published; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/health-education/{item_id}/publish`

Publish after review. Body: {reviewed_by_name} = the single reviewer who approved this version. (reproductive and child health education)

**Authentication:** Bearer access token; allowed roles: admin.

Request body:

```json
{
  "reviewed_by_name": "Dr. Amina Salim"
}
```

Responses: `200` Published; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` The resource does not exist, or it is not yours; `422` Reviewer name required; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)

### POST `/api/v1/admin/health-education/{item_id}/unpublish`

Take the content offline. (reproductive and child health education)

**Authentication:** Bearer access token; allowed roles: admin.

Responses: `200` Unpublished; `401` Missing, invalid or expired token; `403` Your role is not allowed to use this endpoint; `404` Not found; `429` Too many requests, slow down; `500` Unexpected server error (see request_id when contacting support)
