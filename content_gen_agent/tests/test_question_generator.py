"""CG-011 tests.

The exit condition is "generated questions match spec constraints and
reference quality". Quality is a judgement a person makes on the output;
constraints are what can be checked here.

This is the first module where being wrong is worse than being absent. A
question with a broken premise teaches something false, and CG-013 will
generate an answer key from that same premise, so the error compounds rather
than surfacing. Nothing here can verify that the maths is right -- that needs
a human or a second model -- so these tests cover everything else, and the
prompt puts correctness first and tells the model to write fewer questions
rather than guess.

Everything uses FakeLLMClient. No network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brief_mapper import map_all                    # noqa: E402
from llm_client import FakeLLMClient, LLMError      # noqa: E402
from micro_skill_generator import generate_micro_skills   # noqa: E402
from models import QuestionStatus, QuestionType      # noqa: E402
from question_generator import (                     # noqa: E402
    MAX_QUESTIONS,
    MIN_QUESTIONS,
    SYSTEM_PROMPT,
    QuestionError,
    build_user_prompt,
    generate_questions,
)
from sources import find_topic_documents             # noqa: E402

TOPIC_DOCS = find_topic_documents()
needs_docs = pytest.mark.skipif(not TOPIC_DOCS, reason="topic documents not available")


@pytest.fixture(scope="module")
def brief():
    if not TOPIC_DOCS:
        pytest.skip("topic documents not available")
    return map_all()[0]


@pytest.fixture(scope="module")
def skills(brief):
    payload = {"micro_skills": [
        {"skill_name": f"Skill {i}", "description": f"The student does {i}.",
         "prerequisite_position": (i - 1) if i > 1 else None,
         "prerequisite_micro_skill_id": None,
         "assessment_priority": "HIGH" if i % 2 else "MEDIUM"}
        for i in range(1, 8)
    ]}
    return generate_micro_skills(brief, FakeLLMClient([payload])).rows


def _q(i=1, qtype="SHORT_RESPONSE", difficulty=None, family=None,
       positions=(1, 2), text=None, options=False):
    body = text if text is not None else (
        f"Question number {i} asking the student to write the general rule."
    )
    if options:
        body += " a) n+5 b) 5n c) n-5"
    return {
        "question_text": body,
        "question_type": qtype,
        "difficulty": difficulty or (1 if i % 2 else 2),
        "item_family": family or f"family {i}",
        "micro_skill_positions": list(positions),
    }


def _payload(n=10, **kw):
    return {"questions": [_q(i, **kw) for i in range(1, n + 1)]}


def _gen(brief, payload, skills=None, **kw):
    return generate_questions(
        brief, FakeLLMClient([payload]), micro_skills=skills,
        source_provenance_id="SRC-NABLIX-T01-001", **kw,
    )


def _prompt_text() -> str:
    return " ".join(SYSTEM_PROMPT.split())


# ──────────────────────────────────────────────────────────────────────
# The prompt
# ──────────────────────────────────────────────────────────────────────

def test_correctness_is_the_first_rule():
    """Ordering in the prompt is not cosmetic; the model reads it as priority."""
    text = _prompt_text()
    assert "THE MATHS MUST BE CORRECT" in text
    assert text.index("MATHS MUST BE CORRECT") < text.index("ONE CLEAR TASK")


def test_the_prompt_prefers_fewer_questions_to_wrong_ones():
    assert "Fewer good questions is the better outcome" in _prompt_text()


def test_the_prompt_demands_one_task_per_question():
    assert "ONE CLEAR TASK PER QUESTION" in _prompt_text()


def test_the_prompt_forbids_needing_excluded_scope():
    """A rule question must not quietly require expanding brackets."""
    assert "Nothing may require anything from the excluded scope" in _prompt_text()


def test_the_prompt_asks_for_plausible_wrong_options():
    text = _prompt_text()
    assert "base them on the misconceptions" in text
    assert "not on absurdities" in text


@needs_docs
def test_the_prompt_carries_scope_and_misconceptions(brief):
    prompt = build_user_prompt(brief)
    assert "OUT of scope" in prompt
    assert "Misconceptions to test for" in prompt
    for item in brief.included_scope[:2]:
        assert item in prompt


@needs_docs
def test_micro_skills_are_offered_by_position(brief, skills):
    prompt = build_user_prompt(brief, skills)
    assert "Reference them by position" in prompt
    assert "1. Skill 1" in prompt


# ──────────────────────────────────────────────────────────────────────
# A well-behaved model
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_ids_are_minted_here_not_by_the_model(brief, skills):
    result = _gen(brief, _payload(), skills)
    assert [r.question_id for r in result.rows] == [
        f"Q-T01-{i:03d}" for i in range(1, 11)
    ]


@needs_docs
def test_the_answer_spec_id_is_derived_from_the_question_id(brief, skills):
    """Two counters that must agree are one counter. QUESTION_HAS_ANSWER
    cannot fail through drift if the id is derived rather than counted."""
    for row in _gen(brief, _payload(), skills).rows:
        assert row.answer_spec_id == row.question_id.replace("Q-", "ANS-")


@needs_docs
def test_rows_carry_the_topic_provenance_and_defaults(brief, skills):
    row = _gen(brief, _payload(), skills).rows[0]
    assert row.topic_id == brief.topic_id
    assert row.source_provenance_id == "SRC-NABLIX-T01-001"
    assert row.status is QuestionStatus.APPROVED
    assert row.version == "1.0"


@needs_docs
def test_skill_links_are_resolved_to_real_ids(brief, skills):
    """CG-012 turns these into Question_MicroSkills rows."""
    result = _gen(brief, _payload(), skills)
    first = result.rows[0].question_id
    assert result.skill_links[first] == ["T01.M1", "T01.M2"]


@needs_docs
def test_questions_sharing_a_descriptor_share_a_family(brief, skills):
    """A family is a grouping. Variants of one question belong together."""
    payload = {"questions": [
        _q(1, family="context add"), _q(2, family="context add"),
        *[_q(i) for i in range(3, 11)],
    ]}
    rows = _gen(brief, payload, skills).rows
    assert rows[0].item_family_id == rows[1].item_family_id == "FAM-T01-CONTEXT-ADD"


# ──────────────────────────────────────────────────────────────────────
# Constraints
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_too_few_questions_is_refused(brief, skills):
    with pytest.raises(QuestionError, match="at least"):
        _gen(brief, _payload(n=MIN_QUESTIONS - 1), skills)


@needs_docs
def test_too_many_questions_is_refused(brief, skills):
    with pytest.raises(QuestionError, match="at most"):
        _gen(brief, _payload(n=MAX_QUESTIONS + 1), skills)


@needs_docs
def test_an_empty_response_is_refused(brief, skills):
    with pytest.raises(QuestionError, match="no questions"):
        _gen(brief, {"questions": []}, skills)


@needs_docs
def test_a_fragment_is_not_a_question(brief, skills):
    payload = _payload()
    payload["questions"][3]["question_text"] = "Write it."
    with pytest.raises(QuestionError, match="too short to be a task"):
        _gen(brief, payload, skills)


@needs_docs
def test_a_duplicate_question_is_refused(brief, skills):
    payload = _payload()
    payload["questions"][5]["question_text"] = payload["questions"][0]["question_text"]
    with pytest.raises(QuestionError, match="duplicate question_text"):
        _gen(brief, payload, skills)


@needs_docs
def test_an_unknown_question_type_is_refused(brief, skills):
    payload = _payload()
    payload["questions"][2]["question_type"] = "ESSAY"
    with pytest.raises(QuestionError, match="question_type"):
        _gen(brief, payload, skills)


@needs_docs
@pytest.mark.parametrize("qtype", ["SINGLE_CHOICE", "CHOICE_WITH_EXPLANATION"])
def test_a_choice_question_without_options_is_refused(brief, skills, qtype):
    """A choice question with nothing to choose from cannot be answered.

    This is the failure the first live pipeline run actually hit: the model
    wrote a SINGLE_CHOICE question with no options in the text.
    """
    payload = _payload()
    payload["questions"][1]["question_type"] = qtype
    with pytest.raises(QuestionError, match="fewer than two labelled options"):
        _gen(brief, payload, skills)


@needs_docs
def test_one_labelled_option_is_not_enough(brief, skills):
    """Detection uses the same regex the answer generator reads options with,
    so the two cannot disagree about what counts as an option."""
    payload = _payload()
    payload["questions"][1] = _q(2, "SINGLE_CHOICE",
                                 text="Which is right? a) n+5 and nothing else")
    with pytest.raises(QuestionError, match="fewer than two labelled options"):
        _gen(brief, payload, skills)


# ──────────────────────────────────────────────────────────────────────
# Dropping individual bad questions
#
# The first live run failed on one malformed question out of thirteen and
# lost the whole topic. On a six-topic run that decides whether anything
# reaches the workbook at all.
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_by_default_one_bad_question_still_fails_the_batch(brief, skills):
    """Dropping is opt-in; the strict path is unchanged."""
    payload = _payload(n=13)
    payload["questions"][4]["question_type"] = "SINGLE_CHOICE"
    with pytest.raises(QuestionError):
        _gen(brief, payload, skills)


@needs_docs
def test_drop_invalid_keeps_the_good_questions(brief, skills):
    payload = _payload(n=13)
    payload["questions"][4]["question_type"] = "SINGLE_CHOICE"
    result = _gen(brief, payload, skills, drop_invalid=True)
    assert len(result.rows) == 12
    assert result.is_clean


@needs_docs
def test_dropping_is_reported_not_hidden(brief, skills):
    payload = _payload(n=13)
    payload["questions"][4]["question_type"] = "SINGLE_CHOICE"
    result = _gen(brief, payload, skills, drop_invalid=True)
    assert any("dropped 1 unusable question" in i.message for i in result.issues)


@needs_docs
def test_ids_stay_contiguous_after_a_drop(brief, skills):
    """Ids are minted after dropping, so there is no gap to explain."""
    payload = _payload(n=13)
    payload["questions"][4]["question_type"] = "SINGLE_CHOICE"
    rows = _gen(brief, payload, skills, drop_invalid=True).rows
    assert [r.question_id for r in rows] == [f"Q-T01-{i:03d}" for i in range(1, 13)]


@needs_docs
def test_dropping_cannot_rescue_a_batch_below_the_minimum(brief, skills):
    """Removing questions does not fix having too few."""
    payload = _payload(n=9)
    for i in range(2, 9):
        payload["questions"][i]["question_type"] = "SINGLE_CHOICE"
    with pytest.raises(QuestionError):
        _gen(brief, payload, skills, drop_invalid=True)


@needs_docs
def test_dropping_does_not_rescue_a_batch_level_error(brief, skills):
    """A count problem has no position, so nothing is droppable."""
    with pytest.raises(QuestionError, match="at least"):
        _gen(brief, _payload(n=MIN_QUESTIONS - 1), skills, drop_invalid=True)


@needs_docs
def test_a_choice_question_with_options_is_accepted(brief, skills):
    payload = _payload()
    payload["questions"][1] = _q(2, "SINGLE_CHOICE", options=True)
    assert _gen(brief, payload, skills).is_clean


@needs_docs
@pytest.mark.parametrize("bad", [0, 3, "hard", None])
def test_an_invalid_difficulty_is_refused(brief, skills, bad):
    payload = _payload()
    payload["questions"][0]["difficulty"] = bad
    with pytest.raises(QuestionError, match="difficulty"):
        _gen(brief, payload, skills)


@needs_docs
def test_a_missing_item_family_is_refused(brief, skills):
    payload = _payload()
    payload["questions"][4]["item_family"] = "   "
    with pytest.raises(QuestionError, match="item_family"):
        _gen(brief, payload, skills)


# ──────────────────────────────────────────────────────────────────────
# Skill links: what makes a question markable
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_a_question_exercising_no_skill_is_refused(brief, skills):
    payload = _payload()
    payload["questions"][2]["micro_skill_positions"] = []
    with pytest.raises(QuestionError, match="cannot be marked against one"):
        _gen(brief, payload, skills)


@needs_docs
def test_a_skill_position_outside_the_list_is_refused(brief, skills):
    payload = _payload()
    payload["questions"][0]["micro_skill_positions"] = [99]
    with pytest.raises(QuestionError, match="outside the"):
        _gen(brief, payload, skills)


@needs_docs
def test_a_non_numeric_skill_position_is_refused(brief, skills):
    payload = _payload()
    payload["questions"][0]["micro_skill_positions"] = ["first"]
    with pytest.raises(QuestionError, match="not a number"):
        _gen(brief, payload, skills)


# ──────────────────────────────────────────────────────────────────────
# Warnings: suspicious, not fatal
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_uniform_difficulty_warns_but_proceeds(brief, skills):
    result = _gen(brief, _payload(difficulty=1), skills)
    assert result.is_clean
    assert any("every question is difficulty" in i.message for i in result.issues)


@needs_docs
def test_a_single_question_type_warns_but_proceeds(brief, skills):
    result = _gen(brief, _payload(), skills)
    assert result.is_clean
    assert any("every question is" in i.message and "question_type" in i.field
               for i in result.issues)


# ──────────────────────────────────────────────────────────────────────
# Failure handling
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_non_strict_reports_problems_and_produces_no_rows(brief, skills):
    payload = _payload()
    payload["questions"][0]["difficulty"] = 9
    result = _gen(brief, payload, skills, strict=False)
    assert not result.is_clean
    assert result.rows == []
    assert result.skill_links == {}


@needs_docs
def test_every_problem_is_reported_in_one_pass(brief, skills):
    payload = _payload()
    payload["questions"][0]["difficulty"] = 9
    payload["questions"][1]["question_type"] = "ESSAY"
    payload["questions"][2]["micro_skill_positions"] = []
    result = _gen(brief, payload, skills, strict=False)
    assert len(result.errors) >= 3


@needs_docs
def test_an_api_failure_propagates(brief, skills):
    client = FakeLLMClient([LLMError("the api fell over")])
    with pytest.raises(LLMError, match="fell over"):
        generate_questions(brief, client, micro_skills=skills)


# ──────────────────────────────────────────────────────────────────────
# Select-all questions mistyped as SINGLE_CHOICE
#
# The six-topic run produced three of these. The answer generator did the
# right thing and returned "AB" and "ABCD"; the answer key was then refused
# for not being a single letter, which pointed the blame at the wrong module.
# There is no multi-select type in the schema, so the question is the bug.
# ──────────────────────────────────────────────────────────────────────

MULTI_SELECT_TEXT = (
    "In the term 6xy, which of these are factors of the term?\n"
    "a) 6\nb) x\nc) y\nd) 6xy\nWrite the letters of all correct options."
)


def test_the_prompt_says_exactly_one_option_is_correct():
    text = " ".join(SYSTEM_PROMPT.split())
    assert "SINGLE_CHOICE means EXACTLY ONE option is correct" in text
    assert "no select-all-that-apply type" in text


@pytest.mark.parametrize("text", [
    MULTI_SELECT_TEXT,
    "Which of these are terms? a) 4x b) 9 c) + Write the letters of all correct options.",
    "Pick the factors. a) 3 b) x c) 9. Tick all that apply.",
    "a) 3 b) x c) 9. Select all the correct answers.",
])
def test_a_select_all_question_typed_single_choice_is_refused(brief, skills, text):
    payload = _payload()
    payload["questions"][2]["question_type"] = "SINGLE_CHOICE"
    payload["questions"][2]["question_text"] = text
    result = _gen(brief, payload, skills=skills, strict=False)
    assert any("more than one option" in i.message for i in result.errors)


@pytest.mark.parametrize("text", [
    "Which rule describes the pattern? a) Add 2 each time b) Add 3 each time c) Add 5",
    "What does n stand for? a) One particular answer b) A number that can change",
    "Which expression represents the length? a) n + 4 b) n - 4 c) 4n",
    "Write the letter of the correct option. a) 3 b) x",
])
def test_an_ordinary_single_choice_question_is_not_caught(brief, skills, text):
    """A check that fires on good questions costs more than it saves."""
    payload = _payload()
    payload["questions"][2]["question_type"] = "SINGLE_CHOICE"
    payload["questions"][2]["question_text"] = text
    result = _gen(brief, payload, skills=skills, strict=False)
    assert not [i for i in result.errors if "more than one option" in i.message]


def test_a_select_all_question_is_dropped_rather_than_losing_the_topic(brief, skills):
    payload = _payload()
    payload["questions"][2]["question_type"] = "SINGLE_CHOICE"
    payload["questions"][2]["question_text"] = MULTI_SELECT_TEXT
    result = _gen(brief, payload, skills=skills, strict=True, drop_invalid=True)
    assert result.is_clean
    assert len(result.rows) == len(payload["questions"]) - 1
