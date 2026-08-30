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
    """A choice question with nothing to choose from cannot be answered."""
    payload = _payload()
    payload["questions"][1]["question_type"] = qtype
    with pytest.raises(QuestionError, match="no visible options"):
        _gen(brief, payload, skills)


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
