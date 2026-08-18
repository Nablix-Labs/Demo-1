"""Entering Review generates the tutor review, and never blocks on it."""

import asyncio

import pytest

from app.adapters.student_model import StudentModelServiceAdapter
from app.core.exceptions import AdapterError
from app.models.phase4_review import (
    FirstError,
    Phase4ReviewResponse,
    StudentInsights,
    TutorReplay,
    TutorReplayStep,
)
from app.models.session import SessionRecord
from app.models.student_model_session import StudentModelSessionEventResponse
from app.models.topic_event_history import TopicEventHistoryResponse
from app.models.work_artifact import Phase4ReviewPersistRequest
from app.services import session_service
from tests.test_phase4_context_builder import TOPIC_INFO, _attempt


def _history() -> TopicEventHistoryResponse:
    return TopicEventHistoryResponse(
        topic_id="ALG-KS3-01",
        student_id="ST003",
        topic_info=TOPIC_INFO,
        attempts=[_attempt("A1", "INCORRECT")],
    )


def _review() -> Phase4ReviewResponse:
    return Phase4ReviewResponse(
        tutor_replays=[
            TutorReplay(
                review_item_id="REV-001",
                question_id="Q-T01-005",
                attempt_id="A1",
                artifact_id="ART-A1",
                first_error=FirstError(summary="Falls by 3 was treated as adding."),
                replay_steps=[
                    TutorReplayStep(
                        sequence_no=1,
                        narration="You started with t, which is right.",
                        tutor_write="t",
                    )
                ],
            )
        ],
        student_insights=StudentInsights(
            strength_summary="You chose the right starting value.",
            development_summary="Check whether the amount goes up or down.",
            next_practice_focus="Decide the direction before writing the rule.",
            personalised_notes=[
                "A letter can stand for any starting number.",
                "Falls means subtract.",
                "Read the direction word before choosing the operation.",
            ],
        ),
    )


def _event(phase: str) -> StudentModelSessionEventResponse:
    from tests.test_session_events import _session_opened_response

    return StudentModelSessionEventResponse.model_validate(
        _session_opened_response(phase)
    )


def _review_ready_session() -> SessionRecord:
    """A session identified well enough to review; generation reads only ids."""

    return SessionRecord.model_construct(
        session_id="SESSION-001",
        student_id="ST003",
    )


def test_entering_review_generates_the_tutor_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
        access_token: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id, access_token
        return _history()

    monkeypatch.setattr(
        StudentModelServiceAdapter, "fetch_topic_event_history", fetch
    )
    monkeypatch.setattr(
        session_service, "generate_phase4_review", lambda request: _review()
    )
    session = _review_ready_session()

    result = asyncio.run(
        session_service.generate_phase4_review_for(
            session,
            _event("REVIEW"),
            "test-token",
        )
    )

    assert result is not None
    assert result.tutor_replays[0].attempt_id == "A1"
    assert result.student_insights.next_practice_focus


def test_generated_review_is_persisted_for_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: list[Phase4ReviewPersistRequest] = []

    async def fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
        access_token: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id, access_token
        return _history()

    async def persist(
        adapter: StudentModelServiceAdapter,
        request: Phase4ReviewPersistRequest,
        access_token: str,
    ) -> None:
        del adapter, access_token
        persisted.append(request)

    monkeypatch.setattr(
        StudentModelServiceAdapter, "fetch_topic_event_history", fetch
    )
    monkeypatch.setattr(
        StudentModelServiceAdapter, "persist_phase4_review", persist
    )
    monkeypatch.setattr(
        session_service, "generate_phase4_review", lambda request: _review()
    )

    asyncio.run(
        session_service.generate_phase4_review_for(
            _review_ready_session(),
            _event("REVIEW"),
            "test-token",
        )
    )

    assert len(persisted) == 1
    assert persisted[0].student_id == "ST003"
    assert persisted[0].student_insights["next_practice_focus"]
    assert persisted[0].tutor_replays[0]["attempt_id"] == "A1"


def test_review_survives_a_persistence_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
        access_token: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id, access_token
        return _history()

    async def failing_persist(
        adapter: StudentModelServiceAdapter,
        request: Phase4ReviewPersistRequest,
        access_token: str,
    ) -> None:
        del adapter, request, access_token
        raise AdapterError("student_model", "summary store unavailable")

    monkeypatch.setattr(
        StudentModelServiceAdapter, "fetch_topic_event_history", fetch
    )
    monkeypatch.setattr(
        StudentModelServiceAdapter, "persist_phase4_review", failing_persist
    )
    monkeypatch.setattr(
        session_service, "generate_phase4_review", lambda request: _review()
    )

    result = asyncio.run(
        session_service.generate_phase4_review_for(
            _review_ready_session(),
            _event("REVIEW"),
            "test-token",
        )
    )

    # Already generated, so the student still sees it.
    assert result is not None


def test_review_is_not_persisted_when_generation_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: list[Phase4ReviewPersistRequest] = []

    async def failing_fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
        access_token: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id, access_token
        raise AdapterError("student_model", "history unavailable")

    async def persist(
        adapter: StudentModelServiceAdapter,
        request: Phase4ReviewPersistRequest,
        access_token: str,
    ) -> None:
        del adapter, access_token
        persisted.append(request)

    monkeypatch.setattr(
        StudentModelServiceAdapter, "fetch_topic_event_history", failing_fetch
    )
    monkeypatch.setattr(
        StudentModelServiceAdapter, "persist_phase4_review", persist
    )

    asyncio.run(
        session_service.generate_phase4_review_for(
            _review_ready_session(),
            _event("REVIEW"),
            "test-token",
        )
    )

    assert persisted == []


def test_review_generation_failure_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
        access_token: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id, access_token
        raise AdapterError("student_model", "history unavailable")

    monkeypatch.setattr(
        StudentModelServiceAdapter, "fetch_topic_event_history", failing_fetch
    )
    session = _review_ready_session()

    # The student still reaches Review; only the review itself is missing.
    result = asyncio.run(
        session_service.generate_phase4_review_for(
            session,
            _event("REVIEW"),
            "test-token",
        )
    )

    assert result is None


def test_review_lands_on_the_session_when_the_student_enters_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The end-to-end path: finishing Phase 3 leaves a review on the session."""

    from tests import test_canvas

    async def fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
        access_token: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id, access_token
        return _history()

    monkeypatch.setattr(
        StudentModelServiceAdapter, "fetch_topic_event_history", fetch
    )
    monkeypatch.setattr(
        session_service, "generate_phase4_review", lambda request: _review()
    )
    session_id = test_canvas._review_transition_session(monkeypatch)

    response = test_canvas.client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST042",
            "turn_id": "TURN-ST042-CANVAS-1",
            "snapshot_data_url": test_canvas._real_png_data_url(),
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["current_phase"] == "REVIEW"
    stored = session_service._get_owned_session(session_id, "ST042")
    assert stored.phase4_review is not None
    assert stored.phase4_review.tutor_replays[0].attempt_id == "A1"
