from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.ai_engine import openai_client, phase4_review
from app.main import app
from app.models.phase4_review import Phase4ReviewRequest, Phase4ReviewResponse


client = TestClient(app)


def _request_body() -> dict[str, object]:
    return {
        "topic_info": {
            "title": "What Is Algebra?",
            "concept": "Writing a general rule",
            "learning_goals": ["Identify the changing quantity", "Choose the fixed operation"],
        },
        "topic_outcome": {
            "mastery_status": "NEARLY_MASTERED",
            "recommended_next_action": "COMPLETE_TOPIC",
        },
        "replay_items": [
            {
                "review_item_id": "REV-001",
                "phase": "PHASE_3_INDEPENDENT_PRACTICE",
                "evaluation": "INCORRECT",
                "question_id": "Q-T01-005",
                "question_usage_id": "QU-T01-005-P3",
                "attempt_id": "ATTEMPT-021",
                "question_text": "A temperature t falls by 3 degrees. Write the rule.",
                "student_answer": "t + 3",
                "ocr_text": "t + 3",
                "work_artifact": {
                    "artifact_id": "ART-P3-000124",
                    "pdf_url": "https://storage.example/submission.pdf",
                    "page_count": 2,
                },
                "detected_errors": [
                    {"error_code": "ERR-DIRECTION-REVERSED", "micro_skill_id": "T01.M3"}
                ],
                "linked_misconceptions": ["MIS-T01-DIRECTION-LANGUAGE"],
                "canonical_answer": "t - 3",
                "answer_steps": [
                    "Identify t as the starting temperature.",
                    "Translate falls by 3 as subtract 3.",
                    "Write t - 3.",
                ],
            }
        ],
        "whole_topic_evidence": {
            "strong_micro_skill_ids": ["T01.M1"],
            "developing_micro_skill_ids": ["T01.M3"],
            "root_gap_micro_skill_ids": [],
            # Nested by micro-skill, matching what Student Model emits. This
            # fixture said {"ERR-DIRECTION-REVERSED": 2} until 22 Aug 2026, the
            # same wrong shape the model declared, so the pair agreed with each
            # other and disagreed with the service.
            "error_cluster_counts": {"T01.M3": {"ERR-DIRECTION-REVERSED": 2}},
            "misconception_recurrence_counts": {"MIS-T01-DIRECTION-LANGUAGE": 2},
            "hint_count": 0,
            "fresh_question_required": True,
            "phase_2_repair_required": False,
            "final_independent_results": [
                {"question_id": "Q-T01-006", "evaluation": "CORRECT", "independent": True}
            ],
        },
    }


def _response_body() -> dict[str, object]:
    return {
        "tutor_replays": [
            {
                "review_item_id": "REV-001",
                "question_id": "Q-T01-005",
                "attempt_id": "ATTEMPT-021",
                "artifact_id": "ART-P3-000124",
                "first_error": {
                    "summary": "The first error was treating a fall as an increase.",
                    "student_page_no": 1,
                },
                "replay_steps": [
                    {
                        "sequence_no": 1,
                        "narration": "You correctly began with the starting temperature.",
                        "tutor_write": "Start: t",
                    },
                    {
                        "sequence_no": 2,
                        "narration": "A fall means the value decreases by three.",
                        "tutor_write": "falls by 3 → subtract 3",
                    },
                    {
                        "sequence_no": 3,
                        "narration": "So the rule subtracts three from the starting value.",
                        "tutor_write": "t - 3",
                        "board": {
                            "elements": [
                                {
                                    "kind": "value_row",
                                    "values": ["8", "5", "2"],
                                    "arrow_label": "changes",
                                },
                                {
                                    "kind": "brace",
                                    "over": "value_row",
                                    "labels": ["subtract 3"],
                                },
                                {
                                    "kind": "struck",
                                    "text": "t + 3",
                                    "tone": "error",
                                },
                                {
                                    "kind": "boxed",
                                    "text": "Rule: t - 3",
                                    "tone": "correct",
                                },
                                {
                                    "kind": "example",
                                    "text": "Try t = 8: 8 - 3 = 5",
                                },
                            ]
                        },
                    },
                ],
            }
        ],
        "student_insights": {
            "strength_summary": "You identified the changing starting quantity.",
            "development_summary": "Keep checking whether the situation increases or decreases.",
            "learning_pattern_summary": "A repeated direction-language pattern appeared, so check the operation before writing.",
            "recent_improvement_summary": "You later chose the correct operation independently.",
            "next_practice_focus": "Before writing a rule, say whether the quantity increases or decreases.",
            "personalised_notes": [
                "A letter can represent the changing starting quantity.",
                "Direction words tell you which operation to use.",
                "Check whether a quantity rises or falls before writing the rule.",
            ],
        },
    }


