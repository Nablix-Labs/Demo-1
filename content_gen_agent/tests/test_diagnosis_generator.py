"""CG-015 tests: error types and the misconceptions behind them.

The exit condition is "errors link to valid micro-skills, misconceptions have
diagnostic rules". The second half of that is the interesting one, because the
rule names error codes in prose rather than through a foreign key, so nothing
in the schema stops a misconception triggering on an error that was never
defined.

Everything here uses FakeLLMClient. No network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brief_mapper import map_all                    # noqa: E402
from diagnosis_generator import (                   # noqa: E402
    ERROR_SYSTEM_PROMPT,
    MAX_ERRORS,
    MAX_MISCONCEPTIONS,
    MIN_ERRORS,
    MIN_MISCONCEPTIONS,
    MISCONCEPTION_SYSTEM_PROMPT,
    DiagnosisError,
    build_error_prompt,
    build_misconception_prompt,
    generate_error_types,
    generate_misconceptions,
    referenced_error_codes,
)
from llm_client import FakeLLMClient, LLMError      # noqa: E402
from micro_skill_generator import generate_micro_skills   # noqa: E402
from models import DetectionMethod, Severity        # noqa: E402
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


@pytest.fixture
def skills(brief):
    payload = {"micro_skills": [
        {"skill_name": f"Skill {i}", "description": f"The student does {i}.",
         "prerequisite_position": (i - 1) if i > 1 else None,
         "prerequisite_micro_skill_id": None,
         "assessment_priority": "HIGH" if i % 2 else "MEDIUM"}
        for i in range(1, 8)
    ]}
    return generate_micro_skills(brief, FakeLLMClient([payload])).rows


def _e(i=1, descriptor=None, position=None, severity=None, method=None, **kw):
    entry = {
        "descriptor": descriptor or f"ERROR-KIND-{i}",
        "error_name": f"Error name {i}",
        "description": f"Student writes the wrong thing in way {i}.",
        "micro_skill_position": position or ((i % 7) + 1),
        "severity": severity or ("HIGH" if i % 2 else "MEDIUM"),
        "detection_method": method or "SYMBOLIC_PATTERN",
    }
    entry.update(kw)
    return entry


def _payload(n=5, **kw):
    return {"error_types": [_e(i, **kw) for i in range(1, n + 1)]}


def _gen(brief, skills, payload, **kw):
    return generate_error_types(
        brief, FakeLLMClient([payload]), micro_skills=skills, **kw,
    )


def _prompt_text() -> str:
    return " ".join(ERROR_SYSTEM_PROMPT.split())


# ──────────────────────────────────────────────────────────────────────
# The prompt
# ──────────────────────────────────────────────────────────────────────

def test_the_prompt_separates_an_error_from_a_belief():
    """The whole reason there are two tables."""
    text = _prompt_text()
    assert "what a wrong answer LOOKS LIKE, not what the student believes" in text
    assert "belongs in the misconceptions table" in text


def test_the_prompt_describes_every_detection_method():
    """Listing eight bare enum values is how the answer key ended up marking
    42% of questions by loose text match: unexplained options get picked by
    vagueness rather than fit."""
    text = _prompt_text()
    for method in DetectionMethod:
        assert method.value in text, f"{method.value} is offered without explanation"


def test_the_prompt_asks_for_the_cheapest_workable_detection_method():
    assert "Choose the CHEAPEST one that would actually work" in _prompt_text()


def test_the_prompt_says_both_severities_are_used():
    text = _prompt_text()
    assert "Use both" in text
    assert "two HIGH to one MEDIUM" in text


def test_the_prompt_wants_a_concrete_description():
    text = _prompt_text()
    assert "writes 3 - t instead of t - 3" in text
    assert "makes an ordering mistake" in text, "must show the bad example too"


@needs_docs
def test_the_prompt_carries_the_skills_and_the_misconceptions(brief, skills):
    prompt = build_error_prompt(brief, skills)
    assert "1. Skill 1" in prompt
    assert "7. Skill 7" in prompt
    for item in brief.misconceptions_to_prevent[:2]:
        assert item in prompt


@needs_docs
def test_the_prompt_lists_the_excluded_scope(brief, skills):
    prompt = build_error_prompt(brief, skills)
    if brief.excluded_scope:
        assert "Do not write errors about these" in prompt
        assert brief.excluded_scope[0] in prompt


# ──────────────────────────────────────────────────────────────────────
# Building the rows
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_error_codes_are_minted_here_not_by_the_model(brief, skills):
    """The model supplies a descriptor; the code is ours, and carries the
    topic, which is the convention CG-001 settled for new topics."""
    result = _gen(brief, skills, _payload())
    assert result.is_clean
    assert all(row.error_code.startswith("ERR-T01-") for row in result.rows)


@needs_docs
def test_a_position_becomes_a_real_micro_skill_id(brief, skills):
    payload = _payload()
    payload["error_types"][0]["micro_skill_position"] = 3
    result = _gen(brief, skills, payload)
    assert result.rows[0].related_micro_skill_id == skills[2].micro_skill_id


@needs_docs
def test_every_error_links_to_a_skill_that_exists(brief, skills):
    """CG-015's stated exit condition."""
    result = _gen(brief, skills, _payload(n=7))
    known = {row.micro_skill_id for row in skills}
    assert {row.related_micro_skill_id for row in result.rows} <= known


