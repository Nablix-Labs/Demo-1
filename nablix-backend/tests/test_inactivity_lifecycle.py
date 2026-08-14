from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.models.session import NudgeDeliveryRecord
from app.services import session_service


def _record(interaction_id: str) -> NudgeDeliveryRecord:
    return NudgeDeliveryRecord(
        interaction_id=interaction_id,
        session_id="SESSION001",
        source_tutor_turn_id="TUTOR-1",
        question_id="QUESTION-1",
        message="Are you still with me?",
        message_voice="Are you still with me?",
        status="GENERATED",
        created_at=datetime.now(timezone.utc),
    )


def test_inactivity_policy_rejects_non_positive_limits() -> None:
    with pytest.raises(ValidationError):
        Settings(inactivity_generated_nudge_rate_limit=0)


def test_nudge_delivery_is_idempotent_and_follows_lifecycle() -> None:
    record = _record("TURN-NUDGE-LIFECYCLE-1")
    assert session_service.store_nudge_delivery(record) == record
    assert session_service.store_nudge_delivery(record) == record

    presented_at = datetime.now(timezone.utc)
    acknowledged_at = datetime.now(timezone.utc)
    presented = session_service.update_nudge_delivery_status(
        record.session_id,
        record.interaction_id,
        "PRESENTED",
        presented_at,
        acknowledged_at,
    )

    assert presented.presented_at == presented_at
    assert presented.acknowledged_at == acknowledged_at
    assert session_service.nudge_delivery_for(
        record.session_id,
        record.interaction_id,
    ) == presented
    assert session_service.nudge_deliveries_for_tutor_turn(
        record.session_id,
        record.source_tutor_turn_id,
    ) == [presented]
    session_service.clear_nudge_deliveries_for_session(record.session_id)
    assert session_service.nudge_delivery_for(
        record.session_id,
        record.interaction_id,
    ) is None


def test_nudge_delivery_rejects_skipped_lifecycle_state() -> None:
    record = _record("TURN-NUDGE-LIFECYCLE-2")
    session_service.store_nudge_delivery(record)
    presented_at = datetime.now(timezone.utc)
    session_service.update_nudge_delivery_status(
        record.session_id,
        record.interaction_id,
        "PRESENTED",
        presented_at,
        presented_at,
    )

    with pytest.raises(ValueError, match="PRESENTED->PRESENTED"):
        session_service.update_nudge_delivery_status(
            record.session_id,
            record.interaction_id,
            "PRESENTED",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        )
