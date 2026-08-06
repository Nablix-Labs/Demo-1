# Chirudeva Phase 2 integration handoff

Chirudeva owns the interaction state machine, inactivity policy, Wrong 1–4 counter, and side-channel state preservation. Frontend and Student Model changes described below are integration work for their owners; this backend change does not modify either repository.

## Sanya — Explain Again

Chirudeva now calls the configured OpenAI AI-engine client implementing Sanya's contract. There is no canned fallback: a missing client returns HTTP 503, and an invalid LLM response raises an adapter error.

```python
def generate_explain_again_response(
    self,
    request: ExplainAgainRequest,
    system_prompt: str,
) -> ExplainAgainResponse:
    ...
```

The request passed to the function is:

```json
{
  "question": "What does cd mean?",
  "generated_question_rubric": null,
  "active_teaching_objective": null,
  "first_unresolved_concept_id": null,
  "recent_conversation": [{"role": "assistant", "content": "Think about multiplication."}],
  "visible_cue": null,
  "active_scaffold": null,
  "support_state": {
    "active_support_level": "HINT",
    "highest_support_used": "HINT",
    "support_reason_code": "GUIDED_HINT_REQUIRED"
  },
  "selected_error_code": "ERR-T02-ADJACENT-LETTERS-ADDITION",
  "misconception_evidence": "The learner read adjacent letters as addition."
}
```

Return exactly this shape. All three control fields are fixed and prevent Explain Again from grading, advancing, or incrementing attempts.

```json
{
  "tutor_message": "A genuinely different explanation without the final answer.",
  "tutor_message_voice": "The voice-ready version of the same explanation.",
  "answer_reveal_allowed": false,
  "progression_change_requested": false,
  "attempt_increment": 0
}
```

## Sanya — Wrong 4 contract

Chirudeva, not tutor prose, selects `WRONG_1_HINT`, `WRONG_2_HINT`, `WRONG_3_VISUAL_CUE`, then `WRONG_4_INTERVENTION`. On Wrong 4 it sends Saravanan this event:

```json
{
  "request_id": "SESSION...:TURN-GUIDED-WRONG-4:GUIDED_SUPPORT_ESCALATION_REQUIRED",
  "event_type": "GUIDED_SUPPORT_ESCALATION_REQUIRED",
  "source_turn_id": "TURN-GUIDED-WRONG-4",
  "expected_journey_version": 17,
  "topic_id": "ALG-ORI-02",
  "student_id": "ST001",
  "timestamp": "2026-08-05T06:45:20Z",
  "question_id": "Q-T02-004",
  "micro_skill_id": "T02.M1",
  "triggering_response": "x = 4",
  "error_code": "ERR-T02-SUBTRACTION-MISAPPLIED"
}
```

`support_reason_code` is the closed Wrong ladder enum above. `error_code` is not a second invented enum: Wrong 4 accepts only a code in the active question's `tutor_view.potential_errors[].error_code` catalog, whether matched from the learner response or selected by Sanya.

## Manav — inactivity API

Read the server policy from `POST /session/start` or any successful, non-stale `POST /interaction` response:

```json
{
  "inactivity_policy": {
    "initial_idle_threshold_ms": 20000,
    "cooldown_ms": 30000,
    "max_nudges_per_tutor_turn": 2,
    "generated_nudge_rate_limit": 4
  }
}
```

After the client observes inactivity, claim a nudge through the existing endpoint. `idle_duration_ms` is optional client telemetry; eligibility comes from the server's tutor-response timestamp, cooldown, and limits.

```http
POST /interaction
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "session_id": "SESSION...",
  "student_id": "ST001",
  "interaction_type": "INACTIVITY_NUDGE",
  "input_source": "SYSTEM",
  "turn_id": "TURN-NUDGE-1",
  "previous_tutor_turn_id": "TUTOR-...",
  "idle_duration_ms": 20000,
  "current_phase": "GUIDED_PRACTICE",
  "concept_id": "ALG_LINEAR_ONE_STEP",
  "question_id": "Q-T02-004",
  "hint_count": 1
}
```

A generated nudge returns `nudge_delivery.status: "GENERATED"`; a denied claim returns top-level `status: "NUDGE_SUPPRESSED"` with `nudge_delivery: null`. After rendering the generated message, report presentation with a new `turn_id`:

```json
{
  "session_id": "SESSION...",
  "student_id": "ST001",
  "interaction_type": "NUDGE_PRESENTED",
  "input_source": "SYSTEM",
  "turn_id": "TURN-NUDGE-PRESENTED-1",
  "previous_tutor_turn_id": "TUTOR-...",
  "nudge_id": "TURN-NUDGE-1",
  "current_phase": "GUIDED_PRACTICE",
  "concept_id": "ALG_LINEAR_ONE_STEP",
  "question_id": "Q-T02-004",
  "hint_count": 1
}
```

The response then contains `nudge_delivery.status: "PRESENTED"`. Reusing either `turn_id` is idempotent.
The `nudge_id` is exactly the claim response's `nudge_delivery.interaction_id`.

## Manav — deterministic escalation response

Render backend fields; do not infer the ladder from message text:

