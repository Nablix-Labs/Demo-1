# Numera — backend asks after wiring Phase 0→1

**Date:** 2026-07-28
**From:** Manav (frontend)
**Branch:** `manav/phase-0-1-backend-source-of-truth`
**Supersedes the open items in:** [BACKEND-ASKS-AND-FRONTEND-STATUS.md](./BACKEND-ASKS-AND-FRONTEND-STATUS.md) (2026-07-27)

The frontend now drives Phase 0→1 entirely from the backend: the Student Model's
question set, its orientation bundle, and its phase transitions. No local
grading, no mock questions, no client-side routing decisions.

Everything below was verified against the **live VM** (`https://nablix.ai`) on
2026-07-28, not read off the source. Each item has a reproduction command.

---

## TL;DR

| # | Ask | Owner | Blocking? |
|---|-----|-------|-----------|
| 1 | Return `student_code` on `/auth/login` | Chirudeva / Saravanan | **Yes** — every logged-in student is still ST001 |
| 2 | Diagnostic never returns "no gaps" | Saravanan | **Yes** — one branch of the loop is unreachable |
| 3 | No way to resume a session mid-journey | Chirudeva | **Yes** — students re-take the diagnostic every login |
| 4 | `TEACH_BACK` is skipped entirely | Chirudeva / Saravanan | Yes, if teach-back is in scope |
| 5 | Orientation videos have `asset_url: null` | Saravanan | No — frontend falls back by topic code |
| 6 | Answer key is sent to the browser | Saravanan | No, but it's a correctness/integrity hole |
| 7 | Session ids exhaust at 999 and 500 forever | Chirudeva | No, but it took the dev API down twice |
| 8 | `learning.topics.topic_code` is inconsistent | Saravanan | No — worked around |

Items 1–4 are what actually block the demo path.

---

## 1. `/auth/login` must return `student_code` (BLOCKER)

**The claim we were given:** "No backend change is required — Manav just replaces
the hardcoded `ST001` with the authenticated user's `student_code` from
login/profile state."

**That is not possible today.** There is nowhere for the frontend to get it:

- `create_access_token()` (`app/services/security.py`) builds the JWT payload as
  `{sub, role, tier, iat, exp}`, and **`sub` is `str(user.user_id)`** — the
  integer user id, not the `ST###` code.
- `TokenResponse` (`app/schemas/auth.py`) is
  `{access_token, token_type, role, tier, last_journey_state}` — no student code.
- `last_journey_state` looks like a way in, because the raw journey dict holds
  `"student_id": student_code`. But `_project()` in
  `app/services/login_state.py` **drops that key**, and the whole field is
  `null` for a student with no journey.

**Why it matters:** `/session/event` resolves the posted `student_code` to the
student PK and then rejects it when the row's `user_id` ≠ the JWT's `sub`:

```
403 STUDENT_FORBIDDEN — student_code does not belong to the authenticated user
```

So every real student who isn't ST001's owner fails. This is GitHub issue #40.

**The fix is two lines.** `login()` in `app/services/auth_service.py` already
selects the student row for the journey lookup:

```python
student_id = session.execute(
    select(Student.student_id).where(Student.user_id == user.user_id)
).scalar_one_or_none()
```

Select `Student.student_code` alongside it and add `student_code: str | None` to
`TokenResponse`.

**Frontend is ready.** `LoginResponse.student_code` is already typed, stored in
`useAuthStore`, and read by `studentId()` in `lib/api.ts`, which every tutoring
call now goes through. The moment the field appears, it works — no frontend
change needed.

**Repro:**
```bash
curl -s -X POST https://nablix.ai/nablix-auth/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"<a real student>","password":"<pw>"}' | jq
# -> no student_code anywhere in the response
```

---

## 2. The diagnostic never returns "no gaps" (BLOCKER)

The agreed acceptance criteria include:

> Weak result: Diagnostic → Concept Orientation → Guided Practice.
> **No gap: Diagnostic → Independent Practice.**

The second branch is currently unreachable. Submitting **all 8 answers correct**
— taken from each question's own `tutor_view.answer_spec.canonical_answer` —
still comes back as:

```json
{ "current_phase": "CONCEPT_ORIENTATION",
  "routing": { "reason_code": "DIAGNOSTIC_GAPS_FOUND" } }
```

The frontend handles either outcome (it just follows `current_phase`), so
nothing needs to change on our side — but the no-gap path cannot be demonstrated
until the Student Model can actually produce it.

Worth confirming how `_diagnostic_results()` maps `student_response` to
`micro_skill_results`: we send the **option text** (e.g. `"4 × y"`), because
that is what the student picked. If the grader expects the `option_id`
(`"B"`) instead, every answer reads as wrong and gaps are always found. **Please
confirm which one you want** — we'll send whichever is correct.

**Repro:** `POST /session/start`, read `canonical_answer` per question, map it
through `student_view.options` to the option text, submit all 8 to
`/session/{id}/diagnostic/complete`.

---

## 3. No way to resume a session mid-journey (BLOCKER)

`/session/start` **always** emits `DIAGNOSTIC_QUESTION_SET_REQUESTED`, so it
always opens in `DIAGNOSTIC`. There is no resume endpoint.

Consequence: a student who finished orientation yesterday logs in today and is
put through the diagnostic again. Verified live — completed the full
diagnostic → orientation → guided flow as ST008, reloaded, and landed back on
question 1 of the diagnostic.

