# Onboarding API: registration and guardian consent

**From:** Manav (frontend). **For:** Saravanan (backend). **Date:** 29 Sep 2026

The sign-up pages (`/onboard`) and guardian consent pages (`/consent`) are built
and working in the app. They call the endpoints below, which do not exist yet.
Until they do, the pages run on a local mock. When the endpoints are ready, one
setting (`NEXT_PUBLIC_REGISTRATION_LIVE=true`) sends every step to the server,
with no page changes.

Frontend code: `lib/auth/registrationApi.ts` (every request and response type
below is defined there).

## The flow

| Step | Screen | Endpoint |
|---|---|---|
| 1 | Student picks how to sign up (email code, phone code, password, SSO) | `POST /auth/register/start` |
| 2 | Student enters the 6-digit code (skipped when no code was sent) | `POST /auth/register/verify` (and `/resend`) |
| 3 | Student profile: name, age band, year group, tutoring mode | `POST /auth/register/profile` |
| 4 | Guardian details | `POST /consent/guardian` |
| 5 | Guardian enters their 6-digit code | `POST /consent/guardian/verify` (and `/resend`) |
| 6 | Guardian accepts the consents and the safety disclosure | `POST /consent/accept` |

After step 6 the account is `active` and the student is signed in with the
token from that response. They go straight to the diagnostic.

## Conventions

- **Server:** the same auth server as `POST /auth/login` (`nablix.ai:8080`). The
  browser reaches it through the existing `/nablix-auth` proxy, so all paths
  below are relative to it.
- **Format:** JSON request and response bodies, `Content-Type: application/json`.
- **No login token is needed** for steps 1–6: the student has no account yet.
  Each step is tied together by the ids the server returns
  (`registration_id`, then `guardian_id`).
- **Errors:** same body as `/auth/login` today, on any non-2xx:

```json
{ "error_code": "OTP_INVALID", "message": "developer-facing text", "field": "code" }
```

The frontend shows its own wording for each `error_code` (list at the end) and
never shows `message` to the student. `field` is the input that was wrong, or
`null`.

---

## 1. `POST /auth/register/start`

Starts a sign-up and, for the code methods, sends the code.

**Request**, one of:

```json
{ "method": "email_otp", "email": "sam@example.com" }
{ "method": "phone_otp", "phone": "+44 7700 900000" }
{ "method": "password",  "email": "sam@example.com", "password": "at-least-6" }
{ "method": "sso",       "sso_provider": "google" }
```

`sso_provider`: `google` | `microsoft` | `apple` | `school`

**Response 200**

```json
{
  "registration_id": "REG-7f3a…",
  "otp_required": true,
  "otp_sent_to": "s•••@example.com",
  "expires_in_s": 600,
  "redirect_url": null
}
```

| Field | Meaning |
|---|---|
| `registration_id` | Ties every later step together. |
| `otp_required` | `true` → the frontend shows the code screen. `false` → it skips to the profile (e.g. password sign-up, if you do not verify the email first). |
| `otp_sent_to` | Masked email or phone, shown as "We sent a 6-digit code to …". `null` if none. |
| `expires_in_s` | How long the code is valid. `null` if none. |
| `redirect_url` | SSO only. The frontend sends the browser here. After the provider signs the student in, redirect back to `/app/onboard/?registration_id=<id>`: the frontend reads the id and goes straight to the profile step. |

**Errors:** `409 ACCOUNT_EXISTS` (field `email` or `phone`), `422 VALIDATION_ERROR`, `429 RATE_LIMITED`

## 2. `POST /auth/register/verify`

**Request**

```json
{ "registration_id": "REG-7f3a…", "code": "123456" }
```

**Response 200**

```json
{ "verified": true }
```

**Errors:** `400 OTP_INVALID`, `410 OTP_EXPIRED`, `410 REGISTRATION_EXPIRED`, `429 RATE_LIMITED`

### `POST /auth/register/resend`

**Request** `{ "registration_id": "REG-7f3a…" }`

**Response 200** `{ "otp_sent_to": "s•••@example.com", "expires_in_s": 600 }`

## 3. `POST /auth/register/profile`

Creates the student record. The account is `consent_pending` until step 6.

**Request**

```json
{
  "registration_id": "REG-7f3a…",
  "display_name": "Sam",
  "age_band": "11–14 (KS3)",
  "grade_band": "Year 8",
  "preferred_mode": "balanced"
}
```

**Response 200**

```json
{
  "student_id": "…",
  "student_code": "ST101",
  "account_status": "consent_pending"
}
```

`student_code` is the `ST###` code the tutoring API uses. Send it if you already
have it; `null` is fine here as long as step 6 returns it.

**Errors:** `403` if the code in step 2 was required and not verified, `410 REGISTRATION_EXPIRED`, `422 VALIDATION_ERROR`

## 4. `POST /consent/guardian`

