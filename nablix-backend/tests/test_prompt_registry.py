import json
from pathlib import Path

import pytest

from app.ai_engine.prompt_registry import (
    Trigger,
    build_openai_tutor_messages,
    build_openai_tutor_prompt_metadata,
    build_protocol_blocks,
    build_semi_static_block,
    get_phase_block,
    load_prompt_registry,
    normalize_prompt_text,
    serialize_session_context,
    sha256_text,
    validate_prompt_manifest,
    validate_prompt_manifest_at,
)


VALID_PHASES: tuple[str, ...] = (
    "DIAGNOSTIC",
    "CONCEPT_ORIENTATION",
    "GUIDED_PRACTICE",
    "INDEPENDENT_PRACTICE",
    "REVIEW",
)


# Part 14 Test 1: Layer 1 Immutability
def test_layer_1_is_immutable_across_many_dynamic_requests() -> None:
    registry = load_prompt_registry()
    original_layer_1 = registry.layer_1_core
    original_hash = sha256_text(original_layer_1)

    for index in range(100):
        build_openai_tutor_messages(
            phase="GUIDED_PRACTICE" if index % 2 == 0 else "REVIEW",
            active_triggers=[],
            session_context={
                "student_id": f"ST{index}",
                "session_id": f"SESSION{index}",
                "current_question": f"Solve for x: x + {index} = 9",
                "ocr_output": f"x = {index}",
                "rag_content": f"hint {index}",
            },
            conversation_history=[],
            current_user_input=f"x = {index}",
        )

        assert load_prompt_registry().layer_1_core == original_layer_1
        assert sha256_text(load_prompt_registry().layer_1_core) == original_hash


def test_manifest_validation_passes_with_correct_hash() -> None:
    validate_prompt_manifest()


def test_prompt_registry_is_loaded_once_and_reused() -> None:
    assert load_prompt_registry() is load_prompt_registry()


def test_prompt_registry_mappings_are_immutable() -> None:
    registry = load_prompt_registry()

    with pytest.raises(TypeError):
        registry.phases["GUIDED_PRACTICE"] = "changed"  # type: ignore[index]


# Part 14 Test 3: Approved Prompt Version Update
def test_approved_prompt_version_update_passes_validation(tmp_path: Path) -> None:
    registry = load_prompt_registry()
    new_layer_1 = registry.layer_1_core + "\nApproved update.\n"
    new_hash = sha256_text(new_layer_1)

    registry_path = _write_registry(tmp_path, new_layer_1, new_hash)
    manifest_path = registry_path / "prompt_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "prompt_version": "1.0.1",
                "layer_1_sha256": new_hash,
            }
        ),
        encoding="utf-8",
    )

    validate_prompt_manifest_at(registry_path)


# Part 14 Test 2: Unapproved Layer 1 Change
def test_manifest_validation_fails_when_layer_1_changes_by_one_character(tmp_path: Path) -> None:
    registry = load_prompt_registry()
    registry_path = _write_registry(tmp_path, registry.layer_1_core + "x", registry.manifest.layer_1_sha256)

    with pytest.raises(ValueError, match="Layer 1 prompt hash mismatch"):
        validate_prompt_manifest_at(registry_path)


# Part 14 Test 13: Line Ending Stability
def test_crlf_and_lf_normalize_to_same_hash() -> None:
    lf_text = "Line one\nLine two\n"
    crlf_text = "Line one\r\nLine two\r\n"

    assert sha256_text(normalize_prompt_text(lf_text)) == sha256_text(normalize_prompt_text(crlf_text))


# Part 14 Test 4: Exactly One Phase
@pytest.mark.parametrize("phase", VALID_PHASES)
def test_each_valid_phase_returns_exactly_one_prompt_block(phase: str) -> None:
    registry = load_prompt_registry()

    assert get_phase_block(phase) == registry.phases[phase]


