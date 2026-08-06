# Profile page — backend & DB requirements

Frontend for `/profile` is built and working. This is what it needs from the
backend to stop being local-only.

**Current state:** every value on the page reads from the client stores
(`useAuthStore`, `useNumeraStore`), which persist to `localStorage`. Nothing is
invented — where the backend has never supplied a value the card prints "Not
set" rather than a plausible-looking number. That means the page is honest
today, but **nothing survives a different device or a cleared browser.**

---

## 1. What the page shows, and where it comes from now

| Section | Field | Source today | Needs backend? |
|---|---|---|---|
| Identity | Name | `student.name` (onboarding, local) | **Yes** |
| Identity | Photo | `student.avatar`, data URL in `localStorage` | **Yes** |
| Identity | Year / age band | `student.gradeBand` / `.ageBand` (local) | **Yes** |
| Identity | Account status | `accountStatus` (local state machine) — drives the access gate, no longer shown as a chip | **Yes** |
| Identity | Plan / tier | `tier` from `POST /auth/login` | Already real |
| Identity | Student code | `studentCode` from login | Partially — see §5 |
| Learning flow | 6 phase pills + green checklist card | `phasesDone` (local, written by the manual flow) | **Yes** |
| Header | Profile set-up % | counted from filled fields, client-side | No |
| Topic progress | % unlocked | derived from `phasesDone` | **Yes** |
| How you learn | Tutor input mode | `inputMode` (local, drives the lesson) | **Yes** (sync) |
| How you learn | Panel side | `panelSide` (local) | **Yes** (sync) |
| Account | Email | `email` from login | Already real |
| Guardian | Name / relationship / email / phone / verified | local, from onboarding | **Yes** |
| Privacy | 7 consent toggles | `consents` (local) | **Yes** — legally required |

---

## 2. Endpoints needed

### `GET /students/me/profile`

One call that populates the whole page. Everything optional except `student_id`
— the UI already renders "Not set" for anything absent, so a partial response is
safe to ship first.

```jsonc
{
  "student_id": "…",
  "student_code": "ST008",          // see §5
  "email": "student@example.com",
  "tier": "tier_3",
  "account_status": "active",        // enum in §4
  "display_name": "Manav Arya Singh",
  "avatar_url": "https://…/avatars/…jpg",   // null if none
  "age_band": "11-14 (KS3)",
  "grade_band": "Year 9",
  "preferred_mode": "balanced",      // voice | text | balanced
  "guardian": {
    "name": "…", "relationship": "Parent",
    "email": "…", "phone": "…", "verified": true
  },
  "preferences": { "input_mode": "voice", "panel_side": "left" },
  "consents": [
    { "purpose": "account_creation", "accepted_at": "2026-07-01T…", "withdrawn_at": null }
    // one row per purpose, all 7
  ],
  "progress": {
    "topic_id": "…",
    "phases_done": ["diagnostic", "orientation"],
    "sessions_total": 5,
    "minutes_total": 124,
    "questions_correct": 28,
    "questions_total": 35
  }
}
```

The last three `progress` counters are **not on the page yet** — the frontend
has no honest source for them. Send them and I will add the stat row from the
reference design (the big `28 / 2h4m / 86%` numerals). The `/history` page
currently hardcodes the same figures as mock data.

### `PATCH /students/me/profile`

Partial update. The page writes: `display_name`, `age_band`, `grade_band`,
`preferred_mode`, `preferences.input_mode`, `preferences.panel_side`, and the
guardian block. Should return the updated object.

### `POST /students/me/avatar` — multipart

The client already centre-crops to a square and downscales to **256×256 JPEG
q0.85** (~2–20KB) before sending, so the server does not need to resize. Still
validate server-side: content-type allow-list (`jpeg/png/webp`), hard size cap,
re-encode to strip EXIF (a phone photo carries GPS coordinates, and this is a
children's product).

Returns `{ "avatar_url": "…" }`. `DELETE /students/me/avatar` to clear.

> **Note:** avatars are personal data about a minor. They need the same
> retention and deletion path as everything else — deleting the account must
> delete the object, not just the row.

### `PUT /students/me/consents/{purpose}`

```jsonc
{ "granted": true }   // or false to withdraw
```

Must return the resulting `account_status`, because withdrawing an
account-blocking consent restricts the account and the UI has to reflect that
immediately. The frontend already models this — see §3.

### `GET /students/me/sessions` (optional, for a richer page)

Would let the profile show a real streak and recent-topic list instead of the
phase bars alone.

---

## 3. Consent semantics the backend must match

These rules are already implemented client-side in `store/useAuthStore.ts` and
come from §7/§10 of the proposal. The backend is the authority; the frontend
mirrors it.

Seven purposes: `account_creation`, `ai_tutor_usage`, `canvas_processing`,
`voice_processing`, `learning_analytics`, `safety_monitoring`, `marketing`.
All mandatory except `marketing`.

Two tiers of consequence:

- **Account-blocking** — `account_creation`, `ai_tutor_usage`,
  `learning_analytics`, `safety_monitoring`. Withdrawing any one of these sets
  `account_status = consent_withdrawn` and restricts the whole account.
  Re-granting all four restores `active`.
- **Feature-level** — `canvas_processing`, `voice_processing`. Withdrawing
  disables that feature only; the account stays `active`. (This is why the
  lesson screen currently shows "Canvas processing is not available until the
  required consent is completed.")

A consent record is *active* when `accepted_at` is set **and** `withdrawn_at`
is null. Keep withdrawn rows rather than deleting them — the audit trail is the
point.

---

## 4. Enums

`account_status`: `registration_started` · `consent_pending` · `active` ·
`consent_withdrawn` · `suspended` · `locked` · `deleted`

`preferred_mode` / `input_mode`: `voice` · `text` · `balanced`
(`input_mode` is only `voice` | `text`)

`panel_side`: `left` · `right`

`phases_done[]`: `diagnostic` · `orientation` · `teach` · `workbook` ·
`practice` · `review` (order from `lib/phases.ts`)

---

## 5. Blocker carried over from auth

`POST /auth/login` does not return the student's own `ST###` code
(`LoginResponse.student_code` is absent), so every signed-in student falls back
to `ST001` and `student_model` answers `403 STUDENT_FORBIDDEN`. There is a
testing override (`?student=ST008`) in `AppFrame.tsx` as a stopgap.

The profile page prints "Not issued by the backend yet" for the student code
rather than showing a wrong one. **Fixing login to return `student_code` unblocks
this field and the tutoring calls at the same time** — it is the single highest-value
item on this list.

---

## 6. Suggested DB shape

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

-- consent_records already exists per §7; the page needs these columns
-- (student_id, purpose, accepted_at, withdrawn_at) exposed on the profile read.
```

---

## 7. What I need from you to finish the page

1. `student_code` on the login response (§5) — unblocks the most fields.
2. `GET /students/me/profile` in roughly the shape above, even partially filled.
3. Whether avatars go to your object storage or Supabase storage, and the
   upload endpoint's exact contract.
4. The three `progress` counters, if you want the big-numeral stat row added.

Send those and the page switches from local state to live data without any
layout changes — the components already handle missing values.
