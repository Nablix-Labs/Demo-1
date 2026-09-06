# Phase 3 repeated-failure & prerequisite remediation — frontend plan

**Date:** 2026-09-06
**From:** Manav (frontend)
**Specs:** `Nablix_Phase3_Prerequisite_Remediation_Change_Spec_v3` (7pp),
`Nablix_Phase3_TC_Changes_and_New_TC26_Onward_v3` (TC-18/19/20 revised, TC-26…36 new)
**Scope of this document:** frontend only. No backend edits.

---

## 1. What the spec actually asks of the frontend

Spec §12 names two obligations for me, and one prohibition:

> Follow backend routing and display the destination. Do not independently
> calculate prerequisite or repair logic. Whenever `intervention_required = true`,
> show the difficulty-input popup with selections + voice capture and submit the
> student input to the existing event-processing flow.

Everything else — the checkpoint question, the two repair cycles, the
prerequisite lookup, the WEAK marking, the return checkpoint — is Chiru
(Student Model orchestration) and Saravanan (curriculum endpoint). The frontend
must not reimplement any of it, and this plan does not.

**But "follow backend routing" is not a no-op today.** The frontend currently
does not read `routing` at all. That is the bulk of the work below.

---

## 2. The gap that makes this non-trivial

The frontend infers what to do next from `current_phase` plus whether a new
question id arrived. Three of the spec's new states are invisible to that
inference, and one of them is an outright freeze.

### 2.1 The checkpoint re-serve will lock the student out — highest risk

`lib/phase3.ts` locks the canvas by question id and unlocks only when a
*different* id arrives:

- `servedNextQuestion(res, answeredId)` → `served !== answeredQuestionId`
- `phase3Locked(lockedId, activeId)` → locked while the ids match

The whole point of this change is that Repair #1, Repair #2 and prerequisite
remediation all return to the **SAME** `question_id` **and** the same
`question_usage_id` (TC-26, TC-28, TC-32; spec §9 "locked rule").

So on `payload_type: RESUME_SAME_INDEPENDENT_QUESTION`, the id is unchanged,
`servedNextQuestion` returns false, the lock never lifts, and the student comes
back from guided repair to a frozen canvas showing "Answer recorded." with
nothing to press. Identical in feel to the 4 Sep stranding bug
(`docs/bug-phase3-exhausted-blocks-review-2026-09-04.md`).

**This must be fixed by reading `routing`/`payload_type`, not by comparing ids.**
Ids are specified to be identical, so no id-based heuristic can work.

### 2.2 `COLLECT_INTERVENTION_INPUT` is the stranded state again

TC-33/34/35 return `question_set: null`, `recommended_entry_phase: null`,
`current_phase: PHASE_3_INDEPENDENT_PRACTICE`. That is exactly the
"`question_id: null` inside an active phase" shape the 4 Sep bug report called
out as unrenderable. It becomes renderable only because
`payload_type: INTERVENTION_INPUT_REQUIRED` is there to be read — so reading it
is mandatory, not optional polish.

### 2.3 Prerequisite remediation switches topic mid-Phase-3 — no path exists

`START_PREREQUISITE_ORIENTATION` sends the student to `next_topic_id` at
`PHASE_1_ORIENTATION` (TC-31), then back. The only topic-switch machinery today
is `next_topic_handoff` → `handoffDestination()` → `setCurrentTopic()`, and it
lives solely on `app/review/page.tsx` (topic completion). Nothing switches topic
from inside practice.

---

## 3. The backend strips every new signal before the browser sees it

Verified in `nablix-backend/app/models/student_model_session.py`, not inferred.

The Student Model event the tutor backend receives internally
(`StudentModelEvent`, `:220-230`) carries `routing` and `status`. The projection
actually sent to the browser does not:

```python
class PublicStudentModelEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    schema_version: Literal["3.0"]
    request_id: str
    processed_at: str
    journey_state: PublicStudentModelJourney   # only { topic_id }
    phase_payload: PublicStudentModelPhasePayload | None
```

`routing` and `status` are absent, `journey_state` is narrowed to `topic_id`
alone, and `PublicStudentModelPhasePayload` (`:246-252`) keeps only
`phase`, `payload_type`, `question_set`, `orientation_bundle`. Every model on
that path is `extra="forbid"`, so a new field is dropped rather than passed
through.

So of everything this change introduces:

| Signal | Reaches the browser? |
|---|---|
| `phase_payload.payload_type` | **Yes** |
| `routing.next_action` / `reason_code` / `next_topic_id` | No — not on the public model |
| `status.intervention_required` / `status_code` | No — not on the public model |
| `phase_payload.intervention_input_request` | No — `extra="forbid"` drops it |
| `journey_state.phase_3_independent_practice.*`, `repair_state_by_skill` | No — journey narrowed to `topic_id` |

