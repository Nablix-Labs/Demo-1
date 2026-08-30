"""CG-010 tests.

The exit condition is "generated micro-skills cover same scope as reference".
Coverage is a judgement a person makes; what can be tested is everything that
would make the table structurally wrong before anyone gets to judge it.

Reading the 22 approved rows first is what shaped these. Three properties of
the reference drive most of the tests below:

  * 19 of 22 rows carry a prerequisite, so skills form a graph, not a list
  * the graph crosses topics: T02.M1 depends on T01.M6
  * priority is 16 HIGH to 6 MEDIUM, not uniform

A generator that produced seven independent, uniformly-HIGH skills would look
entirely plausible and be wrong on all three counts.

Everything here uses FakeLLMClient. No network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brief_mapper import map_all                    # noqa: E402
from llm_client import FakeLLMClient, LLMError      # noqa: E402
from micro_skill_generator import (                 # noqa: E402
    MAX_SKILLS,
    MIN_SKILLS,
    SYSTEM_PROMPT,
    MicroSkillError,
    build_user_prompt,
    generate_all_micro_skills,
    generate_micro_skills,
)
from models import AssessmentPriority, MicroSkillStatus   # noqa: E402
from sources import find_topic_documents            # noqa: E402

TOPIC_DOCS = find_topic_documents()
needs_docs = pytest.mark.skipif(not TOPIC_DOCS, reason="topic documents not available")


@pytest.fixture(scope="module")
def briefs():
    if not TOPIC_DOCS:
        pytest.skip("topic documents not available")
    return map_all()


@pytest.fixture
def brief(briefs):
    return briefs[0]


def _skill(name="Identify the changing quantity", desc="The student identifies it.",
           position=None, external=None, priority="HIGH"):
    return {
        "skill_name": name, "description": desc,
        "prerequisite_position": position,
        "prerequisite_micro_skill_id": external,
        "assessment_priority": priority,
    }


def _payload(n=7, link=True, priority=None):
    skills = []
    for i in range(1, n + 1):
        skills.append(_skill(
            name=f"Do thing {i}",
            desc=f"The student does thing {i}.",
            position=(i - 1) if (link and i > 1) else None,
            priority=priority or ("HIGH" if i % 2 else "MEDIUM"),
        ))
    return {"micro_skills": skills}


def _gen(brief, payload, **kw):
    return generate_micro_skills(brief, FakeLLMClient([payload]), **kw)


# ──────────────────────────────────────────────────────────────────────
# The prompt
# ──────────────────────────────────────────────────────────────────────

def _prompt_text() -> str:
    """The prompt with line wrapping collapsed.

    Asserting on raw substrings breaks whenever a sentence is rewrapped, which
    is a test failing for formatting rather than meaning.
    """
    return " ".join(SYSTEM_PROMPT.split())


def test_the_prompt_demands_observable_skills():
    assert "OBSERVABLE" in SYSTEM_PROMPT
    assert "cannot see whether it happened" in _prompt_text()


def test_the_prompt_forbids_generating_for_excluded_scope():
    assert "Do not invent skills for the excluded scope" in _prompt_text()


def test_the_prompt_says_priorities_are_not_all_high():
    assert "they are not all HIGH" in _prompt_text()


def test_the_prompt_explains_the_dependency_encoding():
    """The model names prerequisites by position; it never sees an id."""
    text = _prompt_text()
    assert "1-based position" in text
    assert "must be smaller than this skill's own position" in text


@needs_docs
def test_the_prompt_carries_scope_and_misconceptions(brief):
    prompt = build_user_prompt(brief)
    assert brief.learning_goal[:30] in prompt
    assert "Explicitly OUT of scope" in prompt
    assert "Misconceptions" in prompt
    for item in brief.included_scope[:2]:
        assert item in prompt


@needs_docs
def test_earlier_topics_skills_are_offered_as_prerequisites(brief, briefs):
    """Without these the model cannot reproduce T02.M1 depending on T01.M6."""
    first = _gen(briefs[0], _payload())
    prompt = build_user_prompt(briefs[1], first.rows)
    assert "already established in earlier topics" in prompt
    assert first.rows[0].micro_skill_id in prompt


@needs_docs
def test_no_prerequisite_section_when_there_are_none(brief):
    assert "already established" not in build_user_prompt(brief)


# ──────────────────────────────────────────────────────────────────────
# A well-behaved model
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_ids_are_minted_here_not_by_the_model(brief):
    """The model never sees an id. Duplicates and gaps are impossible."""
    result = _gen(brief, _payload())
    assert [r.micro_skill_id for r in result.rows] == [f"T01.M{i}" for i in range(1, 8)]
    assert [r.skill_code for r in result.rows] == [f"M{i}" for i in range(1, 8)]


@needs_docs
def test_a_position_becomes_a_real_id(brief):
    result = _gen(brief, _payload())
    assert result.rows[0].prerequisite_micro_skill_id is None
    assert result.rows[1].prerequisite_micro_skill_id == "T01.M1"
    assert result.rows[6].prerequisite_micro_skill_id == "T01.M6"


@needs_docs
def test_rows_carry_the_topic_and_house_defaults(brief):
    row = _gen(brief, _payload()).rows[0]
    assert row.topic_id == brief.topic_id
    assert row.status is MicroSkillStatus.ACTIVE
    assert row.version == "1.0"
    assert row.assessment_priority in tuple(AssessmentPriority)


@needs_docs
def test_a_clean_run_reports_no_errors(brief):
    result = _gen(brief, _payload())
    assert result.is_clean
    assert result.errors == []


# ──────────────────────────────────────────────────────────────────────
# Dependencies: the property most likely to be silently wrong
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_a_forward_dependency_is_refused(brief):
    """Skill 2 cannot depend on skill 5; ids are assigned in order."""
    payload = _payload()
    payload["micro_skills"][1]["prerequisite_position"] = 5
    with pytest.raises(MicroSkillError, match="later skill"):
        _gen(brief, payload)


@needs_docs
def test_a_self_dependency_is_refused(brief):
    payload = _payload()
    payload["micro_skills"][2]["prerequisite_position"] = 3
    with pytest.raises(MicroSkillError, match="itself"):
        _gen(brief, payload)


@needs_docs
def test_a_position_outside_the_list_is_refused(brief):
    payload = _payload()
    payload["micro_skills"][3]["prerequisite_position"] = 99
    with pytest.raises(MicroSkillError, match="outside the list"):
        _gen(brief, payload)


@needs_docs
def test_an_unoffered_external_prerequisite_is_refused(brief):
    """The model must not invent a dependency on a topic we never showed it."""
    payload = _payload()
    payload["micro_skills"][0]["prerequisite_micro_skill_id"] = "T09.M3"
    with pytest.raises(MicroSkillError, match="not offered as available"):
        _gen(brief, payload)


@needs_docs
def test_a_malformed_external_id_is_refused(brief):
    payload = _payload()
    payload["micro_skills"][0]["prerequisite_micro_skill_id"] = "skill three"
    with pytest.raises(MicroSkillError, match="not a valid id"):
        _gen(brief, payload)


@needs_docs
def test_setting_both_kinds_of_prerequisite_is_refused(brief):
    payload = _payload()
    payload["micro_skills"][1]["prerequisite_micro_skill_id"] = "T01.M1"
    with pytest.raises(MicroSkillError, match="use one"):
        _gen(brief, payload)


@needs_docs
def test_a_list_with_no_dependencies_warns_but_proceeds(brief):
    """The reference links 19 of 22, so a flat list is suspicious, not fatal."""
    result = _gen(brief, _payload(link=False))
    assert result.is_clean
    assert any("no skill depends on another" in i.message for i in result.issues)


# ──────────────────────────────────────────────────────────────────────
# Shape and content
# ──────────────────────────────────────────────────────────────────────

@needs_docs
@pytest.mark.parametrize("count", [1, MIN_SKILLS - 1])
def test_too_few_skills_is_refused(brief, count):
    with pytest.raises(MicroSkillError, match="at least"):
        _gen(brief, _payload(n=count, link=False))


@needs_docs
def test_too_many_skills_is_refused(brief):
    with pytest.raises(MicroSkillError, match="at most"):
        _gen(brief, _payload(n=MAX_SKILLS + 1))


@needs_docs
def test_an_empty_response_is_refused(brief):
    with pytest.raises(MicroSkillError, match="no skills"):
        _gen(brief, {"micro_skills": []})


@needs_docs
def test_a_missing_key_is_refused(brief):
    with pytest.raises(MicroSkillError, match="no skills"):
        _gen(brief, {"something_else": []})


@needs_docs
def test_a_duplicate_skill_name_is_refused(brief):
    payload = _payload()
    payload["micro_skills"][3]["skill_name"] = payload["micro_skills"][0]["skill_name"]
    with pytest.raises(MicroSkillError, match="duplicate skill_name"):
        _gen(brief, payload)


@needs_docs
def test_an_empty_description_is_refused(brief):
    payload = _payload()
    payload["micro_skills"][2]["description"] = "   "
    with pytest.raises(MicroSkillError, match="description"):
        _gen(brief, payload)


@needs_docs
def test_an_invalid_priority_is_refused(brief):
    payload = _payload()
    payload["micro_skills"][1]["assessment_priority"] = "URGENT"
    with pytest.raises(MicroSkillError, match="not HIGH or MEDIUM"):
        _gen(brief, payload)


@needs_docs
def test_uniform_priority_warns_but_proceeds(brief):
    """16 HIGH to 6 MEDIUM in the reference. All-HIGH loses the distinction."""
    result = _gen(brief, _payload(priority="HIGH"))
    assert result.is_clean
    assert any("every skill is" in i.message for i in result.issues)


# ──────────────────────────────────────────────────────────────────────
# Non-strict mode and failures
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_non_strict_returns_the_problems_instead_of_raising(brief):
    payload = _payload()
    payload["micro_skills"][1]["assessment_priority"] = "URGENT"
    result = _gen(brief, payload, strict=False)
    assert not result.is_clean
    assert result.rows == [], "a rejected set must not produce rows"


@needs_docs
def test_every_problem_is_reported_in_one_pass(brief):
    payload = _payload()
    payload["micro_skills"][0]["assessment_priority"] = "URGENT"
    payload["micro_skills"][1]["description"] = ""
    payload["micro_skills"][2]["prerequisite_position"] = 99
    result = _gen(brief, payload, strict=False)
    assert len(result.errors) >= 3


@needs_docs
def test_an_api_failure_propagates(brief):
    client = FakeLLMClient([LLMError("the api fell over")])
    with pytest.raises(LLMError, match="fell over"):
        generate_micro_skills(brief, client)


# ──────────────────────────────────────────────────────────────────────
# Across topics
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_each_topic_can_depend_on_the_ones_before_it(briefs):
    """T02.M1 depends on T01.M6 in the reference. Order is not incidental."""
    payloads = [_payload() for _ in briefs[:2]]
    payloads[1]["micro_skills"][0]["prerequisite_micro_skill_id"] = "T01.M6"
    payloads[1]["micro_skills"][0]["prerequisite_position"] = None

    results = generate_all_micro_skills(
        briefs[:2], FakeLLMClient(payloads),
    )
    assert results[1].rows[0].prerequisite_micro_skill_id == "T01.M6"


@needs_docs
def test_ids_do_not_collide_across_topics(briefs):
    results = generate_all_micro_skills(
        briefs[:3], FakeLLMClient([_payload() for _ in briefs[:3]]),
    )
    all_ids = [r.micro_skill_id for s in results for r in s.rows]
    assert len(all_ids) == len(set(all_ids))
    assert all_ids[0].startswith("T01.")
    assert any(i.startswith("T02.") for i in all_ids)


@needs_docs
def test_a_topic_cannot_depend_on_a_later_topic(briefs):
    """T01 is generated first, so T02's skills are not available to it."""
    payload = _payload()
    payload["micro_skills"][0]["prerequisite_micro_skill_id"] = "T02.M1"
    payload["micro_skills"][0]["prerequisite_position"] = None
    with pytest.raises(MicroSkillError, match="not offered as available"):
        generate_all_micro_skills(briefs[:1], FakeLLMClient([payload]))


@needs_docs
def test_one_call_per_topic(briefs):
    client = FakeLLMClient([_payload() for _ in briefs])
    generate_all_micro_skills(briefs, client)
    assert client.call_count == len(briefs)
    assert all("CG-010" in c["purpose"] for c in client.calls)
