import json
from pathlib import Path

import pytest

from app.models.topic_event_history import (
    DetectedErrorRecord,
    TopicAttemptRecord,
    TopicEventHistoryResponse,
    WorkArtifactRef,
)
from app.services.phase4_context_builder import (
    Phase4ContextError,
    _whole_topic_evidence,
    build_phase4_review_request,
)
from app.services.phase4_replay_filter import filter_replay_attempts


TOPIC_INFO = {
    "title": "Writing general rules",
    "concept": "A letter can stand for any starting number.",
    "learning_goals": ["Translate words into an expression."],
}


def _attempt(
    attempt_id: str,
    evaluation: str,
    *,
    with_artifact: bool = True,
    with_errors: bool = True,
    hint_used: bool = False,
    fresh: bool = False,
) -> TopicAttemptRecord:
    return TopicAttemptRecord(
        attempt_id=attempt_id,
        question_id="Q-T01-005",
        question_usage_id="QU-T01-005-P3",
        phase="PHASE_3_INDEPENDENT_PRACTICE",
        evaluation=evaluation,
        hint_used=hint_used,
        fresh_question_replacement=fresh,
        attempted_at="2026-08-17T10:15:23Z",
        student_response="t + 3",
        question_text="A temperature starts at t and falls by 3 degrees.",
        canonical_answer="t - 3",
        answer_steps=["Identify t.", "Falls by 3 means subtract 3.", "Write t - 3."],
        detected_errors=(
            [
                DetectedErrorRecord(
                    error_code="ERR-DIRECTION-REVERSED",
                    micro_skill_id="T01.M3",
                )
            ]
            if with_errors
            else []
        ),
        linked_misconceptions=["MIS-T01-DIRECTION-LANGUAGE"],
        work_artifact=(
            WorkArtifactRef(
                artifact_id=f"ART-{attempt_id}",
                pdf_url="https://blob.example/submission.pdf",
                page_count=2,
            )
            if with_artifact
            else None
        ),
    )


def _history(attempts: list[TopicAttemptRecord], **evidence: object) -> TopicEventHistoryResponse:
    return TopicEventHistoryResponse(
        topic_id="ALG-KS3-01",
        student_id="ST003",
        topic_info=TOPIC_INFO,
        whole_topic_evidence=evidence,
        attempts=attempts,
    )


def _build(history: TopicEventHistoryResponse):
    return build_phase4_review_request(
        history,
        filter_replay_attempts(history.attempts),
        "NEARLY_MASTERED",
        "START_NEXT_TOPIC",
    )


def test_builds_a_replay_item_per_wrong_attempt() -> None:
    history = _history([_attempt("A1", "INCORRECT"), _attempt("A2", "CORRECT")])

    request = _build(history)

    assert len(request.replay_items) == 1
    item = request.replay_items[0]
    assert item.review_item_id == "REV-001"
    assert item.attempt_id == "A1"
    assert item.canonical_answer == "t - 3"
    assert item.work_artifact.pdf_url == "https://blob.example/submission.pdf"
    assert item.detected_errors[0].error_code == "ERR-DIRECTION-REVERSED"


def test_attempt_without_stored_work_is_not_replayed() -> None:
    history = _history([_attempt("A1", "INCORRECT", with_artifact=False)])

    request = _build(history)

    # Pre-artifact attempts still count as evidence, but cannot be replayed.
    assert request.replay_items == []
    assert len(request.whole_topic_evidence.final_independent_results) == 1


def test_attempt_without_detected_errors_is_not_replayed() -> None:
    history = _history([_attempt("A1", "INCORRECT", with_errors=False)])

    assert _build(history).replay_items == []


def test_attempt_without_question_usage_id_is_not_replayed() -> None:
    attempt = _attempt("A1", "INCORRECT").model_copy(update={"question_usage_id": None})
    history = _history([attempt])

    # Still evidence for the topic summary, just nothing to replay.
    assert _build(history).replay_items == []
    assert len(_build(history).whole_topic_evidence.final_independent_results) == 1


