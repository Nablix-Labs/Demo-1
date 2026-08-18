"""The spec's four Phase 4 replay cases, as tests.

Each case is a real Phase 3 journey; the filter must pick exactly the wrong
independent submissions out of it.
"""

from app.models.topic_event_history import TopicAttemptRecord
from app.services.phase4_replay_filter import filter_replay_attempts


def _attempt(
    attempt_id: str,
    evaluation: str,
    *,
    question_id: str = "Q-T01-005",
    phase: str = "PHASE_3_INDEPENDENT_PRACTICE",
    hint_used: bool = False,
    fresh: bool = False,
) -> TopicAttemptRecord:
    return TopicAttemptRecord(
        attempt_id=attempt_id,
        question_id=question_id,
        question_usage_id=f"QU-{question_id}-P3",
        phase=phase,
        evaluation=evaluation,
        hint_used=hint_used,
        fresh_question_replacement=fresh,
        attempted_at="2026-08-17T10:15:23Z",
    )


def _ids(attempts: list[TopicAttemptRecord]) -> list[str]:
    return [attempt.attempt_id for attempt in attempts]


def test_case_a_first_attempt_correct_has_no_replay() -> None:
    journey = [_attempt("A1", "CORRECT")]

    assert filter_replay_attempts(journey) == []


def test_case_b_replays_only_the_initial_wrong_attempt() -> None:
    journey = [
        _attempt("B1", "INCORRECT"),
        _attempt("B2", "CORRECT", question_id="Q-T01-006", fresh=True),
    ]

    # The fresh correct answer is improvement evidence, never a replay.
    assert _ids(filter_replay_attempts(journey)) == ["B1"]


def test_case_c_replays_both_wrong_attempts_but_not_the_repaired_correct() -> None:
    journey = [
        _attempt("C1", "INCORRECT"),
        _attempt("C2", "INCORRECT", question_id="Q-T01-006", fresh=True),
        _attempt("C3", "CORRECT", question_id="Q-T01-006", fresh=True),
    ]

    assert _ids(filter_replay_attempts(journey)) == ["C1", "C2"]


def test_case_d_hint_then_correct_has_no_replay() -> None:
    journey = [_attempt("D1", "CORRECT", hint_used=True)]

    # A hint is support evidence; it never earns a replay on its own.
    assert filter_replay_attempts(journey) == []


def test_wrong_attempts_outside_phase_3_are_not_replayed() -> None:
    journey = [
        _attempt("G1", "INCORRECT", phase="PHASE_2_GUIDED_LEARNING"),
        _attempt("P1", "INCORRECT"),
    ]

    # Phase 4 reviews independent practice only; guided work is not replayed.
    assert _ids(filter_replay_attempts(journey)) == ["P1"]


def test_wrong_evaluation_spelling_is_accepted() -> None:
    journey = [_attempt("W1", "WRONG")]

    assert _ids(filter_replay_attempts(journey)) == ["W1"]


def test_replays_keep_the_order_the_attempts_were_made() -> None:
    journey = [
        _attempt("F1", "INCORRECT"),
        _attempt("F2", "CORRECT"),
        _attempt("F3", "INCORRECT", question_id="Q-T01-009"),
    ]

    assert _ids(filter_replay_attempts(journey)) == ["F1", "F3"]
