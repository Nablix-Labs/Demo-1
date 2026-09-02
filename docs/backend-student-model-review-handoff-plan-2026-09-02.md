# Backend and Student Model review-handoff plan

Status: agreed design; implementation has not started.

## Scope

Only the Tutor Backend and Student Model contract changes below are in scope.

- No frontend code changes in this implementation.
- T01.M6 micro-skill data has now been updated. Content authoring is not part of this change set; only the end-to-end transition verification uses the updated data.
- No new service, queue, database table, or third-party dependency.
- Existing session JSON persistence is the durable store for the new small receipt fields.

## Root cause model

The observed “refresh, answer again, then Review appears” behavior is not one fault.

1. The final independent answer can be accepted and Student Model can commit `REVIEW` before backend Phase 4 materialization succeeds. The backend currently returns the accepted turn with a null review after a materialization failure; a later `GET /session/{id}` retries materialization. This can make a refresh look as though it performed the transition.
2. The legacy `SESSION_RESUMED` flow accepts a saved journey and its Student Model phase selector has no `REVIEW` branch. It can choose Phase 3 (or default to Phase 2) even for a completed Review journey.
3. `REVIEW_COMPLETED` already receives Student Model's `START_NEXT_TOPIC`, next topic, and entry phase. Backend projects them but leaves the source session as `REVIEW`; the next session is not started by the completion contract.
4. Duplicate-turn replay is partly process-local. After a restart, a persisted `last_processed_turn_id` can outlive the in-memory response cache.
5. Old snapshots without `independent_attempts` can prevent 8001 from starting. This is an availability/rehydration failure, not a Student Model transition decision. The earlier T01.M6 fresh-content gap is no longer the working explanation because its micro-skill data has been updated.
6. `last_student_model` and `student_model_state` can contradict one another. Only the latter represents the authoritative Schema 3 Student Model journey.

## Agreed authority and lifecycle contract

Student Model is the sole authority for topic, phase, mastery, and next-topic selection. Backend validates the returned Schema 3 event, persists it, creates presentation state, and relays a typed handoff. It never chooses a next topic, entry phase, or mastery outcome.

```text
final Phase 3 evidence
  -> Student Model: REVIEW + REVIEW_SUMMARY
  -> Backend: persist authoritative event and FINALIZED_TURN receipt
  -> Backend: Review Materialization PENDING
  -> Backend: up to two generation/persistence attempts
  -> READY, or PENDING for read retry (never return to Phase 3)

REVIEW_COMPLETED
  -> Student Model: START_NEXT_TOPIC + topic_id + entry_phase
  -> Backend: validate, persist handoff, atomically end old session
  -> Caller: immediately POST /session/start with that exact handoff
```

`Review Materialization` is backend presentation state (`PENDING` or `READY`). It does not alter the authoritative Student Model journey.

## Implementation plan

### 1. Make the post-review decision explicit in Student Model

In `mathtutor-student`:

- Keep `handle_review_completed()` as the sole creator of the next-topic decision.
- Make the response contract for `REVIEW_COMPLETED` require `next_action=START_NEXT_TOPIC`, a non-empty `next_topic_id`, and `next_topic_entry_phase` when another topic exists.
- Preserve the completed source journey as `topic_status=COMPLETED`, `mastery_status=MASTERED`, `current_phase=REVIEW`, and read-only review history. Starting the next topic must use the returned next topic, not mutate the completed journey back into a learning phase.
- Retire `SESSION_RESUMED` from the Student Model event dispatch and delete its snapshot-driven phase selection path. `SESSION_OPENED` remains the only rehydration event and reads the persisted Student Model journey.

Acceptance: a completed topic emits one deterministic next-topic handoff; reopening the completed source topic does not create an in-progress Phase 2 or Phase 3 journey.

### 2. Relay the handoff without inventing a decision

In `nablix-backend`:

- Add a typed public `next_topic_handoff` projected solely from the authoritative `REVIEW_COMPLETED` event: source session ID, Student Model request ID, topic ID, and entry phase.
- In `complete_review()`, reject a malformed `REVIEW_COMPLETED` response that lacks the required handoff rather than calculating a fallback topic.
- Persist the handoff with the old session and atomically mark that old session `ended` only after the Student Model completion response is validated and saved.
- Preserve idempotency: repeating the same review-completion turn returns the already-persisted completed session and identical handoff.

Acceptance: backend never calculates curriculum order; one successful completion returns one persisted handoff and an ended source session.

### 3. Retire the competing resume mutation

In backend and Student Model:

