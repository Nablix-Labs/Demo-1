"""Independent Practice shows the learner no tutor marks on their own work.

Phase 3 is evidence of what the student can do unaided, so the tutor layer stays
empty and wrong work is replayed in Phase 4 instead. Two sites enforce it --
`/canvas/submit` before it plans anything, `_process_interaction` by overwriting
the response it just built -- and until now each spelled the rule out as its own
`current_phase == "INDEPENDENT_PRACTICE"` comparison.

No behavioural gap is closed here: both already zeroed `canvas_draw`. What was
missing was a single name, so a reader of either site sees one rule rather than
two coincidences -- and so the sites that do NOT consult it become findable.
`_process_interaction` has three earlier returns that set `canvas_draw` to a
write-request block and never reach the overwrite; whether Phase 3 can reach
them is open, and tracked separately from this change.
"""

from datetime import datetime, timezone

from app.models.session import SessionRecord
from app.services.session_service import independent_practice_is_silent


def _session(phase: str) -> SessionRecord:
    return SessionRecord(
        session_id="SESSION001",
        student_id="ST031",
        concept_id="ALG_LINEAR_ONE_STEP",
        started_at=datetime.now(timezone.utc),
        current_phase=phase,
        current_question="What is the rule?",
        question_id="Q-T01-001",
        question_number=1,
        interaction_mode="TEXT",
        ui_state="AWAITING_ANSWER",
        message="",
        hint_count=0,
        status="started",
    )


def test_only_independent_practice_is_silent() -> None:
    assert independent_practice_is_silent(_session("INDEPENDENT_PRACTICE")) is True
    assert independent_practice_is_silent(
        _session("INDEPENDENT_PRACTICE").model_copy(update={"question_id": None})
    ) is False
    assert independent_practice_is_silent(_session("GUIDED_PRACTICE")) is False
    assert independent_practice_is_silent(_session("CONCEPT_ORIENTATION")) is False
    assert independent_practice_is_silent(_session("REVIEW")) is False
