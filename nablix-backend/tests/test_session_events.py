from collections.abc import Awaitable, Callable
from copy import deepcopy
import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.adapters import provider, student_model
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.main import app
from app.ai_engine.classifier_config import load_classifier_rules
from app.models.adapters import TutorResult
from app.models.guided_learning import GuidedRescue
from app.models.student_model_session import SessionOpenedEvent
from app.services import interaction_service, session_service


client = TestClient(app, headers={"Authorization": "Bearer test-token"})
SessionEventPost = Callable[
    [str, str, dict[str, object], dict[str, str], int, int],
    Awaitable[dict[str, object]],
]


def test_guided_partial_answers_do_not_advance_wrong_support() -> None:
    wrong_partial = TutorResult.model_construct(
        guided_student_state="PARTIAL",
        evaluation="PARTIALLY_CORRECT",
        intent="SUBMITTING_ANSWER",
        answer_value_confirmed=False,
    )
    defence_partial = wrong_partial.model_copy(
        update={"answer_value_confirmed": True}
    )
    stuck = wrong_partial.model_copy(
        update={"intent": "EXPRESSING_CONFUSION"}
    )

    assert not interaction_service._is_support_failure(wrong_partial)
    assert not interaction_service._is_support_failure(defence_partial)
    assert not interaction_service._is_support_failure(stuck)


def test_unresolved_scaffold_turns_include_wrong_answers_and_confusion() -> None:
    wrong = TutorResult.model_construct(
        guided_student_state="WRONG",
        evaluation="INCORRECT",
        intent="SUBMITTING_ANSWER",
    )
    confusion = wrong.model_copy(
        update={
            "guided_student_state": "STUCK",
            "evaluation": "NO_ATTEMPT",
            "intent": "EXPRESSING_CONFUSION",
        }
    )
    clarification = confusion.model_copy(update={"intent": "ASKING_QUESTION"})

    assert interaction_service._is_unresolved_scaffold_turn(wrong)
    assert interaction_service._is_unresolved_scaffold_turn(confusion)
    assert not interaction_service._is_unresolved_scaffold_turn(clarification)


def test_unresolved_partial_does_not_emit_an_incorrect_attempt() -> None:
    rules = load_classifier_rules()
    unresolved = TutorResult.model_construct(
        guided_student_state="PARTIAL",
        evaluation="PARTIALLY_CORRECT",
        intent="SUBMITTING_ANSWER",
        answer_value_confirmed=False,
    )
    defence = unresolved.model_copy(update={"answer_value_confirmed": True})

    assert interaction_service._guided_attempt_event_type(unresolved, rules) is None
    assert interaction_service._guided_attempt_event_type(defence, rules) is None


def test_option_selection_creates_guided_state_when_none_exists() -> None:
    session = session_service.SessionRecord.model_construct(
        question_id="Q-T01-004",
        guided_teaching_state=None,
    )

    state = interaction_service._guided_state_with_selected_option(
        session,
        "B",
        "n + 4",
    )

    assert state.question_id == "Q-T01-004"
    assert state.selected_option_id == "B"
    assert state.selected_option_text == "n + 4"
    assert state.awaiting_response is True


@pytest.mark.parametrize("support_type", ["HINT", "VISUAL_CUE", "SCAFFOLD"])
def test_empty_support_keeps_the_tutor_response_available(
    support_type: str,
) -> None:
    response = _event_response("INCORRECT_ATTEMPT", "REQ-EMPTY-VISUAL")
    phase_payload = response["phase_payload"]
    assert isinstance(phase_payload, dict)
    phase_payload["support_to_serve"] = {
        "support_type": support_type,
        "items": [],
        "retry_same_question": True,
    }
    event = session_service.StudentModelSessionEventResponse.model_validate(response)

    message, visual_cue, steps, action, support_used = (
        interaction_service._support_presentation(event)
    )

    assert message is None
    assert visual_cue is None
    assert steps == []
    assert action is None
    assert support_used is None


def test_missing_support_content_is_not_reported_as_active_support() -> None:
    response = _event_response("INCORRECT_ATTEMPT", "REQ-MISSING-HINT")
    phase_payload = response["phase_payload"]
    assert isinstance(phase_payload, dict)
    phase_payload["support_to_serve"] = {
        "support_type": "HINT",
        "items": [],
        "retry_same_question": True,
    }
    event = session_service.StudentModelSessionEventResponse.model_validate(response)
    session = session_service.SessionRecord.model_construct(student_model_event=event)

    active_support_level, _ = interaction_service._guided_support_levels(session)

    assert active_support_level == "NONE"


