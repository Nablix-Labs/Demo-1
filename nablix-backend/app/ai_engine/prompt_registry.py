from __future__ import annotations

import json
import hashlib
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai_engine.schemas import LearningPhase
else:
    LearningPhase = str


PHASE_PROMPT_FILES: dict[str, str] = {
    "DIAGNOSTIC": "diagnostic.txt",
    "CONCEPT_ORIENTATION": "concept_orientation.txt",
    "GUIDED_PRACTICE": "guided_practice.txt",
    "INDEPENDENT_PRACTICE": "independent_practice.txt",
    "REVIEW": "review.txt",
}

PROTOCOL_PROMPT_FILES: dict[str, str] = {
    "DISTRESS": "distress.txt",
    "LONG_PRESSURE": "long_pressure.txt",
    "HANDWRITING_AMBIGUITY": "handwriting_ambiguity.txt",
    "VOICE_AMBIGUITY": "voice_ambiguity.txt",
    "PARENT_IN_ROOM": "parent_in_room.txt",
    "CONTAMINATED_KNOWLEDGE": "contaminated_knowledge.txt",
}


class Trigger(str, Enum):
    DISTRESS = "DISTRESS"
    LONG_PRESSURE = "LONG_PRESSURE"
    HANDWRITING_AMBIGUITY = "HANDWRITING_AMBIGUITY"
    VOICE_AMBIGUITY = "VOICE_AMBIGUITY"
    PARENT_IN_ROOM = "PARENT_IN_ROOM"
    CONTAMINATED_KNOWLEDGE = "CONTAMINATED_KNOWLEDGE"


TRIGGER_ORDER: tuple[Trigger, ...] = (
    Trigger.DISTRESS,
    Trigger.LONG_PRESSURE,
    Trigger.HANDWRITING_AMBIGUITY,
    Trigger.VOICE_AMBIGUITY,
    Trigger.PARENT_IN_ROOM,
    Trigger.CONTAMINATED_KNOWLEDGE,
)

PROTOCOL_MODULES: dict[Trigger, str] = {
    Trigger.DISTRESS: "DISTRESS",
    Trigger.LONG_PRESSURE: "LONG_PRESSURE",
    Trigger.HANDWRITING_AMBIGUITY: "HANDWRITING_AMBIGUITY",
    Trigger.VOICE_AMBIGUITY: "VOICE_AMBIGUITY",
    Trigger.PARENT_IN_ROOM: "PARENT_IN_ROOM",
    Trigger.CONTAMINATED_KNOWLEDGE: "CONTAMINATED_KNOWLEDGE",
}


@dataclass(frozen=True)
class PromptManifest:
    prompt_version: str
    layer_1_sha256: str


@dataclass(frozen=True)
class PromptRegistry:
    prompt_version: str
    layer_1_core: str
    phases: Mapping[str, str]
    protocols: Mapping[str, str]
    manifest: PromptManifest


@dataclass(frozen=True)
class OpenAITutorPromptMetadata:
    prompt_version: str
    layer1_hash: str
    semi_static_hash: str
    layer1_character_count: int
    semi_static_character_count: int
    session_context_character_count: int
    canonical_triggers: list[str]


@lru_cache(maxsize=1)
def load_prompt_registry() -> PromptRegistry:
    return load_prompt_registry_from_path(_default_registry_path())


def load_prompt_registry_from_path(registry_path: Path) -> PromptRegistry:
    manifest = _load_manifest(registry_path / "prompt_manifest.json")
    registry = PromptRegistry(
        prompt_version=manifest.prompt_version,
        layer_1_core=_read_prompt_file(registry_path / "layer_1_core.txt"),
        phases=MappingProxyType(_load_named_prompts(registry_path / "phases", PHASE_PROMPT_FILES)),
        protocols=MappingProxyType(
            _load_named_prompts(registry_path / "protocols", PROTOCOL_PROMPT_FILES)
        ),
        manifest=manifest,
    )
    _validate_layer_1_hash(registry.layer_1_core, manifest)
    return registry


def validate_prompt_manifest() -> None:
    validate_prompt_manifest_at(_default_registry_path())


def validate_prompt_manifest_at(registry_path: Path) -> None:
    manifest = _load_manifest(registry_path / "prompt_manifest.json")
    layer_1_core = _read_prompt_file(registry_path / "layer_1_core.txt")
    _validate_layer_1_hash(layer_1_core, manifest)


def _validate_layer_1_hash(layer_1_core: str, manifest: PromptManifest) -> None:
    actual_hash = sha256_text(layer_1_core)
    if actual_hash != manifest.layer_1_sha256:
        raise ValueError(
            "Layer 1 prompt hash mismatch: "
            f"expected={manifest.layer_1_sha256} actual={actual_hash}"
        )