```json
{
  "accepted_turn_id": "TURN-GUIDED-WRONG-4",
  "interaction_state_version": 21,
  "tutor_turn_id": "TUTOR-...",
  "guided_student_state": "WRONG",
  "evaluation_reason_code": "RESPONSE_INCORRECT",
  "support_reason_code": "WRONG_4_INTERVENTION",
  "wrong_attempt_count": 4,
  "intervention_triggered": true,
  "selected_error_code": "ERR-T02-SUBTRACTION-MISAPPLIED",
  "support_served_this_turn": "SCAFFOLD",
  "routing_reason_code": "GUIDED_SCAFFOLD_REQUIRED"
}
```

Typed evaluation codes are `ALL_REQUIRED_COMPONENTS_CONFIRMED`, `REQUIRED_COMPONENTS_MISSING`, `RESPONSE_INCORRECT`, `STUDENT_STUCK`, and `RESPONSE_UNCLEAR`. Typed routing codes are the Schema 3.0 values returned by Student Model: `DIAGNOSTIC_STARTED`, `DIAGNOSTIC_GAPS_FOUND`, `DIAGNOSTIC_NO_GAPS`, `ORIENTATION_STARTED`, `ORIENTATION_COMPLETED`, `GUIDED_IN_PROGRESS`, `GUIDED_HINT_REQUIRED`, `GUIDED_SCAFFOLD_REQUIRED`, and `GUIDED_COMPLETED`. `support_reason_code` is a union: a Wrong-ladder code on deterministic escalation turns, otherwise a Student Model routing code when support is served.

## Saravanan — write contract

No Student Model code was changed. Chirudeva continues to write through `POST /session/event`. Wrong 4 now requires `triggering_response` and `error_code` in `GUIDED_SUPPORT_ESCALATION_REQUIRED`; reject the event if either is absent. Apply the event atomically against `expected_journey_version`: record the accepted incorrect attempt and error evidence, advance support/scaffold state, and retain unrelated phase, question, and component state.

At minimum, the durable journey record must retain these values across that partial write:

```json
{
  "current_phase": "PHASE_2_GUIDED_LEARNING",
  "version": 17,
  "phase_2_guided_learning": {
    "current_attempt_sequence": 4,
    "confirmed_concept_ids": ["LIKE_TERMS"],
    "missing_concept_ids": ["SUBTRACTION_STEP"],
    "highest_support_used_by_skill": {"T02.M1": "SCAFFOLD"},
    "current_question_id": "Q-T02-004",
    "current_question_target_micro_skill_ids": ["T02.M1"],
    "current_scaffold_step_number": 1
  }
}
```

These map to the requested preservation groups: attempts, components, support, phase/question, and scaffold. The component and phase-counter names are an external Student Model contract accepted through the phase state's extensible fields; Chirudeva strictly types the question/support fields shown in its `JourneyPhaseState`. Chirudeva also preserves its local `generated_question_rubric`, `active_teaching_objective`, scaffold identifiers/steps, counters, phase, and authoritative `student_model_event` during Explain Again and inactivity.

## Saravanan — response contract

Return the full authoritative `journey_state`, not only changed fields. Chirudeva validates `routing.reason_code` as a typed Schema 3.0 code and reapplies the returned phase/support state. The compact JSON below shows the required response envelope and relevant Phase 2 fields; the full Schema 3.0 response must also include all journey identity/timestamp fields and every phase-state object.

```json
{
  "request_id": "SESSION...:TURN-GUIDED-WRONG-4:GUIDED_SUPPORT_ESCALATION_REQUIRED",
  "schema_version": "3.0",
  "processed_at": "2026-08-05T06:45:21Z",
  "event_result": {},
  "journey_state": {
    "student_id": "ST001",
    "active_session_id": "SESSION...",
    "topic_id": "ALG-ORI-02",
    "current_phase": "PHASE_2_GUIDED_LEARNING",
    "version": 18,
    "phase_2_guided_learning": {
      "status": "IN_PROGRESS",
      "current_question_id": "Q-T02-004",
      "current_question_target_micro_skill_ids": ["T02.M1"],
      "highest_support_used_by_skill": {"T02.M1": "SCAFFOLD"}
    }
  },
  "routing": {
    "reason_code": "GUIDED_SCAFFOLD_REQUIRED",
    "reason": "Maximum guided support is required.",
    "next_action": "SERVE_SUPPORT",
    "next_topic_id": null,
    "next_topic_entry_phase": null,
    "prerequisite_check_required": false,
    "prerequisite_micro_skill_ids": [],
    "content_gap_detected": false,
    "missing_micro_skill_ids": []
  },
  "phase_payload": {
    "phase": "PHASE_2_GUIDED_LEARNING",
    "payload_type": "SCAFFOLD",
    "support_to_serve": {
      "support_type": "SCAFFOLD",
      "scaffold_id": "SCF-T02-M1",
      "current_step_id": "SCF-T02-M1-S1",
      "prompt": "Name the operation to undo first.",
      "expected_response": "addition",
      "steps": [{"step_id": "SCF-T02-M1-S1", "prompt": "Name the operation to undo first.", "expected_response": "addition"}]
    }
  },
  "status": {
    "success": true,
    "status_code": "OK",
    "intervention_required": true,
    "intervention_reason": "WRONG_4",
    "warnings": [],
    "operational_errors": []
  }
}
```
