# Session Transition and Phase 4 Debug Record

**Captured:** 2026-09-02 (UTC)  
**Scope:** one live VM audit and the current frontend/backend source contracts. This is a diagnosis record, not an implementation proposal.

## Current verdict

The earliest confirmed failure for `SESSION462…` is **before Phase 4**. Its Phase 3 correct attempt reached the Student Model, which returned `FRESH_CONTENT_UNAVAILABLE` for missing micro-skills `T01.M1` and `T01.M2`. The backend recorded `WAIT_FOR_CONTENT`; that session did not receive `MASTERED` or `REVIEW`.

A later captured review screen proves a different session did reach Phase 4. It is not the demo screen: its `Mastered` outcome comes from the server payload (the client fallback is `Reviewed`), and its insight wording is not in the repository. `This topic` is a client fallback used when the session lacks a human-readable orientation title.

The current evidence therefore describes session-dependent behavior, not a global inability to enter Review. Correlate the screenshot's session ID before assigning a root cause to the earlier content gap, the canvas transition, or UI routing.

## Live VM evidence

| Surface | Evidence | Result |
|---|---|---|
| 8001 | `nablix-backend.service`; `127.0.0.1:8001`; local `/health` | Active, listening, HTTP 200 at audit time |
| 8080 | Student Model service; nginx TLS listener; `https://nablix.ai:8080/health` resolved locally | Active, listening, HTTP 200 `{"status":"ok"}` |
| Persisted sessions | 10:41–10:43 UTC backend journal | Repeated startup validation failure: `session_summary.session_performance.independent_attempts` absent |
| Phase 3 | `SESSION462…`, 11:07 UTC | `INDEPENDENT_QUESTION_SET_REQUESTED` entered Phase 3; following correct attempt returned `FRESH_CONTENT_UNAVAILABLE` |
| Phase 4 | Initial audit before the later `SESSION55…` trace | No Phase 4 event had then been correlated; the successful `SESSION55…` transition is recorded below |

The snapshot restoration error is a separate 8001 availability/continuity risk. It is not evidence that 8080 was down or that the Phase 4 UI failed.

## Proven successful transition: `SESSION55fee8cc2c384d448e5d7dcd67049842`

| Time (UTC) | Evidence | Result |
|---|---|---|
| 16:46:47 | Phase 3 canvas attempt for `Q-T01-007` | Correct, but remained in Independent Practice |
| 16:54:49–16:54:53 | Canvas attempt for `Q-T01-008` | 8080 returned `CORRECT_ATTEMPT`, `phase: REVIEW`, `payload_type: REVIEW_SUMMARY`, `routing_reason_code: INDEPENDENT_MASTERY`; 8001 returned canvas HTTP 200 |
| 16:54:53 | Phase 4 generation | 8001 topic-history request, OpenAI generation, and 8080 `/phase4-review` persistence each returned 200 |
| 16:55:24 | `POST /session/{id}/review/complete` | 8080 accepted `REVIEW_COMPLETED`; 8001 returned 200; `/session/end` returned 200 |
| After completion | 8001 owned-session read for `ST021` | `current_phase: REVIEW`, `status: ended`, and a non-null `phase4_review` with insights, topic outcome, journey, and replays |

This review is real, not fixture output. Its `phase4_review.topic_outcome.mastery_status` is `MASTERED`; the client fallback would have displayed `Reviewed`. The generic heading `This topic` is a frontend fallback because the returned session lacks an orientation video title.

The screen and completion capture currently identify **two different sessions**: `SESSIONd9bf07d972274620b4335077b8c8988d` was supplied as the screenshot session, while the completion response is for `SESSION55fee8cc2c384d448e5d7dcd67049842`. Do not combine their state: any remaining display/routing bug is now an identity or client-state correlation problem, not a failure of `SESSION55…` to enter Review.

## Transition contract

