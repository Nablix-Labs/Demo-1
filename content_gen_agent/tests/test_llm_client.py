"""Tests for the OpenAI wrapper.

No network. The real client is only checked for the things that can be checked
offline -- configuration, and refusing to start without a key. Everything else
goes through FakeLLMClient, which is also what the generator tests use.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_client import (                          # noqa: E402
    API_KEY_VARS,
    FakeLLMClient,
    LLMClient,
    LLMError,
    LLMNotConfiguredError,
    OpenAIClient,
    find_api_key,
    is_configured,
    parse_json_object,
)


@pytest.fixture(autouse=True)
def no_ambient_key(monkeypatch):
    """Never let a real key on the machine change what these tests do."""
    for name in API_KEY_VARS:
        monkeypatch.delenv(name, raising=False)


# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────

def test_no_key_means_not_configured():
    assert find_api_key() is None
    assert is_configured() is False


def test_the_standard_variable_is_found(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert find_api_key() == "sk-test"
    assert is_configured()


def test_the_nablix_variable_is_accepted_as_a_fallback(monkeypatch):
    """Matches what nablix-backend's rag config already does."""
    monkeypatch.setenv("NABLIX_OPENAI_API_KEY", "sk-nablix")
    assert find_api_key() == "sk-nablix"


def test_the_standard_variable_wins_when_both_are_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-standard")
    monkeypatch.setenv("NABLIX_OPENAI_API_KEY", "sk-nablix")
    assert find_api_key() == "sk-standard"


def test_a_blank_key_counts_as_absent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    assert find_api_key() is None


def test_building_a_client_without_a_key_says_what_to_do():
    with pytest.raises(LLMNotConfiguredError, match="OPENAI_API_KEY"):
        OpenAIClient()


def test_the_error_does_not_leak_a_key(monkeypatch):
    """An error message must never carry the secret."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-value")
    try:
        OpenAIClient(model="whatever")
    except LLMNotConfiguredError as exc:  # pragma: no cover - should not happen
        assert "sk-super-secret-value" not in str(exc)


# ──────────────────────────────────────────────────────────────────────
# JSON parsing
# ──────────────────────────────────────────────────────────────────────

def test_plain_json_parses():
    assert parse_json_object('{"a": 1}') == {"a": 1}


def test_a_fenced_block_is_tolerated():
    """Models add ```json fences even when told not to."""
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_malformed_json_is_reported_clearly():
    with pytest.raises(LLMError, match="did not return valid JSON"):
        parse_json_object("{not json", "my call")


def test_a_json_array_is_rejected():
    with pytest.raises(LLMError, match="expected a JSON object"):
        parse_json_object("[1, 2, 3]")


def test_the_error_names_the_call():
    with pytest.raises(LLMError, match="CG-009 topic metadata"):
        parse_json_object("nope", "CG-009 topic metadata")


# ──────────────────────────────────────────────────────────────────────
# The fake client
# ──────────────────────────────────────────────────────────────────────

def test_the_fake_satisfies_the_protocol():
    assert isinstance(FakeLLMClient(), LLMClient)


def test_the_fake_returns_scripted_responses_in_order():
    client = FakeLLMClient([{"n": 1}, {"n": 2}])
    assert client.complete_json("s", "u")["n"] == 1
    assert client.complete_json("s", "u")["n"] == 2
    assert client.call_count == 2


def test_the_fake_records_what_it_was_asked():
    client = FakeLLMClient([{"ok": True}])
    client.complete_json("system text", "user text", purpose="a purpose")
    assert client.calls[0] == {
        "system": "system text", "user": "user text", "purpose": "a purpose"
    }


def test_the_fake_parses_a_string_response():
    assert FakeLLMClient(['{"a": 1}']).complete_json("s", "u") == {"a": 1}


def test_the_fake_raises_a_scripted_exception():
    """Lets the generator tests cover an API failure."""
    client = FakeLLMClient([LLMError("the api fell over")])
    with pytest.raises(LLMError, match="fell over"):
        client.complete_json("s", "u")


def test_running_out_of_responses_is_an_error():
    client = FakeLLMClient([])
    with pytest.raises(LLMError, match="ran out of scripted responses"):
        client.complete_json("s", "u", purpose="third call")