@needs_docs
def test_rows_are_active_and_typed(brief, skills):
    result = _gen(brief, skills, _payload())
    row = result.rows[0]
    assert row.active is True
    assert isinstance(row.severity, Severity)
    assert isinstance(row.detection_method, DetectionMethod)


@needs_docs
def test_the_descriptor_becomes_the_readable_part_of_the_code(brief, skills):
    payload = _payload(n=4)
    payload["error_types"][0]["descriptor"] = "ADD-AS-MULTIPLY"
    result = _gen(brief, skills, payload)
    assert result.rows[0].error_code == "ERR-T01-ADD-AS-MULTIPLY"


# ──────────────────────────────────────────────────────────────────────
# Refusing what cannot be used
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_a_position_outside_the_offered_skills_is_refused(brief, skills):
    payload = _payload()
    payload["error_types"][1]["micro_skill_position"] = 99
    with pytest.raises(DiagnosisError, match="outside the 7 skills"):
        _gen(brief, skills, payload)


@needs_docs
def test_a_position_that_is_not_a_number_is_refused(brief, skills):
    payload = _payload()
    payload["error_types"][1]["micro_skill_position"] = "third"
    with pytest.raises(DiagnosisError, match="not a whole number"):
        _gen(brief, skills, payload)


@needs_docs
def test_an_invalid_severity_is_refused(brief, skills):
    payload = _payload()
    payload["error_types"][0]["severity"] = "CRITICAL"
    with pytest.raises(DiagnosisError, match="not HIGH or MEDIUM"):
        _gen(brief, skills, payload)


@needs_docs
def test_an_invented_detection_method_is_refused(brief, skills):
    payload = _payload()
    payload["error_types"][0]["detection_method"] = "VIBES"
    with pytest.raises(DiagnosisError, match="detection_method"):
        _gen(brief, skills, payload)


@needs_docs
def test_a_duplicate_descriptor_is_refused(brief, skills):
    """Two rows would otherwise mint the same error code."""
    payload = _payload()
    payload["error_types"][2]["descriptor"] = payload["error_types"][0]["descriptor"]
    with pytest.raises(DiagnosisError, match="duplicate descriptor"):
        _gen(brief, skills, payload)


@needs_docs
def test_a_descriptor_with_nothing_usable_is_refused(brief, skills):
    payload = _payload()
    payload["error_types"][0]["descriptor"] = "!!!"
    with pytest.raises(DiagnosisError, match="nothing usable"):
        _gen(brief, skills, payload)


@needs_docs
def test_an_empty_description_is_refused(brief, skills):
    payload = _payload()
    payload["error_types"][1]["description"] = "   "
    with pytest.raises(DiagnosisError, match="description"):
        _gen(brief, skills, payload)


@needs_docs
@pytest.mark.parametrize("count", [0, 1, MIN_ERRORS - 1])
def test_too_few_errors_is_refused(brief, skills, count):
    with pytest.raises(DiagnosisError):
        _gen(brief, skills, _payload(n=count))


@needs_docs
def test_too_many_errors_is_trimmed_not_refused(brief, skills):
    """A six-topic run lost Topic 3's error types and its misconceptions,
    which depend on them, because the model returned 11 against a ceiling of
    10. The eleventh was fine. The ceiling is a guess, so surplus rows are set
    aside rather than costing the topic its whole diagnosis chain."""
    result = _gen(brief, skills, _payload(n=MAX_ERRORS + 1))

    assert result.is_clean
    assert len(result.rows) == MAX_ERRORS
    assert any("set aside 1" in i.message for i in result.issues)


