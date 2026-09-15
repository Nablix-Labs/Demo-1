import pytest

from app.models.student_model_session import QuestionOption, QuestionType
from app.services.guided_question_opening import (
    authored_question_opening_actions,
    guided_question_opening,
)


@pytest.mark.parametrize(
    ("question_type", "expected_motivation"),
    [
        (
            "MULTI_PART_SHORT_RESPONSE",
            "Take it one part at a time—you do not have to solve every part at once.",
        ),
        (
            "CHOICE_WITH_EXPLANATION",
            "Choose the option that fits best, then talk me through your thinking.",
        ),
        (
            "SHORT_RESPONSE",
            "Take your time and begin with what you notice.",
        ),
    ],
)
def test_guided_question_opening_uses_generic_motivation_when_no_authored_prompt(
    question_type: QuestionType,
    expected_motivation: str,
) -> None:
    message = guided_question_opening(
        "What changes and what stays fixed?",
        question_type,
        "Here is the next question.",
        None,
    )

    assert message == (
        "Here is the next question. What changes and what stays fixed? "
        f"{expected_motivation}"
    )


def test_guided_question_opening_uses_authored_tutor_prompt() -> None:
    message = guided_question_opening(
        "3 + 5, 9 + 5, 14 + 5. Use n for the changing starting number.",
        "SHORT_RESPONSE",
        "Here is the next question.",
        "Look across the three cases. What is staying the same?",
    )

    assert message == (
        "Here is the next question. 3 + 5, 9 + 5, 14 + 5. "
        "Use n for the changing starting number. "
        "Look across the three cases. What is staying the same?"
    )


def test_authored_highlight_action_targets_only_exact_question_tokens() -> None:
    anchors, actions, rejection = authored_question_opening_actions(
        "Q-T01-001",
        "3 + 5, 9 + 5, 14 + 5. Use n for the changing starting number.",
        "Highlight +5 in 3+5, 9+5, 14+5",
    )

    assert rejection is None
    assert len(anchors) > 0
    highlighted = [
        action.target_object_id
        for action in actions
        if action.type == "HIGHLIGHT"
    ]
    target_text = {
        anchor.text for anchor in anchors if anchor.token_id in highlighted
    }
    assert target_text == {"+", "5"}
    assert len(highlighted) == 6


def test_authored_annotation_uses_the_target_token() -> None:
    anchors, actions, rejection = authored_question_opening_actions(
        "Q-T01-002",
        "In m + 7, identify the changing quantity.",
        "Highlight m and annotate changing",
    )

    assert rejection is None
    m_anchor = next(anchor for anchor in anchors if anchor.text == "m")
    assert [(action.type, action.target_object_id, action.text) for action in actions] == [
        ("HIGHLIGHT", m_anchor.token_id, None),
        ("INSERT_LABEL", m_anchor.token_id, "changes"),
    ]


def test_authored_deferred_action_is_not_shown_before_the_student_response() -> None:
    anchors, actions, rejection = authored_question_opening_actions(
        "Q-T01-007",
        "What is the hidden operation in c d?",
        "Insert/highlight a faint × between c and d after response",
    )

    assert anchors
    assert actions == []
    assert rejection == "unsupported_authored_canvas_action"


def test_guided_question_opening_rejects_missing_question_text() -> None:
    with pytest.raises(ValueError, match="non-empty question text"):
        guided_question_opening("   ", "SHORT_RESPONSE", "Let us begin.", None)


def test_guided_question_opening_does_not_include_internal_question_id() -> None:
    message = guided_question_opening(
        "A counter starts at c and increases by 4.",
        "SHORT_RESPONSE",
        "Here is the next question.",
        None,
    )

    assert message.startswith("Here is the next question. A counter starts")
    assert "Q-T01-006" not in message


def test_the_real_q_t01_004_action_highlights_both_options() -> None:
    """Q-T01-004 on the VM: rejected on every single turn.

    The authored action and the served question are both copied from production
    (`nablix_content.question_guided_start_prompts`, 15 Sep): the action names
    two tokens and the option each lives in, and Student Model serves the stem
    apart from the options -- so "n+4" and "12+4" were nowhere in the text the
    grounding looked at and it answered `authored_canvas_targets_not_in_question`.

    Both options are highlighted, because the action asks for both: it says
    "for comparison", and dropping one half would silently discard the
    comparison the author wrote.
    """

    anchors, actions, rejection = authored_question_opening_actions(
        "Q-T01-004",
        "Which is the general rule:",
        "Highlight n in n+4 and 12 in 12+4 for comparison",
        [
            # Exactly as parse_stem_and_options yields them -- option A keeps
            # the stem's trailing "or", which is why the match is
            # context-inside-option and not the other way round.
            QuestionOption(option_id="A", text="12 + 4 or"),
            QuestionOption(option_id="B", text="n + 4"),
        ],
    )

    assert rejection is None
    assert anchors
    assert [
        (action.type, action.target_kind, action.target_object_id)
        for action in actions
    ] == [
        ("HIGHLIGHT", "QUESTION_OPTION", "Q-T01-004:OPTION:A"),
        ("HIGHLIGHT", "QUESTION_OPTION", "Q-T01-004:OPTION:B"),
    ]


def test_an_option_the_action_never_names_is_left_alone() -> None:
    """One clause, one option. The distractor is not swept in with it."""

    _anchors, actions, rejection = authored_question_opening_actions(
        "Q-T01-004",
        "Which is the general rule:",
        "Highlight n in n+4",
        [
            QuestionOption(option_id="A", text="12 + 4 or"),
            QuestionOption(option_id="B", text="n + 4"),
        ],
    )

    assert rejection is None
    assert [action.target_object_id for action in actions] == ["Q-T01-004:OPTION:B"]


def test_an_action_grounded_in_neither_the_stem_nor_the_options_is_refused() -> None:
    _anchors, actions, rejection = authored_question_opening_actions(
        "Q-T01-004",
        "Which is the general rule:",
        "Highlight z in z+9",
        [QuestionOption(option_id="A", text="12 + 4 or")],
    )

    assert actions == []
    assert rejection == "authored_canvas_targets_not_in_question"