# Part 14 Test 4: Exactly One Phase
def test_missing_phase_fails() -> None:
    with pytest.raises(ValueError, match="LearningPhase is required"):
        get_phase_block(None)  # type: ignore[arg-type]


# Part 14 Test 4: Exactly One Phase
def test_unknown_phase_fails() -> None:
    with pytest.raises(ValueError, match="Unknown LearningPhase"):
        get_phase_block("UNKNOWN_PHASE")  # type: ignore[arg-type]


# Part 14 Test 4: Exactly One Phase
def test_invalid_string_phase_fails() -> None:
    with pytest.raises(ValueError, match="Unknown LearningPhase"):
        get_phase_block("guided_practice")  # type: ignore[arg-type]


# Part 14 Test 5: Trigger Order Determinism
def test_same_triggers_in_different_orders_produce_identical_protocol_blocks() -> None:
    first_order = [
        Trigger.PARENT_IN_ROOM,
        Trigger.DISTRESS,
        Trigger.HANDWRITING_AMBIGUITY,
    ]
    second_order = [
        Trigger.HANDWRITING_AMBIGUITY,
        Trigger.PARENT_IN_ROOM,
        Trigger.DISTRESS,
    ]

    assert build_protocol_blocks(first_order) == build_protocol_blocks(second_order)


# Part 14 Test 6: Trigger Deduplication
def test_duplicate_triggers_appear_once() -> None:
    registry = load_prompt_registry()
    blocks = build_protocol_blocks(
        [
            Trigger.DISTRESS,
            Trigger.DISTRESS,
        ]
    )

    assert blocks == [registry.protocols["DISTRESS"]]


# Part 14 Test 12: Unknown Trigger
def test_unknown_trigger_fails() -> None:
    with pytest.raises(ValueError, match="Unknown Trigger"):
        build_protocol_blocks(["UNKNOWN_TRIGGER"])


# Part 14 Test 7: No Active Trigger
def test_empty_trigger_list_returns_no_protocol_blocks() -> None:
    assert build_protocol_blocks([]) == []


# Part 14 Tests 8 and 10: Stable Phase Session / Trigger Transition
def test_same_phase_and_same_triggers_produce_identical_semi_static_text_and_hash() -> None:
    first = build_semi_static_block(
        "GUIDED_PRACTICE",
        [Trigger.DISTRESS, Trigger.VOICE_AMBIGUITY],
    )
    second = build_semi_static_block(
        "GUIDED_PRACTICE",
        [Trigger.DISTRESS, Trigger.VOICE_AMBIGUITY],
    )

    assert first == second
    assert sha256_text(first) == sha256_text(second)


# Part 14 Test 5: Trigger Order Determinism
def test_trigger_order_does_not_affect_semi_static_text_or_hash() -> None:
    first = build_semi_static_block(
        "GUIDED_PRACTICE",
        [Trigger.VOICE_AMBIGUITY, Trigger.DISTRESS],
    )
    second = build_semi_static_block(
        "GUIDED_PRACTICE",
        [Trigger.DISTRESS, Trigger.VOICE_AMBIGUITY],
    )

    assert first == second
    assert sha256_text(first) == sha256_text(second)


# Part 14 Test 6: Trigger Deduplication
def test_duplicate_triggers_do_not_affect_semi_static_text_or_hash() -> None:
    with_duplicates = build_semi_static_block(
        "GUIDED_PRACTICE",
        [Trigger.DISTRESS, Trigger.DISTRESS],
    )
    without_duplicates = build_semi_static_block("GUIDED_PRACTICE", [Trigger.DISTRESS])

    assert with_duplicates == without_duplicates
    assert sha256_text(with_duplicates) == sha256_text(without_duplicates)


# Part 14 Test 9: Phase Transition
def test_phase_change_changes_semi_static_hash() -> None:
    guided = build_semi_static_block("GUIDED_PRACTICE", [Trigger.DISTRESS])
    review = build_semi_static_block("REVIEW", [Trigger.DISTRESS])

    assert sha256_text(guided) != sha256_text(review)