def test_attempt_with_only_unmapped_errors_is_not_replayed() -> None:
    attempt = _attempt("A1", "INCORRECT").model_copy(
        update={
            "detected_errors": [
                DetectedErrorRecord(error_code="ERR-UNMAPPED", micro_skill_id=None)
            ]
        }
    )
    history = _history([attempt])

    assert _build(history).replay_items == []


def test_attempt_keeps_only_the_mapped_errors() -> None:
    attempt = _attempt("A1", "INCORRECT").model_copy(
        update={
            "detected_errors": [
                DetectedErrorRecord(error_code="ERR-MAPPED", micro_skill_id="T01.M3"),
                DetectedErrorRecord(error_code="ERR-UNMAPPED", micro_skill_id=None),
            ]
        }
    )
    history = _history([attempt])

    replay_items = _build(history).replay_items

    assert len(replay_items) == 1
    assert [error.error_code for error in replay_items[0].detected_errors] == [
        "ERR-MAPPED"
    ]


def test_correct_topic_produces_no_replays_but_keeps_evidence() -> None:
    history = _history([_attempt("A1", "CORRECT")])

    request = _build(history)

    assert request.replay_items == []
    assert request.whole_topic_evidence.final_independent_results[0].independent is True


def test_hint_usage_is_counted_and_marks_the_attempt_not_independent() -> None:
    history = _history([_attempt("A1", "CORRECT", hint_used=True)])

    evidence = _build(history).whole_topic_evidence

    assert evidence.hint_count == 1
    assert evidence.final_independent_results[0].independent is False


def test_fresh_question_is_reported_in_evidence() -> None:
    history = _history(
        [_attempt("A1", "INCORRECT"), _attempt("A2", "CORRECT", fresh=True)]
    )

    assert _build(history).whole_topic_evidence.fresh_question_required is True


def test_service_aggregates_are_passed_through() -> None:
    history = _history(
        [_attempt("A1", "INCORRECT")],
        strong_micro_skill_ids=["T01.M1"],
        misconception_recurrence_counts={"MIS-T01-DIRECTION-LANGUAGE": 4},
        phase_2_repair_required=True,
    )

    evidence = _build(history).whole_topic_evidence

    assert evidence.strong_micro_skill_ids == ["T01.M1"]
    assert evidence.misconception_recurrence_counts == {
        "MIS-T01-DIRECTION-LANGUAGE": 4
    }
    assert evidence.phase_2_repair_required is True


def test_missing_topic_info_is_an_error_not_invented_content() -> None:
    history = TopicEventHistoryResponse(
        topic_id="ALG-KS3-01",
        student_id="ST003",
        topic_info={},
        attempts=[_attempt("A1", "INCORRECT")],
    )

    with pytest.raises(Phase4ContextError):
        _build(history)


def test_null_whole_topic_evidence_does_not_raise() -> None:
    """The service sends these keys with a null value when the student has no
    topic learning summary row yet — exactly what a first pass through a topic
    looks like. `list(None)` raised a TypeError, which is not a ValueError, so
    it escaped generate_phase4_review_for's handler and 500'd the student's
    Phase 3 submit rather than degrading to no review."""

    history = TopicEventHistoryResponse(
        topic_id="ALG-KS3-01",
        student_id="ST003",
        topic_info=TOPIC_INFO,
        whole_topic_evidence={
            "strong_micro_skill_ids": None,
            "developing_micro_skill_ids": None,
            "root_gap_micro_skill_ids": None,
            "error_cluster_counts": None,
            "misconception_recurrence_counts": None,
            "phase_2_repair_required": False,
        },
        attempts=[],
    )

    request = build_phase4_review_request(history, [], "DEVELOPING", "START_NEXT_TOPIC")

    assert request.whole_topic_evidence.strong_micro_skill_ids == []
    assert request.whole_topic_evidence.error_cluster_counts == {}


