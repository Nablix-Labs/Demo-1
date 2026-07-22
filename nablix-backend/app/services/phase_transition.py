"""Phase transition rules for Chirudeva Submodule 6.7.

Chirudeva executes Tamil's recommended phase transition; it never decides
learning progression. Every map below is the hardcoded contract from the
6.7 spec — messages and flags must not be generated dynamically.
"""

from typing import cast, get_args

from app.core.logger import logger
from app.models.fields import Phase


VALID_TRANSITIONS: dict[Phase, tuple[Phase, ...]] = {
    "DIAGNOSTIC": ("CONCEPT_ORIENTATION", "GUIDED_PRACTICE"),
    "CONCEPT_ORIENTATION": ("GUIDED_PRACTICE", "DIAGNOSTIC", "REVIEW"),
    "GUIDED_PRACTICE": ("INDEPENDENT_PRACTICE", "DIAGNOSTIC", "REVIEW"),
    "INDEPENDENT_PRACTICE": ("GUIDED_PRACTICE", "REVIEW"),
    "REVIEW": ("GUIDED_PRACTICE", "CONCEPT_ORIENTATION"),
}

DEFAULT_TRANSITION_MESSAGE = "Let us move on to the next step."

# Keyed by (previous_phase, new_phase). Message and voice are identical for
# every pair in the spec, so each string is stored once.
TRANSITION_MESSAGES: dict[tuple[Phase, Phase], str] = {
    ("DIAGNOSTIC", "CONCEPT_ORIENTATION"): (
        "Let us spend a few minutes on the idea behind this before we practise."
    ),
    ("DIAGNOSTIC", "GUIDED_PRACTICE"): (
        "You are solid on the basics. Let us go straight into some practice problems."
    ),
    ("CONCEPT_ORIENTATION", "GUIDED_PRACTICE"): (
        "That is exactly the idea. Let us try one together."
    ),
    ("CONCEPT_ORIENTATION", "DIAGNOSTIC"): (
        "Let us step back for a moment. I want to make sure one earlier piece "
        "is solid before we continue."
    ),
    ("GUIDED_PRACTICE", "INDEPENDENT_PRACTICE"): (
        "You are ready to try this on your own. I will step back and let you "
        "work through it."
    ),
    ("GUIDED_PRACTICE", "REVIEW"): (
        "Looks like you have finished. Let us take a quick look at what you did."
    ),
    ("INDEPENDENT_PRACTICE", "GUIDED_PRACTICE"): (
        "Let us work through this part together."
    ),
    ("INDEPENDENT_PRACTICE", "REVIEW"): (
        "Looks like you have finished. Let us take a quick look at what you did."
    ),
    ("REVIEW", "GUIDED_PRACTICE"): (
        "Let us go back and practise this a bit more together."
    ),
    ("REVIEW", "CONCEPT_ORIENTATION"): (
        "Let us go back to the idea behind this and build it up again."
    ),
}

# show_visual_cue and show_scaffold_panel are always False here: they are
# per-turn tutor outputs overlaid after this map is applied.
UI_STATE_FLAGS: dict[Phase, dict[str, bool]] = {
    "DIAGNOSTIC": {
        "show_canvas": True,
        "show_hint_button": False,
        "show_visual_cue": False,
        "show_scaffold_panel": False,
        "allow_text_input": True,
        "allow_voice_input": True,
    },
    "CONCEPT_ORIENTATION": {
        "show_canvas": True,
        "show_hint_button": False,
        "show_visual_cue": False,
        "show_scaffold_panel": False,
        "allow_text_input": False,  # muted during video
        "allow_voice_input": False,  # muted during video
    },
    "GUIDED_PRACTICE": {
        "show_canvas": True,
        "show_hint_button": True,
        "show_visual_cue": False,
        "show_scaffold_panel": False,
        "allow_text_input": True,
        "allow_voice_input": True,
    },
    "INDEPENDENT_PRACTICE": {
        "show_canvas": True,
        "show_hint_button": True,
        "show_visual_cue": False,
        "show_scaffold_panel": False,
        "allow_text_input": True,
        "allow_voice_input": True,
    },
    "REVIEW": {
        "show_canvas": False,
        "show_hint_button": False,
        "show_visual_cue": False,
        "show_scaffold_panel": False,
        "allow_text_input": True,
        "allow_voice_input": True,
    },
}

# Session counters reset on entry into each phase.
PHASE_COUNTER_RESETS: dict[Phase, dict[str, int | bool]] = {
    "INDEPENDENT_PRACTICE": {"hint_count": 0, "rescue_mode_active": False},
    "GUIDED_PRACTICE": {"attempt_count": 0, "scaffold_step_number": 0},
    "REVIEW": {"mastery_check_question_count": 0},
}

_PHASE_VALUES: tuple[str, ...] = get_args(Phase)


def resolve_transition(current_phase: Phase, recommended: str | None) -> Phase | None:
    """Return the validated new phase, or None to stay in the current one.

    Null/equal recommendations and invalid or unrecognised transitions all
    resolve to None; invalid ones are logged, never silently executed.
    """

    if not recommended:
        logger.warning("Tamil returned null recommended_entry_phase")
        return None
    if recommended == current_phase:
        return None
    if recommended not in _PHASE_VALUES:
        logger.error(f"Unrecognised phase from Tamil: {recommended}")
        return None
    if recommended not in VALID_TRANSITIONS[current_phase]:
        logger.warning(f"Invalid transition attempted: {current_phase} -> {recommended}")
        return None
    return cast(Phase, recommended)