The frontend now lands the student on the right *screen* using
`last_journey_state.current_phase` from the login response, but it cannot open a
session at that phase.

**Ask:** either let `/session/start` resume at the journey's `current_phase`
(it already accepts `initial_phase` for the legacy path), or add
`POST /session/resume`.

Related: re-running a diagnostic for a student whose journey has already
advanced sometimes returns **409** instead — so the behaviour is also
inconsistent between students.

---

## 4. `TEACH_BACK` never runs

`complete_orientation()` in `app/services/session_service.py` asserts the
Student Model returns `PHASE_2_GUIDED_LEARNING`:

```python
_require_schema_phase(response, ("PHASE_2_GUIDED_LEARNING",))
```

So orientation goes straight to guided practice and the `TEACH_BACK` phase is
skipped, even though it exists in `PHASE_FROM_STUDENT_MODEL` and has a built
frontend screen at `/teach/[topic]` (see
[TEACH-BACK-FRONTEND-DESIGN.md](./TEACH-BACK-FRONTEND-DESIGN.md)).

**Ask:** confirm whether teach-back is in scope for this milestone. If it is,
the Student Model needs to route orientation → teach-back → guided, and
`_require_schema_phase` needs to accept it.

---

## 5. Orientation videos come back with `asset_url: null`

The orientation bundle carries the video record but no file:

```json
{ "content_type": "ORIENTATION_VIDEO",
  "video": { "video_id": "VID-KS3-T02-ORI",
             "title": "The Secret Language of Algebra",
             "asset_url": null, "duration_seconds": 75 } }
```

Manjusha uploaded the files to Azure blob and they are public and working:
`https://nablixmathvideos.blob.core.windows.net/numeradev/ALG-ORI-0N.mp4`
(N = 1–6; 7 is a 404).

**Frontend workaround (shipped):** when `asset_url` is null we resolve the file
from the session's topic code — `ALG-ORI-02` → `ALG-ORI-02.mp4`. Verified
playing live: 1920×1080, 78 s.

**Ask:** populate `asset_url` so the Student Model owns its own content and the
frontend can drop the fallback. Note the container sends **no CORS headers** —
fine for a `<video>` tag, but it will block `fetch`/XHR if anything server-side
wants to read it.

---

## 6. The answer key is sent to the browser

Every diagnostic question in `phase_payload.question_set.questions[]` includes:

```json
"tutor_view": { "answer_spec": { "canonical_answer": "B", "accepted_answers": [...] } }
```

This reaches the client on `/session/start`. The frontend never reads it (and
its types deliberately omit `tutor_view`), but anyone with devtools can read
every answer before responding — which also makes any diagnostic result
untrustworthy.

**Ask:** strip `tutor_view` from the payload the tutoring backend forwards to
the client, or have the Student Model expose a student-safe projection.

---

## 7. Session ids exhaust at `SESSION999` and then 500 forever

`_build_session_id()` raises once the in-memory range is used up:

```
RuntimeError: mock session id range exhausted at SESSION999.
```

After that **every** request to `/session/start` returns
`500 INTERNAL_ERROR — "Something went wrong. Please try again."` for everyone,
until `systemctl restart nablix-backend`.

I hit this twice on 2026-07-28 with a frontend retry loop (my bug, since fixed
and covered by tests). But 999 sessions is not many for a shared dev box, the
counter never resets, and the resulting error names neither the cause nor the
remedy.

**Ask:** wrap the counter, or persist session ids, and return a specific
error code so it is diagnosable without reading the traceback.

---

## 8. `learning.topics.topic_code` is inconsistent

Within Algebra, `sequence_no` 1–6 have codes:

| seq | topic_code | subtopic |
|-----|-----------|----------|
| 1 | `ALG-KS3-01` | What Is Algebra? |
| 2 | `ALG-ORI-02` | Algebraic Notation |
| 3 | `ALG-ORI-03` | Variables and Constants |
| 4 | `ALG-04` | Expressions |
| 5 | `ALG-05` | Terms, Coefficients and Factors |
| 6 | `ALG-06` | Substitution |

Three different prefixes for one topic. The video files are uniformly
`ALG-ORI-0N`, so matching a video to a topic by its code fails for four of the
six. The frontend matches on the trailing number instead.

Also, rows 4–6 have `ks_stage`, `sequence_no`, `core_message`, `status` and
`version` all NULL, while rows 1–3 are populated.

**Ask:** normalise the codes and backfill the null columns.

---

## What the frontend now does (no action needed)

For reference, so the contract is unambiguous:

- `POST /session/start` → renders **all** questions from
  `student_model_event.phase_payload.question_set`, not the single
  `current_question` on the record.
- `POST /session/{id}/diagnostic/complete` → sends every answer at once, no
  micro-skill ids (the backend derives them), no client-side grading.
- `POST /session/{id}/orientation/start` → always called on entering the phase,
  even though `/diagnostic/complete` already returns the bundle, because it is
  what sets `phase_1_orientation.status = IN_PROGRESS`.
- `POST /session/{id}/orientation/complete` → called before leaving the phase.
- Routing follows `current_phase` in **both** directions, including the first
  value observed. `question_id: null` is honoured as a real state.
- Voice: `provider`/`voice` are sent on `/voice/tts` and as `tts_provider`/
  `tts_voice` on the `/voice/stream` WS, with all Cartesia and Inworld presets
  exposed in the picker (issue #41).
