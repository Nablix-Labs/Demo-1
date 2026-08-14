# Guided practice: the bank fallback that 409s the session

**For:** Chirudeva (owner, per Sanya 31 Jul 20:18)
**From:** Manav
**Date:** 31 July 2026, updated 20:20 after Sanya's correction

---

## STATUS: assigned to Chiru. This doc is evidence only — no action needed from me.

Sanya confirmed she saw this in the afternoon, that initial guided practice is
correct, and that she has already asked Chiru to fix it. I am not proposing a
fix and I am not touching this code.

## Two proposals in earlier versions of this doc were WRONG. Do not revive them.

For the record, so nobody digs them up:

1. **`cad2484` — clear `student_model_event` on advance.** Would have permanently
   discarded the Student Model's authored questions and locked students onto bank
   content. Reverted (`72a995c`). Sanya was right, and more right than either of
   us knew at the time.
2. **Make `_active_answer_spec` return `None` instead of raising.** Would have
   stopped the 409 by *silently serving the wrong question*. Hides the bug.

Both treated the symptom. The actual defect is that the bank is consulted at all
in a schema-managed session.

## What the logs show

Questions come from the Student Model, exactly as Sanya says. The RAG bank is
only wired into *legacy* sessions (`start_session` → `_start_legacy_session`,
taken only when `initial_phase` is supplied — and the frontend never supplies
it; verified by grep).

But a fallback reaches past it mid-session:

```python
# interaction_service.py:1680  (same gate at :1660 for phase transitions)
elif (conversation_action == "ADVANCE_TO_NEXT_QUESTION"
      and schema_response is None):        # this turn produced no SM event
    advance = await next_question_updates(session, session.current_phase)
    #         └─> get_next_question() → Qdrant → ALG_1STEP_GP_F01
```

On a turn that advances but generates no Student Model event (a hint, a
clarification, an acknowledgement), one question is taken from the bank. The
next turn validates that id against the authored `question_set`, which cannot
contain it → 409, and the session is stuck.

**Evidence — one session, both sources:**

```
SESSION3798e873   (Manjusha, 31 Jul ~20:05, orientation completed cleanly)
  Q-T01-001, Q-T01-004   ← Student Model, served correctly
  ALG_1STEP_GP_F01       ← bank fallback, 409 × 4
```

`ALG_1STEP_GP_F01` exists in exactly one place in the repo:
`app/services/rag/question_serving/question_bank.json:87`.

## Repro detail for Chiru — it is not only after independent practice

Sanya's recollection was that the fallback happens after independent practice.
Tonight's failures did **not**: across the last hour of logs the only phase the
backend ever reported was

```
27 × "current_phase": "GUIDED_PRACTICE"     (no INDEPENDENT_PRACTICE at all)
```

Manjusha's session never reached independent practice and still hit the 409
four times. So the fallback appears to fire from more than one place — worth not
scoping the fix to the post-independent-practice path alone. Both call sites
(`:1660` and `:1680`) share the same `schema_response is None` gate.

## Suggested shape (Chiru's call entirely)

In a schema-managed session, advance should never substitute a bank question —
either take the next one from the stored `question_set`, or fail loudly. A silent
substitution is what turns a missing event into a dead session.

This is the same root as your critical #1 (competing state paths): text and REST
voice go through Schema 3.0, this branch quietly does not.

---

## Who owns which half

This has bounced between people twice now, so writing it down:

| Layer | Owner |
|---|---|
| **Root cause** — canvas runs a separate legacy state path from text/REST voice, so it advances onto bank ids the schema set never had | **Chirudeva** — critical #1 and #3 on Manjusha's list |
| **The raising line** — `_active_answer_spec` / `_schema_question`, and what `student_model_event` means | **Sanya** — "AI-specific state definition" per Manjusha's note |
| The `cad2484` revert decision | Sanya's, already made and correct |

The proposal below is a plaster on Sanya's line. **Chiru's unification removes
the wound entirely** — routing canvas through the same Schema 3.0 state machine
as text means the ids can't diverge in the first place, and this whole class of
409 dies with it.

So the real question is sequencing, not ownership: is the state-machine work
close enough that we should skip the plaster?

---

## Your call — three options

1. **This narrow fix.** Unblocks phase-3 canvas testing tonight. I'd ship it as
   its own revertible commit for you to review, and I would not merge it
   without your yes.
2. **Your proper fix (ask #1 in `BACKEND-ASKS-2026-07-29.md`)** — serve advances
   from the schema `question_set` so the ids never diverge in the first place.
   This is the real answer, and Chirudeva's "one authoritative state machine"
   work would subsume it anyway. If that's landing soon, option 1 is just noise.
3. **`git revert 72a995c`** — re-applies my original fix. I'm explicitly *not*
   recommending this; Sanya rejected it on principle and the principle holds.

**My honest read:** if Chiru's state-machine work is more than a few days out,
take option 1 so Manjusha isn't blocked in the meantime. If it's imminent, skip
it — a plaster on a path that's about to be deleted is churn, and it's one more
thing to unpick during the migration.

---

## What I've verified, and what I haven't

**Verified:** the log sequence above is real and from her session; the call
chain `canvas_service.py:119 → _active_answer_spec → _schema_question` is read
straight from current `main`; `_active_answer_spec` already has a `None` return
path.

**Not verified:** I have not reproduced the canvas 409 end to end myself. My API
repros start sessions directly with `initial_phase`, and those don't carry a
Student Model event, so they never reach the failing branch — which is exactly
why this shows up in real journeys and not in my scripted tests. **Before
shipping option 1 I'd reproduce it through a full journey first and confirm the
fix actually clears it**, rather than trusting the trace alone.

---

## On the frontend side (already done, so you don't need to)

The frontend can't fix the 409, but it was making it worse by lying about it:
"Practice saved — nice work" appeared the instant the button was pressed, before
the server answered — so Manjusha's three failures looked identical to success.

Fixed and deployed: the canvas locks under a "Checking your work…" overlay until
the server responds, the success banner only shows on a real 200, and a failure
shows a retryable error with the student's work untouched. That's why her
screenshot shows the old behaviour and the current build won't.