`payload_type` surviving is the one thread we have, and it is enough for the
worst bug (§2.1). Everything else needs the public projection widened.

### Asks for Chiru

| # | Ask | Blocking |
|---|-----|----------|
| 1 | Add `routing` and `status` to `PublicStudentModelEvent` | **Yes** for F5–F7 |
| 2 | Add `intervention_input_request` to `PublicStudentModelPhasePayload` | **Yes** for F3 |
| 3 | Emit `RESUME_SAME_INDEPENDENT_QUESTION` as `payload_type` on every checkpoint re-serve | **Yes** for F2 |
| 4 | Send the above on `GET /session`, not only on the event reply | **Yes** for F3 |
| 5 | Accept `INTERVENTION_INPUT_SUBMITTED` as an `interaction_type` on `/interaction` | **Yes** for F4 |
| 6 | `audio_ref` — no upload path exists in the frontend | No |

**On ask 3:** the checkpoint question keeps its `question_id` *and*
`question_usage_id` by design (spec §9), so `payload_type` is the only thing
that can distinguish a re-serve from a duplicate reply. If it does not arrive,
no frontend change can unfreeze the student.

**On ask 4:** Phase 3 silent mode has stripped event fields before — a fresh
question arrived with its options only on `GET /session`. If
`intervention_input_request` goes the same way the popup never opens and the
student is stranded with no visible reason.

**On ask 5:** the frontend has no Student Model client; it posts
`interaction_type` (a closed union, `lib/api.ts:344-364`) to `/interaction`.
Adding a value there is far cheaper than new client plumbing and auth.

**Also:** this must travel over REST, not the voice frame. `lib/voiceSupportFrame.ts`
is a hand-maintained allow-list and silently drops fields it does not know —
three REST-fine / voice-broken bugs so far.

## 4. Frontend work

Ordered by dependency. Each item states how it is verified.

**Status, 6 Sep 2026:** F1, F2 and F3 are built — they depend only on
`payload_type`, which survives the public projection. F4–F7 need the asks in §3.

| | | |
|---|---|---|
| F1 | `lib/phase3Routing.ts` + 20 tests from the TC fixtures | **done** |
| F2 | checkpoint re-serve unlocks the canvas | **done** |
| F3 | `components/InterventionInputModal.tsx` + `/dev-screens/intervention` | **done** (fixture only — ask 2) |
| F4 | submit `INTERVENTION_INPUT_SUBMITTED` | blocked on ask 5 |
| F5 | paused-for-intervention screen | blocked on ask 1 |
| F6 | prerequisite journey | blocked on ask 1 |
| F7 | repair destination copy | blocked on ask 1 |

### F1 — `lib/phase3Routing.ts`: read the routing block (new file)

Pure module, no React, fully unit-testable against the TC fixtures.

Parses `routing` + `phase_payload` into one discriminated union the UI can
switch on:

```
SERVE_QUESTION        (FRESH_INDEPENDENT_QUESTION)
RESUME_CHECKPOINT     (RESUME_SAME_INDEPENDENT_QUESTION)
GO_TO_GUIDED_REPAIR   (RETURN_TO_GUIDED_LEARNING + repair_cycle_no)
GO_TO_PREREQUISITE    (START_PREREQUISITE_ORIENTATION + next_topic_id)
COLLECT_INTERVENTION  (COLLECT_INTERVENTION_INPUT)
AWAIT_REVIEW          (AWAIT_INTERVENTION_REVIEW)
START_REVIEW          (START_REVIEW)
UNKNOWN               (anything else — degrade, never throw)
```

Rules, learned the hard way:
- Every field optional; an unrecognised `next_action` yields `UNKNOWN` and the
  screen keeps its current behaviour. Never throw on a missing backend field —
  backend deletes have become live outages before.
- Prefer `phase_payload.payload_type` where present, fall back to
  `routing.next_action`, so a build that ships one before the other still works.
- No repair counting, no prerequisite decisions, no difficulty arithmetic. The
  module reads; it does not decide. (Spec §12.)

**Verify:** unit tests built from the literal TC-18/19/20/26–36 JSON in the spec
PDF, checked into `lib/__tests__/`. Each TC output → expected union member.

### F2 — Lift the lock on checkpoint re-serve

`lib/phase3.ts`: add an explicit unlock signal so `RESUME_CHECKPOINT` clears
`phase3LockedQuestionId` even though the id is unchanged. Threaded into
`app/practice/page.tsx` where `servedNextQuestion` is consulted today.

