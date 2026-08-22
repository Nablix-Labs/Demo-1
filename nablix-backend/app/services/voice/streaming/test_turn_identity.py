"""Tests for voice-owned turn identity and the barge-in signal.

Both changes here follow the same rule: the decision belongs to whoever can
observe the fact.

The voice server now mints `turn_id` itself at EndOfTurn and sends no lineage,
instead of latching both off the browser. That is the fix for the 409 cascade:
turn boundaries are decided by Flux, which only this server observes, so the
browser was minting ids for boundaries it could not see.

The same rule applied the other way removed our playback barge-in. Only the
browser can see whether audio is actually coming out of the speaker, so it
decides; we just report that the student started speaking.

This file lives beside the module rather than in tests/ on purpose.
`streaming_server` runs as its own standalone app, and importing it directly is
how it actually starts; tests/conftest.py pulls in the entire main backend,
which this module does not depend on and should not need in order to be tested.

Run with:

    python3 -m pytest app/services/voice/streaming/test_turn_identity.py
"""

from __future__ import annotations

import asyncio
import importlib
import re
import sys
from pathlib import Path

import pytest
from starlette.websockets import WebSocketState

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streaming_server  # noqa: E402
from streaming_server import (  # noqa: E402
    MIN_REPORTED_DURATION_SECONDS,
    VOICE_TURN_ID_PREFIX,
    _mint_voice_turn_id,
    _reported_audio_duration,
    _turn_timing,
    evaluate_voice_transcript,
)

ID_PATTERN = re.compile(r"^TURN-VOICE-[0-9a-f]{6}-\d{3}$")


# ──────────────────────────────────────────────────────────────────────
# Minting
# ──────────────────────────────────────────────────────────────────────

def test_id_has_the_expected_shape():
    assert ID_PATTERN.match(_mint_voice_turn_id("a3f9c1", 1))


def test_id_starts_with_the_house_prefix():
    """Backend TurnId is NonEmptyText, but its own tests all use TURN-."""
    assert _mint_voice_turn_id("a3f9c1", 1).startswith(VOICE_TURN_ID_PREFIX)
    assert _mint_voice_turn_id("a3f9c1", 1).startswith("TURN-")


def test_id_is_never_empty():
    """TurnId = NonEmptyText, so an empty string would be rejected."""
    assert _mint_voice_turn_id("", 0).strip()


def test_sequence_is_zero_padded_so_ids_sort_in_turn_order():
    ids = [_mint_voice_turn_id("tok123", n) for n in (1, 2, 10, 100)]
    assert ids == sorted(ids), ids


def test_ids_are_unique_within_a_connection():
    ids = [_mint_voice_turn_id("tok123", n) for n in range(1, 51)]
    assert len(set(ids)) == 50


def test_ids_differ_across_connections_at_the_same_sequence():
    """A restart resets the counter, so the token is what keeps ids unique."""
    assert _mint_voice_turn_id("aaaaaa", 1) != _mint_voice_turn_id("bbbbbb", 1)


def test_sequence_above_999_still_produces_a_usable_id():
    """Padding is a minimum width, not a cap. A long session must not collide."""
    big = _mint_voice_turn_id("tok123", 1000)
    assert big.endswith("-1000")
    assert big != _mint_voice_turn_id("tok123", 100)


def test_the_id_says_it_came_from_voice():
    """So a turn can be told from a typed or canvas one in backend logs."""
    assert "VOICE" in _mint_voice_turn_id("a3f9c1", 1)


# ──────────────────────────────────────────────────────────────────────
# The payload we now send
# ──────────────────────────────────────────────────────────────────────

class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return {"message": "ok"}


class _FakeHttpClient:
    """Captures the payload instead of calling the backend."""

    def __init__(self):
        self.payloads = []

    async def post(self, url, json=None, headers=None, timeout=None):
        del url, headers, timeout
        self.payloads.append(json)
        return _FakeResponse(json)


@pytest.fixture
def captured(monkeypatch):
    client = _FakeHttpClient()
    monkeypatch.setattr(streaming_server, "get_backend_http_client", lambda: client)
    return client


