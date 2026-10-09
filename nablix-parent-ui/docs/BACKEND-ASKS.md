# Parent Portal: what the backend needs

The portal is built and runs on sample data (`NEXT_PUBLIC_PARENT_API_MODE=sample`).
Nothing below exists yet. When it does, the frontend switches to `http` and rebuilds.
No other frontend change is needed: the field names below are what `lib/types.ts` reads.

Live at: `https://nablix.ai/app/parent/` (sample data until this list is done).

## 1. Parent accounts: Saravanan (auth service, :8080)

| # | What | Detail |
|---|---|---|
| 1 | `parent_guardian` role | `POST /auth/login` returns `role: "parent_guardian"` for a guardian. The JWT carries the same role. |
| 2 | Guardian account | Create the account when guardian consent is verified (`/consent/guardian/verify`). Email a set-password link: `POST /auth/guardian/set-password {token, password}`. |
| 3 | Guardian ↔ student link | Table `guardian_id, student_id, relationship, verified_at`. One guardian can have several children. |
| 4 | Consent records per student | Internal endpoint, called with the service token: read and update the 7 purposes (`account_creation`, `ai_tutor_usage`, `canvas_processing`, `voice_processing`, `learning_analytics`, `safety_monitoring`, `marketing`) with `accepted_at` and `withdrawn_at`. Withdrawing a required one sets the account to `consent_withdrawn`. |
| 5 | Topic progress per student | Internal endpoint: for each topic, `topic_id, title, strand, mastery_status, current_phase, phases_completed[], started_at, last_activity_at, recommended_next_action`, plus `micro_skills[] {id, label, description, status}` where status is `INDEPENDENTLY_VERIFIED / VERIFIED_WITH_SUPPORT / RESCUE_REQUIRED / UNKNOWN`. |
| 6 | Misconception catalogue | `id, label, description, topic_id`, written for parents (for example "Reads 3x as 3 + x"). |

## 2. Parent API gateway: Chiru, Sanya (nablix-backend, served under `/api`)

One base URL for the frontend (`/api/parent/*`), so there is no CORS and no second proxy.

| # | Endpoint | Returns |
|---|---|---|
| 7 | Verify the JWT and check `role == parent_guardian` | nablix-backend checks only that a token is present today. Every `/parent/*` route must also check the guardian is linked to the child (item 3), else 404. |
| 8 | `GET /parent/children` | `[{student_code, name, year_group}]` |
| 9 | `GET /parent/children/{code}/topics` | Item 5, passed through |
| 10 | `GET /parent/children/{code}/sessions?days=90` | `[{session_id, topic_id, session_date, session_duration_seconds, phases_completed[], tutor_interventions, attempts[]}]` |
| 11 | `GET /parent/children/{code}/misconceptions` | Item 6, passed through |
| 12 | `GET /parent/children/{code}/consents` and `POST {purpose, granted}` | Item 4, passed through. `POST` returns the updated record. |

**New fields on each attempt** (extend `QuestionAttemptRecord`; today only `question_text, phase, evaluation, error_type, hint_level_used, attempted_at` exist):

| Field | Meaning |
|---|---|
| `topic_id`, `micro_skill_id` | Which topic and skill the question tested |
| `time_taken_seconds` | From the question appearing to the answer |
| `visual_cue_shown` | A visual cue was on screen for this question |
| `scaffold_used` | Step-by-step help was used |
| `independent` | Solved with no hint, scaffold or rescue |
| `misconception_id` | The misconception detected, or null |

Session listing is the main gap: sessions can be read today only one at a time by `session_id`.

## 3. Content: Aditya

| # | What |
|---|---|
| 13 | Parent-friendly label and one-line description for each misconception in the question bank (feeds item 6). |

## 4. Decisions: Manjusha

| # | Question |
|---|---|
| 14 | One guardian per student, or several (for example two parents)? |
| 15 | Notification emails (weekly summary, topic mastered, 3 days inactive): in scope? If yes, who sends them? Preferences are stored in the browser for now. |
| 16 | Privacy contact shown to parents (the portal shows `privacy@nablix.ai`). |
| 17 | Should the portal move to `nablix.ai/parent/`? That needs an nginx location, which needs sudo on the VM. |

## 5. Frontend: Manav

| # | What |
|---|---|
| 18 | When 1–12 are live: build with `NEXT_PUBLIC_PARENT_API_MODE=http`, deploy, and test end to end with a real guardian account. |
| 19 | Turn on `NEXT_PUBLIC_REGISTRATION_LIVE` in the student app once items 2 and 4 are verified, so sign-up consent is saved for real. |

## Order

1 → 3 → 7 → 8 → 10 unlock most of the dashboard. 5, 6 and 4 fill topics, mistakes and consent.