Fixes §2.1. Nothing else in `phase3.ts` changes — the id-keyed lock stays the
default, because it is still the right answer for duplicate and out-of-order
replies.

**Verify:** a test that a `RESUME_SAME_INDEPENDENT_QUESTION` reply carrying the
same `question_id` and `question_usage_id` as the locked attempt returns
unlocked; and that a plain duplicate reply (no routing) still stays locked.

### F3 — Intervention difficulty popup — `components/InterventionInputModal.tsx`

The one thing §12 names outright. Modelled on `components/support/ConsentModal.tsx`
(scrim + `role="dialog"` + `aria-modal`), which is the house pattern.

- Opens on `COLLECT_INTERVENTION` from F1.
- Prompt from `intervention_input_request.prompt`, defaulting to
  "What are you finding difficult?".
- Options from `intervention_input_request.selection_options` (`code` + `label`).
  If the array is absent or empty, fall back to the six codes fixed in spec §11
  so the student is never shown an empty popup.
- Multi-select. Submit disabled until ≥1 selection (`selection_required`).
- Voice: a record control using `useVoiceTurn`, transcript shown and editable,
  never required (`voice_input_required: false`). Voice must not auto-submit —
  Phase 3 silent-mode rule: voice may never submit an independent answer, and
  the same caution applies here.
- Not dismissible by clicking away. Spec §11 says the popup is shown *before*
  leaving the student on the intervention state.

**Verify:** render tests for required-selection gating, missing
`selection_options` fallback, voice-optional, and payload shape matching TC-36.

### F4 — Submit the input, then stay paused

`lib/api.ts`: one new client function posting `INTERVENTION_INPUT_SUBMITTED`
with exactly the TC-36 input shape.

Critical: submitting **does not resume the student** (spec §11, TC-36 keeps
`status_code: INTERVENTION_REQUIRED`). The popup closes into F5, not back into
the question.

**Verify:** submitting leaves phase/route unchanged and the paused screen showing.

### F5 — "Paused for review" state on the practice screen

For `AWAIT_REVIEW` / `phase_3_independent_practice.status: PAUSED_FOR_INTERVENTION`.

A plain honest panel: this topic is paused while a teacher looks at it, here is
what you told us, there is no next question. Explicitly suppress the "Review
with tutor" control — `reviewIsReady()` will correctly refuse to navigate, but
offering a button that cannot work is the stranded-screen feel again.

**Verify:** TC-33/34/35 fixtures render the paused panel, no question, no review
button, no infinite spinner.

### F6 — Prerequisite remediation journey

- `GO_TO_PREREQUISITE` → `setCurrentTopic(next_topic_id)` +
  `landingRoute(next_topic_entry_phase, topicId)`, reusing
  `lib/usePhaseRouting.ts` rather than adding a fourth phase→route map.
- Persistent banner while remediating: "We're going back to *X* first, then
  you'll finish this question." Read `routing.return_topic_id` /
  `return_question_id` purely for display.
- On `PREREQUISITE_REMEDIATION_COMPLETED` the backend routes back; F1 sees
  `RESUME_CHECKPOINT` and F2 unlocks. No client-side return bookkeeping — the
  return checkpoint is Chiru's (spec §8/§9), and duplicating it is exactly the
  independent routing calculation §12 forbids.

**Verify:** TC-31 → routed to `ALG-KS3-01` orientation with the banner naming
`ALG-KS3-03`; TC-32 → back on the practice screen with `Q-T03-024` unlocked.

### F7 — Repair destination copy

`RETURN_TO_GUIDED_LEARNING` already routes correctly (`GUIDED_PRACTICE` → `/`),
so this is copy only: say a short line about why we're going back, and
distinguish Repair #1 from Repair #2 using `repair_cycle_no` for display.
Display only — the cap of 2 is enforced by the backend.

---

## 5. Explicitly out of scope

- Repair-cycle counting, the 2-cycle cap, the 3→2→1 difficulty rule.
- Choosing or preserving the checkpoint question / `question_usage_id`.
- Calling the new prerequisite endpoint. The frontend never calls Saravanan's
  service directly and should not start.
- Marking micro-skills WEAK.
- Resolving an intervention. The frontend collects input; it never clears
  `INTERVENTION_REQUIRED`.

---

## 6. Sequencing

1. Ask 1 and 2 answered → F1 (+ TC fixtures) — safe to build against the spec
   JSON before the backend ships, since it is a pure parser.
2. F2 — smallest change, largest risk removed.
3. F3 + F4 + F5 — the popup and its aftermath, the named deliverable.
4. F6, F7.

F1 and F2 are worth doing regardless of when the rest lands: without them, the
first repair cycle that reaches a real student freezes them on the checkpoint
question.