def test_visual_cue_requires_an_authored_visual_cue_item() -> None:
    response = _event_response("INCORRECT_ATTEMPT", "REQ-MISSING-VISUAL")
    phase_payload = response["phase_payload"]
    assert isinstance(phase_payload, dict)
    phase_payload["support_to_serve"] = {
        "support_type": "VISUAL_CUE",
        "items": [
            {
                "content_type": "HINT",
                "content_id": "HINT-T01-L2",
                "content": "Compare the changing and fixed parts.",
            }
        ],
        "retry_same_question": True,
    }
    event = session_service.StudentModelSessionEventResponse.model_validate(response)

    message, visual_cue, steps, action, support_used = (
        interaction_service._support_presentation(event)
    )

    assert message == "Compare the changing and fixed parts."
    assert visual_cue is None
    assert steps == []
    assert action == "GIVE_HINT"
    assert support_used == "HINT"


def test_schema_visual_cue_preserves_the_authored_identity_and_asset() -> None:
    event = session_service.StudentModelSessionEventResponse.model_validate(
        _event_response("INCORRECT_ATTEMPT", "REQ-VISUAL-CUE-ASSET")
    )
    assert event.phase_payload is not None
    event.phase_payload.support_to_serve = {
        "support_type": "VISUAL_CUE",
        "items": [
            {
                "content_type": "VISUAL_CUE",
                "content_id": "VC-T01-GENERAL-VS-PARTICULAR",
                "description": "Compare a particular case with the general rule.",
                "asset_url": "https://example.test/cues/general-rule.png",
                "actions": [],
            }
        ],
    }

    visual_cue = interaction_service._schema_visual_cue(event)

    assert visual_cue is not None
    assert visual_cue.cue_id == "VC-T01-GENERAL-VS-PARTICULAR"
    assert visual_cue.asset_url == "https://example.test/cues/general-rule.png"


