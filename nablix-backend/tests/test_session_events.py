from collections.abc import Awaitable, Callable
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.adapters import provider, student_model
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.main import app
from app.ai_engine.classifier_config import load_classifier_rules
from app.services import interaction_service, session_service


client = TestClient(app, headers={"Authorization": "Bearer test-token"})
SessionEventPost = Callable[
    [str, str, dict[str, object], dict[str, str], int, int],
    Awaitable[dict[str, object]],
]


def test_scaffold_response_matching_accepts_safe_variants() -> None:
    rules = load_classifier_rules()
    accepted = [
        ("½", "½"),
        ("1/2", "½"),
        ("one half is multiplying x", "½"),
        ("it is in front of x", "Before x"),
        ("1/2x", "½x"),
        ("on both sides", "Both sides"),
        ("+4", "add 4"),
        ("+ 4", "increases by 4"),
        ("add four", "add 4"),
        ("the counter increases by four each time", "add 4"),
        ("c is added by 4 each time", "add 4"),
    ]
    rejected = [
        ("1", "½"),
        ("before x", "½"),
        ("x/2", "½x"),
        ("4", "add 4"),
        ("-4", "add 4"),
        ("subtract 4", "add 4"),
    ]

    for student_message, expected_response in accepted:
        assert interaction_service._scaffold_response_is_correct(
            student_message,
            expected_response,
            "INCORRECT",
            rules,
        )
    for student_message, expected_response in rejected:
        assert not interaction_service._scaffold_response_is_correct(
            student_message,
            expected_response,
            "PARTIALLY_CORRECT",
            rules,
        )


def _diagnostic_started_response() -> dict[str, object]:
    return {
        "schema_version": "3.0",
        "request_id": "SESSION001:DIAGNOSTIC_QUESTION_SET_REQUESTED",
        "processed_at": "2026-07-27T10:00:00Z",
        "journey_state": {
            "student_id": "ST001",
            "active_session_id": "SESSION-001",
            "topic_id": "ALG-ORI-02",
            "topic_status": "IN_PROGRESS",
            "mastery_status": "NEW_LEARNER",
            "continuity_status": "ON_TRACK",
            "current_phase": "PHASE_0_DIAGNOSTIC",
            "recommended_entry_phase": "PHASE_0_DIAGNOSTIC",
            "session_count": 1,
            "started_at": "2026-07-27T10:00:00Z",
            "last_activity_at": "2026-07-27T10:00:00Z",
            "phase_0_diagnostic": {
                "status": "IN_PROGRESS",
                "phase_visit_no": 1,
                "target_micro_skill_ids": ["T02.M1"],
                "current_question_id": "Q-T02-D01",
                "current_question_usage_id": "QU-T02-D01-P0",
                "remaining_micro_skill_ids": ["T02.M1"],
                "used_question_ids": [],
                "started_at": "2026-07-27T10:00:00Z",
            },
            "phase_1_orientation": {"status": "NOT_STARTED", "phase_visit_no": None},
            "phase_2_guided_learning": {"status": "NOT_STARTED", "phase_visit_no": None},
            "phase_3_independent_practice": {
                "status": "NOT_STARTED",
                "phase_visit_no": None,
            },
            "review": {"status": "NOT_STARTED", "phase_visit_no": None},
            "version": 1,
            "updated_at": "2026-07-27T10:00:00Z",
        },
        "phase_payload": {
            "phase": "PHASE_0_DIAGNOSTIC",
            "payload_type": "QUESTION_SET",
            "question_set": {
                "difficulty_policy": "DIAGNOSTIC_BASELINE",
                "questions": [
                    {
                        "question_id": "Q-T02-D01",
                        "question_usage_id": "QU-T02-D01-P0",
                        "difficulty": 1,
                        "item_family_id": "FAM-T02-DIAG-M1",
                        "question_role": "DIAGNOSTIC",
                        "support_policy": "NO_SUPPORT",
                        "diagnosis_policy": "CORRECTNESS_ONLY",
                        "max_attempts": 1,
                        "micro_skill_mappings": [
                            {
                                "micro_skill_id": "T02.M1",
                                "is_primary": True,
                                "weight": 1.0,
                            }
                        ],
                        "student_view": {
                            "question_text": "What does 4y mean?",
                            "question_type": "SINGLE_CHOICE",
                            "options": [
                                {"option_id": "A", "text": "4 + y"},
                                {"option_id": "B", "text": "4 x y"},
                            ],
                            "requires_student_response": True,
                        },
                        "tutor_view": {
                            "answer_spec": {
                                "answer_spec_id": "ANS-T02-D01",
                                "canonical_answer": "B",
                                "accepted_answers": ["B"],
                                "verification_method": "EXACT_CHOICE_MATCH",
                            },
                            "potential_errors": [],
                        },
                    }
                ],
            },
            "orientation_bundle": None,
            "support_to_serve": None,
            "rescue_to_serve": None,
            "review_summary": None,
        },
        "event_result": None,
        "routing": {
            "reason_code": "DIAGNOSTIC_STARTED",
            "reason": "Diagnostic question set delivered.",
            "next_action": "WAIT_FOR_STUDENT_RESPONSE",
            "next_topic_id": None,
            "next_topic_entry_phase": None,
            "prerequisite_check_required": False,
            "prerequisite_micro_skill_ids": [],
            "content_gap_detected": False,
            "missing_micro_skill_ids": [],
        },
        "status": {
            "success": True,
            "status_code": "OK",
            "intervention_required": False,
            "intervention_reason": None,
            "warnings": [],
            "operational_errors": [],
        },
    }


def _eight_skill_diagnostic_response() -> dict[str, object]:
    response = deepcopy(_diagnostic_started_response())
    journey = response["journey_state"]
    payload = response["phase_payload"]
    assert isinstance(journey, dict)
    assert isinstance(payload, dict)
    phase = journey["phase_0_diagnostic"]
    question_set = payload["question_set"]
    assert isinstance(phase, dict)
    assert isinstance(question_set, dict)
    base_question = question_set["questions"][0]
    assert isinstance(base_question, dict)
    skills = [f"T02.M{number}" for number in range(1, 9)]
    questions: list[dict[str, object]] = []
    for number, skill in enumerate(skills, start=1):
        question = deepcopy(base_question)
        question["question_id"] = f"Q-T02-D{number:02d}"
        question["question_usage_id"] = f"QU-T02-D{number:02d}-P0"
        question["micro_skill_mappings"] = [
            {"micro_skill_id": skill, "is_primary": True, "weight": 1.0}
        ]
        questions.append(question)
    phase["target_micro_skill_ids"] = skills
    phase["remaining_micro_skill_ids"] = skills
    question_set["questions"] = questions
    return response