@needs_docs
def test_the_trim_says_how_many_came_back(brief, skills):
    result = _gen(brief, skills, _payload(n=MAX_ERRORS + 3))
    warning = next(i for i in result.issues if "set aside" in i.message)
    assert f"returned {MAX_ERRORS + 3}" in warning.message
    assert not warning.is_error


@needs_docs
def test_trimming_keeps_the_first_rows_in_order(brief, skills):
    payload = _payload(n=MAX_ERRORS + 2)
    payload["error_types"][0]["descriptor"] = "FIRST-ONE"
    result = _gen(brief, skills, payload)
    assert result.rows[0].error_code == "ERR-T01-FIRST-ONE"
    assert len(result.rows) == MAX_ERRORS


@needs_docs
def test_too_few_is_still_an_error(brief, skills):
    """Surplus means the model did more than expected. A shortfall means it
    did not do the work, which is a different thing."""
    with pytest.raises(DiagnosisError, match="at least"):
        _gen(brief, skills, _payload(n=MIN_ERRORS - 1))


@needs_docs
def test_generating_without_micro_skills_is_refused(brief):
    """There would be nothing to attach an error to."""
    with pytest.raises(DiagnosisError, match="no micro-skills"):
        generate_error_types(brief, FakeLLMClient([_payload()]), micro_skills=[])


@needs_docs
def test_an_api_failure_propagates(brief, skills):
    client = FakeLLMClient([LLMError("the api fell over")])
    with pytest.raises(LLMError, match="fell over"):
        generate_error_types(brief, client, micro_skills=skills)


# ──────────────────────────────────────────────────────────────────────
# Warnings: usable, but worth saying
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_all_one_severity_warns_but_proceeds(brief, skills):
    result = _gen(brief, skills, _payload(severity="HIGH"))
    assert result.is_clean
    assert any("has no priority" in i.message for i in result.issues)


@needs_docs
def test_a_high_priority_skill_with_no_failure_mode_warns(brief, skills):
    """Error_Types is the entry point to the diagnosis chain: an error leads
    to a misconception, then a hint (CG-017), then a scaffold (CG-018). A
    skill with no error attached silently gets none of them.

    The skills fixture makes odd positions HIGH, so pointing every error at
    position 2 leaves four HIGH skills uncovered.
    """
    result = _gen(brief, skills, _payload(position=2))

    assert result.is_clean, "a warning, not a refusal"
    warning = next(i for i in result.issues if "no error type" in i.message)
    assert "4 HIGH-priority skill(s)" in warning.message
    for expected in ("T01.M1", "T01.M3", "T01.M5", "T01.M7"):
        assert expected in warning.message, "the gap has to be named to be fixed"
    assert "no hint or scaffold either" in warning.message


@needs_docs
def test_the_warning_names_only_the_uncovered_skills(brief, skills):
    """Position 2 is covered, so it must not appear in the list."""
    result = _gen(brief, skills, _payload(position=2))
    warning = next(i for i in result.issues if "no error type" in i.message)
    assert "T01.M2" not in warning.message


@needs_docs
def test_an_uncovered_medium_skill_does_not_warn(brief, skills):
    """A supporting skill can reasonably have no distinctive failure mode.
    Warning on those would bury the HIGH ones in noise."""
    payload = {"error_types": [
        _e(i, position=p) for i, p in enumerate([1, 3, 5, 7, 1], start=1)
    ]}
    result = _gen(brief, skills, payload)

    assert result.is_clean
    # 2, 4 and 6 are the MEDIUM skills and are all uncovered here.
    assert not [i for i in result.issues if "no error type" in i.message]


@needs_docs
def test_covering_every_high_skill_produces_no_warning(brief, skills):
    payload = {"error_types": [
        _e(i, position=p) for i, p in enumerate([1, 2, 3, 4, 5, 6, 7], start=1)
    ]}
    result = _gen(brief, skills, payload)
    assert result.is_clean
    assert not [i for i in result.issues if "no error type" in i.message]


# ──────────────────────────────────────────────────────────────────────
# Recovery
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_one_bad_row_can_be_dropped_rather_than_losing_the_topic(brief, skills):
    payload = _payload(n=6)
    payload["error_types"][2]["severity"] = "CRITICAL"

    result = _gen(brief, skills, payload, drop_invalid=True)

    assert result.is_clean
    assert len(result.rows) == 5
    assert any("dropped 1 unusable row" in i.message for i in result.issues)


