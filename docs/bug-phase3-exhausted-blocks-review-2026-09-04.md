# BUG — Phase 3 with no questions left strands the student instead of moving them to Review

**Reported by:** Manav (frontend)
**Date:** 4 Sep 2026, ~18:00 UTC
**Environment:** `https://nablix.ai/app/` (VM), student **ST015**, topic ALG-ORI-01 / concept `ALG_LINEAR_ONE_STEP`
**Severity:** blocking — nothing can reach Phase 4, so the review work cannot be tested at all
**Owner:** Student Model / tutor backend

---

## Summary

When the Student Model has no `PHASE_3_INDEPENDENT_PRACTICE` questions left for a
student, it returns **nothing** rather than advancing them.

That single condition shows up as two different-looking failures — a dead end
mid-session, and a 503 on session start — and it is almost certainly why nobody
has been able to reach Phase 4 on the VM.

Exhausting independent practice is the normal way a topic *finishes*. It should
route the student to **REVIEW**. Right now it routes them nowhere.

---

## Symptom A — the student is stranded mid-session

Session `SESSION1db628ffd00b4d64bcd9cf69950d04cf`, ST015, ~15:47 UTC.

I drove a real session from guided practice into independent practice and
answered the choice question. The attempt came back as needing rescue, which the
UI handled correctly — it showed *"We'll review this one before a fresh
independent check"* and locked the choices per the Phase 3 rule.

Then nothing arrived. No replacement question, and no rescue. `GET /session`:

```jsonc
{
  "current_phase":             "INDEPENDENT_PRACTICE",
  "question_id":               null,       // ← no question
  "current_question":          null,       // ← nothing to answer
  "question_completed":        true,
  "independent_attempt_count": 1,
  "rescue_mode_active":        false,      // ← no rescue coming either
  "served_question_ids":       ["Q-T01-009"]   // ← only ever one
}
```

The question is closed, no replacement was served, and no rescue was started.
The student is left on a locked screen with no way forward and nothing on the
record that any client could act on.

## Symptom B — a new session cannot start at all

Once ST015's journey state is sitting in Phase 3, `POST /session/start` fails:

```
503  {"error_code":"HTTP_ERROR",
      "message":"Student Model returned no questions for PHASE_3_INDEPENDENT_PRACTICE.",
      "request_id":"REQ4B4B44B5"}
```

Reproduced three times in a row, ~18:02 UTC. So the student cannot continue the
old session **and** cannot open a new one — they are locked out of the topic
entirely.

That error message is what identifies the shared cause: it is the same "no
questions for this phase" condition as Symptom A, surfaced at a different moment.

**Scope:** the JWT is bound to ST015 (starting as `ST001` returns
`STUDENT_FORBIDDEN`, 403), so I could not test whether a fresh student is
affected. It may be state specific to ST015 rather than a topic-wide fault —
worth checking before assuming either.

---

## What we think should happen

Running out of Phase 3 questions is **success**, not an error. Independent
practice ending is the trigger for Phase 4.

1. When the Student Model has no further Phase 3 questions and the attempts so
   far are sufficient, advance the journey to **REVIEW** and materialise the
   Phase 4 review.
2. If it genuinely cannot proceed, say so **on the session record** — a phase, a
   status, anything a client can render. A `current_phase` of
   `INDEPENDENT_PRACTICE` with `question_id: null` is indistinguishable from a
   loading state, so every client will sit and wait forever.
3. `session/start` should not 503 for a student whose journey has completed the
   practice phases. Returning them to their actual position (Review) is the
   correct answer.

Point 2 matters even if 1 is fixed: `question_id: null` inside an active phase is
not a state any frontend can represent honestly.

---

## The frontend is behaving correctly here

Worth stating, because from the outside this looks like a frontend hang:

- **The choices locked** after the accepted submission — Phase 3 spec §3.2, an
  accepted attempt must stop being editable. Correct.
- **"Review with tutor" refused to navigate.** That control reads `GET /session`
  first and only moves when the backend is genuinely in Review. The backend said
  `INDEPENDENT_PRACTICE`, so it stayed put. That guard exists specifically so we
  never drop a student on a Review screen the backend never entered, and it did
  its job.

Neither is something we intend to change. If the backend advances the phase,
both resolve on their own with no frontend release.

---

## Reproduction

1. Sign in as ST015 on `https://nablix.ai/app/`.
2. Work through guided practice until the phase becomes `INDEPENDENT_PRACTICE`.
3. Answer the independent choice question.
4. `GET /session/{id}` → `question_id: null`, `current_phase: INDEPENDENT_PRACTICE`.
   The screen is locked with no next question.
5. Clear the session and reload → `POST /session/start` → 503, message above.

ST015 is currently in exactly this state, so step 5 reproduces on its own.

---

## What this blocks

- **Phase 4 verification end to end.** The review screen and the PR #257 boards
  are built, deployed and verified against a fixture
  (`https://nablix.ai/app/dev-screens/phase4` — no login, no backend), but
  nothing has been proven against a real session record because no real session
  can get there.
- **Any QA of independent practice or review**, ours or Manjusha's.

Once a session can reach Review I can verify the whole Phase 4 path against live
data the same day.

---

## Note on the earlier report

The `/interaction` 500 → 409 I flagged around 12:45 UTC has **cleared** —
`/interaction` returns 200 again. Please disregard that one; this is a different
and reproducible fault.