def _event_response(
    event_type: str,
    request_id: str,
) -> dict[str, object]:
    response = deepcopy(_diagnostic_started_response())
    response["request_id"] = request_id
    journey = response["journey_state"]
    payload = response["phase_payload"]
    routing = response["routing"]
    assert isinstance(journey, dict)
    assert isinstance(payload, dict)
    assert isinstance(routing, dict)

    if event_type == "DIAGNOSTIC_COMPLETED":
        journey["mastery_status"] = "DEVELOPING"
        journey["recommended_entry_phase"] = "PHASE_1_ORIENTATION"
        journey["phase_0_diagnostic"] = {
            "status": "COMPLETED",
            "phase_visit_no": 1,
            "target_micro_skill_ids": ["T02.M1"],
            "used_question_ids": ["Q-T02-D01"],
        }
        journey["phase_1_orientation"] = {
            "status": "NOT_STARTED",
            "phase_visit_no": None,
            "target_micro_skill_ids": ["T02.M1"],
        }
        payload.update(
            {
                "phase": "PHASE_1_ORIENTATION",
                "payload_type": "ORIENTATION_BUNDLE",
                "question_set": None,
                "orientation_bundle": {
                    "target_micro_skill_ids": ["T02.M1"],
                    "delivery_sequence": [
                        {
                            "sequence_no": 1,
                            "content_type": "ORIENTATION_VIDEO",
                            "video": {
                                "video_id": "VID-KS3-T02-ORI",
                                "title": "The Secret Language of Algebra",
                                "asset_url": None,
                                "duration_seconds": 75,
                            },
                            "worked_example": None,
                        },
                        {
                            "sequence_no": 2,
                            "content_type": "WORKED_EXAMPLE",
                            "video": None,
                            "worked_example": {
                                "worked_example_id": "WE-KS3-T02-01",
                                "title": "Many Cases, One General Rule",
                                "covered_micro_skill_ids": ["T02.M1"],
                                "final_answer": "n + 4",
                                "student_answer_required": False,
                                "steps": [
                                    {
                                        "step_id": "WE-KS3-T02-01-S01",
                                        "sequence_no": 1,
                                        "screen_content": "2 + 4",
                                        "narration_text": "Start with one case.",
                                        "must_show": None,
                                        "must_not_show": None,
                                    }
                                ],
                            },
                        }
                    ],
                },
            }
        )
        routing.update(
            {
                "reason_code": "DIAGNOSTIC_GAPS_FOUND",
                "reason": "Gaps identified in T02.M1.",
                "next_action": "START_ORIENTATION",
            }
        )
    elif event_type == "WORKED_EXAMPLE_REQUESTED":
        journey["current_phase"] = "PHASE_1_ORIENTATION"
        journey["recommended_entry_phase"] = "PHASE_1_ORIENTATION"
        journey["phase_1_orientation"] = {
            "status": "IN_PROGRESS",
            "phase_visit_no": 1,
            "target_micro_skill_ids": ["T02.M1"],
        }
        payload.update(
            {
                "phase": "PHASE_1_ORIENTATION",
                "payload_type": "ORIENTATION_BUNDLE",
                "question_set": None,
                "orientation_bundle": {
                    "target_micro_skill_ids": ["T02.M1"],
                    "delivery_sequence": [
                        {
                            "sequence_no": 1,
                            "content_type": "ORIENTATION_VIDEO",
                            "video": {
                                "video_id": "VID-KS3-T02-ORI",
                                "title": "The Secret Language of Algebra",
                                "asset_url": None,
                                "duration_seconds": 75,
                            },
                            "worked_example": None,
                        },
                        {
                            "sequence_no": 2,
                            "content_type": "WORKED_EXAMPLE",
                            "video": None,
                            "worked_example": {
                                "worked_example_id": "WE-KS3-T02-01",
                                "title": "Many Cases, One General Rule",
                                "covered_micro_skill_ids": ["T02.M1"],
                                "final_answer": "n + 4",
                                "student_answer_required": False,
                                "steps": [
                                    {
                                        "step_id": "WE-KS3-T02-01-S01",
                                        "sequence_no": 1,
                                        "screen_content": "2 + 4",
                                        "narration_text": "Start with one case.",
                                        "must_show": None,
                                        "must_not_show": None,
                                    }
                                ],
                            },
                        }
                    ],
                },
            }
        )
        routing.update(
            {
                "reason_code": "ORIENTATION_STARTED",
                "reason": "Delivering orientation for T02.M1.",
                "next_action": "PLAY_VIDEO_THEN_WORKED_EXAMPLE",
            }
        )
    elif event_type == "ORIENTATION_COMPLETED":
        journey["current_phase"] = "PHASE_2_GUIDED_LEARNING"
        journey["recommended_entry_phase"] = "PHASE_2_GUIDED_LEARNING"
        journey["phase_1_orientation"] = {
            "status": "COMPLETED",
            "phase_visit_no": 1,
            "target_micro_skill_ids": ["T02.M1"],
        }
        journey["phase_2_guided_learning"] = {
            "status": "IN_PROGRESS",
            "phase_visit_no": 1,
            "target_micro_skill_ids": ["T02.M1"],
            "completed_micro_skill_ids": [],
            "remaining_micro_skill_ids": ["T02.M1"],
            "highest_support_used_by_skill": {},
            "current_question_id": "Q-T02-004",
            "current_question_target_micro_skill_ids": ["T02.M1"],
            "used_question_ids": [],
        }
        question_set = deepcopy(
            _diagnostic_started_response()["phase_payload"]["question_set"]
        )
        assert isinstance(question_set, dict)
        question = question_set["questions"][0]
        assert isinstance(question, dict)
        question["question_id"] = "Q-T02-004"
        question["question_usage_id"] = "QU-T02-004-P2"
        question["question_role"] = "GUIDED"
        question["micro_skill_mappings"] = [
            {
                "micro_skill_id": "T02.M5",
                "is_primary": True,
                "weight": 0.7,
            },
            {
                "micro_skill_id": "T02.M1",
                "is_primary": False,
                "weight": 0.3,
            },
        ]
        question["student_view"]["question_text"] = "Solve for x: x + 4 = 9"
        question["tutor_view"]["answer_spec"]["canonical_answer"] = "x = 5"
        question["tutor_view"]["answer_spec"]["accepted_answers"] = ["x = 5"]
        question["tutor_view"]["potential_errors"] = [
            {
                "error_code": "ERR-T02-SUBTRACTION-MISAPPLIED",
                "error_description": "Subtraction was applied incorrectly.",
                "detection_method": "EXACT_NOTATION_MATCH",
                "response_patterns": ["x = 4"],
                "linked_misconceptions": [],
            }
        ]
        payload.update(
            {
                "phase": "PHASE_2_GUIDED_LEARNING",
                "payload_type": "QUESTION_SET",
                "question_set": question_set,
                "orientation_bundle": None,
            }
        )
        routing.update(
            {
                "reason_code": "ORIENTATION_COMPLETED",
                "reason": "Proceeding to Guided Learning for T02.M1.",
                "next_action": "START_GUIDED",
            }
        )
    elif event_type == "CORRECT_ATTEMPT":
        journey["current_phase"] = "PHASE_2_GUIDED_LEARNING"
        journey["recommended_entry_phase"] = "PHASE_2_GUIDED_LEARNING"
        journey["phase_2_guided_learning"] = {
            "status": "IN_PROGRESS",
            "phase_visit_no": 1,
            "target_micro_skill_ids": ["T02.M1"],
            "completed_micro_skill_ids": ["T02.M1"],
            "remaining_micro_skill_ids": [],
            "highest_support_used_by_skill": {"T02.M1": "HINT"},
            "current_question_id": None,
            "used_question_ids": ["Q-T02-004"],
        }
        payload.update(
            {
                "phase": "PHASE_2_GUIDED_LEARNING",
                "payload_type": "QUESTION_SET",
                "question_set": {"questions": []},
                "orientation_bundle": None,
            }
        )
        response["event_result"] = {
            "skill_updates": [
                {
                    "micro_skill_id": "T02.M1",
                    "new_status": "COMPLETED",
                }
            ]
        }
        routing.update(
            {
                "reason_code": "GUIDED_IN_PROGRESS",
                "reason": "T02.M1 completed. Remaining: none.",
                "next_action": "WAIT_FOR_STUDENT_RESPONSE",
            }
        )
    elif event_type == "INCORRECT_ATTEMPT":
        response = _event_response("ORIENTATION_COMPLETED", request_id)
        journey = response["journey_state"]
        payload = response["phase_payload"]
        routing = response["routing"]
        assert isinstance(journey, dict)
        assert isinstance(payload, dict)
        assert isinstance(routing, dict)
        journey["phase_2_guided_learning"] = {
            "status": "IN_PROGRESS",
            "phase_visit_no": 1,
            "target_micro_skill_ids": ["T02.M1"],
            "completed_micro_skill_ids": [],
            "remaining_micro_skill_ids": ["T02.M1"],
            "highest_support_used_by_skill": {"T02.M1": "HINT"},
            "current_question_id": "Q-T02-004",
            "current_question_target_micro_skill_ids": ["T02.M1"],
            "used_question_ids": [],
        }
        payload["payload_type"] = "SUPPORT_AND_RETRY"
        payload["support_to_serve"] = {
            "support_type": "HINT_AND_VISUAL_CUE",
            "items": [
                {
                    "content_type": "HINT",
                    "content_id": "HINT-T02-M1-L1",
                    "content": "Undo the addition first.",
                    "level": 1,
                },
                {
                    "content_type": "VISUAL_CUE",
                    "content_id": "VC-T02-COEFFICIENT-COUNT",
                    "description": "Count the equal letter terms.",
                    "actions": [
                        {
                            "action": "HIGHLIGHT_TOKEN",
                            "target": "x",
                            "style": "VARIABLE",
                        }
                    ],
                }
            ],
            "retry_same_question": True,
        }
        routing.update(
            {
                "reason_code": "GUIDED_HINT_REQUIRED",
                "reason": "Student incorrect. Delivering support for retry.",
                "next_action": "DELIVER_SUPPORT_AND_RETRY",
            }
        )
    elif event_type == "GUIDED_PHASE_COMPLETED":
        response = _event_response("ORIENTATION_COMPLETED", request_id)
        journey = response["journey_state"]
        payload = response["phase_payload"]
        routing = response["routing"]
        assert isinstance(journey, dict)
        assert isinstance(payload, dict)
        assert isinstance(routing, dict)
        journey["current_phase"] = "PHASE_3_INDEPENDENT_PRACTICE"
        journey["recommended_entry_phase"] = "PHASE_3_INDEPENDENT_PRACTICE"
        journey["phase_2_guided_learning"]["status"] = "COMPLETED"
        journey["phase_2_guided_learning"]["completed_micro_skill_ids"] = ["T02.M1"]
        journey["phase_2_guided_learning"]["remaining_micro_skill_ids"] = []
        journey["phase_3_independent_practice"] = {
            "status": "IN_PROGRESS",
            "phase_visit_no": 1,
            "target_micro_skill_ids": ["T02.M1"],
            "remaining_micro_skill_ids": ["T02.M1"],
            "verified_micro_skill_ids": [],
            "current_question_id": "Q-T02-004",
            "used_question_ids": [],
        }
        payload["phase"] = "PHASE_3_INDEPENDENT_PRACTICE"
        payload["payload_type"] = "QUESTION_SET"
        routing.update(
            {
                "reason_code": "GUIDED_COMPLETED",
                "reason": "Proceeding to Independent Practice.",
                "next_action": "START_INDEPENDENT",
            }
        )
    elif event_type in {
        "GUIDED_SUPPORT_ESCALATION_REQUIRED",
        "GUIDED_STUCK_SUPPORT_REQUIRED",
    }:
        response = _event_response("ORIENTATION_COMPLETED", request_id)
        journey = response["journey_state"]
        payload = response["phase_payload"]
        routing = response["routing"]
        assert isinstance(journey, dict)
        assert isinstance(payload, dict)
        assert isinstance(routing, dict)
        journey["phase_2_guided_learning"]["highest_support_used_by_skill"] = {
            "T02.M1": "SCAFFOLD"
        }
        payload["payload_type"] = "SCAFFOLD"
        payload["support_to_serve"] = {
            "support_type": "SCAFFOLD",
            "scaffold_id": "SCF-T02-M1",
            "current_step_id": "SCF-T02-M1-S1",
            "prompt": "Which operation should you undo first?",
            "expected_response": "Addition",
            "steps": [
                {
                    "step_id": "SCF-T02-M1-S1",
                    "prompt": "Which operation should you undo first?",
                    "expected_response": "Addition",
                },
                {
                    "step_id": "SCF-T02-M1-S2",
                    "prompt": "What should you subtract from both sides?",
                    "expected_response": "4",
                },
                {
                    "step_id": "SCF-T02-M1-S3",
                    "prompt": "Where should you subtract 4?",
                    "expected_response": "Both sides",
                },
                {
                    "step_id": "SCF-T02-M1-S4",
                    "prompt": "What is the resulting value of x?",
                    "expected_response": "x = 5",
                }
            ],
            "retry_same_question": True,
        }
        routing.update(
            {
                "reason_code": "GUIDED_SCAFFOLD_REQUIRED",
                "reason": "Delivering scaffolded support.",
                "next_action": "DELIVER_SCAFFOLD_STEP",
            }
        )
        if event_type == "GUIDED_SUPPORT_ESCALATION_REQUIRED":
            status = response["status"]
            assert isinstance(status, dict)
            status["intervention_required"] = True
            status["intervention_reason"] = "WRONG_4"
    return response


