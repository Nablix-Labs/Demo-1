# Profile page — backend & DB requirements

**From:** Manav (frontend) · **Grouped by owner** at Manjusha's request.

The frontend for `/profile` is built and working. Everything below is what it
needs from the backend to stop being local-only.

**Current state:** every value reads from the client stores (`useAuthStore`,
`useNumeraStore`), persisted to `localStorage`. Nothing is invented — where the
backend has never supplied a value the card prints "Not set" rather than a
plausible-looking number. The page is honest today, but **nothing survives a
different device or a cleared browser.**

**How ownership below was decided:** the table in `CONTEXT.md`, cross-checked
against `git log` authorship per file. Where the evidence is thin it says so
rather than guessing — see ask #1.

---

## Summary — who does what

| # | Owner | Ask | Severity |
|---|---|---|---|
| 1 | **UNCONFIRMED — Manjusha to assign** | Return `student_code` on the login response | **Blocking** |
| 2 | **Chiru** — Tutor Backend | `GET /students/me/profile` | High |
| 3 | **Chiru** — Tutor Backend | `PATCH /students/me/profile` | High |
| 4 | **Chiru** — Tutor Backend | `POST` / `DELETE /students/me/avatar` | Medium |
| 5 | **UNASSIGNED — Manjusha to assign** | Persist consents server-side — nothing exists today | **High / compliance** |
| 6 | **Saravanan** — Student Model | `phases_done[]` + progress counters | Medium |
| 7 | **Sanya** — Tutor Backend | `GET /students/me/sessions` | Low / optional |
| 8 | **Manjusha** — Product | Four decisions before anyone builds | Decision |

**Aditya: nothing here.** Voice and RAG are untouched by this page — flagged so
you do not need to read further.

---

# 1. UNCONFIRMED OWNER — `student_code` on the login response

**Highest-value item on the list, and I could not establish who owns it.
Manjusha, please assign.**

`/auth/login` is served by the **Nablix platform auth server**
(`nablix.ai:8080`), which is *not* in the `Demo-1` monorepo — so git authorship
proves nothing here, and `CONTEXT.md`'s ownership table has no auth row. The
only auth file in this repo is `app/api/auth.py`, a 23-line bearer-token
dependency that does not issue tokens.

### The problem

Verified 2026-07-28 by reading the auth service source on the VM:

- `create_access_token()` builds the JWT as `{sub, role, tier, iat, exp}` —
  `sub` is `str(user.user_id)`, an **integer user id, not the `ST###` code**.
- `TokenResponse` is `{access_token, token_type, role, tier, last_journey_state}`
  — no `student_code`.
- `last_journey_state` looks like a way in (the raw journey dict holds
  `"student_id": student_code`) but `_project()` in `login_state.py` **drops
  that key**, and it is `None` for any student with no prior journey.

