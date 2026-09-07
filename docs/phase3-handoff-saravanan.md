# Phase 3 remediation — Saravanan handoff

**Date:** 2026-09-07 · **From:** Chirudeva (tutor backend) · **Spec:** *Phase 3
Repeated Failure & Prerequisite Remediation*, v3, 5 Sep 2026

## Status and ownership

**Implemented locally:** checkpoint validation, terminal intervention
presentation and enforcement, feedback ingestion and forwarding, durable pending
feedback and receipt state, content-gap visibility. Nothing is deployed.

**Proposed, awaiting your agreement:** the upstream JSON below. These are the
exact fields the tutor backend understands today, not a demand that you adopt
these names. When your format is agreed, replace the mapping at the adapter/model
boundary — do not add a second parser or guess at a fallback endpoint.

You own question selection and authored difficulty, repair counts per
student/topic/skill, prerequisite lookup and ordering, WEAK-equivalent state,
cross-topic lifecycle, and intervention decisions and resolution. The tutor
backend implements none of those policies and calls no curriculum endpoint.

**Changed since the 6 Sep draft.** The frontend's contract was already merged, so
the tutor backend was reshaped to match it rather than the other way round. Two
things you care about moved:

1. **The reason-code vocabulary changed** to the spec §11 codes the frontend
   ships (`DONT_UNDERSTAND_QUESTION`, `WORDS_SYMBOLS_CONFUSING`,
   `WORKING_MISTAKES` — see below). The previous draft's `QUESTION_UNCLEAR` /
   `WORDS_OR_SYMBOLS_CONFUSING` / `CALCULATION_MISTAKES` are gone.
2. **`feedback` is now nested**, `{selected_reason_codes, voice_input}`, where
   `voice_input` is `{provided, audio_ref, transcript}`. The flat
   `voice_transcript` / `audio_ref` pair is gone.

Everything structural — the checkpoint object, the intervention object, the
event name, the deduplication rules — is unchanged from the last draft.

## Contract mapping

| Required meaning | Current backend expectation | Agreed representation |
| --- | --- | --- |
| Frozen Phase 3 question and position | `journey_state.phase_3_independent_practice.return_checkpoint` | Awaiting agreement |
| Completed repairs for the checkpoint skill | `phase_3_independent_practice.phase2_repair_count`, optional int 0–2 | Awaiting agreement |
| Stable intervention case, scope, resolution | `journey_state.intervention` | Awaiting agreement |
| Feedback already accepted, incl. after reopening | `intervention.feedback`, null until accepted | Awaiting agreement |
| Terminal exhaustion trigger | `routing.reason_code = AUTOMATED_REMEDIATION_EXHAUSTED` plus an active case | Awaiting agreement |
| Feedback event and receipt | `INTERVENTION_INPUT_SUBMITTED` on the existing `/session/event` | Awaiting agreement |
| Where a prerequisite journey returns to | `routing.return_topic_id` / `return_question_id`, both optional | Awaiting agreement |
| Prerequisite lookup | No backend call implemented; curriculum path unspecified | Awaiting agreement |

Keep the Schema 3.0 top-level envelope, which forbids unknown top-level keys.
Every new persisted field has an explicit default, so older responses and stored
snapshots still load.

## Proposed checkpoint object

Under `journey_state.phase_3_independent_practice.return_checkpoint`:

```json
{
  "topic_id": "ALG-ORI-02",
  "micro_skill_id": "T02.M1",
  "phase_visit_no": 1,
  "question_position_no": 3,
  "checkpoint_question_id": "Q-T02-CHECKPOINT",
  "question_usage_id": "QU-T02-CHECKPOINT"
}
```

`phase_visit_no` identifies the original visit; it is not a counter to bump each
time the student comes back. Journey identity also uses topic and journey
`started_at`.

Return this when the checkpoint is first served, throughout both repairs, and on
reopening. The served question must match its question id, usage id, topic and
micro-skill mapping, and `current_question_id` must name it. Question content and
authored difficulty stay yours and stay unchanged.

On a return, retain `used_question_ids`, completed skills and verified skills.
The backend exempts only the matching checkpoint from its reused-question
rejection and restores the original position, even for a one-question set. Other
reused questions are still errors. Do not replace or drop the checkpoint while
its skill is unresolved; after verification the journey may clear it.

New attempts carry new turn and event identities even though the question and
usage identities are fixed. A replayed accepted turn is still a duplicate.

**One thing to know about `used_question_ids`.** The tutor backend distinguishes
a first serve from a re-serve by whether the checkpoint question id is already in
`used_question_ids` — that is what tells the browser to hand the canvas back
rather than treat the reply as a duplicate. So add the id when the question is
answered, not when it is served. If you add it at serve time, say so: a first
serve then reads as a re-serve, which is harmless today but I would rather know
than assume.

## Proposed intervention object

Under `journey_state.intervention`:

```json
{
  "intervention_id": "INT-001",
  "topic_id": "ALG-ORI-02",
  "micro_skill_id": "T02.M1",
  "reason_code": "AUTOMATED_REMEDIATION_EXHAUSTED",
  "state": "ACTIVE",
  "feedback": null
}
```

An active case must belong to the journey topic and to Phase 3. A terminal
response may carry `phase_payload: null`. On `SESSION_OPENED`, return the active
case even when the routing reason says the session merely resumed — the case
carries the terminal reason itself.

Given that, the backend pauses learning, keeps reads, closure and feedback
available, and projects the §11 popup for the browser. Existing Wrong-4
`intervention_required` booleans and content gaps do **not** create this case. An
exhaustion marker with no case identity is rejected rather than assigned an
invented id.