def _session_opened_response(phase: str) -> dict[str, object]:
    if phase == "PHASE_0_DIAGNOSTIC":
        return _eight_skill_diagnostic_response()
    if phase == "PHASE_1_ORIENTATION":
        return _event_response("DIAGNOSTIC_COMPLETED", "")
    if phase == "PHASE_2_GUIDED_LEARNING":
        return _event_response("ORIENTATION_COMPLETED", "")
    if phase == "PHASE_3_INDEPENDENT_PRACTICE":
        return _event_response("GUIDED_PHASE_COMPLETED", "")
    if phase == "REVIEW":
        response = _event_response("GUIDED_PHASE_COMPLETED", "")
        journey = response["journey_state"]
        payload = response["phase_payload"]
        assert isinstance(journey, dict)
        assert isinstance(payload, dict)
        journey["current_phase"] = "REVIEW"
        journey["recommended_entry_phase"] = "REVIEW"
        journey["review"] = {"status": "IN_PROGRESS", "phase_visit_no": 1}
        payload.update(
            {
                "phase": "REVIEW",
                "payload_type": "REVIEW_SUMMARY",
                "question_set": None,
                "review_summary": {"summary": "Review your completed work."},
            }
        )
        return response
    raise ValueError(f"Unsupported test phase: {phase}")


def _recommended_not_started_response(phase: str) -> dict[str, object]:
    response = _session_opened_response(phase)
    journey = response["journey_state"]
    assert isinstance(journey, dict)
    if phase == "PHASE_2_GUIDED_LEARNING":
        journey["current_phase"] = "PHASE_1_ORIENTATION"
        phase_state = journey["phase_2_guided_learning"]
    elif phase == "PHASE_3_INDEPENDENT_PRACTICE":
        journey["current_phase"] = "PHASE_2_GUIDED_LEARNING"
        phase_state = journey["phase_3_independent_practice"]
    else:
        raise ValueError(f"Unsupported recommended phase: {phase}")
    assert isinstance(phase_state, dict)
    phase_state.update(
        {
            "status": "NOT_STARTED",
            "phase_visit_no": None,
            "current_question_id": None,
            "used_question_ids": [],
        }
    )
    return response


