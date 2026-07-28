from copy import deepcopy

from fastapi.testclient import TestClient
from app.adapters import provider, student_model
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.main import app
from app.services import session_service


client = TestClient(app, headers={"Authorization": "Bearer test-token"})


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
        question["student_view"]["question_text"] = "Solve for x: x + 4 = 9"
        question["tutor_view"]["answer_spec"]["canonical_answer"] = "x = 5"
        question["tutor_view"]["answer_spec"]["accepted_answers"] = ["x = 5"]
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
    elif event_type == "GUIDED_SUPPORT_ESCALATION_REQUIRED":
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
            "steps": [
                {
                    "step_id": "SCF-T02-M1-S1",
                    "prompt": "Which operation should you undo first?",
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
    return response


def test_session_start_uses_schema_3_diagnostic_contract(monkeypatch) -> None:
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
    assert payload["event_type"] == "DIAGNOSTIC_QUESTION_SET_REQUESTED"
    assert payload["topic_id"] == "ALG-ORI-02"
    assert payload["student_id"] == "ST001"
    assert isinstance(payload["timestamp"], str)


def test_student_model_request_ids_remain_unique_after_session_counter_restart() -> None:
    first = session_service._student_model_request_id(
        "SESSION001",
        "DIAGNOSTIC_QUESTION_SET_REQUESTED",
    )
    second = session_service._student_model_request_id(
        "SESSION001",
        "DIAGNOSTIC_QUESTION_SET_REQUESTED",
    )

    assert first != second
    assert first.startswith("SESSION001:DIAGNOSTIC_QUESTION_SET_REQUESTED:")
    assert second.startswith("SESSION001:DIAGNOSTIC_QUESTION_SET_REQUESTED:")


def test_diagnostic_and_orientation_lifecycle_uses_micro_skills(monkeypatch) -> None:
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
    assert completed["message"] == "Now let’s use this idea together in a question."
    assert [event["event_type"] for event in events] == [
        "DIAGNOSTIC_QUESTION_SET_REQUESTED",
        "DIAGNOSTIC_COMPLETED",
        "WORKED_EXAMPLE_REQUESTED",
        "ORIENTATION_COMPLETED",
    ]

    guided_incorrect = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
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
    assert isinstance(events[-1]["error_code"], str)
    assert guided_incorrect.json()["student_model_state"][
        "highest_support_used_by_skill"
    ] == {"T02.M1": "HINT"}
    assert guided_incorrect.json()["show_visual_cue"] is True
    assert guided_incorrect.json()["visual_cue"] == {
        "show": True,
        "cue_type": "VC-T02-COEFFICIENT-COUNT",
        "description": "Count the equal letter terms.",
    }
    assert guided_incorrect.json()["message"] == "Undo the addition first."

    for answer in ("x = 3", "x = 2"):
        guided_incorrect = client.post(
            "/interaction",
            json={
                "session_id": session_id,
                "student_id": "ST001",
                "interaction_type": "ANSWER_SUBMISSION",
                "input_source": "TEXT",
                "text_input": answer,
                "current_phase": "GUIDED_PRACTICE",
                "concept_id": "ALG_LINEAR_ONE_STEP",
                "question_id": "Q-T02-004",
                "hint_count": 0,
            },
        )
        assert guided_incorrect.status_code == 200

    assert events[-2]["event_type"] == "INCORRECT_ATTEMPT"
    assert events[-1]["event_type"] == "GUIDED_SUPPORT_ESCALATION_REQUIRED"
    assert guided_incorrect.json()["show_scaffold_panel"] is True
    assert guided_incorrect.json()["scaffold_steps"] == [
        "Which operation should you undo first?"
    ]

    guided = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
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
        if payload["event_type"] == "DIAGNOSTIC_QUESTION_SET_REQUESTED":
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


def test_legacy_session_keeps_legacy_student_model_interaction(monkeypatch) -> None:
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
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    assert started.json()["student_model_event"] is None

    interaction = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "text_input": "x = 3",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "ALG_EQ_GP_001",
            "hint_count": 0,
        },
    )
    assert interaction.status_code == 200
    assert captured["url"] == "https://student-model.example/interaction"
    assert captured["headers"] == {"Authorization": "Bearer test-token"}