def _live_capture() -> TopicEventHistoryResponse:
    """The real POST /topic/event-history body for ST010 on ALG-KS3-01.

    Captured from the deployed Student Model on 22 Aug 2026, the first time a
    service token got past the auth gate. Unmodified.

    It exists because every shape this repo got wrong about that endpoint came
    from guessing at its output rather than reading it. A synthetic fixture
    would have agreed with the guess.
    """

    path = Path(__file__).parent / "fixtures" / "topic_event_history_ST010.json"
    return TopicEventHistoryResponse.model_validate(json.loads(path.read_text()))


def test_live_capture_builds_two_replays() -> None:
    """ST010 answered two Independent Practice questions wrong, on purpose, and
    both stored work. That is the only shape that produces a work panel."""

    history = _live_capture()
    # topic_info is empty in the captured response because learning.topics has
    # no content for this topic yet. That is a data gap on the Student Model
    # side, not a shape problem, so it is supplied here to exercise the rest.
    history = history.model_copy(
        update={
            "topic_info": {
                "title": "One-step linear equations",
                "concept": "A letter can stand for any starting number.",
                "learning_goals": ["Translate words into an expression."],
            }
        }
    )

    request = build_phase4_review_request(
        history,
        filter_replay_attempts(history.attempts),
        "MASTERED",
        "START_REVIEW",
    )

    assert [item.work_artifact.artifact_id for item in request.replay_items] == [
        "ART-18",
        "ART-19",
    ]
    assert [item.question_id for item in request.replay_items] == [
        "Q-T01-007",
        "Q-T01-005",
    ]


def test_error_cluster_counts_are_nested_by_micro_skill() -> None:
    """Student Model's merge_error_counts builds {micro_skill: {code: count}}.
    This repo declared dict[str, int], which is the shape of its OTHER counter
    (top_error_codes), and every review died on the mismatch."""

    history = _live_capture()
    evidence = _whole_topic_evidence(history)

    assert evidence.error_cluster_counts == {"T01.M3": {"ERR-DIRECTION-REVERSED": 2}}


def test_repeated_attempt_ids_across_questions_are_not_a_collision() -> None:
    """attempt_id is f"ATTEMPT-{attempt_sequence:03d}" and the sequence restarts
    per question, so every attempt in this real capture is ATTEMPT-001. Rejecting
    that as a duplicate blocked the review outright."""

    history = _live_capture()
    replays = filter_replay_attempts(history.attempts)

    assert len({a.attempt_id for a in replays}) == 1, "precondition: ids collide"
    assert len(replays) == 2
    # Distinct questions, so the (question_usage_id, attempt_id) pair separates them.
    assert len({(a.question_usage_id, a.attempt_id) for a in replays}) == 2


def test_topic_info_gap_degrades_to_no_review() -> None:
    """Unpatched, the live capture still cannot produce a review: learning.topics
    carries no title/concept/learning_goals for this topic. Naming the wrong
    concept to a student is worse than showing no review, so this raises rather
    than inventing one."""

    with pytest.raises(Phase4ContextError):
        build_phase4_review_request(
            _live_capture(), [], "MASTERED", "START_REVIEW"
        )


def test_journey_questions_cover_correct_attempts_not_just_replays() -> None:
    """replay_items holds only wrong attempts, so a correct question has no text
    for the tutor to label unless journey_questions carries it."""

    correct = _attempt("A2", "CORRECT").model_copy(
        update={"question_usage_id": "QU-T01-009-P3", "question_id": "Q-T01-009"}
    )
    history = TopicEventHistoryResponse(
        topic_id="ALG-ORI-01",
        student_id="ST001",
        topic_info=TOPIC_INFO,
        attempts=[_attempt("A1", "INCORRECT"), correct],
    )

    request = build_phase4_review_request(history, [_attempt("A1", "INCORRECT")], "M", "N")

    assert len(request.replay_items) == 1
    assert {(q.question_usage_id, q.attempt_id) for q in request.journey_questions} == {
        ("QU-T01-005-P3", "A1"),
        ("QU-T01-009-P3", "A2"),
    }