def _independent_rescue_response() -> dict[str, object]:
    response = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
    payload = response["phase_payload"]
    journey = response["journey_state"]
    assert isinstance(payload, dict)
    assert isinstance(journey, dict)
    phase_state = journey["phase_3_independent_practice"]
    assert isinstance(phase_state, dict)
    phase_state["status"] = "RESCUE_REQUIRED"
    payload["payload_type"] = "RESCUE_AND_FRESH_QUESTION"
    payload["rescue_to_serve"] = {
        "parallel_example": {
            "worked_steps": ["Undo the addition.", "Then divide both sides."]
        }
    }
    return response


def _use_live_student_model(
    monkeypatch: pytest.MonkeyPatch,
    post_json: SessionEventPost,
) -> None:
    settings = Settings(
        student_model_url="https://student-model.example",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", post_json)


def test_session_start_uses_schema_3_diagnostic_contract_by_default(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, timeout_seconds, retry_count
        captured.update({"url": url, "payload": payload, "headers": headers})
        response = _eight_skill_diagnostic_response()
        response["request_id"] = payload["request_id"]
        return response

    settings = Settings(
        student_model_url="https://student-model.example",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", fake_post_json)

    response = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "VOICE",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_phase"] == "DIAGNOSTIC"
    assert body["current_question"] == "What does 4y mean?"
    assert body["question_type"] == "SINGLE_CHOICE"
    assert body["question_id"] == "Q-T02-D01"
    assert body["show_canvas"] is False
    assert body["show_hint_button"] is False
    assert body["show_visual_cue"] is False
    assert body["show_scaffold_panel"] is False
    assert body["message"] == (
        "I’ll ask you a few short questions to understand what you already know "
        "about this topic. Select the answer you think is correct."
    )
    assert body["diagnostic_transition_message"] == "Okay. Let’s continue."
    assert body["diagnostic_transition_messages"] == [
        "Okay. Let’s continue with the next one.",
        "Now, see what you think about this question.",
        "Let’s try the next one.",
        "Here’s another one for you to consider.",
        "Take a look at this one and choose what you think is correct.",
        "Ready for another? Try this one.",
        "Let’s keep going with one more question.",
    ]
    assert body["student_model_state"]["target_micro_skill_ids"] == [
        "T02.M1",
        "T02.M2",
        "T02.M3",
        "T02.M4",
        "T02.M5",
        "T02.M6",
        "T02.M7",
        "T02.M8",
    ]
    assert len(body["student_model_event"]["phase_payload"]["question_set"]["questions"]) == 8
    public_json = response.text
    for private_field in (
        "correct_answer",
        "canonical_answer",
        "accepted_answers",
        "tutor_view",
        "micro_skill_mappings",
        "potential_errors",
        "results_by_skill",
        "weak_micro_skill_ids",
        "reason_code",
    ):
        assert private_field not in public_json
    stored = session_service._sessions[body["session_id"]]
    assert stored.correct_answer == "B"
    assert stored.student_model_event is not None
    internal_question_set = stored.student_model_event.phase_payload.question_set
    assert internal_question_set is not None
    assert internal_question_set.questions[0].tutor_view.answer_spec.canonical_answer == "B"
    assert captured["url"] == "https://student-model.example/session/event"
    assert captured["headers"] == {"Authorization": "Bearer test-token"}
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["event_type"] == "SESSION_OPENED"
    assert payload["topic_id"] == "ALG-ORI-02"
    assert payload["student_id"] == "ST001"
    assert isinstance(payload["timestamp"], str)


@pytest.mark.parametrize(
    ("student_model_phase", "expected_phase", "expected_question_id"),
    [
        ("PHASE_0_DIAGNOSTIC", "DIAGNOSTIC", "Q-T02-D01"),
        ("PHASE_1_ORIENTATION", "CONCEPT_ORIENTATION", None),
        ("PHASE_2_GUIDED_LEARNING", "GUIDED_PRACTICE", "Q-T02-004"),
        (
            "PHASE_3_INDEPENDENT_PRACTICE",
            "INDEPENDENT_PRACTICE",
            "Q-T02-004",
        ),
        ("REVIEW", "REVIEW", None),
    ],
)
def test_session_start_restores_each_student_model_phase(
    monkeypatch: pytest.MonkeyPatch,
    student_model_phase: str,
    expected_phase: str,
    expected_question_id: str | None,
) -> None:
    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        response = _session_opened_response(student_model_phase)
        response["request_id"] = payload["request_id"]
        return response

    _use_live_student_model(monkeypatch, fake_post_json)

    response = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_phase"] == expected_phase
    assert body["ui_state"] == expected_phase
    assert body["question_id"] == expected_question_id
    assert body["recommended_entry_phase"] == expected_phase
    assert body["student_model_event"]["phase_payload"]["phase"] == student_model_phase


def test_session_start_restores_saved_question_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        response = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
        response["request_id"] = payload["request_id"]
        journey = response["journey_state"]
        phase_payload = response["phase_payload"]
        assert isinstance(journey, dict)
        assert isinstance(phase_payload, dict)
        phase_state = journey["phase_3_independent_practice"]
        question_set = phase_payload["question_set"]
        assert isinstance(phase_state, dict)
        assert isinstance(question_set, dict)
        questions = question_set["questions"]
        assert isinstance(questions, list)
        second_question = deepcopy(questions[0])
        assert isinstance(second_question, dict)
        second_question["question_id"] = "Q-T02-I02"
        second_question["question_usage_id"] = "QU-T02-I02-P3"
        student_view = second_question["student_view"]
        tutor_view = second_question["tutor_view"]
        assert isinstance(student_view, dict)
        assert isinstance(tutor_view, dict)
        answer_spec = tutor_view["answer_spec"]
        assert isinstance(answer_spec, dict)
        student_view["question_text"] = "Solve for x: 2x = 14"
        answer_spec["canonical_answer"] = "x = 7"
        answer_spec["accepted_answers"] = ["x = 7"]
        questions.append(second_question)
        phase_state["current_question_id"] = "Q-T02-I02"
        return response

    _use_live_student_model(monkeypatch, fake_post_json)

    response = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_phase"] == "INDEPENDENT_PRACTICE"
    assert body["question_id"] == "Q-T02-I02"
    assert body["question_number"] == 2
    assert body["current_question"] == "Solve for x: 2x = 14"
    assert session_service._sessions[body["session_id"]].correct_answer == "x = 7"


def test_repeated_session_start_restores_authoritative_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_events: list[dict[str, object]] = []

    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        captured_events.append(payload)
        response = _session_opened_response("PHASE_2_GUIDED_LEARNING")
        response["request_id"] = payload["request_id"]
        return response

    _use_live_student_model(monkeypatch, fake_post_json)
    request = {
        "student_id": "ST001",
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "interaction_mode": "TEXT",
    }

    first = client.post("/session/start", json=request)
    second = client.post("/session/start", json=request)

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["session_id"] != second_body["session_id"]
    assert first_body["current_phase"] == second_body["current_phase"] == "GUIDED_PRACTICE"
    assert first_body["question_id"] == second_body["question_id"] == "Q-T02-004"
    assert first_body["student_model_event"]["journey_state"] == second_body[
        "student_model_event"
    ]["journey_state"]
    assert [event["event_type"] for event in captured_events] == [
        "SESSION_OPENED",
        "SESSION_OPENED",
    ]
    restored = client.get(f"/session/{second_body['session_id']}")
    assert restored.status_code == 200
    assert restored.json() == second_body


@pytest.mark.parametrize(
    "failure",
    [
        "IDENTITY_MISMATCH",
        "INCONSISTENT_PHASE",
        "MISMATCHED_TYPE",
        "MISSING_CONTENT",
    ],
)
def test_session_start_rejects_invalid_restore_without_local_state(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    event_types: list[object] = []

    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        event_types.append(payload["event_type"])
        response = _session_opened_response("PHASE_2_GUIDED_LEARNING")
        response["request_id"] = payload["request_id"]
        if failure == "IDENTITY_MISMATCH":
            journey = response["journey_state"]
            assert isinstance(journey, dict)
            journey["student_id"] = "ST999"
        elif failure == "INCONSISTENT_PHASE":
            journey = response["journey_state"]
            assert isinstance(journey, dict)
            journey["recommended_entry_phase"] = "PHASE_1_ORIENTATION"
        else:
            phase_payload = response["phase_payload"]
            assert isinstance(phase_payload, dict)
            if failure == "MISMATCHED_TYPE":
                phase_payload["payload_type"] = "ORIENTATION_BUNDLE"
            else:
                phase_payload["question_set"] = None
        return response

    _use_live_student_model(monkeypatch, fake_post_json)
    sessions_before = set(session_service._sessions)

    response = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )

    assert response.status_code == 503
    assert event_types == ["SESSION_OPENED"]
    assert set(session_service._sessions) == sessions_before


def test_session_start_restores_guided_support_presentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        response = _event_response("INCORRECT_ATTEMPT", str(payload["request_id"]))
        journey = response["journey_state"]
        assert isinstance(journey, dict)
        phase_state = journey["phase_2_guided_learning"]
        assert isinstance(phase_state, dict)
        phase_state["current_attempt_sequence"] = 2
        phase_state["current_hint_count"] = 1
        return response

    _use_live_student_model(monkeypatch, fake_post_json)

    response = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_phase"] == "GUIDED_PRACTICE"
    assert body["question_id"] == "Q-T02-004"
    assert body["show_visual_cue"] is True
    assert body["show_scaffold_panel"] is False
    assert body["message"] == "Undo the addition first."
    assert body["attempt_count"] == 1
    assert body["hint_count"] == 1


def test_session_start_restores_independent_rescue_presentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        response = _independent_rescue_response()
        response["request_id"] = payload["request_id"]
        return response

    _use_live_student_model(monkeypatch, fake_post_json)
    response = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_phase"] == "INDEPENDENT_PRACTICE"
    assert body["show_scaffold_panel"] is True
    assert "scaffold_steps" not in body


@pytest.mark.parametrize(
    ("phase", "expected_initializer"),
    [
        ("PHASE_2_GUIDED_LEARNING", "GUIDED_QUESTION_SET_REQUESTED"),
        ("PHASE_3_INDEPENDENT_PRACTICE", "INDEPENDENT_QUESTION_SET_REQUESTED"),
    ],
)
def test_restored_not_started_phase_initializes_before_answer(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    expected_initializer: str,
) -> None:
    events: list[dict[str, object]] = []

    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        events.append(payload)
        event_type = str(payload["event_type"])
        if event_type == "SESSION_OPENED":
            response = _recommended_not_started_response(phase)
        elif event_type == expected_initializer:
            response = _session_opened_response(phase)
            phase_payload = response["phase_payload"]
            assert isinstance(phase_payload, dict)
            question_set = phase_payload["question_set"]
            assert isinstance(question_set, dict)
            question = question_set["questions"][0]
            assert isinstance(question, dict)
            question["question_id"] = "Q-T02-INITIALIZED"
            journey = response["journey_state"]
            assert isinstance(journey, dict)
            phase_key = (
                "phase_2_guided_learning"
                if phase == "PHASE_2_GUIDED_LEARNING"
                else "phase_3_independent_practice"
            )
            phase_state = journey[phase_key]
            assert isinstance(phase_state, dict)
            phase_state["current_question_id"] = "Q-T02-INITIALIZED"
        elif phase == "PHASE_2_GUIDED_LEARNING":
            response = _event_response("INCORRECT_ATTEMPT", "")
        else:
            response = _session_opened_response(phase)
        response["request_id"] = payload["request_id"]
        return response

    _use_live_student_model(monkeypatch, fake_post_json)
    started = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert started.status_code == 200
    body = started.json()
    session = session_service._sessions[body["session_id"]]
    session_service._sessions[body["session_id"]] = session.model_copy(
        update={
            "current_question": None,
            "question_type": None,
            "question_id": None,
            "correct_answer": None,
        }
    )

    answered = client.post(
        "/interaction",
        json={
            "session_id": body["session_id"],
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-RESTORED-ANSWER-1",
            "previous_tutor_turn_id": session.last_tutor_turn_id,
            "text_input": "x = 4",
            "current_phase": body["current_phase"],
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": body["question_id"],
            "hint_count": 0,
        },
    )

    assert answered.status_code == 200
    assert [event["event_type"] for event in events[:3]] == [
        "SESSION_OPENED",
        expected_initializer,
        "INCORRECT_ATTEMPT",
    ]
    assert events[2]["question_id"] == "Q-T02-INITIALIZED"
    if phase == "PHASE_3_INDEPENDENT_PRACTICE":
        assert events[1]["phase2_repair_results"] == [
            {"micro_skill_id": "T02.M1", "highest_support_used": "NONE"}
        ]
        assert events[1]["used_question_ids"] == []
    else:
        assert events[1]["target_micro_skill_ids"] == ["T02.M1"]
def test_student_model_request_ids_are_stable_across_retries() -> None:
    first = session_service._student_model_request_id(
        "SESSION001",
        "TURN001",
        "DIAGNOSTIC_QUESTION_SET_REQUESTED",
    )
    second = session_service._student_model_request_id(
        "SESSION001",
        "TURN001",
        "DIAGNOSTIC_QUESTION_SET_REQUESTED",
    )

    assert first == second == "SESSION001:TURN001:DIAGNOSTIC_QUESTION_SET_REQUESTED"


def test_diagnostic_and_orientation_lifecycle_uses_micro_skills(monkeypatch) -> None:
    atomic_settings = Settings(student_model_atomic_guided_events_enabled=True)
    monkeypatch.setattr(
        interaction_service,
        "get_settings",
        lambda: atomic_settings,
    )
    events: list[dict[str, object]] = []

    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        events.append(payload)
        event_type = str(payload["event_type"])
        incorrect_count = sum(
            event["event_type"] == "INCORRECT_ATTEMPT" for event in events
        )
        response_type = (
            "GUIDED_SUPPORT_ESCALATION_REQUIRED"
            if event_type == "INCORRECT_ATTEMPT" and incorrect_count == 4
            else event_type
        )
        return _event_response(response_type, str(payload["request_id"]))

    settings = Settings(
        student_model_url="https://student-model.example",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", fake_post_json)

    started = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "VOICE",
        },
    )
    session_id = started.json()["session_id"]

    diagnostic = client.post(
        f"/session/{session_id}/diagnostic/complete",
        json={
            "student_id": "ST001",
            "answers": [
                {"question_id": "Q-T02-D01", "student_response": "A"},
            ],
        },
    )

    assert diagnostic.status_code == 200
    assert diagnostic.json()["current_phase"] == "CONCEPT_ORIENTATION"
    assert diagnostic.json()["current_question"] is None
    assert diagnostic.json()["message"] == (
        "I found one idea that will be useful to look at before we continue. "
        "Let’s watch a short explanation together."
    )
    assert diagnostic.json()["orientation_messages"]["before_video_message"] == (
        "Watch how the numbers change and what stays the same. "
        "You can pause or replay any part."
    )
    assert events[-1]["micro_skill_results"] == [
        {"micro_skill_id": "T02.M1", "result": "INCORRECT"}
    ]

    premature_completion = client.post(
        f"/session/{session_id}/orientation/complete",
        json={
            "student_id": "ST001",
            "completed_video_ids": [],
            "completed_worked_example_ids": [],
        },
    )
    assert premature_completion.status_code == 409
    assert len(events) == 2

    orientation_started = client.post(
        f"/session/{session_id}/orientation/start",
        json={"student_id": "ST001"},
    )
    assert orientation_started.status_code == 200
    assert events[-1]["target_micro_skill_ids"] == ["T02.M1"]
    assert orientation_started.json()["message"] == (
        "Watch how the numbers change and what stays the same. "
        "You can pause or replay any part."
    )

    incomplete_orientation = client.post(
        f"/session/{session_id}/orientation/complete",
        json={
            "student_id": "ST001",
            "completed_video_ids": ["VID-KS3-T02-ORI"],
            "completed_worked_example_ids": [],
        },
    )
    assert incomplete_orientation.status_code == 409
    assert "WE-KS3-T02-01" in incomplete_orientation.json()["message"]
    assert len(events) == 3

    orientation_completed = client.post(
        f"/session/{session_id}/orientation/complete",
        json={
            "student_id": "ST001",
            "completed_video_ids": ["VID-KS3-T02-ORI"],
            "completed_worked_example_ids": ["WE-KS3-T02-01"],
        },
    )

    assert orientation_completed.status_code == 200
    completed = orientation_completed.json()
    assert completed["current_phase"] == "GUIDED_PRACTICE"
    assert completed["question_id"] == "Q-T02-004"
    assert completed["student_model_state"]["target_micro_skill_ids"] == ["T02.M1"]
    assert completed["message"] == "Now let’s use this idea together in a question."
    assert [event["event_type"] for event in events] == [
        "SESSION_OPENED",
        "DIAGNOSTIC_COMPLETED",
        "WORKED_EXAMPLE_REQUESTED",
        "ORIENTATION_COMPLETED",
    ]

    event_count_before_stuck = len(events)
    for expected_stuck_count in (1, 2):
        stuck = client.post(
            "/interaction",
            json={
                "session_id": session_id,
                "student_id": "ST001",
                "interaction_type": "ANSWER_SUBMISSION",
                "input_source": "TEXT",
                "turn_id": f"TURN-STUCK-{expected_stuck_count}",
                "text_input": "I don't know",
                "current_phase": "GUIDED_PRACTICE",
                "concept_id": "ALG_LINEAR_ONE_STEP",
                "question_id": "Q-T02-004",
                "hint_count": 0,
            },
        )

        assert stuck.status_code == 200
        assert stuck.json()["attempt_count"] == 0
        if expected_stuck_count == 1:
            assert len(events) == event_count_before_stuck
            assert "scaffold_steps" not in stuck.json()
            assert stuck.json()["current_scaffold_step_id"] is None
        else:
            assert len(events) == event_count_before_stuck + 1
            assert events[-1]["event_type"] == "GUIDED_STUCK_SUPPORT_REQUIRED"
            assert events[-1]["micro_skill_id"] == "T02.M1"
            assert stuck.json()["scaffold_step_text"] == (
                "Which operation should you undo first?"
            )
            assert stuck.json()["current_scaffold_step_id"] == "SCF-T02-M1-S1"
            assert stuck.json()["message"] == "Which operation should you undo first?"
        assert "scaffold_expected_response" not in stuck.json()
        assert client.get(f"/session/{session_id}").json()["stuck_count"] == (
            expected_stuck_count
        )

    scaffold_event_count = len(events)
    wrong_scaffold_step = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-SCAFFOLD-WRONG-1",
            "text_input": "subtraction",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )
    assert wrong_scaffold_step.status_code == 200
    assert len(events) == scaffold_event_count
    assert wrong_scaffold_step.json()["current_scaffold_step_id"] == "SCF-T02-M1-S1"
    assert wrong_scaffold_step.json()["scaffold_step_number"] == 1
    assert "scaffold_steps" not in wrong_scaffold_step.json()
    assert wrong_scaffold_step.json()["scaffold_step_text"] == (
        "Which operation should you undo first?"
    )
    assert wrong_scaffold_step.json()["message"] == (
        "Let’s stay with this step: Which operation should you undo first?"
    )

    next_scaffold_step = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-SCAFFOLD-NEXT-1",
            "text_input": "addition",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )
    assert next_scaffold_step.status_code == 200
    assert len(events) == scaffold_event_count
    assert next_scaffold_step.json()["current_scaffold_step_id"] == "SCF-T02-M1-S2"
    assert next_scaffold_step.json()["scaffold_step_number"] == 2
    assert next_scaffold_step.json()["total_scaffold_steps"] == 4
    assert next_scaffold_step.json()["scaffold_step_text"] == (
        "What should you subtract from both sides?"
    )
    assert next_scaffold_step.json()["scaffold_step_voice"] == (
        "What should you subtract from both sides?"
    )

    third_scaffold_step = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-SCAFFOLD-THIRD-1",
            "text_input": "4",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )
    assert third_scaffold_step.status_code == 200
    assert third_scaffold_step.json()["current_scaffold_step_id"] == "SCF-T02-M1-S3"
    assert third_scaffold_step.json()["scaffold_step_number"] == 3
    assert third_scaffold_step.json()["scaffold_step_text"] == (
        "Where should you subtract 4?"
    )

    fourth_scaffold_step = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-SCAFFOLD-FOURTH-1",
            "text_input": "on both sides",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )
    assert fourth_scaffold_step.status_code == 200
    assert fourth_scaffold_step.json()["current_scaffold_step_id"] == "SCF-T02-M1-S4"
    assert fourth_scaffold_step.json()["scaffold_step_number"] == 4
    assert fourth_scaffold_step.json()["scaffold_step_text"] == (
        "What is the resulting value of x?"
    )

    completed_scaffold = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-SCAFFOLD-COMPLETE-1",
            "text_input": "x = 5",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )
    assert completed_scaffold.status_code == 200
    assert len(events) == scaffold_event_count
    assert completed_scaffold.json()["current_scaffold_step_id"] is None
    assert completed_scaffold.json()["show_scaffold_panel"] is False
    assert "scaffold_steps" not in completed_scaffold.json()
    assert completed_scaffold.json()["message"] == (
        "Now use those steps on the original question. What would you try first?"
    )

    guided_incorrect = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-GUIDED-WRONG-1",
            "text_input": "x = 4",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )

    assert guided_incorrect.status_code == 200
    assert events[-1]["event_type"] == "INCORRECT_ATTEMPT"
    assert events[-1]["question_id"] == "Q-T02-004"
    assert events[-1]["micro_skill_ids"] == ["T02.M1"]
    assert events[-1]["student_response"] == "x = 4"
    assert events[-1]["error_code"] == "ERR-T02-SUBTRACTION-MISAPPLIED"
    assert client.get(f"/session/{session_id}").json()["stuck_count"] == 0
    assert guided_incorrect.json()["student_model_state"][
        "highest_support_used_by_skill"
    ] == {"T02.M1": "HINT"}
    assert guided_incorrect.json()["show_visual_cue"] is True
    assert guided_incorrect.json()["visual_cue"] == {
        "show": True,
            "cue_type": "VC-T02-COEFFICIENT-COUNT",
            "description": "Count the equal letter terms.",
            "actions": [
                {
                    "action": "HIGHLIGHT_TOKEN",
                    "target": "x",
                    "style": "VARIABLE",
                }
            ],
        }
    assert guided_incorrect.json()["message"] == (
        "Let us review the equation and try the next step carefully. "
        "Undo the addition first."
    )

    for answer in ("x = 3", "x = 2"):
        guided_incorrect = client.post(
            "/interaction",
            json={
                "session_id": session_id,
                "student_id": "ST001",
                "interaction_type": "ANSWER_SUBMISSION",
                "input_source": "TEXT",
                "turn_id": f"TURN-GUIDED-WRONG-{answer}",
                "text_input": answer,
                "current_phase": "GUIDED_PRACTICE",
                "concept_id": "ALG_LINEAR_ONE_STEP",
                "question_id": "Q-T02-004",
                "hint_count": 0,
            },
        )
        assert guided_incorrect.status_code == 200

    assert events[-1]["event_type"] == "INCORRECT_ATTEMPT"
    assert guided_incorrect.json()["show_scaffold_panel"] is False

    fourth_wrong = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-GUIDED-WRONG-4",
            "text_input": "x = 4",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )

    assert fourth_wrong.status_code == 200
    assert events[-1]["event_type"] == "GUIDED_SUPPORT_ESCALATION_REQUIRED"
    assert events[-1]["triggering_response"] == "x = 4"
    assert events[-1]["error_code"] == "ERR-T02-SUBTRACTION-MISAPPLIED"
    assert fourth_wrong.json()["show_scaffold_panel"] is True
    assert events[-1]["micro_skill_id"] == "T02.M1"
    assert fourth_wrong.json()["current_scaffold_step_id"] == "SCF-T02-M1-S1"
    assert fourth_wrong.json()["wrong_attempt_count"] == 4
    assert fourth_wrong.json()["evaluation_reason_code"] == "RESPONSE_INCORRECT"
    assert fourth_wrong.json()["support_reason_code"] == "WRONG_4_INTERVENTION"
    assert fourth_wrong.json()["routing_reason_code"] == "GUIDED_SCAFFOLD_REQUIRED"
    assert fourth_wrong.json()["intervention_triggered"] is True

    for scaffold_answer in ("addition", "4", "on both sides", "x = 5"):
        scaffold_response = client.post(
            "/interaction",
            json={
                "session_id": session_id,
                "student_id": "ST001",
                "interaction_type": "ANSWER_SUBMISSION",
                "input_source": "TEXT",
                "turn_id": f"TURN-SCAFFOLD-ANSWER-{scaffold_answer}",
                "text_input": scaffold_answer,
                "current_phase": "GUIDED_PRACTICE",
                "concept_id": "ALG_LINEAR_ONE_STEP",
                "question_id": "Q-T02-004",
                "hint_count": 0,
            },
        )
        assert scaffold_response.status_code == 200

    assert scaffold_response.json()["show_scaffold_panel"] is False
    assert scaffold_response.json()["current_scaffold_step_id"] is None

    guided = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-GUIDED-CORRECT-1",
            "text_input": "x = 5",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )

    assert guided.status_code == 200
    assert events[-2]["event_type"] == "CORRECT_ATTEMPT"
    assert events[-2]["question_id"] == "Q-T02-004"
    assert events[-2]["micro_skill_ids"] == ["T02.M1"]
    assert events[-2]["student_response"] == "x = 5"
    assert events[-2]["support_used"] == "SCAFFOLD"
    assert events[-1]["event_type"] == "GUIDED_PHASE_COMPLETED"
    assert events[-1]["completed_micro_skill_ids"] == ["T02.M1"]
    assert guided.json()["current_phase"] == "INDEPENDENT_PRACTICE"
    state = guided.json()["student_model_state"]
    assert state["target_micro_skill_ids"] == ["T02.M1"]
    assert state["completed_micro_skill_ids"] == []


