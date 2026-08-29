"""Entering Review generates and stores the tutor review."""

import asyncio

import pytest
from fastapi import HTTPException

from app.adapters.student_model import StudentModelServiceAdapter
from app.core.exceptions import AdapterError, AdapterRequestRejected
from app.models.phase4_review import (
    FirstError,
    Phase4ReviewResponse,
    StudentInsights,
    TutorReplay,
    TutorReplayStep,
)
from app.models.session import SessionRecord, SessionStartRequest
from app.models.student_model_session import StudentModelSessionEventResponse
from app.models.topic_event_history import TopicEventHistoryResponse
from app.models.work_artifact import Phase4ReviewPersistRequest
from app.services import session_service
from tests.test_phase4_context_builder import TOPIC_INFO, _attempt
from tests.test_session_events import _session_opened_response


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


def test_deterministic_fields_are_forwarded_not_generated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """question_text, work_artifact, topic_outcome, question_journey are known
    before the model is ever called — forwarded from the request that was
    built, not asked of the model (see #4 of the frontend handoff)."""

    async def fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id
        return _history()

    monkeypatch.setattr(
        StudentModelServiceAdapter, "fetch_topic_event_history", fetch
    )
    # The model's own output never sets these — proving the forwarding, not a
    # value the generation step happened to produce.
    monkeypatch.setattr(
        session_service, "generate_phase4_review", lambda request: _review()
    )
    session = _review_ready_session()

    result = asyncio.run(
        session_service.generate_phase4_review_for(
            session,
            _event("REVIEW"),
        )
    )

    assert result is not None
    replay = result.tutor_replays[0]
    assert replay.question_text == "A temperature starts at t and falls by 3 degrees."
    assert replay.work_artifact is not None
    assert replay.work_artifact.pdf_url == "https://blob.example/submission.pdf"
    assert replay.work_artifact.page_count == 2

    assert result.topic_outcome is not None
    assert result.topic_outcome.mastery_status
    assert result.topic_outcome.recommended_next_action

    assert result.question_journey is not None
    assert len(result.question_journey) == 1
    assert result.question_journey[0].question_id == "Q-T01-005"
    assert result.question_journey[0].evaluation == "INCORRECT"
    assert result.question_journey[0].attempted_at == "2026-08-17T10:15:23Z"


def test_entering_review_generates_the_tutor_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id
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
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id
        return _history()

    async def persist(
        adapter: StudentModelServiceAdapter,
        request: Phase4ReviewPersistRequest,
    ) -> None:
        del adapter
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
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id
        return _history()

    async def failing_persist(
        adapter: StudentModelServiceAdapter,
        request: Phase4ReviewPersistRequest,
    ) -> None:
        del adapter, request
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
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id
        raise AdapterError("student_model", "history unavailable")

    async def persist(
        adapter: StudentModelServiceAdapter,
        request: Phase4ReviewPersistRequest,
    ) -> None:
        del adapter
        persisted.append(request)

    monkeypatch.setattr(
        StudentModelServiceAdapter, "fetch_topic_event_history", failing_fetch
    )
    monkeypatch.setattr(
        StudentModelServiceAdapter, "persist_phase4_review", persist
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            session_service.generate_phase4_review_for(
                _review_ready_session(),
                _event("REVIEW"),
            )
        )

    assert persisted == []
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "PHASE4_REVIEW_UNAVAILABLE"


def test_rejected_history_request_does_not_block_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 4xx is a sibling of AdapterError, not a subclass; catch it too.

    The history endpoint 404s until it is built, so this is the live path.
    """

    async def rejected(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id
        raise AdapterRequestRejected(
            "student_model",
            "https://student-model.example/topic/event-history",
            404,
            "not found",
            {},
        )

    monkeypatch.setattr(
        StudentModelServiceAdapter, "fetch_topic_event_history", rejected
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            session_service.generate_phase4_review_for(
                _review_ready_session(),
                _event("REVIEW"),
            )
        )

    assert error.value.status_code == 503


def test_malformed_evidence_does_not_block_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bad data from the service must degrade to no review, not an error."""

    async def fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id
        return TopicEventHistoryResponse(
            topic_id="ALG-KS3-01",
            student_id="ST003",
            topic_info=TOPIC_INFO,
            whole_topic_evidence={"error_cluster_counts": {"ERR-X": "not-an-int"}},
            attempts=[_attempt("A1", "INCORRECT")],
        )

    monkeypatch.setattr(
        StudentModelServiceAdapter, "fetch_topic_event_history", fetch
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            session_service.generate_phase4_review_for(
                _review_ready_session(),
                _event("REVIEW"),
            )
        )

    assert error.value.status_code == 503


def test_rejected_persistence_keeps_the_generated_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id
        return _history()

    async def rejected(
        adapter: StudentModelServiceAdapter,
        request: Phase4ReviewPersistRequest,
    ) -> None:
        del adapter, request
        raise AdapterRequestRejected(
            "student_model",
            "https://student-model.example/phase4-review",
            404,
            "not found",
            {},
        )

    monkeypatch.setattr(
        StudentModelServiceAdapter, "fetch_topic_event_history", fetch
    )
    monkeypatch.setattr(
        StudentModelServiceAdapter, "persist_phase4_review", rejected
    )
    monkeypatch.setattr(
        session_service, "generate_phase4_review", lambda request: _review()
    )

    result = asyncio.run(
        session_service.generate_phase4_review_for(
            _review_ready_session(),
            _event("REVIEW"),
        )
    )

    assert result is not None