@needs_docs
def test_a_dropped_row_is_reported_with_its_reason(brief, skills):
    payload = _payload(n=6)
    payload["error_types"][2]["severity"] = "CRITICAL"
    result = _gen(brief, skills, payload, drop_invalid=True)
    assert any("dropped: " in i.message and "CRITICAL" in i.message
               for i in result.issues)


@needs_docs
def test_dropping_cannot_rescue_a_batch_that_is_too_small(brief, skills):
    """Removing a row does not fix having too few of them."""
    payload = _payload(n=MIN_ERRORS)
    payload["error_types"][0]["severity"] = "CRITICAL"
    with pytest.raises(DiagnosisError):
        _gen(brief, skills, payload, drop_invalid=True)


@needs_docs
def test_non_strict_returns_the_problems_instead_of_raising(brief, skills):
    payload = _payload()
    payload["error_types"][0]["severity"] = "CRITICAL"
    result = _gen(brief, skills, payload, strict=False)
    assert not result.is_clean
    assert result.rows == [], "a rejected set must not produce rows"


@needs_docs
def test_every_problem_is_reported_in_one_pass(brief, skills):
    payload = _payload()
    payload["error_types"][0]["severity"] = "CRITICAL"
    payload["error_types"][1]["description"] = ""
    payload["error_types"][2]["micro_skill_position"] = 99
    result = _gen(brief, skills, payload, strict=False)
    assert len(result.errors) >= 3


@needs_docs
def test_the_raw_response_survives(brief, skills):
    payload = _payload()
    result = _gen(brief, skills, payload)
    assert result.raw_response["error_types"][0]["descriptor"] == "ERROR-KIND-1"


# ──────────────────────────────────────────────────────────────────────
# Misconceptions
#
# The interesting part of CG-015. diagnosis_rule points at Error_Types
# through prose rather than a foreign key, so nothing in the schema stops a
# misconception triggering on an error that was never defined. The platform
# reads that rule, so a dangling code is a misconception that can never fire.
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def error_rows(brief, skills):
    return _gen(brief, skills, _payload(n=5)).rows


def _m(i=1, descriptor=None, rule=None, codes=(), **kw):
    entry = {
        "descriptor": descriptor or f"BELIEF-KIND-{i}",
        "name": f"Belief name {i}",
        "description": f"Student believes the wrong thing in way {i}.",
        "diagnosis_rule": rule or (
            f"Trigger after {codes[(i - 1) % len(codes)]} when the pattern "
            f"repeats across cases." if codes else "Trigger after ERR-T01-X."
        ),
    }
    entry.update(kw)
    return entry


def _mpayload(error_rows, n=3, **kw):
    codes = [row.error_code for row in error_rows]
    return {"misconceptions": [_m(i, codes=codes, **kw) for i in range(1, n + 1)]}


def _mgen(brief, error_rows, payload, **kw):
    return generate_misconceptions(
        brief, FakeLLMClient([payload]), error_types=error_rows, **kw,
    )


def _mprompt_text() -> str:
    return " ".join(MISCONCEPTION_SYSTEM_PROMPT.split())


# -- the prompt --------------------------------------------------------

def test_the_misconception_prompt_separates_belief_from_observation():
    text = _mprompt_text()
    assert "A misconception is a BELIEF, not an observation" in text
    assert "is an error and does not belong here" in text


def test_the_prompt_forbids_inventing_an_error_code():
    """The lesson from micro-skills, where the model invented a prerequisite
    id when none were offered."""
    text = _mprompt_text()
    assert "copied EXACTLY" in text
    assert "Never invent an error code" in text


def test_the_prompt_asks_for_a_condition_not_just_a_trigger():
    """One wrong answer is a slip. A pattern is a belief."""
    text = _mprompt_text()
    assert "One wrong answer is a slip. A pattern is a belief." in text


def test_the_prompt_says_one_belief_causes_several_errors():
    assert "One belief usually causes SEVERAL errors" in _mprompt_text()


@needs_docs
def test_the_available_error_codes_reach_the_prompt(brief, error_rows):
    prompt = build_misconception_prompt(brief, error_rows)
    for row in error_rows:
        assert row.error_code in prompt
        assert row.error_name in prompt


