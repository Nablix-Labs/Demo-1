# Backend — what's blocking us right now

**2026-07-28 · from Manav (frontend)**
Short version. Full detail + repro commands: [BACKEND-ASKS-PHASE-0-1.md](./BACKEND-ASKS-PHASE-0-1.md)

The frontend side of Phase 0→1 is done and deployed. Everything below is backend.

---

## 1. 🔴 Session start keeps dying — `DUPLICATE_REQUEST`

**Priority: everything else is blocked behind this.**

`POST /session/start` fails for everyone, recovers on its own, then fails again.

```
attempt 1 -> REJECTED (collided on SESSION010:DIAGNOSTIC_QUESTION_SET_REQUESTED)
attempt 2 -> REJECTED (collided on SESSION011:…)
...
```

**Cause.** Two things combine:

- `_build_session_id()` counts from an **in-memory** `_next_session_number = 1`
  → ids reset to `SESSION001` on every restart.
- The start event's id is built from the session id alone:
  `request_id = f"{session_id}:DIAGNOSTIC_QUESTION_SET_REQUESTED"`

student_model dedupes `request_id` **permanently** (Postgres). After a restart
the backend replays ids that were already consumed, so they're refused.

It gets **worse with every restart**, never better — the burned set only grows.
This is also why it "works for one person but not another": it depends purely on
where the counter happens to sit.

**Fix — one line:**
```python
request_id=f"{session_id}:DIAGNOSTIC_QUESTION_SET_REQUESTED:{uuid4()}"
```
or persist the counter so ids are never reused. Same applies to
`_schema_request_id()`.

⚠️ **Restarting is not a workaround** — it resets the counter to 1 and
guarantees collisions from the first request.

*(Same root cause as the `SESSION999` exhaustion — both go away with this fix.)*

---

## 2. No way to resume a session mid-journey

`/session/start` always requests a **diagnostic** set, so a student who comes
back re-takes the diagnostic every login. Chiru has already scoped this; nothing
more needed from us. Frontend uses `last_journey_state` to land them on the right
screen, but it can't open a session at that phase.

---

## 3. `TEACH_BACK` never runs

`complete_orientation()` requires the Student Model to return
`PHASE_2_GUIDED_LEARNING`, so orientation goes straight to guided practice and
teach-back is skipped — even though the phase exists and the screen is built.

**Need to know:** is teach-back in scope for this milestone?

---

## 4. Smaller, non-blocking

| | |
|---|---|
| **Answer key sent to the browser** | `tutor_view.answer_spec.canonical_answer` ships to the client with every diagnostic. Any student can read the answers, which also makes results untrustworthy. |
| **Orientation videos have `asset_url: null`** | Frontend fills it from the topic code for now. Populate it and we drop the workaround. |
| **`learning.topics` codes inconsistent** | `ALG-KS3-01`, `ALG-ORI-02`, `ALG-04` for one topic; rows 4–6 have `ks_stage`, `sequence_no`, `core_message`, `status`, `version` all NULL. |

---

## Already done ✅

- **`student_code` on `/auth/login`** — shipped and verified live today. Frontend
  picks it up automatically.
- **"No gaps" diagnostic branch** — this was our bug, not yours: we were sending
  the option *text* where `accepted_answers` holds option *ids*. Fixed. Both
  branches now work (`DIAGNOSTIC_NO_GAPS` → `INDEPENDENT_PRACTICE`).

## One request

PR #42 edited `Numera-ui/` directly, and a frontend deploy from before that merge
overwrote it (restored now). Could frontend changes come to us as an ask instead?
We deploy the built bundle to the VM, so anything committed but not in our build
silently disappears on the next deploy.
