import asyncio
import os
from threading import Event

import pytest

from app.models.canvas_teaching import (
    CanvasSpeechAnchor,
    CanvasTeachingBeat,
    CanvasTeachingOperation,
    CanvasTeachingPlan,
)
from app.services import canvas_teaching_planner, interaction_service, session_service
from tests.test_canvas_teaching_planner import _anchor, _enabled_rules, _tutor


def _plan(turn_id: str) -> CanvasTeachingPlan:
    return CanvasTeachingPlan(
        plan_id=f"Q-DEFERRED:{turn_id}:canvas-teaching",
        question_id="Q-DEFERRED",
        source_turn_id=turn_id,
        tutor_turn_id="TUTOR-DEFERRED",
        scene_revision=9,
        mode="append",
        teaching_mode="GUIDED",
        beats=[
            CanvasTeachingBeat(
                beat_id="beat-1",
                sequence=1,
                speech_anchor=CanvasSpeechAnchor(
                    start_char=0,
                    end_char=4,
                    text="Look",
                ),
                operations=[
                    CanvasTeachingOperation(
                        operation_id="op-1",
                        kind="FOCUS",
                        target_kind="CANVAS_ZONE",
                        target_ids=["ZONE:QUESTION"],
                        zone="QUESTION",
                        persistence="PULSE",
                    )
                ],
            )
        ],
    )


def test_deferred_canvas_plan_is_pending_until_background_work_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "SESSIONdeferredplan"
    turn_id = "TURN-DEFERRED-READY"
    started = Event()
    release = Event()

    def blocking_plan(**_: object) -> CanvasTeachingPlan:
        started.set()
        assert release.wait(timeout=1)
        return _plan(turn_id)

    monkeypatch.setattr(interaction_service, "plan_canvas_teaching", blocking_plan)
    session_service.start_deferred_canvas_teaching_plan(
        session_id,
        turn_id,
        9,
        "Q-DEFERRED",
    )

    async def run() -> None:
        task = asyncio.create_task(
            interaction_service._generate_deferred_canvas_teaching_plan(
                session_id,
                turn_id,
                {"question_id": "Q-DEFERRED"},
            )
        )
        assert await asyncio.to_thread(started.wait, 1)
        pending = session_service.deferred_canvas_teaching_plan_for(session_id, turn_id)
        assert pending is not None
        assert pending.status == "PENDING"
        release.set()
        await task

    asyncio.run(run())
    ready = session_service.deferred_canvas_teaching_plan_for(session_id, turn_id)
    assert ready is not None
    assert ready.status == "READY"
    assert ready.canvas_teaching_plan == _plan(turn_id)


def test_deferred_canvas_plan_failure_does_not_escape_the_tutor_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "SESSIONdeferredfailure"
    turn_id = "TURN-DEFERRED-FAILURE"

    def failing_plan(**_: object) -> CanvasTeachingPlan:
        raise RuntimeError("planner unavailable")

    monkeypatch.setattr(interaction_service, "plan_canvas_teaching", failing_plan)
    session_service.start_deferred_canvas_teaching_plan(
        session_id,
        turn_id,
        10,
        "Q-DEFERRED",
    )

    asyncio.run(
        interaction_service._generate_deferred_canvas_teaching_plan(
            session_id,
            turn_id,
            {"question_id": "Q-DEFERRED"},
        )
    )

    unavailable = session_service.deferred_canvas_teaching_plan_for(session_id, turn_id)
    assert unavailable is not None
    assert unavailable.status == "UNAVAILABLE"
    assert unavailable.canvas_teaching_plan is None


def test_openai_deferred_canvas_plan_smoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the background delivery path against OpenAI only when explicitly enabled."""

    if os.getenv("NABLIX_RUN_OPENAI_SMOKE") != "true":
        pytest.skip("Set NABLIX_RUN_OPENAI_SMOKE=true to run the billed OpenAI smoke test.")

    monkeypatch.setattr(
        canvas_teaching_planner,
        "load_classifier_rules",
        _enabled_rules,
    )

    session_id = "SESSIONdeferredopenai"
    turn_id = "TURN-DEFERRED-OPENAI"
    session_service.start_deferred_canvas_teaching_plan(
        session_id,
        turn_id,
        3,
        "Q1",
    )

    asyncio.run(
        interaction_service._generate_deferred_canvas_teaching_plan(
            session_id,
            turn_id,
            {
                "question_id": "Q1",
                "question": "3 + 5 | 9 + 5 | 14 + 5",
                "source_turn_id": turn_id,
                "tutor_turn_id": "TUTOR-DEFERRED-OPENAI",
                "scene_revision": 3,
                "tutor_message_voice": "Those first numbers are different.",
                "tutor": _tutor(),
                "question_anchors": [_anchor()],
                "student_response": "They are different.",
                "canonical_answer": "n + 5",
                "active_support_level": "HINT",
                "current_unresolved_component_id": "FIXED_VALUE",
            },
        )
    )

    ready = session_service.deferred_canvas_teaching_plan_for(session_id, turn_id)
    assert ready is not None
    assert ready.status == "READY"
    assert ready.canvas_teaching_plan is not None
    assert ready.canvas_teaching_plan.source_turn_id == turn_id
