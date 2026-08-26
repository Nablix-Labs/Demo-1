"""Anchoring the active teaching step into the question the learner is reading."""

from app.models.student_model_session import AnswerSpec
from app.services.question_anchors import plan_question_anchors, question_text_tokens

_QUESTION_ID = "Q-T01-003"
_NAMES_THE_VARIABLE = "Ravi scores n points and then scores 4 more. Write the new-score rule."
_SHOWS_EXAMPLES_ONLY = "Priya scored 12 points, then 20 points. Each time she scores 4 more."


def _answer_spec(canonical: str = "n + 4") -> AnswerSpec:
    return AnswerSpec(
        answer_spec_id="ANS-T01-003",
        canonical_answer=canonical,
        accepted_answers=[],
        verification_method="SYMBOLIC_EQUIVALENCE",
    )


def test_question_tokens_are_stable_and_addressable() -> None:
    tokens = question_text_tokens(_QUESTION_ID, _NAMES_THE_VARIABLE)

    assert tokens[0].token_id == f"{_QUESTION_ID}:QTOKEN:1"
    assert [token.token_id for token in tokens] == [
        f"{_QUESTION_ID}:QTOKEN:{index}" for index in range(1, len(tokens) + 1)
    ]


def test_every_span_selects_its_own_token_text() -> None:
    """The frontend resolves these spans against the same string, so they must cut exactly."""

    for token in question_text_tokens(_QUESTION_ID, _NAMES_THE_VARIABLE):
        assert _NAMES_THE_VARIABLE[token.char_start : token.char_end] == token.text


def test_changing_step_anchors_the_named_variable() -> None:
    anchors = plan_question_anchors(
        _QUESTION_ID, _NAMES_THE_VARIABLE, _answer_spec(), "CHANGING_VALUE"
    )

    assert [(anchor.text, anchor.label) for anchor in anchors] == [("n", "changes")]
    anchor = anchors[0]
    assert _NAMES_THE_VARIABLE[anchor.char_start : anchor.char_end] == "n"


def test_changing_step_falls_back_to_the_example_starting_values() -> None:
    """A question that never names the variable still shows what varies."""

    anchors = plan_question_anchors(
        _QUESTION_ID, _SHOWS_EXAMPLES_ONLY, _answer_spec(), "CHANGING_VALUE"
    )

    assert [anchor.text for anchor in anchors] == ["12", "20"]
    assert {anchor.label for anchor in anchors} == {"changes"}


def test_fixed_step_anchors_the_value_that_stays() -> None:
    anchors = plan_question_anchors(
        _QUESTION_ID, _NAMES_THE_VARIABLE, _answer_spec(), "FIXED_VALUE"
    )

    assert [(anchor.text, anchor.label) for anchor in anchors] == [("4", "stays fixed")]


def test_a_leading_article_is_not_read_as_the_variable() -> None:
    question = "A number a increases by 4."

    anchors = plan_question_anchors(
        _QUESTION_ID, question, _answer_spec("a + 4"), "CHANGING_VALUE"
    )

    assert [anchor.char_start for anchor in anchors] == [question.index(" a ") + 1]


def test_no_anchors_without_an_active_step_or_answer_contract() -> None:
    assert plan_question_anchors(_QUESTION_ID, _NAMES_THE_VARIABLE, _answer_spec(), None) == []
    assert plan_question_anchors(_QUESTION_ID, _NAMES_THE_VARIABLE, None, "CHANGING_VALUE") == []
    assert plan_question_anchors(None, _NAMES_THE_VARIABLE, _answer_spec(), "CHANGING_VALUE") == []
    assert plan_question_anchors(_QUESTION_ID, "", _answer_spec(), "CHANGING_VALUE") == []


def test_general_rule_step_anchors_nothing() -> None:
    """Nothing in the question is the answer, so nothing is pointed at."""

    assert plan_question_anchors(
        _QUESTION_ID, _NAMES_THE_VARIABLE, _answer_spec(), "GENERAL_RULE"
    ) == []


def test_guided_turn_returns_anchors_for_the_active_step(monkeypatch) -> None:
    """The response carries the spans alongside the question string they index."""

    from app.models.guided_learning import GuidedTeachingState
    from app.services import interaction_service, session_service

    question = _NAMES_THE_VARIABLE
    session = session_service.SessionRecord.model_construct(
        current_phase="GUIDED_PRACTICE",
        question_id=_QUESTION_ID,
        current_question=question,
        guided_teaching_state=GuidedTeachingState(
            question_id=_QUESTION_ID,
            objective_component_ids=[],
            confirmed_component_ids=[],
            missing_component_ids=[],
            active_component_id=None,
            last_tutor_question_type="COMPONENT",
            selected_option_id=None,
            awaiting_response=True,
            active_step_id="CHANGING_VALUE",
        ),
    )
    monkeypatch.setattr(
        interaction_service, "_active_answer_spec", lambda _session: _answer_spec()
    )

    anchors = interaction_service._question_anchors(session)

    assert [(anchor.text, anchor.label) for anchor in anchors] == [("n", "changes")]
    assert question[anchors[0].char_start : anchors[0].char_end] == "n"