def test_review_generation_failure_returns_retryable_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id
        raise AdapterError("student_model", "history unavailable")

    monkeypatch.setattr(
        StudentModelServiceAdapter, "fetch_topic_event_history", failing_fetch
    )
    session = _review_ready_session()

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            session_service.generate_phase4_review_for(
                session,
                _event("REVIEW"),
            )
        )

    assert error.value.status_code == 503
    assert error.value.detail == {
        "code": "PHASE4_REVIEW_UNAVAILABLE",
        "message": "The session review could not be prepared. Retry the review.",
    }


def test_review_lands_on_the_session_when_the_student_enters_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The end-to-end path: finishing Phase 3 leaves a review on the session."""

    from tests import test_canvas

    async def fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id
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


def test_session_opening_in_review_generates_the_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A student who finishes Independent Practice, leaves, and comes back opens
    a session already in Review. That path builds the SessionRecord directly and
    never runs _apply_schema_event, which is the only other place the review is
    generated, so the screen rendered permanently empty for them.

    Observed on ST020, 22 Aug 2026: SESSION_OPENED returned a REVIEW payload,
    the session came back current_phase=REVIEW with phase_transitions=[] and
    phase4_review=null.
    """

    async def fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id
        return _history()

    async def persist(
        adapter: StudentModelServiceAdapter,
        request: Phase4ReviewPersistRequest,
    ) -> None:
        del adapter, request

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: object,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = _session_opened_response("REVIEW")
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(StudentModelServiceAdapter, "fetch_topic_event_history", fetch)
    monkeypatch.setattr(StudentModelServiceAdapter, "persist_phase4_review", persist)
    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", send_session_event
    )
    monkeypatch.setattr(
        session_service, "generate_phase4_review", lambda request: _review()
    )

    session = asyncio.run(
        session_service.start_session(
            SessionStartRequest(
                student_id="ST020",
                concept_id="ALG_LINEAR_ONE_STEP",
                interaction_mode="TEXT",
            ),
            "student-token",
        )
    )

    assert session.current_phase == "REVIEW"
    assert session.phase4_review is not None, "a session opening in Review has no review"
    assert session.phase4_review.tutor_replays[0].review_item_id == "REV-001"


def test_entering_review_stays_200_while_the_retry_read_reports_the_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A generation failure is reported on the read, never on the way in.

    Raising out of start_session looks like the stricter, safer choice and is
    the opposite: the 503 is raised before the client is told its session_id,
    and that id is the argument to the GET which is the only retry. The student
    is locked out of Review entirely rather than shown it late. The same applies
    to /interaction and /canvas/submit, where the failure would report the
    student's accepted final answer as a failed submission.

    So the transition answers 200 with no review, and GET /session/{id} answers
    PHASE4_REVIEW_UNAVAILABLE until generation succeeds. An absent review is
    still never shown as success -- the client renders Phase 4 only on a
    non-null phase4_review.
    """

    generation_works = False

    async def fetch(
        adapter: StudentModelServiceAdapter,
        student_id: str,
        topic_id: str,
    ) -> TopicEventHistoryResponse:
        del adapter, student_id, topic_id
        if not generation_works:
            raise AdapterError("student_model", "history unavailable")
        return _history()

    async def persist(
        adapter: StudentModelServiceAdapter,
        request: Phase4ReviewPersistRequest,
    ) -> None:
        del adapter, request

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: object,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = _session_opened_response("REVIEW")
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(StudentModelServiceAdapter, "fetch_topic_event_history", fetch)
    monkeypatch.setattr(StudentModelServiceAdapter, "persist_phase4_review", persist)
    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", send_session_event
    )
    monkeypatch.setattr(
        session_service, "generate_phase4_review", lambda request: _review()
    )

    session = asyncio.run(
        session_service.start_session(
            SessionStartRequest(
                student_id="ST021",
                concept_id="ALG_LINEAR_ONE_STEP",
                interaction_mode="TEXT",
            ),
            "student-token",
        )
    )

    # The way in: the transition is persisted and the id reaches the client.
    assert session.current_phase == "REVIEW"
    assert session.phase4_review is None

    # The read: visibly unavailable, not a 200 carrying a null review.
    with pytest.raises(HTTPException) as error:
        asyncio.run(session_service.get_session(session.session_id, "ST021"))
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "PHASE4_REVIEW_UNAVAILABLE"

    # The retry, once the provider recovers.
    generation_works = True
    recovered = asyncio.run(session_service.get_session(session.session_id, "ST021"))
    assert recovered.phase4_review is not None
    assert recovered.phase4_review.tutor_replays[0].review_item_id == "REV-001"


def test_review_unavailable_reaches_the_client_as_a_readable_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PHASE4_REVIEW_UNAVAILABLE must arrive as error_code, not as prose.

    The review screen branches on this code to decide between "Review could not
    be prepared, Retry" and a generic failure. FastAPI's handler used to render
    a dict detail with str(), so the browser received the Python repr
    "{'code': 'PHASE4_REVIEW_UNAVAILABLE', ...}" inside `message` and would have
    had to pattern-match a language's repr format out of a human sentence.
    """

    from fastapi.testclient import TestClient

    from app.main import app
    from tests.test_session_events import _use_live_student_model

    async def post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, headers, timeout_seconds, retry_count
        if url.endswith("/topic/event-history"):
            raise AdapterError("student_model", "history unavailable")
        body = _session_opened_response("REVIEW")
        body["request_id"] = payload["request_id"]
        return body

    _use_live_student_model(monkeypatch, post_json)
    client = TestClient(app, headers={"Authorization": "Bearer test-token"})

    started = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    # The way in stays 200 so the client learns the id it needs to retry with.
    assert started.status_code == 200, started.text
    session_id = started.json()["session_id"]

    read = client.get(f"/session/{session_id}", params={"student_id": "ST001"})
    assert read.status_code == 503
    assert read.json()["error_code"] == "PHASE4_REVIEW_UNAVAILABLE"