Omitting a case does not resolve a halt the backend has persisted. An explicit
`state: "RESOLVED"` for the same case lets ordinary state application resume;
there is no backend resolution endpoint. Reopening after a human resolves it must
return the resolved, current journey. Feedback submission must never resolve the
case.

## Proposed feedback event and receipt

The frontend now reaches this through `POST /interaction` with
`interaction_type: INTERVENTION_INPUT_SUBMITTED` — it has no Student Model
client of its own. The backend forwards a versioned event through the existing
adapter to `/session/event`:

```json
{
  "request_id": "INTERVENTION_INPUT_SUBMITTED:stable-uuid",
  "event_type": "INTERVENTION_INPUT_SUBMITTED",
  "student_id": "ST440",
  "topic_id": "ALG-ORI-02",
  "timestamp": "2026-09-07T09:00:00Z",
  "source_turn_id": "INTERVENTION_INPUT_SUBMITTED:stable-uuid",
  "expected_journey_version": 12,
  "intervention_id": "INT-001",
  "micro_skill_id": "T02.M1",
  "feedback": {
    "selected_reason_codes": ["DONT_KNOW_HOW_TO_START", "WORDS_SYMBOLS_CONFUSING"],
    "voice_input": {
      "provided": true,
      "audio_ref": null,
      "transcript": "I cannot choose the operation."
    }
  }
}
```

The accepted vocabulary is exactly these six, and nothing else validates:

`DONT_UNDERSTAND_QUESTION`, `DONT_KNOW_HOW_TO_START`, `CANNOT_APPLY_IDEA`,
`WORDS_SYMBOLS_CONFUSING`, `WORKING_MISTAKES`, `OTHER`.

Codes are deduplicated and sorted by the backend. `voice_input` may be omitted
entirely; when present, `audio_ref` is **always null** — there is no audio upload
anywhere in the product, and the transcript is the evidence. No audio bytes are
stored by this change. Please accept the null rather than requiring a reference.

**Fixed behaviour, negotiable representation:**

- Persist the feedback against the case and return it as
  `journey_state.intervention.feedback`, in the ordinary response envelope. The
  backend derives "already submitted" from that receipt and never publishes the
  student's own words back to the browser.
- Keep the case `ACTIVE` and every piece of learning state unchanged. Only the
  intervention evidence, journey version, activity metadata, active-session
  metadata and session count may differ in the acknowledgement. Do not return a
  next-topic handoff. The backend rejects an acknowledgement that changes
  anything else, and keeps the submission pending for retry.
- Request identity is UUIDv5 over JSON `[student_id, topic_id, intervention_id]`,
  prefixed with the event name. It excludes session id, so it is stable across
  reopens. `source_turn_id` reuses it.
- **Deduplicate by that identity before checking the expected journey version.**
  Identical normalized feedback returns its receipt. Different evidence for the
  same case is a conflict. Retry timestamps and session metadata must not make an
  identical submission look like a different event.
- Uniqueness must be enforced upstream, in your transaction. The backend's
  process-local lock cannot guarantee it across processes or sessions.
- The backend saves the pending event before sending it and replays that exact
  event after an uncertain failure or a restart. Once acknowledged, a local
  identical retry returns the receipt without calling you again.
- A version conflict that is not an already-accepted event stays a conflict. The
  frontend reopens the topic to get current state and retries the same evidence
  under the same case identity.

## Routing fields the browser now reads

The tutor backend publishes a narrowed `routing` block to the browser:
`next_action`, `reason_code`, `next_topic_id`, `next_topic_entry_phase`,
`return_topic_id`, `return_question_id`, `content_gap_detected`. `reason` is not
published — it reads as prose for a log, not for a student.

`return_topic_id` and `return_question_id` are new optional fields on
`StudentModelRouting`. **Where you do not send them, the backend fills them from
`return_checkpoint`**, so the "you will come back to…" banner works before your
side ships. If you do send them, yours win.

The backend also derives the Phase 3 `payload_type` the browser routes on —
`FRESH_INDEPENDENT_QUESTION`, `RESUME_SAME_INDEPENDENT_QUESTION`,
`INTERVENTION_INPUT_REQUIRED` — from `return_checkpoint` and
`journey_state.intervention`. **You do not need to change `payload_type`**; keep
sending `QUESTION_SET`. If you would rather own that vocabulary, say so and the
derivation comes out.

## Remaining integration work and acceptance

**Awaiting agreement or implementation:** reduced-difficulty selection, the
at-most-two-repairs rule, the prerequisite route and WEAK semantics,
earliest-topic handling, prerequisite completion and return, and reviewer
resolution.

Cross-topic execution needs a separate backend change and should not be assumed
working: the phase validator does not currently accept Independent Practice →
Orientation, and session and topic ownership across a prerequisite hop has to be
agreed before that is relaxed.

**Verify together, once your fields land:** first reduced checkpoint → Repair 1 →
same checkpoint → Repair 2 → same checkpoint → prerequisite route → same
checkpoint, reopening the session at each stage. Confirm a failed route or a
failed post-prerequisite return raises the case and pauses the topic. Then
against the real database: duplicate feedback after a lost response, two
simultaneous sessions, changed feedback, and an explicit human resolution.

**Local validation.** 719 of 720 tests in `tests/` pass. The one failure, a
Phase 2 duplicate-turn test, is unrelated and fails on a clean checkout of
`main` too. 38 tests cover this work. They run
against the repository's fake Student Model boundary and exercise snapshot
restoration — not a live database and not a migration. Every JSON example above
validates against the implemented models. Live Student Model, cross-topic
remediation and deployment remain unverified.

Run from `nablix-backend/`:

```bash
PYTHONPATH=. /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/ -q
```