@pytest.mark.parametrize("rescue_type", ["PARALLEL_EXAMPLE", "TUTOR_SOLVED"])
def test_empty_rescue_keeps_the_tutor_response_available(
    rescue_type: str,
) -> None:
    rescue = GuidedRescue.model_validate(
        {
            "rescue_type": rescue_type,
            "micro_skill_id": "T01.M1",
            "parallel_example": None,
            "tutor_solved": None,
        }
    )

    assert interaction_service._guided_rescue_message(rescue) is None


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
            "n + 5",
            rules,
        )
    for student_message, expected_response in rejected:
        assert not interaction_service._scaffold_response_is_correct(
            student_message,
            expected_response,
            "PARTIALLY_CORRECT",
            "n + 5",
            rules,
        )

    for student_message in ["the starting variable", "n"]:
        assert interaction_service._scaffold_response_is_correct(
            student_message,
            "Starting number",
            "INCORRECT",
            "n + 5",
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
    elif event_type in {
        "GUIDED_PHASE_COMPLETED",
        "INDEPENDENT_QUESTION_SET_REQUESTED",
    }:
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
    elif event_type == "GUIDED_SUPPORT_REQUESTED":
        response = _event_response("ORIENTATION_COMPLETED", request_id)
        journey = response["journey_state"]
        payload = response["phase_payload"]
        routing = response["routing"]
        assert isinstance(journey, dict)
        assert isinstance(payload, dict)
        assert isinstance(routing, dict)
        journey["phase_2_guided_learning"]["highest_support_used_by_skill"] = {
            "T02.M1": "HINT"
        }
        payload["payload_type"] = "SUPPORT_AND_RETRY"
        payload["support_to_serve"] = {
            "support_type": "HINT",
            "items": [
                {
                    "content_type": "HINT",
                    "content_id": "HINT-T02-M1-L1",
                    "content": "Undo the addition first.",
                    "level": 1,
                }
            ],
            "retry_same_question": True,
        }
        routing.update(
            {
                "reason_code": "GUIDED_HINT_REQUIRED",
                "reason": "Student requested help. Delivering support for retry.",
                "next_action": "DELIVER_SUPPORT_AND_RETRY",
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
    elif event_type == "MAXIMUM_GUIDED_SUPPORT_PARALLEL":
        response = _event_response("ORIENTATION_COMPLETED", request_id)
        journey = response["journey_state"]
        payload = response["phase_payload"]
        routing = response["routing"]
        assert isinstance(journey, dict)
        assert isinstance(payload, dict)
        assert isinstance(routing, dict)
        journey["phase_2_guided_learning"]["highest_support_used_by_skill"] = {
            "T02.M1": "PARALLEL_EXAMPLE"
        }
        payload.update(
            {
                "payload_type": "RESCUE",
                "question_set": None,
                "support_to_serve": None,
                "rescue_to_serve": {
                    "rescue_type": "PARALLEL_EXAMPLE",
                    "micro_skill_id": "T02.M1",
                    "parallel_example": {
                        "parallel_example_id": "PAR-T02-M1",
                        "problem": "Solve y + 3 = 8.",
                        "worked_steps": [
                            "Step 1: Subtract 3 from both sides.",
                            "Step 2: y = 5.",
                        ],
                        "final_answer": "y = 5",
                    },
                },
            }
        )
        routing.update(
            {
                "reason_code": "PARALLEL_EXAMPLE_REQUIRED",
                "reason": "Delivering a parallel example.",
                "next_action": "DELIVER_PARALLEL_EXAMPLE",
            }
        )
    elif event_type == "MAXIMUM_GUIDED_SUPPORT_REQUIRED":
        response = _event_response("ORIENTATION_COMPLETED", request_id)
        journey = response["journey_state"]
        payload = response["phase_payload"]
        routing = response["routing"]
        assert isinstance(journey, dict)
        assert isinstance(payload, dict)
        assert isinstance(routing, dict)
        journey["phase_2_guided_learning"].update(
            {
                "status": "COMPLETED",
                "completed_micro_skill_ids": ["T02.M1"],
                "remaining_micro_skill_ids": [],
                "highest_support_used_by_skill": {"T02.M1": "TUTOR_SOLVED"},
                "used_question_ids": ["Q-T02-004"],
            }
        )
        payload.update(
            {
                "payload_type": "RESCUE",
                "question_set": None,
                "support_to_serve": None,
                "rescue_to_serve": {
                    "rescue_type": "TUTOR_SOLVED",
                    "micro_skill_id": "T02.M1",
                    "tutor_solved": {
                        "explanation": "Subtract 4 from both sides. The correct answer is x = 5.",
                        "final_answer": "x = 5",
                        "answer_steps": ["x + 4 - 4 = 9 - 4", "x = 5"],
                    },
                },
            }
        )
        routing.update(
            {
                "reason_code": "GUIDED_PHASE_COMPLETED",
                "reason": "Tutor-solved support completed the guided skill.",
                "next_action": "PROCEED_TO_PHASE_3",
            }
        )
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


def test_student_model_response_logs_its_payload_type_and_rescue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Only rejections used to be logged, so a rescue that never arrived and a
    # rescue that arrived and was dropped looked identical in the journal.
    records: list[dict[str, object]] = []

    class RecordingLogger:
        def info(self, event: str, extra: dict[str, object]) -> None:
            records.append({"event": event, **extra})

        def __getattr__(self, name: str):
            return lambda *args, **kwargs: None

    async def serve_rescue(*args: object) -> dict[str, object]:
        del args
        response = _independent_rescue_response()
        response["request_id"] = "SESSION001:SESSION001:SESSION_OPENED"
        return response

    monkeypatch.setattr(student_model, "post_json", serve_rescue)
    monkeypatch.setattr(student_model, "logger", RecordingLogger())
    adapter = student_model.StudentModelServiceAdapter(
        Settings(
            student_model_url="https://student-model.example",
            student_model_topic_ids={},
            use_mock_student_model=False,
        )
    )

    asyncio.run(
        adapter.send_session_event(
            SessionOpenedEvent(
                request_id="SESSION001:SESSION001:SESSION_OPENED",
                event_type="SESSION_OPENED",
                topic_id="ALG-ORI-02",
                student_id="ST001",
                timestamp="2026-08-01T00:00:00Z",
            ),
            "token",
        )
    )

    assert len(records) == 1
    logged = records[0]
    assert logged["event"] == "student_model_event_response"
    assert logged["payload_type"] == "RESCUE_AND_FRESH_QUESTION"
    assert logged["phase"] == "PHASE_3_INDEPENDENT_PRACTICE"
    assert logged["student_model_event"] == "SESSION_OPENED"


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
    restored = client.get(
        f"/session/{second_body['session_id']}",
        params={"student_id": second_body["student_id"]},
    )
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


def test_active_support_is_visible_on_a_blank_canvas_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A support event remains visible even when the canvas has no usable work."""

    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        return _event_response("INCORRECT_ATTEMPT", str(payload["request_id"]))

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
    assert started.json()["show_visual_cue"] is True

    blank_canvas_turn = client.post(
        "/interaction",
        json={
            "session_id": started.json()["session_id"],
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "CANVAS",
            "turn_id": "TURN-BLANK-CANVAS-1",
            "text_input": "I am not sure yet",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )

    assert blank_canvas_turn.status_code == 200, blank_canvas_turn.text
    body = blank_canvas_turn.json()
    assert body["support_message"] == "Undo the addition first."
    assert body["support_served_this_turn"] is None
    assert body["show_visual_cue"] is False
    assert body["visual_cue"] is None
    assert body["canvas_draw"] == []


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
    if phase == "PHASE_3_INDEPENDENT_PRACTICE":
        assert [event["event_type"] for event in events] == ["SESSION_OPENED"]
        assert answered.json()["independent_outcome"] == "AWAITING_SUBMISSION"
        assert answered.json()["attempt_increment"] == 0
        return
    assert [event["event_type"] for event in events[:3]] == [
        "SESSION_OPENED",
        expected_initializer,
        "INCORRECT_ATTEMPT",
    ]
    assert events[2]["question_id"] == "Q-T02-INITIALIZED"
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
    assert completed["message"] == (
        "Now let’s use this idea together in a question. "
        "Solve for x: x + 4 = 9. "
        "Look through the choices carefully—you already know enough to make a start."
    )
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
            assert len(events) == event_count_before_stuck + 1
            assert events[-1]["event_type"] == "GUIDED_SUPPORT_REQUESTED"
            assert "scaffold_steps" not in stuck.json()
            assert stuck.json()["current_scaffold_step_id"] is None
        else:
            assert len(events) == event_count_before_stuck + 2
            assert events[-1]["event_type"] == "GUIDED_STUCK_SUPPORT_REQUIRED"
            assert events[-1]["micro_skill_id"] == "T02.M1"
            assert events[-1].get("triggering_response") is None
            assert events[-1].get("error_code") is None
            assert stuck.json()["scaffold_step_text"] == (
                "Which operation should you undo first?"
            )
            assert stuck.json()["current_scaffold_step_id"] == "SCF-T02-M1-S1"
            # The scaffold prompt is surfaced beside the tutor reply, not as it
            # (see "feat: narrate guided support in tutor responses").
            assert stuck.json()["message"]
            assert stuck.json()["message"] != "Which operation should you undo first?"
        assert "scaffold_expected_response" not in stuck.json()
        assert client.get(f"/session/{session_id}", params={"student_id": "ST001"}).json()["stuck_count"] == (
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
    assert wrong_scaffold_step.json()["message"] != (
        "Let’s stay with this step: Which operation should you undo first?"
    )
    assert (
        session_service._sessions[session_id].scaffold_failure_count == 1
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
    assert session_service._sessions[session_id].scaffold_failure_count == 0

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
    assert client.get(f"/session/{session_id}", params={"student_id": "ST001"}).json()["stuck_count"] == 0
    assert guided_incorrect.json()["student_model_state"][
        "highest_support_used_by_skill"
    ] == {"T02.M1": "HINT"}
    assert guided_incorrect.json()["show_visual_cue"] is True
    assert guided_incorrect.json()["visual_cue"] == {
        "show": True,
            "cue_id": "VC-T02-COEFFICIENT-COUNT",
            "cue_type": None,
            "description": "Count the equal letter terms.",
            "asset_url": None,
            "actions": [
                {
                    "action": "HIGHLIGHT_TOKEN",
                    "target": "x",
                    "style": "VARIABLE",
                }
            ],
        }
    assert guided_incorrect.json()["message"] != "Undo the addition first."
    assert guided_incorrect.json()["message"]
    assert guided_incorrect.json()["support_message"] == "Undo the addition first."
    assert guided_incorrect.json()["support_served_this_turn"] == "VISUAL_CUE"

    for wrong_number in range(2, 5):
        guided_incorrect = client.post(
            "/interaction",
            json={
                "session_id": session_id,
                "student_id": "ST001",
                "interaction_type": "ANSWER_SUBMISSION",
                "input_source": "TEXT",
                "turn_id": f"TURN-GUIDED-WRONG-{wrong_number}",
                "text_input": "x = 4",
                "current_phase": "GUIDED_PRACTICE",
                "concept_id": "ALG_LINEAR_ONE_STEP",
                "question_id": "Q-T02-004",
                "hint_count": 0,
            },
        )
        assert guided_incorrect.status_code == 200
        assert guided_incorrect.json()["wrong_attempt_count"] == wrong_number

    assert events[-1]["event_type"] == "GUIDED_SUPPORT_ESCALATION_REQUIRED"
    assert events[-1]["micro_skill_id"] == "T02.M1"
    assert events[-1]["triggering_response"] == "x = 4"
    assert events[-1]["error_code"] == "ERR-T02-SUBTRACTION-MISAPPLIED"
    # Wrong-4 defers to the Student Model's scaffold routing reason when a
    # scaffold is actually served (see "fix(interaction): require evidence for
    # Wrong-4 escalation").
    assert guided_incorrect.json()["support_reason_code"] == "GUIDED_SCAFFOLD_REQUIRED"
    assert guided_incorrect.json()["intervention_triggered"] is False
    assert guided_incorrect.json()["show_scaffold_panel"] is True
    assert guided_incorrect.json()["current_scaffold_step_id"] == "SCF-T02-M1-S1"

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

    parallel = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-GUIDED-POST-SCAFFOLD-WRONG",
            "text_input": "x = 4",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )
    assert parallel.status_code == 200
    assert events[-1]["event_type"] == "MAXIMUM_GUIDED_SUPPORT_PARALLEL"
    assert events[-1]["error_code"] == "ERR-T02-SUBTRACTION-MISAPPLIED"
    # Stepwise presentation: the payload is withheld and step 1 arrives as a
    # canvas action instead, so the client never holds the later steps.
    assert parallel.json()["guided_rescue"] is None
    assert parallel.json()["support_served_this_turn"] == "PARALLEL_EXAMPLE"
    assert "Solve y + 3 = 8" in parallel.json()["message"]
    parallel_action = parallel.json()["tutor_canvas_actions"][0]
    assert parallel_action["type"] == "SHOW_PARALLEL"
    assert parallel_action["rescue_id"] == "PAR-T02-M1"
    assert parallel_action["step_index"] == 1
    assert parallel_action["total_steps"] == 4
    assert parallel_action["answer_reveal_allowed"] is False
    assert (
        parallel_action["return_target_object_id"]
        == "TUTOR_ANCHOR:QUESTION:Q-T02-004"
    )

    tutor_solved = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-GUIDED-POST-PARALLEL-WRONG",
            "text_input": "x = 4",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )
    assert tutor_solved.status_code == 200, tutor_solved.text
    assert events[-1]["event_type"] == "MAXIMUM_GUIDED_SUPPORT_REQUIRED"
    assert events[-1]["error_code"] == "ERR-T02-SUBTRACTION-MISAPPLIED"
    # Stepwise Tutor-Solved defers the Phase 3 handover: the student is still
    # being walked through the rescue, so INDEPENDENT_QUESTION_SET_REQUESTED
    # waits for the final render acknowledgement.
    assert "INDEPENDENT_QUESTION_SET_REQUESTED" not in [
        event["event_type"] for event in events
    ]
    assert tutor_solved.json()["guided_rescue"] is None
    assert tutor_solved.json()["support_served_this_turn"] == "TUTOR_SOLVED"
    solved_action = tutor_solved.json()["tutor_canvas_actions"][0]
    assert solved_action["type"] == "TUTOR_SOLVED_STEP"
    assert solved_action["step_index"] == 1
    assert solved_action["answer_reveal_allowed"] is False
    assert "x = 5" not in tutor_solved.json()["message"]
    assert tutor_solved.json()["current_phase"] == "GUIDED_PRACTICE"


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


def test_phase3_content_gap_is_persisted_without_synthetic_review() -> None:
    event_dict = {
        "schema_version": "3.0",
        "request_id": "SESSION001:SESSION_OPENED",
        "processed_at": "2026-08-06T12:00:00Z",
        "journey_state": {
            "student_id": "ST010",
            "active_session_id": "SESSION-001",
            "topic_id": "ALG-KS3-01",
            "topic_status": "IN_PROGRESS",
            "mastery_status": "NEARLY_MASTERED",
            "continuity_status": "ON_TRACK",
            "current_phase": "PHASE_3_INDEPENDENT_PRACTICE",
            "recommended_entry_phase": "PHASE_3_INDEPENDENT_PRACTICE",
            "session_count": 1,
            "started_at": "2026-08-06T12:00:00Z",
            "last_activity_at": "2026-08-06T12:00:00Z",
            "phase_0_diagnostic": {"status": "COMPLETED", "phase_visit_no": 1},
            "phase_1_orientation": {"status": "COMPLETED", "phase_visit_no": 1},
            "phase_2_guided_learning": {"status": "COMPLETED", "phase_visit_no": 1},
            "phase_3_independent_practice": {
                "status": "IN_PROGRESS",
                "phase_visit_no": 1,
                "target_micro_skill_ids": ["T01.M6"],
                "remaining_micro_skill_ids": ["T01.M6"],
                "verified_micro_skill_ids": [],
                "used_question_ids": ["Q-T01-008"],
            },
            "review": {"status": "NOT_STARTED", "phase_visit_no": None},
            "version": 30,
            "updated_at": "2026-08-06T12:00:00Z",
        },
        "phase_payload": {
            "phase": "PHASE_3_INDEPENDENT_PRACTICE",
            "payload_type": "RESCUE_AND_FRESH_QUESTION",
            "question_set": {"questions": []},
            "rescue_to_serve": {
                "rescue_type": "PARALLEL_EXAMPLE",
                "micro_skill_id": "T01.M6",
                "parallel_example": None,
                "fresh_retry_question_id": None,
            },
        },
        "event_result": None,
        "routing": {
            "reason_code": "INDEPENDENT_FAILURE",
            "reason": "Independent verification failed for T01.M6.",
            "next_action": "DELIVER_RESCUE_AND_FRESH_RETRY",
            "prerequisite_check_required": False,
            "prerequisite_micro_skill_ids": [],
            "content_gap_detected": True,
            "missing_micro_skill_ids": ["T01.M6"],
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
    parsed = session_service.StudentModelSessionEventResponse.model_validate(event_dict)
    validated = session_service._validate_session_opened_payload(parsed)
    assert validated == parsed.phase_payload


def test_tc21_phase3_null_payload_is_stored_unchanged(
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
        return response

    _use_live_student_model(monkeypatch, fake_post_json)
    started = client.post(
        "/session/start",
        json={"student_id": "ST001", "concept_id": "ALG_LINEAR_ONE_STEP", "interaction_mode": "TEXT"},
    )
    session = session_service._sessions[started.json()["session_id"]]
    stored_event = session.student_model_event
    assert stored_event is not None
    stored_phase3 = stored_event.journey_state.phase_3_independent_practice.model_copy(
        update={"used_question_ids": ["Q-T02-004"]}
    )
    stored_journey = stored_event.journey_state.model_copy(
        update={"phase_3_independent_practice": stored_phase3}
    )
    session = session.model_copy(
        update={"student_model_event": stored_event.model_copy(update={"journey_state": stored_journey})}
    )
    body = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
    body["phase_payload"] = None
    body["routing"].update(
        {
            "reason_code": "FRESH_CONTENT_UNAVAILABLE",
            "reason": "No fresh question is available.",
            "next_action": "WAIT_FOR_CONTENT",
            "content_gap_detected": True,
            "missing_micro_skill_ids": ["T02.M1"],
        }
    )
    body["status"].update(
        {
            "status_code": "CONTENT_GAP",
            "intervention_required": True,
            "intervention_reason": "Missing fresh independent question.",
        }
    )
    event = session_service.StudentModelSessionEventResponse.model_validate(body)

    updated = asyncio.run(session_service._apply_schema_event(session, event))

    assert updated.current_phase == "INDEPENDENT_PRACTICE"
    assert updated.question_id is None
    assert updated.student_model_event == event
    assert updated.student_model_event.routing.missing_micro_skill_ids == ["T02.M1"]


def test_tc21_rejects_reused_fresh_question(
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
        return response

    _use_live_student_model(monkeypatch, fake_post_json)
    started = client.post(
        "/session/start",
        json={"student_id": "ST001", "concept_id": "ALG_LINEAR_ONE_STEP", "interaction_mode": "TEXT"},
    )
    session = session_service._sessions[started.json()["session_id"]]
    body = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
    stored_event = session.student_model_event
    assert stored_event is not None
    stored_phase3 = stored_event.journey_state.phase_3_independent_practice.model_copy(
        update={"used_question_ids": ["Q-T02-004"]}
    )
    session = session.model_copy(
        update={
            "student_model_event": stored_event.model_copy(
                update={
                    "journey_state": stored_event.journey_state.model_copy(
                        update={"phase_3_independent_practice": stored_phase3}
                    )
                }
            )
        }
    )
    journey = body["journey_state"]["phase_3_independent_practice"]
    journey["used_question_ids"] = ["Q-T02-004"]
    event = session_service.StudentModelSessionEventResponse.model_validate(body)

    with pytest.raises(HTTPException) as error:
        asyncio.run(session_service._apply_schema_event(session, event))
    assert error.value.status_code == 503
    assert "previously used" in str(error.value.detail)


def test_resume_is_retired_and_never_mutates_the_journey(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A client snapshot is not a resume authority (ADR 0004).

    The saved_journey the browser sent chose the phase, and the selector that
    read it had no REVIEW branch -- it fell through to Guided Learning, so a
    refresh could reopen a finished topic mid-lesson. The endpoint answers
    explicitly for one release, and sends no Student Model event at all.
    """

    events: list[object] = []

    async def send_session_event(adapter: object, event: object, access_token: str):
        del adapter, access_token
        events.append(event)
        body = _session_opened_response("PHASE_2_GUIDED_LEARNING")
        body["request_id"] = getattr(event, "request_id")
        return session_service.StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(
        student_model.StudentModelServiceAdapter,
        "send_session_event",
        send_session_event,
    )
    settings = Settings(
        student_model_url="https://student-model.example",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    started = client.post(
        "/session/start",
        json={"student_id": "ST001", "concept_id": "ALG_LINEAR_ONE_STEP", "interaction_mode": "TEXT"},
    )
    session_id = started.json()["session_id"]
    before = session_service._sessions[session_id]
    opened_events = len(events)

    resumed = client.post(
        f"/session/{session_id}/resume",
        json={
            "student_id": "ST001",
            "turn_id": "TURN-RESUME",
            "saved_journey": {
                "phase_2_guided_learning": {
                    "target_micro_skill_ids": ["T02.M1"],
                    "remaining_micro_skill_ids": ["T02.M1"],
                    "used_question_ids": ["Q-T02-OLD"],
                }
            },
        },
    )

    assert resumed.status_code == 410, resumed.text
    assert resumed.json()["error_code"] == "SESSION_RESUME_RETIRED"
    # No event, and no journey movement: the request could not select a phase.
    assert len(events) == opened_events
    after = session_service._sessions[session_id]
    assert after.current_phase == before.current_phase
    assert after.student_model_event == before.student_model_event


def test_tc25_review_complete_forwards_correlated_event_and_persists_next_topic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []

    async def send_session_event(adapter: object, event: object, access_token: str):
        del adapter, access_token
        events.append(event)
        body = _session_opened_response("REVIEW")
        body["request_id"] = getattr(event, "request_id")
        if getattr(event, "event_type") == "REVIEW_COMPLETED":
            body["phase_payload"] = None
            body["journey_state"]["topic_status"] = "COMPLETED"
            body["journey_state"]["mastery_status"] = "MASTERED"
            body["journey_state"]["recommended_entry_phase"] = None
            body["journey_state"]["review"]["status"] = "COMPLETED"
            body["routing"].update(
                {
                    "reason_code": "REVIEW_COMPLETED",
                    "next_action": "START_NEXT_TOPIC",
                    "next_topic_id": "ALG-ORI-02",
                    "next_topic_entry_phase": "PHASE_0_DIAGNOSTIC",
                }
            )
        return session_service.StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(
        student_model.StudentModelServiceAdapter,
        "send_session_event",
        send_session_event,
    )
    settings = Settings(
        student_model_url="https://student-model.example",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    started = client.post(
        "/session/start",
        json={"student_id": "ST001", "concept_id": "ALG_LINEAR_ONE_STEP", "interaction_mode": "TEXT"},
    )
    session_id = started.json()["session_id"]

    completed = client.post(
        f"/session/{session_id}/review/complete",
        json={"student_id": "ST001", "turn_id": "TURN-TC25"},
    )

    assert completed.status_code == 200, completed.text
    review_event = events[-1]
    assert getattr(review_event, "event_type") == "REVIEW_COMPLETED"
    assert getattr(review_event, "source_turn_id") == "TURN-TC25"
    assert getattr(review_event, "expected_journey_version") == 1
    stored = session_service._sessions[session_id]
    assert stored.student_model_event is not None
    assert stored.student_model_event.routing.next_topic_id == "ALG-ORI-02"
    # Both halves of the routing reach the wire; an entry phase that stays
    # behind leaves the frontend guessing which phase to open the next topic in.
    state = completed.json()["student_model_state"]
    assert state["next_topic_recommendation"] == "ALG-ORI-02"
    assert state["next_topic_entry_phase"] == "PHASE_0_DIAGNOSTIC"


def test_first_question_of_a_phase_is_question_number_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the off-by-one: entering a phase is a question-id change,
    so the old increment-on-id-change branch clobbered the correct position-in-
    set value on exactly the first question of every phase."""

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

    _use_live_student_model(monkeypatch, fake_post_json)
    started = client.post(
        "/session/start",
        json={"student_id": "ST001", "concept_id": "ALG_LINEAR_ONE_STEP", "interaction_mode": "TEXT"},
    )
    session = session_service._sessions[started.json()["session_id"]]
    assert session.question_id != "Q-T02-004"

    body = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
    event = session_service.StudentModelSessionEventResponse.model_validate(body)
    entered_phase = asyncio.run(session_service._apply_schema_event(session, event))

    assert entered_phase.question_id == "Q-T02-004"
    assert entered_phase.question_number == 1

    # A second question served within the same phase still increments normally.
    second_body = deepcopy(body)
    journey = second_body["journey_state"]
    payload = second_body["phase_payload"]
    assert isinstance(journey, dict)
    assert isinstance(payload, dict)
    question_set = payload["question_set"]
    assert isinstance(question_set, dict)
    second_question = deepcopy(question_set["questions"][0])
    second_question["question_id"] = "Q-T02-005"
    second_question["question_usage_id"] = "QU-T02-005-P3"
    question_set["questions"].append(second_question)
    journey["phase_3_independent_practice"]["current_question_id"] = "Q-T02-005"
    second_event = session_service.StudentModelSessionEventResponse.model_validate(second_body)
    advanced = asyncio.run(session_service._apply_schema_event(entered_phase, second_event))

    assert advanced.question_id == "Q-T02-005"
    assert advanced.question_number == 2


def test_no_next_topic_projects_both_routing_fields_as_null() -> None:
    """After the last content-backed topic both fields are null -- never a
    silently defaulted phase the frontend would route on."""

    from app.models.student_model_session import StudentModelSessionEventResponse
    from app.services.student_model_session import project_student_model_state

    event = StudentModelSessionEventResponse.model_validate(
        _eight_skill_diagnostic_response()
    )
    state = project_student_model_state(event)
    assert state.next_topic_recommendation is None
    assert state.next_topic_entry_phase is None


def test_core_state_restores_snapshot_without_next_topic_entry_phase() -> None:
    """Persisted sessions from before the routing field was added still load."""

    from app.models.student_model_session import StudentModelCoreState

    state = StudentModelCoreState.model_validate(
        {
            "student_id": "ST001",
            "topic_id": "ALG-KS3-01",
            "current_phase": "REVIEW",
            "mastery_status": "MASTERED",
            "continuity_status": "CONTINUE",
            "recommended_entry_phase": None,
            "target_micro_skill_ids": ["T01.M1"],
            "completed_micro_skill_ids": ["T01.M1"],
            "independently_verified_micro_skill_ids": ["T01.M1"],
            "unresolved_micro_skill_ids": [],
            "highest_support_used_by_skill": {},
            "used_question_ids": ["Q-T01-001"],
            "current_question_id": None,
            "transition_reason": "Review complete.",
            "next_topic_recommendation": None,
        }
    )

    assert state.next_topic_entry_phase is None


def test_topic_code_starts_a_session_with_no_configured_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G1: Saravanan's topic code is authoritative. Sent directly it needs no
    entry in student_model_topic_codes -- the dictionary that made every new
    topic a Nablix deploy."""

    opened: dict[str, str] = {}

    async def send_session_event(adapter, event, access_token):
        del adapter, access_token
        opened["topic_id"] = event.topic_id
        body = _session_opened_response("PHASE_0_DIAGNOSTIC")
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    from app.adapters.student_model import StudentModelServiceAdapter
    from app.models.student_model_session import StudentModelSessionEventResponse

    settings = Settings(
        student_model_url="https://student-model.test",
        student_model_topic_codes={},
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", send_session_event
    )

    started = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "topic_code": "ALG-ORI-02",
            "interaction_mode": "TEXT",
        },
    )

    assert started.status_code == 200, started.text
    assert opened["topic_id"] == "ALG-ORI-02"


def test_session_start_without_either_identifier_is_rejected() -> None:
    started = client.post(
        "/session/start",
        json={"student_id": "ST001", "interaction_mode": "TEXT"},
    )
    assert started.status_code == 422
