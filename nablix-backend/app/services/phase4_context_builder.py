"""Assemble the Phase 4 review request from authoritative backend evidence.

The tutor engine phrases this evidence for the student; it never decides any
of it. Everything here comes from the Student Model service or from facts
about the attempts themselves — nothing is invented locally.
"""

from __future__ import annotations

from app.core.logger import logger
from app.models.phase4_review import (
    DetectedError,
    FinalIndependentResult,
    JourneyQuestion,
    Phase4ReviewRequest,
    ReplayItem,
    TopicInfo,
    TopicOutcome,
    WholeTopicEvidence,
    WorkArtifact,
)
from app.models.topic_event_history import (
    TopicAttemptRecord,
    TopicEventHistoryResponse,
)
from app.services.phase4_replay_filter import PHASE_3


class Phase4ContextError(ValueError):
    pass


def _replay_item(index: int, attempt: TopicAttemptRecord) -> ReplayItem | None:
    """Build one replay item, or None when it cannot be replayed.

    Several kinds of wrong attempt cannot be shown to the student: one whose
    work was never stored (it predates work artifacts, or storage failed),
    one with no usage id, and one with no error mapped to a specific skill
    (an error can arrive with no micro_skill_id -- that's routine upstream
    data, not corruption). All still count as evidence for the topic
    summary; they just have nothing to replay.
    """

    if attempt.work_artifact is None:
        logger.info(
            "phase4_replay_item_skipped",
            extra={"attempt_id": attempt.attempt_id, "reason": "no_work_artifact"},
        )
        return None
    if attempt.question_usage_id is None:
        logger.info(
            "phase4_replay_item_skipped",
            extra={"attempt_id": attempt.attempt_id, "reason": "no_question_usage_id"},
        )
        return None
    detected_errors = [
        DetectedError(error_code=error.error_code, micro_skill_id=error.micro_skill_id)
        for error in attempt.detected_errors
        if error.micro_skill_id is not None
    ]
    if not detected_errors:
        logger.info(
            "phase4_replay_item_skipped",
            extra={"attempt_id": attempt.attempt_id, "reason": "no_detected_errors"},
        )
        return None
    return ReplayItem(
        review_item_id=f"REV-{index:03d}",
        phase=PHASE_3,
        evaluation="INCORRECT" if attempt.evaluation == "INCORRECT" else "WRONG",
        question_id=attempt.question_id,
        question_usage_id=attempt.question_usage_id,
        attempt_id=attempt.attempt_id,
        question_text=attempt.question_text,
        student_answer=attempt.student_response,
        work_artifact=WorkArtifact(
            artifact_id=attempt.work_artifact.artifact_id,
            pdf_url=attempt.work_artifact.pdf_url,
            page_count=attempt.work_artifact.page_count,
        ),
        detected_errors=detected_errors,
        linked_misconceptions=attempt.linked_misconceptions,
        canonical_answer=attempt.canonical_answer,
        answer_steps=attempt.answer_steps,
    )


def _whole_topic_evidence(
    history: TopicEventHistoryResponse,
) -> WholeTopicEvidence:
    """Aggregate analytics come from the service; per-attempt facts are counted
    here from the attempts themselves, so the service need not restate them."""

    evidence = history.whole_topic_evidence
    phase_3 = [a for a in history.attempts if a.phase == PHASE_3]
    # `or []` rather than a .get default: the service SENDS these keys with a
    # null value when the student has no topic learning summary row yet, so the
    # default never applied and list(None) raised a TypeError -- which is not a
    # ValueError, so it escaped generate_phase4_review_for's handler and 500'd
    # the student's Phase 3 submit instead of degrading to no review.
    return WholeTopicEvidence(
        strong_micro_skill_ids=list(evidence.get("strong_micro_skill_ids") or []),
        developing_micro_skill_ids=list(
            evidence.get("developing_micro_skill_ids") or []
        ),
        root_gap_micro_skill_ids=list(evidence.get("root_gap_micro_skill_ids") or []),
        error_cluster_counts={
            skill: dict(counts)
            for skill, counts in (evidence.get("error_cluster_counts") or {}).items()
        },
        misconception_recurrence_counts=dict(
            evidence.get("misconception_recurrence_counts") or {}
        ),
        hint_count=sum(1 for attempt in phase_3 if attempt.hint_used),
        fresh_question_required=any(
            attempt.fresh_question_replacement for attempt in phase_3
        ),
        phase_2_repair_required=bool(evidence.get("phase_2_repair_required", False)),
        final_independent_results=[
            FinalIndependentResult(
                question_id=attempt.question_id,
                evaluation=attempt.evaluation,
                independent=(
                    attempt.independent_success
                    if attempt.independent_success is not None
                    else not attempt.hint_used
                ),
            )
            for attempt in phase_3
        ],
    )


def build_phase4_review_request(
    history: TopicEventHistoryResponse,
    replay_attempts: list[TopicAttemptRecord],
    mastery_status: str,
    recommended_next_action: str,
) -> Phase4ReviewRequest:
    """Turn one topic's history into the tutor engine's review request."""

    try:
        topic_info = TopicInfo.model_validate(history.topic_info)
    except ValueError as error:
        # Never fabricate topic content: a review naming the wrong concept is
        # worse for the student than no review.
        raise Phase4ContextError(
            f"topic_info missing for topic={history.topic_id}: {error}"
        ) from error

    replay_items = [
        item
        for item in (
            _replay_item(index, attempt)
            for index, attempt in enumerate(replay_attempts, start=1)
        )
        if item is not None
    ]
    return Phase4ReviewRequest(
        topic_info=topic_info,
        topic_outcome=TopicOutcome(
            mastery_status=mastery_status,
            recommended_next_action=recommended_next_action,
        ),
        replay_items=replay_items,
        whole_topic_evidence=_whole_topic_evidence(history),
        # Every Phase 3 attempt with question text, so the tutor can label the
        # correct rows too -- replay_items only ever holds the wrong ones.
        journey_questions=[
            JourneyQuestion(
                question_usage_id=attempt.question_usage_id,
                attempt_id=attempt.attempt_id,
                question_text=attempt.question_text,
            )
            for attempt in history.attempts
            if attempt.phase == PHASE_3 and attempt.question_text
        ],
    )