# -- reading codes back out of prose -----------------------------------

@pytest.mark.parametrize("rule, expected", [
    ("Trigger after ERR-T01-ADD-AS-MULTIPLY when the rule adds.",
     ["ERR-T01-ADD-AS-MULTIPLY"]),
    ("Trigger after ERR-T01-A and ERR-T01-B together.",
     ["ERR-T01-A", "ERR-T01-B"]),
    ("Trigger after ERR-ADD-AS-MULTIPLY.", ["ERR-ADD-AS-MULTIPLY"]),
    ("No code here at all.", []),
    ("", []),
])
def test_error_codes_are_read_back_out_of_the_rule(rule, expected):
    assert referenced_error_codes(rule) == expected


# -- building the rows -------------------------------------------------

@needs_docs
def test_misconception_ids_are_minted_here_and_carry_the_topic(brief, error_rows):
    result = _mgen(brief, error_rows, _mpayload(error_rows))
    assert result.is_clean
    assert all(row.misconception_id.startswith("MIS-T01-") for row in result.rows)


@needs_docs
def test_rows_carry_the_house_defaults(brief, error_rows):
    row = _mgen(brief, error_rows, _mpayload(error_rows)).rows[0]
    assert row.active is True
    assert row.version == "1.0"


@needs_docs
def test_a_rule_naming_two_real_codes_is_accepted(brief, error_rows):
    codes = [r.error_code for r in error_rows]
    payload = _mpayload(error_rows)
    payload["misconceptions"][0]["diagnosis_rule"] = (
        f"Trigger after {codes[0]} or {codes[1]} when the student repeats it.")
    assert _mgen(brief, error_rows, payload).is_clean


# -- the load-bearing check --------------------------------------------

@needs_docs
def test_a_rule_naming_an_error_that_does_not_exist_is_refused(brief, error_rows):
    payload = _mpayload(error_rows)
    payload["misconceptions"][1]["diagnosis_rule"] = (
        "Trigger after ERR-T01-MADE-UP when something happens.")
    with pytest.raises(DiagnosisError, match="does not exist"):
        _mgen(brief, error_rows, payload)


@needs_docs
def test_a_rule_naming_another_topics_error_is_refused(brief, error_rows):
    """Error codes are per-topic, so a T02 code is dangling here."""
    payload = _mpayload(error_rows)
    payload["misconceptions"][0]["diagnosis_rule"] = (
        "Trigger after ERR-T02-COEFFICIENT-NOTATION when misread.")
    with pytest.raises(DiagnosisError, match="does not exist"):
        _mgen(brief, error_rows, payload)


@needs_docs
def test_a_rule_naming_no_error_at_all_is_refused(brief, error_rows):
    payload = _mpayload(error_rows)
    payload["misconceptions"][0]["diagnosis_rule"] = (
        "Trigger when the student seems confused about letters.")
    with pytest.raises(DiagnosisError, match="nothing can ever trigger it"):
        _mgen(brief, error_rows, payload)


@needs_docs
def test_the_message_names_every_missing_code(brief, error_rows):
    payload = _mpayload(error_rows)
    payload["misconceptions"][0]["diagnosis_rule"] = (
        "Trigger after ERR-T01-NOPE and ERR-T01-ALSO-NOPE together.")
    result = _mgen(brief, error_rows, payload, strict=False)
    message = " ".join(i.message for i in result.errors)
    assert "ERR-T01-ALSO-NOPE" in message and "ERR-T01-NOPE" in message
    assert "do not exist" in message, "plural when there are several"


# -- refusing the rest -------------------------------------------------

@needs_docs
def test_a_duplicate_descriptor_is_refused_for_misconceptions(brief, error_rows):
    payload = _mpayload(error_rows)
    payload["misconceptions"][2]["descriptor"] = \
        payload["misconceptions"][0]["descriptor"]
    with pytest.raises(DiagnosisError, match="duplicate descriptor"):
        _mgen(brief, error_rows, payload)


@needs_docs
def test_an_empty_diagnosis_rule_is_refused(brief, error_rows):
    payload = _mpayload(error_rows)
    payload["misconceptions"][1]["diagnosis_rule"] = "   "
    with pytest.raises(DiagnosisError, match="diagnosis_rule"):
        _mgen(brief, error_rows, payload)