So the frontend cannot derive it client-side. `lib/api.ts` falls back to a fixed
`ST001`, and `/session/event` rejects every other student with
`403 STUDENT_FORBIDDEN` on their first correct answer (GitHub issue #40).

### Smallest fix

`login()` already selects `Student.student_id` for the `last_journey_state`
lookup — have it select `student_code` too and add the field to `TokenResponse`.
One field.

**Do this first: it unblocks the profile page and the tutoring calls together.**

---

# 2–4. Chiru — Tutor Backend

*Basis: 17 commits on `*student*` files, the most of anyone.*

## 2. `GET /students/me/profile`

One call that populates the whole page. Everything optional except
`student_id` — the UI already renders "Not set" for anything absent, so a
partial response is safe to ship first.

```jsonc
{
  "student_id": "…",
  "student_code": "ST008",                    // see ask #1
  "email": "student@example.com",
  "tier": "tier_3",
  "account_status": "active",                 // enum below
  "display_name": "Manav Arya Singh",
  "avatar_url": "https://…/avatars/…jpg",     // null if none
  "age_band": "11-14 (KS3)",
  "grade_band": "Year 9",
  "preferred_mode": "balanced",               // voice | text | balanced
  "guardian": {
    "name": "…", "relationship": "Parent",
    "email": "…", "phone": "…", "verified": true
  },
  "preferences": { "input_mode": "voice", "panel_side": "left" },
  "consents": [                               // see ask #5
    { "purpose": "account_creation", "accepted_at": "2026-07-01T…", "withdrawn_at": null }
    // one row per purpose, all 7
  ],
  "progress": {                               // see ask #6
    "topic_id": "…",
    "phases_done": ["diagnostic", "orientation"],
    "sessions_total": 5,
    "minutes_total": 124,
    "questions_correct": 28,
    "questions_total": 35
  }
}
```

## 3. `PATCH /students/me/profile`

Partial update. The page writes `display_name`, `age_band`, `grade_band`,
`preferred_mode`, `preferences.input_mode`, `preferences.panel_side`, and the
guardian block. Should return the updated object.

## 4. `POST /students/me/avatar` — multipart, and `DELETE` to clear

Returns `{ "avatar_url": "…" }`.

The client already centre-crops to a square and downscales to **256×256 JPEG
q0.85** (~2–20KB), so the server does not need to resize. It **does** still need
to:

- enforce a content-type allow-list (`jpeg` / `png` / `webp`) and a hard size cap;
- **re-encode to strip EXIF** — a phone photo carries GPS coordinates, and these
  are children;
- delete the stored object on account deletion, not just the row.

### What the page shows, and where each value comes from now

| Section | Field | Source today | Needs backend? |
|---|---|---|---|
| Identity | Name | `student.name` (onboarding, local) | **Yes** |
| Identity | Photo | `student.avatar`, data URL in `localStorage` | **Yes** |
| Identity | Year / age band | `student.gradeBand` / `.ageBand` (local) | **Yes** |
| Identity | Account status | `accountStatus` — drives the access gate | **Yes** |
| Identity | Plan / tier | `tier` from `POST /auth/login` | Already real |
| Identity | Student code | `studentCode` from login | Ask #1 |
| Learning flow | 6 phase pills + green checklist | `phasesDone` (local) | Ask #6 |
| Topic progress | % unlocked | derived from `phasesDone` | Ask #6 |
| Header | Profile set-up % | counted from filled fields, client-side | No |
| How you learn | Tutor input mode | `inputMode` (local, drives the lesson) | **Yes** (sync) |
| How you learn | Panel side | `panelSide` (local) | **Yes** (sync) |
| Account | Email | `email` from login | Already real |
| Guardian | Name / relationship / email / phone / verified | local, from onboarding | **Yes** |
| Privacy | 7 consent toggles | `consents` (local only) | Ask #5 |

---

# 5. UNASSIGNED — consents are not persisted anywhere

**Verified: the string "consent" does not appear anywhere in
`nablix-backend/app/`.** No table, no endpoint, no model.

All seven toggles live in `useAuthStore` and persist only to the student's
`localStorage`. So consent for a minor currently survives nowhere and is
auditable nowhere — the withdrawal audit trail the proposal's §7 describes does
not exist server-side, and clearing a browser silently resets it.

This is a compliance gap rather than a profile-page gap, and it has no owner in
`CONTEXT.md`'s table. **Manjusha to assign.**

## `PUT /students/me/consents/{purpose}`

```jsonc
{ "granted": true }   // or false to withdraw
```

Must return the resulting `account_status` — withdrawing an account-blocking
consent restricts the account and the UI has to reflect that immediately.

## Semantics the backend must match

These rules are implemented client-side in `store/useAuthStore.ts` and come from
§7/§10 of the proposal. The backend should be the authority; the frontend
mirrors it.

Seven purposes: `account_creation`, `ai_tutor_usage`, `canvas_processing`,
`voice_processing`, `learning_analytics`, `safety_monitoring`, `marketing`.
All mandatory except `marketing`.

- **Account-blocking** — `account_creation`, `ai_tutor_usage`,
  `learning_analytics`, `safety_monitoring`. Withdrawing any one sets
  `account_status = consent_withdrawn` and restricts the whole account.
  Re-granting all four restores `active`.
- **Feature-level** — `canvas_processing`, `voice_processing`. Withdrawing
  disables that feature only; the account stays `active`. (This is why the
  lesson screen shows "Canvas processing is not available until the required
  consent is completed.")

A record is *active* when `accepted_at` is set **and** `withdrawn_at` is null.
Keep withdrawn rows rather than deleting them — the audit trail is the point.

---

# 6. Saravanan — Student Model

*Basis: `CONTEXT.md` — Schema 3.0 and learner journey events. No commits in
`Demo-1`; the Student Model is a separate service.*

- `phases_done[]` on the learner journey — drives the six phase pills and the
  green checklist card.
- Progress counters: `sessions_total`, `minutes_total`, `questions_correct`,
  `questions_total`.
- Confirm the `students` join needed for ask #1.

The counters are **not on the page yet** — there is no honest source for them,
and `/history` currently hardcodes the same figures as mock data. Send them and
I will add the big-numeral stat row from the reference design.

---

# 7. Sanya — sessions endpoint (optional)

*Basis: 24 commits on `*session*`; already owns session resume per `CONTEXT.md`.*

## `GET /students/me/sessions`

Totals plus recent topics. Only needed for a richer page — a real streak and a
recent-topic list instead of the phase pills alone. Nothing is blocked on it.

---

# 8. Manjusha — decisions needed before anyone builds

| Decision | Why it is yours |
|---|---|
| Are student photos allowed at all? | These are KS3–KS4 minors. A product/legal call that comes before storage design. |
| Avatar retention + deletion policy | Account deletion must delete the stored object, not just the row. |
| Consent wording, and whether `marketing` stays off by default | Currently off by default and client-side only. |
| **Assign owners for asks #1 and #5** | Neither the platform auth server nor consent persistence has an owner in `CONTEXT.md`. |

---

# Reference

## Enums

`account_status`: `registration_started` · `consent_pending` · `active` ·
`consent_withdrawn` · `suspended` · `locked` · `deleted`

`preferred_mode`: `voice` · `text` · `balanced` (`input_mode` is only
`voice` | `text`)

`panel_side`: `left` · `right`

`phases_done[]`: `diagnostic` · `orientation` · `teach` · `workbook` ·
`practice` · `review` (order from `lib/phases.ts`)

## Suggested DB shape

```sql
-- extend the existing student/profile table
ALTER TABLE students
  ADD COLUMN display_name    text,
  ADD COLUMN avatar_url      text,
  ADD COLUMN age_band        text,
  ADD COLUMN grade_band      text,
  ADD COLUMN preferred_mode  text CHECK (preferred_mode IN ('voice','text','balanced'));

CREATE TABLE student_preferences (
  student_id  uuid PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
  input_mode  text CHECK (input_mode IN ('voice','text')),
  panel_side  text CHECK (panel_side IN ('left','right')),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE guardians (
  student_id   uuid PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
  name         text,
  relationship text,
  email        text,
  phone        text,
  verified     boolean NOT NULL DEFAULT false
);

-- Ask #5: no consent storage exists yet. Minimum shape:
CREATE TABLE consent_records (
  student_id   uuid NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  purpose      text NOT NULL,
  accepted_at  timestamptz,
  withdrawn_at timestamptz,
  PRIMARY KEY (student_id, purpose)
);
```

## What is already done, so nobody rebuilds it

- The page renders fully against local state. No layout changes are needed when
  the API lands — every component already handles a missing value.
- Avatar downscaling is done client-side (see ask #4).
- Consent semantics (account-blocking vs feature-level) are implemented and
  working client-side — verified: an account missing two account-blocking
  consents is correctly bounced to `/restricted`.
