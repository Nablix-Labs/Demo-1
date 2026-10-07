# Teach-Back engine handoff

Implemented: conceptual evaluation, tutor wording, safety/input-confidence checks, typed output, and validation of permitted actions. The approved prompt is in `nablix-backend/prompts/ai_tutor/phases/teach_back.txt`; messages and the two-failure threshold are in `configs/teach_back_tutor.yaml`.

## Chirudeva: orchestration

Call `TutorEngineServiceAdapter.respond_to_teach_back(content, student_input, input_source, transcript_confidence, history)`, or the internal `POST /ai-engine/teach-back/respond` endpoint. Its request fields are `content`, `student_input`, `input_source` (`TEXT`/`VOICE`), optional `transcript_confidence`, and `conversation_history`.

`content` follows `app/models/teach_back.py`: run/state, targets with authored expected concepts and misconception catalogues, actual teaching summaries, and completed worked examples. Supply the persisted current-skill failure count and completed skills on every call.

The reply contains `evaluation`, `tutor_message`, `tutor_message_voice`, and `next_action`. `evaluation.understanding_status` is `UNDERSTOOD`, `MISCONCEPTION`, or null. Error details stay internal. The engine proposes and validates an action; it does not save progress or change phases.

| Reply | Orchestration action |
|---|---|
| `NEXT_MICRO_SKILL` | Record understanding; advance to the next unfinished target |
| `MOVE_TO_PHASE_2` | Save the final understood turn, then complete Teach-Back |
| `ASK_REEXPLANATION` with misconception | Save the first failure; retain the target |
| `RETURN_TO_ORIENTATION` | Atomically save the second failure and request orientation for that skill |
| Null verdict | Save the conversation without incrementing failures or marking understanding |

Branch before numerical question grading. Own pending-event recovery, duplicate/stale-request handling, failure-count persistence, same-run resume after orientation, and final completion recovery. Reset failures after a completed orientation revisit or skill advancement. Preserve understood skills and historical misconceptions. Do not update solving attempts, hints, or mastery from these turns.

Use the YAML opening message with the current teaching summary's skill name. Return only tutor wording and public phase/UI state to the student.

## Saravanan: Student Model

Extend `TEACH_BACK_TURN_RECORDED` with `RETURN_TO_ORIENTATION`, `tutor_response_voice`, and `failed_explanation_count`. Persist the count and last tutor reply; validate the count against saved evidence. Return the unresolved skill's orientation bundle atomically, then resume the same Teach-Back run after orientation with count zero and completed skills retained.

Diagnostic completion needs question-level results and a diagnostic run ID. Orientation completion can supply Teach-Back content, guided practice, or a content gap. Missing authored concepts/teaching coverage must stop progression.

## Manav: frontend

Render the tutor's text/voice and follow authoritative phase transitions. This phase accepts text and final voice transcripts, with no Canvas, score, attempt counter, or hint ladder. No frontend changes are included here.

## Verification

Engine checks cover verdicts, both failure stages, discussion/acknowledgements, unclear voice, invalid codes, leaked references, missing content, and service failure. The optional live evaluation is `tests/test_teach_back_openai_smoke.py`, enabled by `NABLIX_RUN_OPENAI_SMOKE=true` and `NABLIX_OPENAI_API_KEY`; it prints replies for conversational review.

Full session recovery and end-to-end checks belong to orchestration/frontend integration. Live conversational quality has not been verified without AI credentials.
