import pytest

from app.models.topic_event_history import (
    DetectedErrorRecord,
    TopicAttemptRecord,
    TopicEventHistoryResponse,
    WorkArtifactRef,
)
from app.services.phase4_context_builder import (
    Phase4ContextError,
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