def _evaluate(turn_id, previous_tutor_turn_id, transcript_final=True):
    return asyncio.run(
        evaluate_voice_transcript(
            "SESSION001", "ST001", "x equals five", 0.93, 1.2, "token",
            turn_id, previous_tutor_turn_id, transcript_final, None,
        )
    )


def test_a_null_lineage_is_accepted(captured):
    """The core of the change: we send no previous_tutor_turn_id.

    The backend resolves it from SessionRecord.last_tutor_turn_id, and
    _turn_is_stale treats None as not stale, so this needs no backend change.
    """
    _evaluate("TURN-VOICE-a3f9c1-001", None)
    payload = captured.payloads[0]
    assert payload["previous_tutor_turn_id"] is None
    assert payload["turn_id"] == "TURN-VOICE-a3f9c1-001"
    assert payload["transcript_final"] is True


def test_the_minted_id_survives_into_the_payload(captured):
    minted = _mint_voice_turn_id("a3f9c1", 7)
    _evaluate(minted, None)
    assert captured.payloads[0]["turn_id"] == minted


def test_a_missing_turn_id_is_still_refused(captured):
    """Kept as a backstop against our own minting breaking, not the client's."""
    with pytest.raises(ValueError, match="turn_id is required"):
        _evaluate(None, None)
    assert captured.payloads == [], "must not reach the backend"


def test_a_non_final_transcript_is_still_refused(captured):
    with pytest.raises(ValueError, match="transcript_final"):
        _evaluate("TURN-VOICE-a3f9c1-001", None, transcript_final=False)
    assert captured.payloads == []


# ──────────────────────────────────────────────────────────────────────
# The Nova-3 latch is gated on config, not deleted
# ──────────────────────────────────────────────────────────────────────

def _reload_with_model(monkeypatch, model: str):
    monkeypatch.setenv("VOICE_STT_MODEL", model)
    return importlib.reload(streaming_server)


def test_flux_is_off_by_default():
    """Nova-3 stays the default; Flux is opt-in via the environment."""
    fresh = importlib.reload(streaming_server)
    assert fresh.STT_MODEL == "nova-3"
    assert fresh.USE_FLUX is False


def test_the_flux_switch_is_driven_by_the_environment(monkeypatch):
    """The client latch is guarded by USE_FLUX, so this is what gates it."""
    fresh = _reload_with_model(monkeypatch, "flux")
    assert fresh.USE_FLUX is True
    fresh = _reload_with_model(monkeypatch, "nova-3")
    assert fresh.USE_FLUX is False


def test_the_switch_ignores_case_and_padding(monkeypatch):
    assert _reload_with_model(monkeypatch, "  FLUX  ").USE_FLUX is True


@pytest.fixture(autouse=True)
def _restore_module(monkeypatch):
    """Leave the module as we found it, whatever a reload test did."""
    yield
    monkeypatch.delenv("VOICE_STT_MODEL", raising=False)
    importlib.reload(streaming_server)


# ──────────────────────────────────────────────────────────────────────
# Guard against the old design creeping back
# ──────────────────────────────────────────────────────────────────────

SOURCE = (Path(__file__).resolve().parent / "streaming_server.py").read_text()


def test_the_flux_dispatch_sends_no_lineage():
    """If someone re-adds previous_tutor_turn_id here, the 409s come back.

    Checked against the source because the call sits in a closure inside the
    WebSocket handler and cannot be reached directly.
    """
    assert "turn_id, None, True," in SOURCE


def test_the_client_latch_is_gated():
    """Nova-3 still needs the latch; Flux must never read it."""
    assert 'if "turn_id" in data:' in SOURCE, "the Nova-3 latch has gone entirely"
    assert "if not USE_FLUX:" in SOURCE, "the guard on the latch has gone"

    latch = SOURCE.index('if "turn_id" in data:')
    guard = SOURCE.rfind("if not USE_FLUX:", 0, latch)
    assert guard != -1, "the client latch is no longer behind a USE_FLUX guard"
    assert SOURCE[guard:latch].count("\n") < 3, (
        "a USE_FLUX guard exists but not immediately above the latch"
    )