- Deprecate `POST /session/{id}/resume` with a stable, explicit retirement response for one compatibility release; remove it after callers are confirmed absent.
- Remove `SessionResumedEvent`, `saved_journey`, `phase_for_saved`, and the snapshot-mutation handler after the compatibility period.
- Continue using `GET /session/{id}` only to load a live backend session.
- When the backend has lost its process/session state, create a new in-process record by calling `SESSION_OPENED`; Student Model reads its own stored journey.

Acceptance: no request payload can write or select a journey phase. Review rehydration can never resolve to Phase 2 or Phase 3 merely because those historical blocks exist.

### 4. Separate an accepted Review transition from review materialization

In backend session wiring:

- Add a persisted `review_materialization_state` with `PENDING` and `READY` values; default it safely for legacy sessions.
- When Student Model returns `REVIEW`, persist the authoritative event and `PENDING` before calling Phase 4 generation.
- Make two total bounded attempts to generate and persist Phase 4, with structured warning logs on each failure.
- On success, atomically persist the generated review and `READY`.
- On exhausted attempts, retain `REVIEW` and `PENDING`; `GET /session/{id}` retries only review materialization. It must never resend a Student Model answer event.
- Return the accepted final turn with explicit materialization state, rather than a structurally successful-but-ambiguous null review.

Acceptance: a transient Phase 4 failure produces `REVIEW + PENDING`; a later read can produce `READY`; Student Model journey version and `CORRECT_ATTEMPT` count do not change during that retry.

### 5. Make final independent turns durable and idempotent

In backend persistence/wiring:

- Add a small persisted final-turn receipt to `SessionRecord`: accepted turn ID, request/evidence fingerprint, Student Model request ID, resulting journey version, phase, and review materialization state.
- On an exact duplicate final turn after a process restart, return the receipt-derived terminal response without OCR, tutor evaluation, or a second Student Model event.
- On the same turn ID with changed evidence, return the existing 409 conflict.
- Keep the current in-memory response cache as a fast path only; it is no longer correctness-critical.

Acceptance: restart between response loss and retry still produces one Student Model `CORRECT_ATTEMPT` and one Review decision.

### 6. Repair session compatibility and public projection

In backend models/response mapping:

- Treat a missing legacy `session_summary.session_performance.independent_attempts` as `0` on deserialization. Preserve present values unchanged.
- Keep `last_student_model` private if diagnostics still need it; exclude it from `SessionResponse` and all public session projections.
- Keep `student_model_state` as the only public progression source and ensure it is projected from the most recently persisted authoritative Schema 3 event.

Acceptance: old snapshots cold-start cleanly, and public session JSON has no contradictory mastery or phase source.

### 7. Add backend-only evidence for every lifecycle decision

Use the existing backend logger and session JSON state; do not add observability infrastructure.

- Persist a transition receipt for `CORRECT_ATTEMPT → REVIEW`, review materialization changes, `REVIEW_COMPLETED`, and next-topic handoff.
- Emit one privacy-safe structured log for each receipt with session ID, student ID, topic ID, source turn/request ID, Student Model journey version, phase, materialization state, and next-topic ID/phase when present.
- Never log transcript, OCR text, canvas images, or answer values in these receipt events.

Acceptance: one session ID can be traced from final evidence through the Student Model event, Phase 4 materialization, completion, and next-topic handoff without privileged broad-log access.

## Verification sequence

1. Restore a pre-field snapshot and cold-start 8001; confirm `independent_attempts=0` only when absent.
2. Use the updated T01.M6 micro-skill data to submit the first correct Phase 3 question; assert Student Model remains in independent practice.
3. Submit the final correct Phase 3 question with the updated data; assert exactly one `CORRECT_ATTEMPT`, `REVIEW`, a persisted final-turn receipt, and either `PENDING` or `READY`.
4. Force one Phase 4 generation failure; assert the answer remains accepted, no Student Model event repeats, and a later session read changes only `PENDING → READY`.
5. Restart backend and resend the identical final turn; assert receipt replay with no OCR/tutor/Student Model work. Change evidence for the same turn ID; assert 409.
6. Complete review; assert Student Model returns the deterministic next-topic handoff, backend ends the old session atomically, and a second completion returns the same handoff.
7. Start a new session from that exact handoff; assert Student Model opens the next topic at its selected entry phase and never reopens the completed source topic.
8. Exercise the retired resume endpoint and assert the explicit compatibility response; verify `SESSION_OPENED` correctly rehydrates a stored REVIEW journey.
9. Inspect the public response for absence of `last_student_model` and the lifecycle receipt/log fields for the exact session.

## Required external handoff

The server contract can guarantee that review completion returns an authoritative next-topic handoff and ends the old session. It cannot set a browser's local session ID or navigate the browser.

Therefore, the user-visible automatic next topic requires one caller action outside this backend/Student Model-only implementation: consume `next_topic_handoff` and immediately call the existing session-start flow with its exact topic and entry phase. This is an integration dependency, not a second decision-maker; it must not calculate or substitute curriculum data.

