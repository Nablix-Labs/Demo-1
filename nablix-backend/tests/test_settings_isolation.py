"""The suite must not read the deployment .env.

conftest closes two doors (Settings.env_file, and the load_dotenv() calls four
modules make at import). Both are invisible: if a fifth module starts calling
load_dotenv, or a new settings source appears, the leak returns silently and
the suite goes back to depending on whose machine it runs on. These tests are
the tripwire.
"""

import asyncio

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.models.session import SessionStartRequest
from app.services import session_service


def test_settings_do_not_read_the_deployment_env_file() -> None:
    assert Settings.model_config.get("env_file") is None


def test_no_deployment_credential_reaches_the_test_process() -> None:
    """A live key here means the suite is calling real services on someone's bill.

    Asserted on a freshly constructed Settings, not the fixture's patched one:
    the fixture proves what tests are handed, this proves what the environment
    itself carries.
    """

    fresh = Settings()

    # Reported by field name only. Asserting on the values themselves makes
    # pytest print the leaked secret into the failure output, which is how a
    # credential ends up in a CI log.
    leaked = [
        name
        for name in (
            "mathpix_app_key",
            "mathpix_app_id",
            "openai_api_key",
            "student_model_jwt_secret",
            "student_model_url",
        )
        if getattr(fresh, name)
    ]

    assert leaked == [], f"deployment credentials reached the test process: {leaked}"
    assert fresh.use_mock_vision is True


def test_session_start_rejects_an_unmapped_concept_id() -> None:
    """The shared fixture now configures a topic code for every test, so this
    validation branch is no longer reachable by accident. It is still the
    boundary that rejects an unknown topic, so it gets its own test.
    """

    with pytest.raises(HTTPException) as rejected:
        asyncio.run(
            session_service.start_session(
                SessionStartRequest(
                    student_id="ST001",
                    concept_id="NOT_A_CONFIGURED_CONCEPT",
                    interaction_mode="TEXT",
                ),
                "student-token",
            )
        )

    assert rejected.value.status_code == 422
    assert "topic_code" in str(rejected.value.detail)