def test_phase4_review_rejects_unknown_contract_fields() -> None:
    body = _request_body()
    body["unexpected"] = True

    response = client.post("/ai-engine/phase4/review/generate", json=body)

    assert response.status_code == 422


def test_phase4_review_rejects_non_phase3_replay_item() -> None:
    body = _request_body()
    replay_items = body["replay_items"]
    assert isinstance(replay_items, list)
    replay_items[0]["phase"] = "PHASE_2_GUIDED_LEARNING"

    response = client.post("/ai-engine/phase4/review/generate", json=body)

    assert response.status_code == 422


def test_phase4_review_generates_exact_replay_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def generate_phase4_review(
            self,
            context: dict[str, object],
            schema: dict[str, object],
        ) -> dict[str, object]:
            assert "pdf_url" not in str(context)
            assert schema == Phase4ReviewResponse.model_json_schema()
            return _response_body()

    monkeypatch.setattr(
        phase4_review,
        "build_openai_phase4_review_client",
        lambda settings: FakeClient(),
    )

    result = phase4_review.generate_phase4_review(Phase4ReviewRequest.model_validate(_request_body()))

    assert [replay.attempt_id for replay in result.tutor_replays] == ["ATTEMPT-021"]
    assert result.tutor_replays[0].first_error.student_page_no == 1
    assert len(result.student_insights.personalised_notes) == 3
    board = result.tutor_replays[0].replay_steps[2].board
    assert board is not None
    assert [element.kind for element in board.elements] == [
        "value_row",
        "brace",
        "struck",
        "boxed",
        "example",
    ]


def test_phase4_schema_is_openai_strict_and_keeps_nullable_fields() -> None:
    schema = openai_client.openai_strict_schema(
        Phase4ReviewResponse.model_json_schema()
    )

    def assert_strict(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                assert_strict(item)
            return
        if not isinstance(node, dict):
            return
        properties = node.get("properties")
        if isinstance(properties, dict):
            assert node["required"] == list(properties)
            assert node["additionalProperties"] is False
        for value in node.values():
            assert_strict(value)

    assert_strict(schema)
    first_error = schema["$defs"]["FirstError"]
    assert "student_page_no" in first_error["required"]
    assert {item.get("type") for item in first_error["properties"]["student_page_no"]["anyOf"]} == {
        "integer",
        "null",
    }


def test_phase4_review_rejects_invented_replay_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_response = _response_body()
    replays = invalid_response["tutor_replays"]
    assert isinstance(replays, list)
    replays[0]["attempt_id"] = "ATTEMPT-999"

    class FakeClient:
        def generate_phase4_review(
            self,
            context: dict[str, object],
            schema: dict[str, object],
        ) -> dict[str, object]:
            return invalid_response

    monkeypatch.setattr(
        phase4_review,
        "build_openai_phase4_review_client",
        lambda settings: FakeClient(),
    )

    with pytest.raises(phase4_review.Phase4ReviewValidationError, match="exactly match"):
        phase4_review.generate_phase4_review(Phase4ReviewRequest.model_validate(_request_body()))


def test_phase4_review_rejects_isolated_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _request_body()
    evidence = body["whole_topic_evidence"]
    assert isinstance(evidence, dict)
    evidence["misconception_recurrence_counts"] = {"MIS-T01-DIRECTION-LANGUAGE": 1}

    class FakeClient:
        def generate_phase4_review(
            self,
            context: dict[str, object],
            schema: dict[str, object],
        ) -> dict[str, object]:
            return _response_body()

    monkeypatch.setattr(
        phase4_review,
        "build_openai_phase4_review_client",
        lambda settings: FakeClient(),
    )

    with pytest.raises(phase4_review.Phase4ReviewValidationError, match="repeated misconception"):
        phase4_review.generate_phase4_review(Phase4ReviewRequest.model_validate(body))
