# The canvas 409 on phase 3 — and a smaller fix than the one you rejected

**For:** Sanya and Chirudeva
**From:** Manav
**Date:** 31 July 2026

**Short version:** this is Chirudeva's critical #3 ("Canvas bypasses the
authoritative Guided Learning flow") showing up in Manjusha's testing tonight.
The line that raises is in Sanya's area, so there's a 3-line plaster she could
approve — but if Chiru's state-machine work is landing this week, the plaster is
wasted effort and we should just wait. That's the decision I need from you two,
not from me.

---

## First: the revert is done, and you were right

`cad2484` is reverted (`72a995c`, on `main`, deployed to the VM).

Your objection was correct and I should have raised it with you before touching
that path: clearing `student_model_event` on a bank advance does drop the
session out of schema management, which means Saravanan's Student Model stops
being authoritative for the rest of the phase. That's your service's contract
and not a call for me to make unilaterally. Sorry for the detour.

---

## But it's now blocking Manjusha on phase 3

With the revert in, the 409 is back, and it's reaching canvas submissions.
Manjusha hit it at 19:30 IST today — **second canvas submission on phase 3,
three consecutive failures.**

Straight from the VM log, her session:

```
15:29:14  POST /canvas/submit
          Mathpix 200 → Student Model 200 → Qdrant next-question 200
          → 200 OK                                          ← first submit fine

15:30:19  POST /canvas/submit
          Mathpix 200 → 409 Conflict                        ← Student Model never called
15:30:37  POST /canvas/submit → 409 Conflict
15:31:03  POST /canvas/submit → 409 Conflict
```

The pattern is the familiar one: the first submission succeeds and advances the
session onto a bank question (`ALG_1STEP_GP_F02`), and from then on the id isn't
in the schema `question_set`, so every subsequent submission dies.

---

## The exact line, this time

I traced it properly rather than inferring:

```python
# app/services/canvas_service.py:119
answer_spec=_active_answer_spec(session),
```

```python
# app/services/interaction_service.py:213
def _active_answer_spec(session: SessionRecord) -> AnswerSpec | None:
    if session.student_model_event is None:
        return None                                   # ← already returns None here
    return _schema_question(session).tutor_view.answer_spec
    #      ^^^^^^^^^^^^^^^^^^^^^^^^^ raises the 409 when the id isn't in the set
```

That's the whole mechanism. It fires after OCR and before the Student Model
call, which matches the log exactly (Mathpix succeeds, nothing after it runs).

---

## Proposal: three lines, and it doesn't do the thing you objected to

Make `_active_answer_spec` return `None` when the question isn't in the set,
instead of raising:

```python
def _active_answer_spec(session: SessionRecord) -> AnswerSpec | None:
    if session.student_model_event is None:
        return None
    question = _schema_question_or_none(session)   # non-raising lookup
    return question.tutor_view.answer_spec if question else None
```

Why I think this one is acceptable where `cad2484` wasn't:

| | `cad2484` (rejected) | This proposal |
|---|---|---|
| Touches `student_model_event` | **Yes — cleared it** | **No** |
| Session stays schema-managed | No | **Yes** |
| SM stays authoritative | No | **Yes** |
| Changes question progression | Indirectly | No |
| Scope | Advance path | One lookup |

The `None` case is not a new code path — the function already returns `None` one
line above when there's no event, so **every caller handles `None` today**. We'd
just be saying "no answer spec available for this question" instead of failing
the whole request.

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