def test_the_turn_is_minted_before_it_is_run():
    assert "_mint_voice_turn_id(" in SOURCE, "nothing mints a turn id"
    assert "voice_turn_sequence += 1" in SOURCE, (
        "the per-connection counter is never advanced, so ids would repeat"
    )

    mint = SOURCE.index("voice_turn_sequence += 1")
    run = SOURCE.find("_run_turn(\n", mint)
    assert run != -1, "no _run_turn call follows the minting"
    assert mint < run


# ──────────────────────────────────────────────────────────────────────
# Turn timing: separating speaking time from detection time
# ──────────────────────────────────────────────────────────────────────

def test_detection_is_wall_clock_minus_speaking_time():
    """A student who spoke for 4s on a 4.6s turn cost 0.6s of detection."""
    spoken, detection = _turn_timing(10.0, 14.0, 4.6)
    assert spoken == pytest.approx(4.0)
    assert detection == pytest.approx(0.6)


def test_a_long_utterance_is_not_mistaken_for_slow_detection():
    """The whole point. Wall clock alone cannot tell these two apart."""
    talkative = _turn_timing(0.0, 8.0, 8.5)
    hesitant = _turn_timing(0.0, 1.0, 8.5)

    assert talkative[1] == pytest.approx(0.5)
    assert hesitant[1] == pytest.approx(7.5)
    assert talkative[1] < hesitant[1], (
        "the talkative student must not look like slow detection"
    )


def test_a_window_starting_mid_stream_is_handled():
    """audio_window_start is a position in the stream, not zero per turn."""
    spoken, detection = _turn_timing(123.4, 125.4, 2.3)
    assert spoken == pytest.approx(2.0)
    assert detection == pytest.approx(0.3)


def test_integer_windows_are_accepted():
    assert _turn_timing(1, 3, 2.5) == (pytest.approx(2.0), pytest.approx(0.5))


@pytest.mark.parametrize("start,end", [
    (None, 4.0),
    (4.0, None),
    (None, None),
    ("0.0", 4.0),
    (4.0, "8.0"),
])
def test_a_missing_or_unusable_window_reports_unknown(start, end):
    """None, not zero. Zero would read as 'detection is free'."""
    assert _turn_timing(start, end, 5.0) == (None, None)


def test_booleans_are_not_treated_as_numbers():
    """bool is an int in Python, so True would otherwise arrive as 1.0."""
    assert _turn_timing(True, 4.0, 5.0) == (None, None)
    assert _turn_timing(0.0, True, 5.0) == (None, None)


def test_a_window_that_goes_backwards_is_refused():
    """Windows should advance; if they stop, the arithmetic is meaningless."""
    assert _turn_timing(10.0, 4.0, 5.0) == (None, None)


def test_a_zero_length_window_is_still_a_real_answer():
    """An empty turn is not the same as a missing measurement."""
    spoken, detection = _turn_timing(5.0, 5.0, 0.8)
    assert spoken == 0.0
    assert detection == pytest.approx(0.8)


def test_detection_can_be_negative_and_is_not_hidden():
    """If it goes negative our clock assumption is wrong, and we want to see it."""
    _, detection = _turn_timing(0.0, 10.0, 4.0)
    assert detection == pytest.approx(-6.0)


def test_both_window_fields_are_read_from_flux():
    assert 'data.get("audio_window_start")' in SOURCE
    assert 'data.get("audio_window_end")' in SOURCE


# ──────────────────────────────────────────────────────────────────────
# What we report to the backend as audio duration
# ──────────────────────────────────────────────────────────────────────

def test_speaking_time_is_reported_not_wall_clock():
    """Detection lag and teardown are not speech."""
    assert _reported_audio_duration(4.0, 6.5) == pytest.approx(4.0)


def test_it_falls_back_to_the_wall_clock_when_flux_gave_no_window():
    """The field is required, so an approximate value beats a failed turn."""
    assert _reported_audio_duration(None, 6.5) == pytest.approx(6.5)


def test_zero_is_floored_because_the_backend_rejects_it():
    """validate_audio_duration_seconds refuses <= 0, failing the whole turn."""
    assert _reported_audio_duration(0.0, 5.0) == MIN_REPORTED_DURATION_SECONDS
    assert _reported_audio_duration(0.0, 5.0) > 0


