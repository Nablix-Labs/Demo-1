# Student Model `/interaction` Removal and Schema 3.0 Migration

## 1. Purpose and decision

This specification coordinates the removal of the Student Model's legacy
`POST /interaction` endpoint and completes the migration to the Schema 3.0
`POST /session/event` endpoint.

Owners:

- **Saravanan:** `Nablix-Labs/mathtutor-student` and its deployed API.
- **Chirudeva:** the Nablix backend wiring in `nablix-backend`.

Decision:

1. `POST /session/event` becomes the **only Student Model write endpoint**.
2. Every accepted action that creates or changes learner or journey state must
   use `/session/event`; no Nablix production path may call the Student Model
   `/interaction`.
3. The Nablix tutor-facing `POST /interaction` route remains. It receives
   learner turns and may call Student Model `/session/event`. It is a different
   endpoint from the Student Model route being removed.
4. OCR-only canvas processing, speech transport, health checks, and other
   operations with no Student Model meaning do not need a session event.
5. A failed Student Model write must fail the parent Nablix operation
   explicitly. There will be no silent local or legacy fallback.

The actual Schema 3.0 path is singular: `/session/event`, not
`/session/events`.

## 2. Verified current state

Evidence was collected on 30 July 2026.

### Live Student Model API

[`https://nablix.ai:8080/openapi.json`](https://nablix.ai:8080/openapi.json)
currently identifies itself as `AI Math Tutor API` version `0.1.0` and exposes
both:

- `POST /interaction`, tagged `student-model`
- `POST /session/event`, tagged `session-engine`

The live `/session/event` request schema only documents four required fields:
`request_id`, `event_type`, `topic_id`, and `student_id`. It allows arbitrary
additional properties, so OpenAPI does not tell a caller which fields each
event requires. The live health response is only `{"status":"ok"}`; it does not
identify the deployed commit. Therefore, the OpenAPI surface is verified live,
but its source revision cannot be proven from `/health`.

### Current Student Model `master`

The audited GitHub revision is
[`33987c0`](https://github.com/Nablix-Labs/mathtutor-student/commit/33987c0daf205876190ae87f6a05e1ddcc7a9b80).
It already registers Schema 3.0 handlers for session opening, diagnostic,
orientation, guided and independent attempts, escalation, resume, and review.

It does **not** register:

- `HINT_REQUESTED`
- `PARTIAL_ATTEMPT`

The legacy `/interaction` request still owns `hint_level_used`, legacy mastery
counters, the append-only mastery ledger, and persistent misconception
tracking. The Schema 3.0 `JourneyRepository` writes `journey_state`,
`current_phase_v3`, and `active_session_id`, while intentionally leaving the
legacy counter and enum columns unchanged.

This creates a removal blocker: the current progress summary still reads
legacy `MasteryProgress` columns such as `attempt_count`, `correct_count`,
`mastery_status`, `hint_dependency_score`, `error_counts`, and
`intervention_required`. Those values would become stale after `/interaction`
is removed unless Schema 3.0 updates or replaces them.

Duplicate Schema requests currently return `409 DUPLICATE_REQUEST`. That is not
safe for an ambiguous network failure: if the Student Model commits an event
but the response is lost, Nablix retries the same `request_id` and receives a
failure instead of the committed response.

### Current Nablix backend

The audited local backend revision is `0a14a0e` on branch
`deva/RAG-wiring`, with uncommitted local work present.

The Student Model adapter has two write methods:

- `update_from_event(...)` posts to Student Model `/interaction`.
- `send_session_event(...)` posts to Student Model `/session/event`.

Production callers of `update_from_event(...)` are:

- Legacy evaluated tutor events in `interaction_service.py`
- Every explicit `/hint/request` in `hint_service.py`
- Eligible standalone canvas attempts in `canvas_service.py`

Schema-managed guided and independent answer submissions already use
`/session/event`. Session start, diagnostic completion, orientation start, and
orientation completion also use `/session/event`.

Remaining wiring gaps include:

- An `initial_phase` supplied at session start creates a legacy session and
  bypasses Schema 3.0.
- Explicit hints still retrieve/generate content through the tutor pipeline and
  then record `HINT_REQUESTED` through Student Model `/interaction`.
- Standalone canvas attempts still persist learner updates through
  `/interaction`.
- `PARTIALLY_CORRECT` is not emitted as a Schema 3.0 event.
- `/session/end` generates a local review and ends only the process-local Nablix
  session; it does not send `REVIEW_COMPLETED`.
- Nablix models do not yet cover every handler available on current Student
  Model `master`, including `FRESH_INDEPENDENT_QUESTION_REQUESTED` and
  `REVIEW_COMPLETED`.

## 3. Target request flow and event contract

### Sole-write-gateway invariant

```text
Frontend action
    -> Nablix public route
    -> local validation/evaluation
    -> Student Model POST /session/event
    -> validate authoritative Schema 3.0 response
    -> commit/update Nablix session projection
    -> return to frontend
```

Nablix must not update learner-facing phase, hint count, attempt progression, or
completion state before the required Student Model event succeeds.

The Student Model response remains authoritative:

- `journey_state`: durable learner and phase state
- `phase_payload`: questions, orientation, support, rescue, or review content
- `event_result`: attempt, skill, and misconception evidence
- `routing`: the next action and transition reason
- `status`: success, intervention, warnings, and operational errors

### Required contract characteristics

1. **Typed events:** OpenAPI must expose a discriminated union keyed by
   `event_type`, with required fields for each event.
2. **Stable identity:** Nablix forwards the caller's Bearer token unchanged.
   Student Model verifies the token, resolves JWT `sub` to the owning user, and
   confirms that the request's Student Model student code belongs to that user.
   Events use a string topic code resolvable by Student Model. Missing/invalid
   authentication returns 401; ownership mismatch returns 403.
3. **Stable idempotency:** one deterministic `request_id` per logical event.
   Retrying it returns the original successful envelope with a duplicate/replay
   indication; it must not return a terminal `409`.
4. **Strict validation:** missing, invalid, or out-of-order event fields fail
   before learner state changes.
5. **Atomicity:** event reservation, journey mutation, mastery projection,
   history/misconception recording, and stored response envelope commit in one
   transaction.
6. **No content competition:** if `phase_payload` supplies a hint, visual cue,
   scaffold, question, rescue, or review, Nablix uses that content instead of
   independently selecting a conflicting version.
7. **Explicit failure:** authentication, mapping, validation, and downstream
   failures surface with actionable status and response context. There is no
   `/interaction` or mock fallback.

### Event catalogue

Every event requires non-empty string `request_id`, literal `event_type`,
non-empty string topic code `topic_id`, non-empty Student Model student code
`student_id`, and an RFC 3339 UTC `timestamp`. Lists marked `[]` must be
non-empty unless explicitly described as prior-use history. `input_source` is
one of `TEXT`, `VOICE`, or `CANVAS`; `support_used` is one of `NONE`, `HINT`,
`VISUAL_CUE`, `SCAFFOLD`, `PARALLEL_EXAMPLE`, or `TUTOR_SOLVED`.
Event-specific requirements are:

| Event | Required event-specific fields |
|---|---|
| `SESSION_OPENED` | None; Student Model loads an existing journey or creates the diagnostic journey |
| `DIAGNOSTIC_QUESTION_SET_REQUESTED` | None; retained only for an explicit routed content request |
| `DIAGNOSTIC_COMPLETED` | `micro_skill_results[]` containing `micro_skill_id` and `result` |
| `WORKED_EXAMPLE_REQUESTED` | `target_micro_skill_ids[]` |
| `ORIENTATION_COMPLETED` | `target_micro_skill_ids[]` |
| `GUIDED_QUESTION_SET_REQUESTED` | `target_micro_skill_ids[]` |
| `CORRECT_ATTEMPT` | `question_id`, `micro_skill_ids[]`, `student_response`, `input_source`, `support_used` |
| `PARTIAL_ATTEMPT` | `question_id`, `micro_skill_ids[]`, `student_response`, `error_code`, `input_source`, `support_used` |
| `INCORRECT_ATTEMPT` | `question_id`, `micro_skill_ids[]`, `student_response`, `error_code`, `input_source`, `support_used` |
| `HINT_REQUESTED` | `question_id`, `requested_hint_level`, `input_source`; Student Model derives micro-skills from the authoritative question |
| `GUIDED_SUPPORT_ESCALATION_REQUIRED` | `question_id`, `micro_skill_id` |
| `MAXIMUM_GUIDED_SUPPORT_PARALLEL` | `question_id`, `micro_skill_id`; returns a parallel worked example |
| `MAXIMUM_GUIDED_SUPPORT_REQUIRED` | `question_id`, `micro_skill_id`; returns the tutor-solved rescue |
| `GUIDED_PHASE_COMPLETED` | `completed_micro_skill_ids[]` |
| `INDEPENDENT_QUESTION_SET_REQUESTED` | `phase2_repair_results[]`, `used_question_ids[]` |
| `INDEPENDENT_RETRY_COMPLETED` | `question_id`, `micro_skill_ids[]`, `student_response`, `independent_success`, `input_source`, `support_used="NONE"`; `error_code` when unsuccessful |
| `FRESH_INDEPENDENT_QUESTION_REQUESTED` | `target_micro_skill_ids[]`, `used_question_ids[]` |
| `REVIEW_COMPLETED` | None beyond the common fields |

`SESSION_OPENED` loads the durable Student Model journey and returns resume
routing for an existing learner. Saravanan must deprecate the external
`SESSION_RESUMED` handler that accepts caller-supplied `saved_journey`, confirm
it has no consumer, and remove it. Nablix must never submit saved journey state.

Non-graded acknowledgements, clarifications, partial/final transcript transport,
duplicate/stale turns, and technical failures do not create Student Model
events. Operational telemetry for those cases belongs outside the learner-state
event stream.

### Deterministic request IDs and replays

Request IDs are produced once and reused unchanged for every retry:

| Logical action | Request ID |
|---|---|
| Open/resume invocation | `{session_id}:SESSION_OPENED:{open_operation_id}` |
| Accepted tutor or canvas turn | `{session_id}:{source_turn_id}:{event_type}` |
| Explicit hint | `{session_id}:{question_id}:HINT_REQUESTED:{requested_hint_level}` |
| Phase/content transition | `{session_id}:{event_type}:{expected_journey_version}` |
| Review completion | `{session_id}:REVIEW_COMPLETED` |

`open_operation_id` is minted once for each start/resume invocation and reused
only for its retries, so a later resume cannot replay an old opening snapshot.
For accepted turns, Nablix owns `source_turn_id`: text uses the required client
turn ID, voice uses the server-generated final-transcript turn ID, and canvas
uses its submission ID. Nablix stores that ID before the downstream call and
reuses it for transport retries.

The same retry reuses the original timestamp and body. Student Model stores the
validated request as JSONB with the committed envelope and uses JSONB equality
to compare retries. An identical retry returns HTTP 200, the original envelope,
and `Idempotent-Replayed: true`. A different body under the same ID returns 409
`IDEMPOTENCY_KEY_REUSED`. Concurrent identical requests wait for or read the
single committed outcome. Idempotency records do not expire before the learner
event is purged under the applicable retention policy.

“One transaction” means one Student Model database transaction covering event
reservation, journey mutation, read-model projection, history and
misconception writes, and the stored response. It does not span Nablix and
Student Model.

All new mutating events advance journey version by exactly one. A replay and a
read-only `SESSION_OPENED` for an existing journey leave it unchanged; creating
a new journey begins at version 1. Every
content-bearing event stores its complete response as `last_event_response`.
`SESSION_OPENED` returns that exact last envelope when resuming support/rescue,
or reconstructs only when no stored envelope exists.

The common error envelope is
`{"error_code":"...","message":"...","field":null,"request_id":null}`.
Use 401 for authentication, 403 for ownership, 404 for unknown
student/topic/content, 409 for idempotency or invalid journey sequence, 422 for
schema/unsupported events, and 5xx for operational failures.

### Minimum new event

`HINT_REQUESTED` is required for explicit hint-button use:

```json
{
  "request_id": "SESSION123:Q-T02-010:HINT_REQUESTED:1",
  "event_type": "HINT_REQUESTED",
  "topic_id": "ALG-ORI-02",
  "student_id": "ST001",
  "timestamp": "2026-07-30T12:00:00Z",
  "question_id": "Q-T02-010",
  "requested_hint_level": 1,
  "input_source": "TEXT"
}
```

The response must advance the support cursor, record hint usage, and return the
selected seeded hint in `phase_payload.support_to_serve`. For example,
`HINT-T02-FRAC-COEFF-L1` currently contains “Which number is multiplying x?”
in the Student Model content data.

`requested_hint_level` is an integer from 1 through 3 and must equal the next
level in the durable support cursor. Student Model derives the micro-skills from
`question_id`; it does not trust a caller-supplied mapping. A new successful
hint advances journey version by one. A replay leaves it unchanged.

The response requires:

```json
{
  "phase_payload": {
    "phase": "PHASE_2_GUIDED_LEARNING",
    "payload_type": "SUPPORT_AND_RETRY",
    "support_to_serve": {
      "support_type": "HINT_AND_VISUAL_CUE",
      "items": [
        {
          "content_type": "HINT",
          "content_id": "HINT-T02-FRAC-COEFF-L1",
          "content": "Which number is multiplying x?",
          "level": 1
        }
      ],
      "retry_same_question": true
    }
  },
  "routing": {
    "next_action": "DELIVER_SUPPORT_AND_RETRY"
  }
}
```

The `items` list may additionally contain the catalog’s matching visual cue,
but must contain exactly one selected hint. Missing hint content returns 409
`HINT_CONTENT_UNAVAILABLE`; a request beyond level 3 returns 409
`HINT_SEQUENCE_EXHAUSTED`. Neither failure mutates learner state.

### Partial attempts

Add `PARTIAL_ATTEMPT`. It records partial evidence and the detected error,
without counting the skill as completed or independently verified. In Guided
Learning it keeps the question active and returns the next support. In
Independent Practice it records failed verification and returns the same
rescue/retry routing class as an unsuccessful independent attempt while
preserving `PARTIAL` in the evidence. Nablix must not normalize a partial result
to correct or incorrect.

## 4. Saravanan: Student Model changes

Saravanan owns the following changes in
[`Nablix-Labs/mathtutor-student`](https://github.com/Nablix-Labs/mathtutor-student):

### SM-1 — Publish typed Schema 3.0 request models

- Replace the generic `SessionEventIn` plus unrestricted extras with typed
  per-event models and a discriminated union.
- Keep common fields in one base model.
- Make event-specific fields required where handlers currently assume them,
  including `question_id`, `micro_skill_ids`, `student_response`,
  `error_code`, support fields, diagnostic results, and completion fields.
- Regenerate OpenAPI so consumers can implement against the real contract.

### SM-2 — Add explicit hint handling

- Add and register `HINT_REQUESTED`.
- Validate phase, current question, micro-skill ownership, and requested level.
- Reuse the existing question `support_catalog` and guided-support cursor.
- Return the authoritative hint through `support_to_serve`.
- Update highest support used, hint dependency evidence, last activity, and
  journey version.
- Store the exact response envelope for resume.
- Do not treat a normal hint click as
  `GUIDED_SUPPORT_ESCALATION_REQUIRED`; escalation remains a separate event.

### SM-3 — Resolve partial-attempt behavior

- Implement and register `PARTIAL_ATTEMPT`.
- Ensure the response contains the appropriate support, attempt evidence,
  misconception updates, routing, and journey mutation.

### SM-4 — Preserve all state previously written by `/interaction`

For every graded or hint-assisted Schema event:

- Keep the Schema 3.0 journey authoritative.
- Maintain any projections still required by progress, login, admin, and
  reporting APIs.
- Preserve the existing append-only mastery history for every committed graded
  Schema event.
- Persist misconception records, not only misconception counts nested in
  `journey_state`.
- Produce or project `attempt_count`, `correct_count`, mastery,
  hint-dependency, error counts, and intervention state needed by
  `/student/{student_id}/progress/summary`.

The preferred outcome is one authoritative Schema state plus deliberate
read-model projections. Do not run the legacy mastery engine as a second,
independent decision-maker.

Projection rules:

- `attempt_count`: committed graded attempt events, including independent
  retries; exclude hint requests and non-graded transport.
- `correct_count`: committed `CORRECT_ATTEMPT` events plus successful
  independent retries.
- Mastery, phase, and intervention: project the committed Schema journey and
  status.
- `hint_dependency_score`: graded attempts whose `support_used` is not `NONE`,
  divided by graded attempts; zero when there are no graded attempts.
- `error_counts`: committed partial/incorrect errors grouped by canonical
  `error_code`.
- Mastery history: append once per committed graded event.
- Misconception records: update from committed partial/incorrect
  `misconception_updates`.

Before cutover, run a database migration that preserves existing legacy
aggregates as the baseline and initializes missing Schema projections. From the
cutover event onward, only Schema handlers advance them. The migration reports
rows it cannot reconcile instead of silently resetting their history.

The migration adds `schema3_projection_started_at` and
`schema3_projection_version` to each projected learner/topic row. Under a
database lock, it:

1. Copies the existing legacy aggregate values as the cutover baseline.
2. Projects current mastery, phase, and intervention from `journey_state` when
   present.
3. Records the current journey version as `schema3_projection_version`.
4. Writes unreconciled student/topic IDs and reasons to a migration report and
   aborts cutover while that report is non-empty.

The migration is rerunnable: rows with the same recorded version are unchanged.
Each later Schema event applies its delta only when its prior journey version
matches `schema3_projection_version`, then advances both versions in the same
transaction.

### SM-5 — Make retries replay-safe

- Store the successful `SessionEventOut` envelope against `request_id`.
- Implement the HTTP 200 replay and canonical-payload rules defined above.
- Keep the event reservation and state mutation in the same transaction.
- Document the replay header in OpenAPI.

### SM-6 — Complete lifecycle parity

- Retain and document the current handlers for `SESSION_OPENED`,
  `REVIEW_COMPLETED`, `FRESH_INDEPENDENT_QUESTION_REQUESTED`, and
  maximum-support paths.
- Use `REVIEW_COMPLETED` for the explicit successful `/session/end` workflow;
  do not add `SESSION_ENDED`.
- Intentional logout must remain resumable and must not be interpreted as
  completion.
- Add a build revision to `/health` or deployment metadata so live verification
  can identify the running source.

### SM-7 — Deprecate and remove `/interaction`

- First mark `/interaction` deprecated in OpenAPI and operational logs.
- Confirm no Nablix environment calls it.
- Remove the router registration, `InteractionEventIn`,
  `StudentModelStateOut`, and route-only tests/code.
- Retain shared repositories or tables only when used by Schema 3.0,
  reporting, migration, or retention requirements.
- After removal, live OpenAPI must not contain `/interaction`.

## 5. Chirudeva: Nablix backend wiring changes

Chirudeva owns the following changes in the current `nablix-backend`:

### NB-1 — Add the complete typed event models

- Add typed Nablix request models for every event Nablix emits, including
  `HINT_REQUESTED`, `PARTIAL_ATTEMPT`, fresh-question when routed, and
  completion. Do not duplicate unused Student Model-only variants.
- Keep one adapter method, `send_session_event(...)`.
- Validate `SessionEventOut` identity, status, and event-specific payload before
  changing the local session.

Response validation requires:

- Response `request_id`, journey `student_id`, and journey `topic_id` match the
  request.
- `schema_version == "3.0"`, `status.success == true`, and no operational error.
- Journey version is unchanged for a replay/read-only open or advances as the
  event catalogue specifies.
- Content-producing events return the required `phase_payload` type: question
  set, orientation bundle, support, rescue, or review.
- Attempt events return `event_result.attempt` and the expected routing action.
- Applying a response locally is idempotent by `request_id`: local attempt and
  history records carry `student_model_request_id` and are upserted/deduplicated
  on that key. Phase, hint, question, and counters are set from the
  authoritative response rather than incremented from the replay.

### NB-2 — Migrate explicit hints

- Change `/hint/request` to send `HINT_REQUESTED` to Student Model
  `/session/event`.
- Use `phase_payload.support_to_serve` as the hint source.
- Set local hint/session projections from the returned authoritative level only
  after success; do not increment them again when handling a replay.
- Preserve the Student Model hint text exactly in the displayed/stored `hint`
  field. Pronunciation formatting may occur only in a separate voice field and
  must not change the displayed mathematical content.
- Remove the `update_from_event(HINT_REQUESTED)` call.

### NB-3 — Migrate all tutor turns that currently write `/interaction`

- Map correct, incorrect, and partial evaluated events to their Schema 3.0
  equivalents.
- Do not send legacy `HINT_USED` or `SESSION_STARTED`. Send no learner-state
  event for the explicitly listed non-graded/transport cases.
- Text and voice must share this same mapping because voice is a transport into
  the normal tutor pipeline.
- Preserve one deterministic event ID per accepted turn.

### NB-4 — Migrate canvas learner updates

- Keep `/canvas/submit` as the OCR/canvas-facing Nablix route.
- For `STANDALONE_ATTEMPT`, send the evaluated result through the same Schema
  correct/incorrect/partial event used for text, with
  `input_source="CANVAS"`.
- Include normalized student response and error code already produced by canvas
  review.
- Do not create a Student Model `CANVAS_SUBMITTED` event unless canvas
  submission itself has independent learner-state semantics.

### NB-5 — Remove the legacy session fork

- Stop `initial_phase` from creating `_start_legacy_session(...)` in production.
- Remove `initial_phase` from the production request contract. During the
  coordinated client rollout, reject it with HTTP 422 rather than ignoring or
  translating it.
- Chirudeva owns the corresponding Numera UI request change or names the
  frontend owner before enabling the rejection.
- Start and resume through `SESSION_OPENED`; let Student Model routing select
  the phase.
- Mint one `open_operation_id` at the start of each Nablix invocation and reuse
  it for that invocation's downstream retries. A later resume mints a new ID.
- Remove `NABLIX_STUDENT_MODEL_SESSION_OPENED_ENABLED` after the deployed
  `SESSION_OPENED` handler is verified; a permanent feature switch would retain
  two behavior paths.
- Remove the integer `student_model_topic_ids` mapping after all writes use
  Schema topic codes. Keep only the verified concept-to-topic-code mapping.

### NB-6 — Wire resume and completion

- Use durable Student Model login/journey state to restore sessions; do not infer
  resume from process-local Nablix history.
- Send `SESSION_OPENED`; Student Model determines new versus resumable from its
  durable journey and returns the appropriate routing.
- Add Bearer authentication to the Nablix completion path.
- Student Model owns factual `review_summary`, mastery, and next-topic routing.
  The final successful independent attempt that reaches mastery must return the
  summary in `phase_payload.review_summary`; Nablix stores that envelope.
- Nablix may generate presentation wording grounded only in that stored summary
  through the existing review-generation route.
- The client displays the review, then its explicit `/session/end` action sends
  `REVIEW_COMPLETED`. On success Nablix applies next-topic routing and marks the
  local session ended.
- Do not send completion on logout.

### NB-7 — Make Student Model failure authoritative

- Require the authenticated access token on every Nablix route that emits a
  Student Model event and forward it unchanged; completion is the currently
  missing route.
- Reuse the existing bounded retry helper with the same deterministic
  `request_id`.
- Treat a valid replay response as success.
- On exhausted transport, authentication, mapping, validation, or Student Model
  operational failure, return an explicit error and leave the Nablix learner
  transition uncommitted.
- Log structured endpoint, request ID, event type, student code, topic code,
  status, and response body. Never log the Bearer token.

### NB-8 — Remove the legacy client surface

After all callers are migrated:

- Delete `update_from_event(...)` and its protocol declaration.
- Delete `/interaction` payload construction from the Student Model adapter.
- Delete `StudentModelEvent`/`StudentModelResult` fields used only by the legacy
  Student Model contract.
- Remove `student_model_topic_ids` and legacy response-to-phase transition code.
- Keep the Nablix public `/interaction` tutor route.

## 6. Event migration matrix

| Nablix action | Current Student Model write | Required Schema 3.0 event | Owner/gap |
|---|---|---|---|
| Start normal session | `/session/event` with diagnostic request or optional `SESSION_OPENED` | `SESSION_OPENED` | Chirudeva enables unconditionally after live verification |
| Resume incomplete journey | Incomplete/local restoration | `SESSION_OPENED`, returning resume routing from durable state | Chirudeva wiring |
| Request diagnostic set | `/session/event` | `DIAGNOSTIC_QUESTION_SET_REQUESTED` when explicitly required by routing | Already supported |
| Complete diagnostic | `/session/event` | `DIAGNOSTIC_COMPLETED` | Already supported |
| Request orientation content | `/session/event` | `WORKED_EXAMPLE_REQUESTED` | Already supported |
| Complete orientation | `/session/event` | `ORIENTATION_COMPLETED` | Already supported |
| Request guided set | `/session/event` | `GUIDED_QUESTION_SET_REQUESTED` | Already supported |
| Correct guided/independent answer | Mixed: Schema or legacy `/interaction` | `CORRECT_ATTEMPT` | Remove legacy branch |
| Incorrect guided/independent answer | Mixed: Schema or legacy `/interaction` | `INCORRECT_ATTEMPT` | Remove legacy branch |
| Partially correct answer | Legacy `/interaction` or no Schema event | `PARTIAL_ATTEMPT` | New Saravanan handler and Chirudeva wiring |
| Explicit hint button | `/interaction` with `HINT_REQUESTED` | `HINT_REQUESTED` | New Saravanan handler and Chirudeva wiring |
| Confusion/support escalation | `/session/event` conditionally | `GUIDED_SUPPORT_ESCALATION_REQUIRED` | Already supported |
| Maximum support | `/session/event` conditionally | `MAXIMUM_GUIDED_SUPPORT_PARALLEL` for a parallel example; `MAXIMUM_GUIDED_SUPPORT_REQUIRED` for tutor-solved rescue | Align Nablix models and transitions |
| Standalone canvas attempt | `/interaction` | Correct/incorrect/partial attempt with `input_source="CANVAS"` | Chirudeva wiring |
| Voice answer | Normal tutor pipeline, then mixed write | Same attempt event with `input_source="VOICE"` | Remove legacy branch |
| Fresh independent question | Incomplete coverage | `FRESH_INDEPENDENT_QUESTION_REQUESTED` | Call only when routing explicitly returns `REQUEST_FRESH_INDEPENDENT_QUESTION`; otherwise no Nablix caller |
| Independent retry completion | `/session/event` | `INDEPENDENT_RETRY_COMPLETED` | Already supported |
| Guided phase completion | `/session/event` | `GUIDED_PHASE_COMPLETED` | Already supported |
| End/review completion | Local only | `REVIEW_COMPLETED` | Chirudeva wiring |
| Logout | No completion event | No completion event; retain resumable journey | Preserve behavior |

## 7. Delivery sequence and ownership

| Order | Deliverable | Owner | Dependency |
|---:|---|---|---|
| 1 | Freeze the typed event catalogue and the contract in this document | Saravanan + Chirudeva | None |
| 2 | Add typed OpenAPI models, `HINT_REQUESTED`, retry replay, and state/reporting parity | Saravanan | Step 1 |
| 3 | Deploy Student Model and verify live OpenAPI plus authenticated event calls | Saravanan | Step 2 |
| 4 | Add Nablix typed models and migrate hint, canvas, legacy tutor, resume, and completion paths | Chirudeva | Step 3 contract |
| 5 | Remove legacy session start and integer topic mapping | Chirudeva | Step 4 |
| 6 | Run end-to-end journey and failure/retry checks against the deployed Student Model | Both | Steps 3–5 |
| 7 | Prove zero `/interaction` consumers: source/config evidence from Chirudeva and access-log evidence from Saravanan | Both | Step 6 |
| 8 | Remove Student Model `/interaction` and deploy | Saravanan | Step 7 |
| 9 | Confirm live OpenAPI, logs, progress, resume, and review after removal | Both | Step 8 |

Do not remove `/interaction` from Student Model before Step 7. Do not retain
dual writes as a steady state: they can double-count attempts and allow Schema
and legacy mastery decisions to diverge.

Step 7 requires a jointly signed environment inventory. For local development
and CI, record source/config checks and passing integration tests. For Demo-1,
production, and every active deployed preview/staging environment, record the
deployed Nablix revision and Student Model URL, prove the code/config contains
no legacy client, and have Saravanan inspect Student Model access logs for
legacy calls for seven days or one full scheduled demo/release cycle, whichever
is longer.

Keep the last pre-removal Student Model deployment artifact available for that
same observation window. Roll back if Schema writes cause lost/double-counted
attempts, incorrect routing/content, broken resume/progress, or sustained
authentication/5xx failures. Rollback is an incident action, not permission to
retain dual writes.

## 8. Acceptance criteria and removal gate

The migration is complete only when all checks below pass.

### Contract and live API

- [ ] Live OpenAPI documents typed request variants for every supported event.
- [ ] Live OpenAPI no longer contains Student Model `/interaction`.
- [ ] Live `/health` or deployment metadata identifies the deployed revision.
- [ ] Unknown event types and missing event-specific fields fail before mutation.

### Nablix call paths

- [ ] `rg "update_from_event|student_model_url.*interaction|/interaction"`
  finds no production Student Model client call. The expected remaining
  `/interaction` references are only the Nablix tutor-facing route, frontend
  tutor calls, tests for that public route, or historical documentation.
- [ ] Hint, text, voice, and standalone canvas learner updates all use
  `/session/event`.
- [ ] `initial_phase` cannot open a production legacy session.
- [ ] Session completion uses `REVIEW_COMPLETED`; logout does not.
- [ ] No production setting can silently select a legacy or mock Student Model
  write path.

### Behavioral parity

- [ ] An explicit hint request returns the seeded hint selected by Student
  Model and advances the support cursor exactly once; the corresponding graded
  attempt updates hint dependency from that recorded support.
- [ ] Correct, incorrect, partial, canvas, and voice attempts update journey,
  mastery, skill, and misconception evidence as specified.
- [ ] Progress summary values remain correct without `/interaction`.
- [ ] The projection/backfill migration preserves existing learner aggregates
  and reports every unreconciled row.
- [ ] Login/resume returns the exact last support/question payload and does not
  depend on a Nablix process remaining alive.
- [ ] Review/completion produces the expected summary and next-topic routing.

### Reliability and security

- [ ] Retrying the same committed `request_id` returns the original response and
  does not apply the event twice.
- [ ] Reusing a `request_id` with a different payload is rejected.
- [ ] A failed Student Model call leaves the corresponding Nablix learner
  transition uncommitted.
- [ ] Student ownership, topic-code resolution, and Bearer verification pass for
  every migrated route.
- [ ] Logs provide event/request/status context without tokens or credentials.
- [ ] Every active environment has a recorded revision/config check and the
  required zero-legacy-call observation window.

### Minimum end-to-end journey

Saravanan provisions a resettable migration-test learner and token linked to
the seeded topic containing question `Q-T02-010` and hint
`HINT-T02-FRAC-COEFF-L1`. The test records request IDs, response versions,
routing, and payloads. Each new mutating event must advance the version once;
replays must not. Simulate a lost response with a test proxy that drops the
first committed HTTP 200 before Nablix receives it.

Run one authenticated real-service journey covering:

1. Login and `SESSION_OPENED`
2. Diagnostic request and completion
3. Orientation request and completion
4. Guided incorrect attempt returning seeded level-1 hint
   `HINT-T02-FRAC-COEFF-L1`
5. Explicit `HINT_REQUESTED` for the next durable level, returning
   `HINT-T02-FRAC-COEFF-L2`; drop its first committed response and verify the
   same-ID replay
6. Guided correct attempt and phase completion
7. Independent incorrect attempt and retry
8. One voice attempt while the learning phase is active
9. One standalone canvas attempt while the learning phase is active
10. Independent correct attempts until the mastery response contains
    `phase_payload.review_summary`
11. Logout and resume without completion
12. Review completion

Step 4 requires content ID `HINT-T02-FRAC-COEFF-L1`, level 1, and text “Which
number is multiplying x?”. Step 5 requires content ID
`HINT-T02-FRAC-COEFF-L2`, level 2, and text “A fraction can be a coefficient.
Write the fraction immediately before the letter.”
The progress assertion compares attempt, correct, hint-dependency, error, and
mastery projections to the formulas in SM-4. The resume assertion compares the
returned `last_event_response` to the last pre-logout content envelope.

Focused repository tests are necessary, but they do not replace this deployed
journey.

## 9. Evidence and source versions

- Live OpenAPI:
  [`https://nablix.ai:8080/openapi.json`](https://nablix.ai:8080/openapi.json)
  retrieved 30 July 2026; audited response SHA-256
  `08ed486b1a2830477c8830851ec06185496c8bd232506605e35d2622d425f58f`.
- Live interactive docs:
  [`https://nablix.ai:8080/docs`](https://nablix.ai:8080/docs).
- Student Model source:
  [`Nablix-Labs/mathtutor-student@33987c0`](https://github.com/Nablix-Labs/mathtutor-student/tree/33987c0daf205876190ae87f6a05e1ddcc7a9b80).
- Student Model handler registry:
  [`app/services/session_handlers.py`](https://github.com/Nablix-Labs/mathtutor-student/blob/33987c0daf205876190ae87f6a05e1ddcc7a9b80/app/services/session_handlers.py#L751-L768).
- Student Model generic live request model:
  [`app/schemas/session.py`](https://github.com/Nablix-Labs/mathtutor-student/blob/33987c0daf205876190ae87f6a05e1ddcc7a9b80/app/schemas/session.py#L14-L22).
- Legacy hint field:
  [`app/schemas/events.py`](https://github.com/Nablix-Labs/mathtutor-student/blob/33987c0daf205876190ae87f6a05e1ddcc7a9b80/app/schemas/events.py#L6-L22).
- Seeded hint and scaffold content:
  [`nablix_content_data.sql`](https://github.com/Nablix-Labs/mathtutor-student/blob/33987c0daf205876190ae87f6a05e1ddcc7a9b80/nablix_content_data.sql#L141).
- Nablix backend source: local `nablix-backend` commit `0a14a0e`, branch
  `deva/RAG-wiring`, including uncommitted changes present during this audit.
- Key Nablix files:
  `app/adapters/student_model.py`, `app/services/interaction_service.py`,
  `app/services/hint_service.py`, `app/services/canvas_service.py`,
  `app/services/session_service.py`, and
  `app/models/student_model_session.py`.

This specification is a source and contract audit. It does not claim observed
production call volume or identify the live deployment commit where the
service does not expose one.

The GitHub repository is private; pinned source links require Nablix
organization access.