# Part 14 Test 10: Trigger Transition
def test_trigger_change_changes_semi_static_hash() -> None:
    distress = build_semi_static_block("GUIDED_PRACTICE", [Trigger.DISTRESS])
    voice = build_semi_static_block("GUIDED_PRACTICE", [Trigger.VOICE_AMBIGUITY])

    assert sha256_text(distress) != sha256_text(voice)


# Part 14 Test 7: No Active Trigger
def test_layer_1_is_not_included_in_semi_static_block() -> None:
    registry = load_prompt_registry()
    semi_static = build_semi_static_block("GUIDED_PRACTICE", [])

    assert registry.layer_1_core not in semi_static
    assert semi_static == registry.phases["GUIDED_PRACTICE"]


def test_same_session_context_with_different_key_order_serializes_identically() -> None:
    first = {
        "current_phase": "GUIDED_PRACTICE",
        "attempt_count": 1,
    }
    second = {
        "attempt_count": 1,
        "current_phase": "GUIDED_PRACTICE",
    }

    assert serialize_session_context(first) == serialize_session_context(second)


def test_session_context_output_contains_valid_json_inside_tags() -> None:
    serialized = serialize_session_context(
        {
            "attempt_count": 1,
            "current_phase": "GUIDED_PRACTICE",
        }
    )

    assert serialized.startswith("<SESSION_CONTEXT>\n")
    assert serialized.endswith("\n</SESSION_CONTEXT>")
    json_text = serialized.removeprefix("<SESSION_CONTEXT>\n").removesuffix("\n</SESSION_CONTEXT>")

    assert json.loads(json_text) == {
        "attempt_count": 1,
        "current_phase": "GUIDED_PRACTICE",
    }
    assert json_text == '{"attempt_count":1,"current_phase":"GUIDED_PRACTICE"}'


# Part 14 Tests 8 and 11: Stable Phase Session / Runtime Leakage Protection
def test_dynamic_context_changes_do_not_change_layer_1_hash() -> None:
    registry = load_prompt_registry()
    layer_1_hash = sha256_text(registry.layer_1_core)

    serialize_session_context(
        {
            "attempt_count": 1,
            "current_question": "Solve for x: x + 4 = 9",
            "student_attempt": "x = 13",
        }
    )
    serialize_session_context(
        {
            "attempt_count": 2,
            "current_question": "Solve for x: 2x + 5 = 13",
            "student_attempt": "x = 4",
        }
    )

    assert sha256_text(registry.layer_1_core) == layer_1_hash


# Part 14 Test 8: Stable Phase Session
def test_dynamic_context_changes_do_not_change_semi_static_hash() -> None:
    semi_static = build_semi_static_block("GUIDED_PRACTICE", [Trigger.DISTRESS])
    semi_static_hash = sha256_text(semi_static)

    serialize_session_context(
        {
            "attempt_count": 1,
            "hint_count": 0,
            "ocr_output": "x = 13",
            "voice_confidence": None,
        }
    )
    serialize_session_context(
        {
            "attempt_count": 2,
            "hint_count": 1,
            "rag_content": ["Use inverse operations."],
            "voice_confidence": 0.91,
        }
    )

    assert sha256_text(build_semi_static_block("GUIDED_PRACTICE", [Trigger.DISTRESS])) == semi_static_hash


def test_openai_tutor_message_order_is_correct() -> None:
    messages = build_openai_tutor_messages(
        "GUIDED_PRACTICE",
        [Trigger.DISTRESS],
        {"attempt_count": 1},
        [{"role": "assistant", "content": "Try the inverse operation."}],
        "x = 13",
    )

    assert [message["role"] for message in messages] == [
        "system",
        "system",
        "system",
        "assistant",
        "user",
    ]