def test_the_floor_also_applies_to_the_fallback():
    assert _reported_audio_duration(None, 0.0) == MIN_REPORTED_DURATION_SECONDS


def test_a_negative_value_can_never_be_sent():
    """Whatever goes wrong upstream, the request must stay valid."""
    assert _reported_audio_duration(-3.0, 5.0) > 0
    assert _reported_audio_duration(None, -3.0) > 0


def test_a_short_utterance_is_preserved_not_floored():
    """The floor is a backstop, not a rounding rule."""
    assert _reported_audio_duration(0.4, 2.0) == pytest.approx(0.4)


def _end_of_turn_block() -> str:
    """The Flux EndOfTurn handler, up to the next event branch."""
    start = SOURCE.index('elif event == "EndOfTurn":')
    end = SOURCE.index('elif event in ("EagerEndOfTurn"', start)
    return SOURCE[start:end]


def test_duration_is_taken_before_the_supersede_cancel():
    """The old reading ran the clock through _cancel_active_turn too."""
    block = _end_of_turn_block()
    dur = block.index("duration = _reported_audio_duration(")
    cancel = block.index('_cancel_active_turn("superseded"')
    assert dur < cancel, "duration is still measured after the cancel"


def test_the_flux_dispatch_no_longer_reads_the_wall_clock_for_duration():
    """Scoped to the Flux path.

    Nova-3 still computes its duration from the wall clock and is left alone,
    so asserting against the whole file would fail for the wrong reason.
    """
    assert "duration = max(time.time() - audio_started_at" not in _end_of_turn_block()


def test_the_nova3_path_still_has_its_own_duration():
    """Guards the change from spreading into the legacy path."""
    assert "duration = max(time.time() - audio_started_at" in SOURCE


# ──────────────────────────────────────────────────────────────────────
# The barge-in signal
# ──────────────────────────────────────────────────────────────────────

def _start_of_turn_block() -> str:
    """The StartOfTurn handler, up to the next event branch."""
    start = SOURCE.index('if event == "StartOfTurn":')
    end = SOURCE.index('elif event == "Update":', start)
    return SOURCE[start:end]


def test_student_speaking_is_emitted_on_start_of_turn():
    assert '"type": "student_speaking",' in _start_of_turn_block()


def test_student_speaking_is_sent_before_any_barge_in_branching():
    """Its only value is latency, so it must not wait on a decision."""
    block = _start_of_turn_block()
    signal = block.index('"type": "student_speaking",')
    branch = block.index("if turn_state == TurnState.SPEAKING:")
    assert signal < branch, "the signal is sent after the barge-in branching"


def test_student_speaking_is_not_filtered_server_side():
    """It must fire on EVERY StartOfTurn.

    Filtering here is what made the old playback flag report an interruption
    on every ordinary turn: this process cannot see whether audio is playing,
    so any condition it applies is guesswork. The frontend filters instead.
    """
    block = _start_of_turn_block()
    before = block[: block.index('"type": "student_speaking",')]
    send = before.rindex("await _send_json_if_connected(")
    guarded = [
        line.strip()
        for line in before[send:].splitlines()
        if line.strip().startswith(("if ", "elif "))
    ]
    assert not guarded, f"the signal is conditional on {guarded}"


def test_the_server_side_playback_flag_is_gone():
    """It could never be cleared, so it fired on every normal turn."""
    assignments = [
        line.strip()
        for line in SOURCE.splitlines()
        if "client_audio_playing" in line and not line.strip().startswith("#")
    ]
    assert not assignments, f"the flag is back: {assignments}"


def test_the_spurious_playback_barge_in_log_is_gone():
    """Those log lines were meaningless and actively misled debugging."""
    assert "Barge-in during playback" not in SOURCE


def test_the_two_real_barge_in_branches_are_kept():
    """Removing the wrong branch must not take the working ones with it."""
    block = _start_of_turn_block()
    assert "if turn_state == TurnState.SPEAKING:" in block
    assert "elif turn_state == TurnState.PROCESSING:" in block
    assert "_suppress_active_turn" in block