Saves the guardian and sends them a 6-digit code. The code proves who they are.
It is **not** consent.

**Request**

```json
{
  "registration_id": "REG-7f3a…",
  "name": "Pat Parent",
  "relationship": "Parent",
  "email": "pat@example.com",
  "phone": null
}
```

`relationship`: `Parent` | `Guardian` | `Carer`. `phone` is optional and sent as `null` when blank.

**Response 200**

```json
{ "guardian_id": "GRD-19c2…", "otp_sent_to": "p•••@example.com", "expires_in_s": 600 }
```

**Errors:** `410 REGISTRATION_EXPIRED`, `422 VALIDATION_ERROR`, `429 RATE_LIMITED`

## 5. `POST /consent/guardian/verify`

**Request**

```json
{ "guardian_id": "GRD-19c2…", "code": "123456" }
```

**Response 200**

```json
{ "guardian_verified": true }
```

**Errors:** `400 OTP_INVALID`, `410 OTP_EXPIRED`, `429 RATE_LIMITED`

### `POST /consent/guardian/resend`

**Request** `{ "guardian_id": "GRD-19c2…" }`

**Response 200** `{ "otp_sent_to": "p•••@example.com", "expires_in_s": 600 }`

## 6. `POST /consent/accept`

Records each consent, records the disclosure acknowledgement, activates the
account, and signs the student in.

**Request**

```json
{
  "registration_id": "REG-7f3a…",
  "guardian_id": "GRD-19c2…",
  "accepted_purposes": [
    "account_creation", "ai_tutor_usage", "canvas_processing",
    "voice_processing", "learning_analytics", "safety_monitoring"
  ],
  "disclosure_version": "v1.0"
}
```

`marketing` appears in the list only if the guardian ticked it.

**Response 200**: the same shape as the `/auth/login` response, plus `account_status`:

```json
{
  "access_token": "eyJ…",
  "token_type": "bearer",
  "role": "student",
  "tier": "tier_1",
  "student_code": "ST101",
  "last_journey_state": null,
  "account_status": "active"
}
```

The frontend uses this exactly like a login, so the student does not have to
log in again.

**Errors:** `403 GUARDIAN_NOT_VERIFIED`, `422 MANDATORY_CONSENT_MISSING`, `410 REGISTRATION_EXPIRED`

---

## Values

**Consent purposes (7).** All required except `marketing`:

| purpose | Required | If withdrawn later |
|---|---|---|
| `account_creation` | yes | account restricted |
| `ai_tutor_usage` | yes | account restricted |
| `learning_analytics` | yes | account restricted |
| `safety_monitoring` | yes | account restricted |
| `canvas_processing` | yes | canvas turned off only |
| `voice_processing` | yes | voice turned off only |
| `marketing` | no, off by default | nothing |

Store one row per purpose with `accepted_at` and `withdrawn_at`. A consent is
active when `accepted_at` is set and `withdrawn_at` is null. Keep withdrawn rows:
they are the audit trail.

**`account_status`:** `registration_started` · `consent_pending` · `active` ·
`consent_withdrawn` · `suspended` · `locked` · `deleted`

**`age_band`** (exact strings; the dash is an en dash): `11–14 (KS3)` · `14–16 (KS4)`

**`grade_band`:** `Year 7` · `Year 8` · `Year 9` · `Year 10` · `Year 11`

**`preferred_mode`:** `voice` · `balanced` · `text`

**`disclosure_version`:** `v1.0`

## Error codes the frontend understands

| error_code | Student sees |
|---|---|
| `ACCOUNT_EXISTS` | An account already exists for this email or phone. Try logging in instead. |
| `OTP_INVALID` | That code isn't right. Check it and try again. |
| `OTP_EXPIRED` | That code has expired. Ask for a new one. |
| `RATE_LIMITED` | Too many attempts. Please wait a minute and try again. |
| `REGISTRATION_EXPIRED` | This sign-up has timed out. Please start again. |
| `GUARDIAN_NOT_VERIFIED` | The guardian needs to verify their code first. |
| `MANDATORY_CONSENT_MISSING` | All required consents must be accepted to continue. |
| `VALIDATION_ERROR` | Please check the *field* and try again. |

Any other failure shows a general "try again" message. A 404 or 5xx page from a
proxy shows "Can't reach the sign-up service".

## Suggestions for the backend

- Codes: 6 digits, valid about 10 minutes, a few attempts before
  `RATE_LIMITED`. Store only a hash of the code.
- Expire an unfinished `registration_id` after a day or so
  (`REGISTRATION_EXPIRED`).
- Nothing about the student's profile is final until step 6. Access stays
  blocked while the account is `consent_pending`.

## Not in this round

Changing consent after sign-up (the `/consent/manage` page) and the profile
page's read/update endpoints are specified separately in `PROFILE-BACKEND.md`.
They can follow once this flow is live.