def test_openai_tutor_messages_place_layer_1_first() -> None:
    registry = load_prompt_registry()
    messages = build_openai_tutor_messages(
        "GUIDED_PRACTICE",
        [],
        {"attempt_count": 1},
        [],
        "x = 13",
    )

    assert messages[0] == {"role": "system", "content": registry.layer_1_core}


def test_openai_tutor_messages_place_semi_static_block_second() -> None:
    semi_static = build_semi_static_block("GUIDED_PRACTICE", [Trigger.DISTRESS])
    messages = build_openai_tutor_messages(
        "GUIDED_PRACTICE",
        [Trigger.DISTRESS],
        {"attempt_count": 1},
        [],
        "x = 13",
    )

    assert messages[1] == {"role": "system", "content": semi_static}


# Part 14 Test 9: Phase Transition
def test_openai_tutor_messages_place_session_context_after_semi_static_block() -> None:
    context = {"attempt_count": 1, "current_phase": "GUIDED_PRACTICE"}
    messages = build_openai_tutor_messages(
        "GUIDED_PRACTICE",
        [],
        context,
        [],
        "x = 13",
    )

    assert messages[2] == {"role": "system", "content": serialize_session_context(context)}


def test_openai_tutor_messages_place_user_input_last() -> None:
    messages = build_openai_tutor_messages(
        "GUIDED_PRACTICE",
        [],
        {"attempt_count": 1},
        [{"role": "assistant", "content": "Try again."}],
        "x = 13",
    )

    assert messages[-1] == {"role": "user", "content": "x = 13"}


# Part 14 Test 11: Runtime Leakage Protection
def test_user_input_is_not_inside_stable_prefix() -> None:
    messages = build_openai_tutor_messages(
        "GUIDED_PRACTICE",
        [Trigger.DISTRESS],
        {"attempt_count": 1},
        [],
        "x = 13",
    )

    stable_prefix = messages[0]["content"] + messages[1]["content"]

    assert "x = 13" not in stable_prefix


# Part 14 Test 11: Runtime Leakage Protection
def test_session_context_is_not_inside_layer_1_or_semi_static_block() -> None:
    messages = build_openai_tutor_messages(
        "GUIDED_PRACTICE",
        [Trigger.DISTRESS],
        {"attempt_count": 1, "student_attempt": "x = 13"},
        [],
        "x = 13",
    )

    assert "student_attempt" not in messages[0]["content"]
    assert "student_attempt" not in messages[1]["content"]
    assert "student_attempt" in messages[2]["content"]


def test_openai_tutor_prompt_metadata_contains_hashes_counts_and_canonical_triggers() -> None:
    metadata = build_openai_tutor_prompt_metadata(
        "GUIDED_PRACTICE",
        [Trigger.VOICE_AMBIGUITY, Trigger.DISTRESS, Trigger.DISTRESS],
        {"attempt_count": 1},
    )

    assert metadata.prompt_version == load_prompt_registry().prompt_version
    assert metadata.layer1_hash != ""
    assert metadata.semi_static_hash != ""
    assert metadata.layer1_character_count > 0
    assert metadata.semi_static_character_count > 0
    assert metadata.session_context_character_count > 0
    assert metadata.canonical_triggers == ["DISTRESS", "VOICE_AMBIGUITY"]


def _write_registry(tmp_path: Path, layer_1_core: str, layer_1_sha256: str) -> Path:
    registry_path = tmp_path / "ai_tutor"
    registry_path.mkdir()
    (registry_path / "layer_1_core.txt").write_text(layer_1_core, encoding="utf-8")
    (registry_path / "prompt_manifest.json").write_text(
        json.dumps(
            {
                "prompt_version": "1.0.0",
                "layer_1_sha256": layer_1_sha256,
            }
        ),
        encoding="utf-8",
    )
    return registry_path


# Part 14 Test 12: Unknown Trigger
def test_unknown_trigger_rejects_prompt_build() -> None:
    with pytest.raises(ValueError, match="Unknown Trigger"):
        build_protocol_blocks(["UNKNOWN_TRIGGER"])