def test_diagnostic_no_gaps_honors_direct_independent_transition(monkeypatch) -> None:
    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        if payload["event_type"] != "DIAGNOSTIC_COMPLETED":
            response = _diagnostic_started_response()
            response["request_id"] = payload["request_id"]
            return response
        response = deepcopy(_diagnostic_started_response())
        response["request_id"] = payload["request_id"]
        journey = response["journey_state"]
        phase_payload = response["phase_payload"]
        routing = response["routing"]
        assert isinstance(journey, dict)
        assert isinstance(phase_payload, dict)
        assert isinstance(routing, dict)
        journey["mastery_status"] = "NEARLY_MASTERED"
        journey["current_phase"] = "PHASE_3_INDEPENDENT_PRACTICE"
        journey["recommended_entry_phase"] = "PHASE_3_INDEPENDENT_PRACTICE"
        journey["phase_3_independent_practice"] = {
            "status": "IN_PROGRESS",
            "phase_visit_no": 1,
            "target_micro_skill_ids": ["T02.M1"],
            "verified_micro_skill_ids": [],
            "unresolved_micro_skill_ids": [],
            "remaining_micro_skill_ids": ["T02.M1"],
            "current_question_id": "Q-T02-I01",
            "used_question_ids": ["Q-T02-D01"],
        }
        question_set = deepcopy(phase_payload["question_set"])
        assert isinstance(question_set, dict)
        question = question_set["questions"][0]
        assert isinstance(question, dict)
        question["question_id"] = "Q-T02-I01"
        question["question_usage_id"] = "QU-T02-I01-P3"
        question["question_role"] = "INDEPENDENT"
        phase_payload.update(
            {
                "phase": "PHASE_3_INDEPENDENT_PRACTICE",
                "payload_type": "QUESTION_SET",
                "question_set": question_set,
            }
        )
        routing.update(
            {
                "reason_code": "DIAGNOSTIC_NO_GAPS",
                "reason": "No diagnostic gaps.",
                "next_action": "START_INDEPENDENT",
            }
        )
        return response

    settings = Settings(
        student_model_url="https://student-model.example",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", fake_post_json)

    started = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    ).json()
    completed = client.post(
        f"/session/{started['session_id']}/diagnostic/complete",
        json={
            "student_id": "ST001",
            "answers": [
                {"question_id": "Q-T02-D01", "student_response": "B"},
            ],
        },
    )

    assert completed.status_code == 200
    body = completed.json()
    assert body["current_phase"] == "INDEPENDENT_PRACTICE"
    assert body["phase_transitions"][-1]["entry_reason"] == "DIAGNOSTIC_NO_GAPS"
    assert body["message"] == (
        "You already understand the main ideas in this topic. "
        "Let’s try some more challenging questions on your own."
    )