def get_phase_block(phase: LearningPhase) -> str:
    if phase is None:
        raise ValueError("LearningPhase is required")

    if phase not in PHASE_PROMPT_FILES:
        raise ValueError(f"Unknown LearningPhase: {phase}")

    registry = load_prompt_registry()
    try:
        return registry.phases[phase]
    except KeyError as error:
        raise ValueError(f"Prompt artifact missing for LearningPhase: {phase}") from error


def build_protocol_blocks(active_triggers: Collection[Trigger | str]) -> list[str]:
    registry = load_prompt_registry()
    trigger_set = {_coerce_trigger(trigger) for trigger in active_triggers}

    return [
        registry.protocols[PROTOCOL_MODULES[trigger]]
        for trigger in TRIGGER_ORDER
        if trigger in trigger_set
    ]


def build_semi_static_block(phase: LearningPhase, active_triggers: Collection[Trigger | str]) -> str:
    sections = [get_phase_block(phase), *build_protocol_blocks(active_triggers)]
    return "\n\n".join(sections)


def build_openai_tutor_messages(
    phase: LearningPhase,
    active_triggers: Collection[Trigger | str],
    session_context: dict[str, object],
    conversation_history: list[dict[str, str]],
    current_user_input: str,
) -> list[dict[str, str]]:
    registry = load_prompt_registry()
    semi_static_block = build_semi_static_block(phase, active_triggers)
    serialized_context = serialize_session_context(session_context)

    return [
        {"role": "system", "content": registry.layer_1_core},
        {"role": "system", "content": semi_static_block},
        {"role": "system", "content": serialized_context},
        *[_coerce_history_message(message) for message in conversation_history],
        {"role": "user", "content": current_user_input},
    ]


def build_openai_tutor_prompt_metadata(
    phase: LearningPhase,
    active_triggers: Collection[Trigger | str],
    session_context: dict[str, object],
) -> OpenAITutorPromptMetadata:
    registry = load_prompt_registry()
    semi_static_block = build_semi_static_block(phase, active_triggers)
    serialized_context = serialize_session_context(session_context)
    canonical_triggers = [trigger.value for trigger in _canonical_triggers(active_triggers)]

    return OpenAITutorPromptMetadata(
        prompt_version=registry.prompt_version,
        layer1_hash=sha256_text(registry.layer_1_core),
        semi_static_hash=sha256_text(semi_static_block),
        layer1_character_count=len(registry.layer_1_core),
        semi_static_character_count=len(semi_static_block),
        session_context_character_count=len(serialized_context),
        canonical_triggers=canonical_triggers,
    )


def serialize_session_context(context: dict[str, object]) -> str:
    serialized = json.dumps(
        context,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return normalize_prompt_text(f"<SESSION_CONTEXT>\n{serialized}\n</SESSION_CONTEXT>")


def normalize_prompt_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _default_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "prompts" / "ai_tutor"


def _coerce_trigger(trigger: Trigger | str) -> Trigger:
    if isinstance(trigger, Trigger):
        return trigger
    try:
        return Trigger(trigger)
    except ValueError as error:
        raise ValueError(f"Unknown Trigger: {trigger}") from error


def _canonical_triggers(active_triggers: Collection[Trigger | str]) -> list[Trigger]:
    trigger_set = {_coerce_trigger(trigger) for trigger in active_triggers}
    return [trigger for trigger in TRIGGER_ORDER if trigger in trigger_set]


def _coerce_history_message(message: dict[str, str]) -> dict[str, str]:
    role = message.get("role")
    content = message.get("content")
    if role not in {"system", "user", "assistant"}:
        raise ValueError(f"Invalid conversation history role: {role}")
    if not isinstance(content, str):
        raise ValueError("Conversation history message content must be a string")
    return {"role": role, "content": content}


def _load_named_prompts(directory: Path, prompt_files: dict[str, str]) -> dict[str, str]:
    return {
        prompt_name: _read_prompt_file(directory / file_name)
        for prompt_name, file_name in prompt_files.items()
    }


def _load_manifest(manifest_path: Path) -> PromptManifest:
    manifest_data = json.loads(_read_prompt_file(manifest_path))
    if not isinstance(manifest_data, dict):
        raise ValueError("prompt manifest must be a JSON object")

    prompt_version = manifest_data.get("prompt_version")
    layer_1_sha256 = manifest_data.get("layer_1_sha256")
    if not isinstance(prompt_version, str) or prompt_version == "":
        raise ValueError("prompt manifest missing prompt_version")
    if not isinstance(layer_1_sha256, str) or layer_1_sha256 == "":
        raise ValueError("prompt manifest missing layer_1_sha256")

    return PromptManifest(prompt_version=prompt_version, layer_1_sha256=layer_1_sha256)


def _read_prompt_file(path: Path) -> str:
    return normalize_prompt_text(path.read_text(encoding="utf-8"))
