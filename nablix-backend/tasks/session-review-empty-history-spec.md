# Spec: End Review Sessions with Student Model History

## Objective

Allow every valid session to end after reaching `REVIEW`, including sessions
with zero locally recorded attempts. Empty sessions use a deterministic
zero-attempt review response. Populated sessions keep the existing review
pipeline and local attempt history unchanged. This backend-only slice does not
invent a Student Model `session_history` contract that the Student Model does
not currently publish.

## Commands

- Focused tests: `cd nablix-backend && pytest -q tests/test_session_events.py tests/test_session_review.py tests/test_session.py`
- Full backend tests: `cd nablix-backend && pytest -q`

## Project Structure

- `app/services/session_service.py` — session transition and `/session/end` orchestration.
- `app/models/student_model_session.py` — Student Model Schema 3.0 response models.
- `app/models/session.py` — local session and summary models.
- `app/models/session_review.py` — review request validation contract.
- `app/ai_engine/session_review.py` — review validation and generation.
- `tests/` — API and integration regression coverage.

## Code Style

Keep the empty-session branch explicit and isolated from populated review
generation. Do not append a synthetic `QuestionAttemptRecord` merely to
satisfy a non-empty-list check.

## Testing Strategy

- Reproduce the Phase 3 content-exhaustion transition into `REVIEW`.
- End a REVIEW session with empty local history successfully.
- Verify the final summary contains zero attempts and no fabricated questions.
- Verify non-empty local history continues through the existing review path.
- Preserve existing review validation for non-empty histories.
- Run the focused suite, then the full backend suite.

## Boundaries

- Always: validate external payloads; preserve existing non-empty review
  behavior; add a regression test.
- Ask first: changing the Student Model event contract, changing review output
  semantics, or adding dependencies.
- Never: fabricate attempts, silently fall back to stale local history, or
  weaken validation for populated histories.

## Success Criteria

1. Any session in `REVIEW` can complete through `/session/end`.
2. Empty local history produces a valid zero-attempt completion summary.
3. Populated local history continues through the existing review pipeline.
4. The Phase 3 exhaustion-to-end regression test passes.
5. No existing non-empty review behavior regresses.

## Open Questions

- A future cross-repository change may add a Student Model `session_history`
  contract; it is intentionally out of scope for this minimal backend fix.