def test_diagnostic_requires_every_mapping_for_one_skill_to_be_correct(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        captured.update(payload)
        if payload["event_type"] == "SESSION_OPENED":
            response = _diagnostic_started_response()
            phase_payload = response["phase_payload"]
            assert isinstance(phase_payload, dict)
            question_set = phase_payload["question_set"]
            assert isinstance(question_set, dict)
            questions = question_set["questions"]
            assert isinstance(questions, list)
            second = deepcopy(questions[0])
            second["question_id"] = "Q-T02-D01-B"
            second["question_usage_id"] = "QU-T02-D01-B-P0"
            questions.append(second)
            response["request_id"] = payload["request_id"]
            return response
        return _event_response(
            str(payload["event_type"]),
            str(payload["request_id"]),
        )

    settings = Settings(
        student_model_url="https://student-model.example",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", fake_post_json)

    started = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    ).json()
    completed = client.post(
        f"/session/{started['session_id']}/diagnostic/complete",
        json={
            "student_id": "ST001",
            "answers": [
                {"question_id": "Q-T02-D01", "student_response": "B"},
                {"question_id": "Q-T02-D01-B", "student_response": "A"},
            ],
        },
    )

    assert completed.status_code == 200
    assert captured["micro_skill_results"] == [
        {"micro_skill_id": "T02.M1", "result": "INCORRECT"}
    ]
    assert completed.json()["current_phase"] == "CONCEPT_ORIENTATION"


def test_diagnostic_rejects_incomplete_answers_without_transition(monkeypatch) -> None:
    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        response = _diagnostic_started_response()
        response["request_id"] = payload["request_id"]
        return response

    settings = Settings(
        student_model_url="https://student-model.example",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", fake_post_json)

    started = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    ).json()
    rejected = client.post(
        f"/session/{started['session_id']}/diagnostic/complete",
        json={"student_id": "ST001", "answers": []},
    )

    assert rejected.status_code == 422
    stored = session_service._sessions[started["session_id"]]
    assert stored.current_phase == "DIAGNOSTIC"
    assert stored.phase_transitions == []


def test_session_start_requires_bearer_token() -> None:
    unauthenticated = TestClient(app)
    response = unauthenticated.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert response.status_code == 401


def test_session_start_rejects_malformed_student_model_response(monkeypatch) -> None:
    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, payload, headers, timeout_seconds, retry_count
        return {"schema_version": "3.0"}

    settings = Settings(
        student_model_url="https://student-model.example",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", fake_post_json)
    sessions_before = set(session_service._sessions)

    response = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )

    assert response.status_code == 503
    assert set(session_service._sessions) == sessions_before


def test_diagnostic_validation_errors_do_not_mutate_phase(monkeypatch) -> None:
    active_response: dict[str, object] = _diagnostic_started_response()

    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        response = deepcopy(active_response)
        response["request_id"] = payload["request_id"]
        return response

    settings = Settings(
        student_model_url="https://student-model.example",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", fake_post_json)

    def start_with(response: dict[str, object]) -> str:
        active_response.clear()
        active_response.update(response)
        started = client.post(
            "/session/start",
            json={
                "student_id": "ST001",
                "concept_id": "ALG_LINEAR_ONE_STEP",
                "interaction_mode": "TEXT",
            },
        )
        assert started.status_code == 200
        return str(started.json()["session_id"])

    duplicate_session_id = start_with(_diagnostic_started_response())
    duplicate = client.post(
        f"/session/{duplicate_session_id}/diagnostic/complete",
        json={
            "student_id": "ST001",
            "answers": [
                {"question_id": "Q-T02-D01", "student_response": "A"},
                {"question_id": "Q-T02-D01", "student_response": "B"},
            ],
        },
    )
    assert duplicate.status_code == 422
    assert session_service._sessions[duplicate_session_id].current_phase == "DIAGNOSTIC"

    unsupported_response = _diagnostic_started_response()
    unsupported_payload = unsupported_response["phase_payload"]
    assert isinstance(unsupported_payload, dict)
    unsupported_question_set = unsupported_payload["question_set"]
    assert isinstance(unsupported_question_set, dict)
    unsupported_question = unsupported_question_set["questions"][0]
    assert isinstance(unsupported_question, dict)
    unsupported_question["tutor_view"]["answer_spec"][
        "verification_method"
    ] = "SYMBOLIC_EQUIVALENCE"
    unsupported_session_id = start_with(unsupported_response)
    unsupported = client.post(
        f"/session/{unsupported_session_id}/diagnostic/complete",
        json={
            "student_id": "ST001",
            "answers": [
                {"question_id": "Q-T02-D01", "student_response": "B"},
            ],
        },
    )
    assert unsupported.status_code == 422
    assert session_service._sessions[unsupported_session_id].current_phase == "DIAGNOSTIC"

    unknown_skill_response = _diagnostic_started_response()
    unknown_payload = unknown_skill_response["phase_payload"]
    assert isinstance(unknown_payload, dict)
    unknown_question_set = unknown_payload["question_set"]
    assert isinstance(unknown_question_set, dict)
    unknown_question = unknown_question_set["questions"][0]
    assert isinstance(unknown_question, dict)
    unknown_question["micro_skill_mappings"] = [
        {"micro_skill_id": "T02.UNKNOWN", "is_primary": True, "weight": 1.0}
    ]
    unknown_session_id = start_with(unknown_skill_response)
    unknown = client.post(
        f"/session/{unknown_session_id}/diagnostic/complete",
        json={
            "student_id": "ST001",
            "answers": [
                {"question_id": "Q-T02-D01", "student_response": "B"},
            ],
        },
    )
    assert unknown.status_code == 503
    assert session_service._sessions[unknown_session_id].current_phase == "DIAGNOSTIC"


def test_session_start_fails_without_topic_mapping_or_remote_service(
    monkeypatch,
) -> None:
    monkeypatch.setenv("NABLIX_STUDENT_MODEL_TOPIC_CODES", "{}")
    unmapped_settings = Settings(
        _env_file=None,
        student_model_url="https://student-model.example",
        student_model_topic_codes={},
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: unmapped_settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: unmapped_settings)
    sessions_before = set(session_service._sessions)

    unmapped = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert unmapped.status_code == 422
    assert set(session_service._sessions) == sessions_before

    monkeypatch.setenv(
        "NABLIX_STUDENT_MODEL_TOPIC_CODES",
        '{"ALG_LINEAR_ONE_STEP":"ALG-ORI-02"}',
    )
    mapped_settings = Settings(
        _env_file=None,
        student_model_url="https://student-model.example",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
    )

    async def failing_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del url, payload, headers, timeout_seconds, retry_count
        raise AdapterError(
            adapter_name,
            "url=https://student-model.example/session/event status=503 body=offline",
        )

    monkeypatch.setattr(provider, "get_settings", lambda: mapped_settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: mapped_settings)
    monkeypatch.setattr(student_model, "post_json", failing_post_json)
    failed = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert failed.status_code == 503
    assert set(session_service._sessions) == sessions_before


def test_legacy_initial_phase_session_is_rejected(monkeypatch) -> None:
    captured: dict[str, object] = {}
    settings = Settings(
        student_model_url="https://student-model.example",
        student_model_topic_ids={"ALG_LINEAR_ONE_STEP": 2},
        use_mock_student_model=False,
        qdrant_url="https://qdrant.test",
        qdrant_api_key="test-key",
    )

    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, timeout_seconds, retry_count
        captured.update(url=url, payload=payload, headers=headers)
        return {
            "mastery_status": "DEVELOPING",
            "continuity_status": "on_track",
            "recommended_entry_phase": None,
            "hint_dependency_score": 0.0,
            "intervention_required": False,
            "intervention_reason": None,
        }

    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", fake_post_json)
    started = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
            "initial_phase": "GUIDED_PRACTICE",
        },
    )
    assert started.status_code == 409
    assert "Legacy initial_phase sessions are not supported" in started.json()["message"]
    assert captured == {}