## Non-goals

- No further T01.M6 content authoring; its updated micro-skill data is used only to verify this contract.
- No frontend routing, persistence, or review rendering work.
- No fabricated Phase 4 review data or client-side transition to Review.
- No Student Model decision fallback in backend.
- No new endpoint for generating review and no background worker.

## Claude Code implementation prompt

```text
Implement the agreed Backend + Student Model-only review-handoff plan in /Users/tacticalcamel/Desktop/Nablix.

Read first:
- /Users/tacticalcamel/Desktop/Nablix/AGENTS.md
- nablix-backend/CONTEXT.md
- mathtutor-student/CONTEXT.md
- nablix-backend/docs/adr/0003-student-model-authoritative-next-topic-handoff.md
- nablix-backend/docs/adr/0004-student-model-owned-journey-rehydration.md
- docs/backend-student-model-review-handoff-plan-2026-09-02.md

Scope is strictly nablix-backend and mathtutor-student. Do not edit Numera-ui or author further T01.M6 content: its micro-skill data is now updated and should be used only for end-to-end verification. Do not add a service, queue, database table, dependency, fallback topic, or client-side routing workaround. Preserve unrelated dirty work and inspect every target file before editing.

Non-negotiable authority rules:
1. Student Model alone decides mastery, phase, next topic, and next entry phase.
2. Backend validates, persists, materializes Phase 4, and relays the Student Model decision. It never calculates replacement curriculum data.
3. Only a Student Model MASTERED outcome can enter REVIEW.
4. Review materialization is backend presentation state only: PENDING or READY. It never moves the Student Model journey backwards or asks the student to re-answer accepted evidence.

Implement these changes in the smallest coherent set:

1. Student Model REVIEW_COMPLETED contract
   - Require deterministic START_NEXT_TOPIC, next_topic_id, and next_topic_entry_phase when a next topic exists.
   - Keep the completed source topic MASTERED/COMPLETED/REVIEW as read-only history.
   - Retire SESSION_RESUMED handling and the snapshot-driven phase selection path. SESSION_OPENED remains the authoritative rehydration read.

2. Backend review completion handoff
   - Add a typed public next_topic_handoff projected only from the Student Model REVIEW_COMPLETED event.
   - Reject malformed completion responses; do not calculate a fallback topic.
   - Persist the handoff and atomically mark the source session ended after successful validation.
   - Make repeated REVIEW_COMPLETED turns idempotently return the same handoff.

3. Retire backend resume mutation
   - Deprecate POST /session/{id}/resume with a stable explicit compatibility error for one release; remove StudentResumed/saved_journey mutation code after verification.
   - A lost backend session must be rehydrated through SESSION_OPENED, never a client-supplied journey snapshot.

4. Phase 4 materialization and retry
   - Persist review_materialization_state (PENDING/READY) with safe legacy defaults.
   - Persist REVIEW and PENDING before Phase 4 generation.
   - Make two bounded total materialization attempts with structured warning logs.
   - On exhaustion keep REVIEW+PENDING; GET /session/{id} may retry materialization only. Never resend CORRECT_ATTEMPT.
   - Expose the state in the accepted final-turn response.

5. Durable final-turn idempotency
   - Persist a minimal receipt for final independent turns in existing SessionRecord JSON: turn ID, evidence fingerprint, Student Model request ID, journey version, result phase, materialization state.
   - After restart, an exact duplicate must return receipt-derived state without OCR, tutor evaluation, or a second Student Model call. Changed evidence for the same turn ID stays 409.

6. Compatibility and projection
   - Missing legacy independent_attempts restores as zero; existing values are preserved.
   - Exclude last_student_model from all public session responses. Keep student_model_state as the only public progression projection.

7. Observability
   - Add privacy-safe structured backend logs and persisted lifecycle receipts for final evidence, REVIEW materialization state, REVIEW_COMPLETED, and next-topic handoff.
   - Include IDs, Student Model journey version, phase, materialization state, and handoff values only. Never log transcript, OCR, canvas, or answer content.

Tests and verification:
- Add only focused existing-style tests for the listed acceptance scenarios: legacy restore/cold start, Phase 3 final turn, PENDING→READY without another Student Model event, restart-safe duplicate replay, completion handoff plus old-session termination, SESSION_OPENED review rehydration, retired resume endpoint, and public response field exclusion.
- Run the relevant backend tests from nablix-backend and Student Model tests from mathtutor-student.
- Do not commit, push, deploy, or edit unrelated files. Report changed files, tests run, failures, and the one unavoidable external integration dependency: the caller must adopt next_topic_handoff and invoke existing session start to make the next lesson visible.
```