| Step | Browser input | 8001 action/output | 8080 action/output | Required next action |
|---|---|---|---|---|
| Final Phase 3 canvas turn | `POST /canvas/submit`: `session_id`, `student_id`, stable `turn_id`, `snapshot_data_url`, `strokes`, `canvas_events`, `submission_role` | Validates and grades the attempt; returns an `InteractionResponse` including phase fields but no `phase4_review` | Receives a Schema 3 event with `source_turn_id` and expected journey version | Capture this POST status/body with its session ID |
| Student Model transition | N/A | Maps the validated Student Model state into the Nablix session and persists it | Returns the current journey phase/routing | `MASTERED` must lead to `REVIEW`; `FRESH_CONTENT_UNAVAILABLE` is an earlier content failure |
| Review generation | N/A | On `REVIEW`, persists the phase, fetches topic event history, generates the review, and stores full `phase4_review` locally | Receives `/topic/event-history`; later receives compact `/phase4-review` persistence data | Capture session-scoped 8001 and 8080 outcomes |
| Review UI handoff | `GET /session/{session_id}?student_id=…` | Returns a session containing both `current_phase: "REVIEW"` and non-null `phase4_review`, or 503 `PHASE4_REVIEW_UNAVAILABLE` while retrying | N/A | UI navigates only when both conditions are true |
| Review completion | `POST /session/{id}/review/complete`: `student_id`, `turn_id` | Sends `REVIEW_COMPLETED` to the Student Model | Advances the learner journey after review | Verify this separately; `/session/end` only marks the local session ended |

## Confirmed gaps and ownership

| Priority | Gap | Owner | Evidence / decision |
|---|---|---|---|
| High | Phase 3 lacks fresh content after a correct attempt (`T01.M1`, `T01.M2`) | Student Model/content | Earliest observed failure. Repair/publish the missing content or correct its eligibility before changing review UI code. |
| High | Older persisted sessions omit `independent_attempts` | Backend persistence | Add a backward-compatible restoration path and prove it with an old snapshot; this caused the 8001 crash loop. |
| High | No Phase 4 live trace exists | Cross-system verification | Capture final submit, session read, and correlated 8001/8080 logs for one session ID before assigning a Phase 4 owner. |
| High | `REQ7570CBF3` at 16:48:07 UTC reached `/interaction` as `VOICE` with no usable `voice_transcript` | Frontend/deployed transport | The 8001 shared request service rejects this exact shape with 422. Current REST voice source refuses blank transcripts before posting, and current streamed voice posts a required `transcript` to `/voice/transcript`; capture the live request body and deployed asset/version before changing either service. |
| Medium | UI readiness accepts any non-null `phase4_review`, but the renderer requires populated insight fields | Frontend/backend contract | A malformed/legacy review could miss the retry state. Do not change this without an actual captured payload. |
| Medium | UI derives its rail only from tutor replays and drops the supplied `question_journey` | Frontend | Hides some completed Phase 3 context; does not block Phase 4 rendering. |
| Medium | Review completion errors are swallowed while the UI exits | Frontend/backend wiring | Can leave the Student Model in `REVIEW`, affecting the next session; it is post-display and separate from the current blocker. |

## Required correlation for a Phase 4 verdict

Use one session ID and one time window. Capture, in order:

1. The browser request/response for final `POST /canvas/submit`.
2. The browser request/response for `GET /session/{session_id}`.
3. The matching 8001 logs for Student Model response and Phase 4 generation.
4. The matching 8080 records for `/session/event`, `/topic/event-history`, and `/phase4-review`.

Expected interpretations:

- `FRESH_CONTENT_UNAVAILABLE` before `REVIEW`: Student Model/content gap; Phase 4 is not yet in scope.
- `REVIEW` + non-null `phase4_review` from GET, but no screen: frontend routing/rendering defect.
- `REVIEW` + GET 503 `PHASE4_REVIEW_UNAVAILABLE`: backend generation/history/validation failure; retry is expected UI behavior.
- Final submit succeeds but GET is absent, fails, or is routed incorrectly: frontend/backend transport gap.

## Limits

The `developer` VM user cannot read detailed nginx or Student Model journals (`adm`/journal access is unavailable). The present evidence is sufficient to rule out a current port outage and identify the Phase 3 content blocker, but not to assign a Phase 4 root cause.