@needs_docs
@pytest.mark.parametrize("count", [0, MIN_MISCONCEPTIONS - 1])
def test_too_few_misconceptions_is_refused(brief, error_rows, count):
    with pytest.raises(DiagnosisError):
        _mgen(brief, error_rows, _mpayload(error_rows, n=count))


@needs_docs
def test_too_many_misconceptions_is_trimmed_not_refused(brief, error_rows):
    result = _mgen(brief, error_rows, _mpayload(error_rows, n=MAX_MISCONCEPTIONS + 1))
    assert result.is_clean
    assert len(result.rows) == MAX_MISCONCEPTIONS
    assert any("set aside 1" in i.message for i in result.issues)


@needs_docs
def test_generating_without_error_types_is_refused(brief):
    """A diagnosis rule would have nothing to trigger on."""
    with pytest.raises(DiagnosisError, match="no error types"):
        generate_misconceptions(
            brief, FakeLLMClient([{"misconceptions": []}]), error_types=[])


# -- warnings ----------------------------------------------------------

@needs_docs
def test_an_error_no_misconception_explains_warns(brief, error_rows):
    """The tutor can detect it but has nothing to re-teach."""
    codes = [r.error_code for r in error_rows]
    payload = _mpayload(error_rows, n=3)
    for entry in payload["misconceptions"]:
        entry["diagnosis_rule"] = f"Trigger after {codes[0]} when repeated."
    result = _mgen(brief, error_rows, payload)
    assert result.is_clean
    assert any("never explained by any misconception" in i.message
               for i in result.issues)
    assert any(codes[3] in i.message for i in result.issues)


@needs_docs
def test_covering_every_error_produces_no_orphan_warning(brief, error_rows):
    codes = [r.error_code for r in error_rows]
    payload = _mpayload(error_rows, n=3)
    payload["misconceptions"][0]["diagnosis_rule"] = (
        f"Trigger after {codes[0]} or {codes[1]} when repeated.")
    payload["misconceptions"][1]["diagnosis_rule"] = (
        f"Trigger after {codes[2]} when repeated.")
    payload["misconceptions"][2]["diagnosis_rule"] = (
        f"Trigger after {codes[3]} or {codes[4]} when repeated.")
    result = _mgen(brief, error_rows, payload)
    assert not [i for i in result.issues if "never explained" in i.message]


# -- recovery ----------------------------------------------------------

@needs_docs
def test_one_bad_misconception_can_be_dropped(brief, error_rows):
    payload = _mpayload(error_rows, n=4)
    payload["misconceptions"][1]["diagnosis_rule"] = "Trigger after ERR-T01-NOPE."

    result = _mgen(brief, error_rows, payload, drop_invalid=True)

    assert result.is_clean
    assert len(result.rows) == 3
    assert any("dropped: " in i.message and "ERR-T01-NOPE" in i.message
               for i in result.issues)


@needs_docs
def test_non_strict_returns_the_problems_for_misconceptions(brief, error_rows):
    payload = _mpayload(error_rows)
    payload["misconceptions"][0]["diagnosis_rule"] = "Trigger after ERR-T01-NOPE."
    result = _mgen(brief, error_rows, payload, strict=False)
    assert not result.is_clean
    assert result.rows == []


# -- the two tables together -------------------------------------------

@needs_docs
def test_errors_then_misconceptions_produce_a_consistent_pair(brief, skills):
    """The chain CG-016 will build on: every code a rule names is real."""
    errors = _gen(brief, skills, _payload(n=6))
    misconceptions = _mgen(brief, errors.rows, _mpayload(errors.rows, n=4))

    assert errors.is_clean and misconceptions.is_clean
    known = {row.error_code for row in errors.rows}
    for row in misconceptions.rows:
        named = referenced_error_codes(row.diagnosis_rule)
        assert named, f"{row.misconception_id} has no trigger"
        assert set(named) <= known, f"{row.misconception_id} names an unknown code"


@needs_docs
def test_ids_from_both_tables_do_not_collide(brief, skills):
    from id_service import IdService
    service = IdService("T01")
    errors = generate_error_types(
        brief, FakeLLMClient([_payload(n=5)]), micro_skills=skills,
        id_service=service)
    misconceptions = generate_misconceptions(
        brief, FakeLLMClient([_mpayload(errors.rows, n=3)]),
        error_types=errors.rows, id_service=service)
    ids = [r.error_code for r in errors.rows] + \
          [r.misconception_id for r in misconceptions.rows]
    assert len(ids) == len(set(ids))
