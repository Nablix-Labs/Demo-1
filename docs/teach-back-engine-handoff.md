# Teach-Back integration handoff

Saravanan, the backend orchestration is implemented locally on `deva/teach-back-orchestration`. Student Model still owns learning progress. The current `mathtutor-student` checkout matches `origin/master` at `6a4f0ad`; the remaining contract work below blocks live integration.

## Backend behavior

Orientation can enter Teach-Back without guided questions. `journey_state.current_phase` stays `PHASE_1_ORIENTATION`, the payload uses `PHASE_1_TEACH_BACK`, and the backend exposes `TEACH_BACK`. Guided payloads still go directly to Guided Practice.

`POST /interaction` accepts `TEACH_BACK_SUBMISSION` or `ANSWER_SUBMISSION`, with text or a final voice transcript and an omitted/null `question_id`. It uses retained authored content and server conversation history. Canvas input is rejected before OCR or state writes. Teach-Back does not grade problems or update their evidence, hints, scores, or mastery.

Each validated reply and exact outgoing event is saved before the mutation. `GET /session/{session_id}?student_id=...` recovers pending work without another engine call. The final understood turn is recorded before `TEACH_BACK_COMPLETED`, which uses the acknowledged journey version. Durable receipts replay accepted turns and reject changed evidence under the same turn ID. Orientation visits have distinct identities and retain their original event envelopes for retries.

## Remaining work in Student Model

- Persist and return `failed_explanation_count` in `TeachBackRepository.run_state`. The current serializer omits it. Derive it from recorded evaluations: first misconception becomes 1, understanding resets it to 0, and null verdicts leave it unchanged, including null-verdict `ASK_REEXPLANATION`.
- Accept `RETURN_TO_ORIENTATION` in `TeachBackNextAction`. Record the second misconception and count 2 in the same transaction that returns the failed skill's orientation bundle. Do not require a separate backend content fetch.
- Return both the orientation bundle and `phase_payload.teach_back` on that response. The state must name the same run/current skill and retain understood skills. The bundle must target only the failed skill.
- Accept, persist, and return `tutor_response_voice`. Each turn acknowledgement must include `state.last_tutor_response` with the exact `tutor_response`, `tutor_response_voice`, `tutor_next_action`, and `turn_id` sent by the backend. The current handler stores text/action/turn ID, while `run_state` omits the stored reply entirely.
- Completing the orientation revisit must resume the same run with count 0, the failed skill still current, and understood skills retained. Return full authored Teach-Back content on `SESSION_OPENED`, including the last tutor text/voice. State-only acknowledgements are accepted when this backend session already retains matching content.
- Preserve request-ID replay before the version check. A replay must return the retained response without inserting another turn. `TEACH_BACK_COMPLETED` must return guided questions after every target is understood.

Contract definitions are in `nablix-backend/app/models/student_model_session.py` and `app/models/teach_back.py`. The backend already sends `diagnostic_run_id` and `question_results` with question IDs, usage IDs, and graded results. Student Model selects primary-skill targets; the backend does not duplicate that selection.

## Verification needed together

The 40 focused backend checks pass, including 15 orchestration route/recovery cases. They use the repository's simulated Student Model transport and disabled database persistence. They prove orchestration behavior, not a live service or database integration.

The broad backend run has 1,053 passing tests and 29 failures. A clean `origin/main` checkout reproduces the same 29 failures: 28 RAG/service checks and the existing orientation-opening wording assertion in `test_session_events.py`. There are no new failing test names.

After the Student Model changes and required migrations are applied to a local test database, run a real integration smoke: diagnostic selection, first failure, second-failure orientation, same-run resume, final completion, refresh/restart, and lost-response replay. Inspect `student_model.teach_back_runs`, `teach_back_results`, `teach_back_turns`, retained event responses, and the backend session snapshot. Confirm one turn per accepted ID, persisted counts/replies, retained understood skills, and unchanged problem attempts/mastery. This smoke remains pending because the current Student Model contract is incomplete. Nothing here is deployment proof.

## Manav's frontend dependency

`Numera-ui/lib/teachback/teachApi.ts` still returns scripted turns. `app/teach/TeachBackClient.tsx` supplies a null session ID and canvas input. Replace these with authenticated session/interaction calls, render backend text/voice, and follow the returned phase instead of a fixed turn count. Send a stable `turn_id`, `previous_tutor_turn_id`, `concept_id`, phase, and hint count; voice needs `voice_transcript` and `transcript_final: true`. On a failed mutation, refresh the session before another learning turn. Route mapping already recognizes `TEACH_BACK`. Browser acceptance remains with Manav.
