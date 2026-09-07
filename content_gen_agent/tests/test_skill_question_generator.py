"""CG-011 rewritten: one micro-skill at a time.

Everything here exists because of a finding in the content review. The old
generator wrote ~18 questions per topic and worked out afterwards which skill
each one assessed, which left 17 of 53 skills with nothing, gave T06.M1 16 of
its topic's 20, and produced 7 diagnostics across six topics.

No network. FakeLLMClient throughout.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brief_mapper import map_all                    # noqa: E402
from coverage_plan import plan_for_skill            # noqa: E402
from llm_client import FakeLLMClient, LLMError      # noqa: E402
from micro_skill_generator import generate_micro_skills   # noqa: E402
from models import Phase, QuestionStatus            # noqa: E402
from skill_question_generator import (              # noqa: E402
    PHASE_GUIDANCE,
    SYSTEM_PROMPT,
    SkillQuestionError,
    _absent_reference,
    build_user_prompt,
    generate_for_skill,
    generate_for_topic,
    prose_phrase,
)
from sources import find_topic_documents            # noqa: E402

TOPIC_DOCS = find_topic_documents()
needs_docs = pytest.mark.skipif(not TOPIC_DOCS, reason="topic documents not available")

P0 = Phase.PHASE_0_DIAGNOSTIC
P2 = Phase.PHASE_2_GUIDED_LEARNING
P3 = Phase.PHASE_3_INDEPENDENT_PRACTICE

CHOICE_TEXT = "Which rule works for every step? a) n + 3  b) 3n  c) n - 3"
CANVAS_TEXT = "When x = 5, work out the value of 3x + 2."


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


def _entry(slot, qtype=None, text=None, family=None):
    plan = plan_for_skill()
    phase = plan[slot - 1].phase
    if qtype is None:
        qtype = "SINGLE_CHOICE" if phase is not P2 else "SHORT_RESPONSE"
    if text is None:
        text = CHOICE_TEXT if qtype == "SINGLE_CHOICE" else \
            f"Work out the value of the expression for slot {slot}."
    return {"slot": slot, "question_type": qtype, "question_text": text,
            "item_family": family or f"FAMILY-{slot}"}


def _payload(overrides=None):
    """A full seven-slot response, with the given slots replaced.

    Keyed by slot NUMBER, so it takes a dict rather than keywords.
    """
    entries = {i: _entry(i) for i in range(1, len(plan_for_skill()) + 1)}
    entries.update(overrides or {})
    return {"questions": [e for e in entries.values() if e is not None]}


def _gen(brief, skill, payload, **kw):
    kw.setdefault("source_provenance_id", "SRC-NABLIX-T01-001")
    return generate_for_skill(brief, skill, FakeLLMClient([payload]), **kw)


def _prompt_text() -> str:
    return " ".join(SYSTEM_PROMPT.split())


def _rejected(brief, skill, payload, slot, reason):
    """Assert a question was refused: excluded, its slot recorded, reason kept.

    Refusing no longer means raising. A bad question is dropped, its slot is
    reported unfilled, and the wording survives as a warning -- "slot 6 is
    missing" alone would not tell anyone why.
    """
    result = _gen(brief, skill, payload, retry=False)

    assert result.is_complete is False, "the slot should be recorded unfilled"
    assert slot not in {n for n in range(1, 8)
                        if any(r.difficulty and True for r in result.rows)
                        } or len(result.rows) == 6
    assert any(reason in i.message for i in result.issues), \
        f"the reason must survive; got {[i.message for i in result.issues]}"
    assert all(not i.is_error for i in result.issues), \
        "a dropped question does not make the others unusable"
    return result


# ──────────────────────────────────────────────────────────────────────
# The prompt
# ──────────────────────────────────────────────────────────────────────

def test_the_prompt_names_the_one_skill_as_the_thing_being_assessed():
    """The review: the primary skill must be what the question is written to
    assess, not a prerequisite, not the first skill used while solving."""
    text = _prompt_text()
    assert "EVERY QUESTION MUST ASSESS THE ONE MICRO-SKILL GIVEN BELOW" in text
    assert "A question may of course USE earlier skills. It must not be ABOUT them." in text


def test_the_prompt_forbids_referring_to_absent_assets():
    """From the review: a question cited a support card the package lacked."""
    text = _prompt_text()
    assert "Do not refer to anything the student cannot see" in text
    assert "using the supporting card" in text


def test_the_prompt_states_exactly_one_correct_option():
    text = _prompt_text()
    assert "EXACTLY ONE option may be correct" in text
    assert "no two options may be different spellings of the same answer" in text


def test_phase_three_guidance_bans_prose_and_asks_for_a_mix():
    guidance = PHASE_GUIDANCE[P3]
    assert "NO OPEN PROSE" in guidance
    assert "do not make all three multiple choice" in guidance


def test_phase_zero_guidance_asks_for_a_discriminator():
    assert "DISCRIMINATE" in PHASE_GUIDANCE[P0]


def test_phase_two_guidance_allows_explanation():
    """The tutor is present, so prose is fine here. The rule is Phase 3's."""
    assert "may ask the student to explain" in PHASE_GUIDANCE[P2]


@needs_docs
def test_the_prompt_carries_the_skill_and_every_slot(brief, skills):
    prompt = build_user_prompt(brief, skills[2], plan_for_skill())
    assert skills[2].skill_name in prompt
    assert skills[2].description in prompt
    for n in range(1, 8):
        assert f"slot {n}:" in prompt
    assert "PHASE_0_DIAGNOSTIC, difficulty 2" in prompt


@needs_docs
def test_the_prompt_names_the_prerequisite_as_usable_but_not_the_subject(brief, skills):
    prompt = build_user_prompt(brief, skills[2], plan_for_skill())
    assert "may use but must not be about" in prompt


@needs_docs
def test_each_slot_offers_only_the_types_its_phase_allows(brief, skills):
    prompt = build_user_prompt(brief, skills[0], plan_for_skill())
    diagnostic = prompt.split("slot 2:")[0]
    assert "question_type one of: SINGLE_CHOICE" in diagnostic
    assert "SHORT_RESPONSE" not in diagnostic


# ──────────────────────────────────────────────────────────────────────
# A well-behaved model
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_seven_questions_come_back_for_one_skill(brief, skills):
    result = _gen(brief, skills[0], _payload())
    assert result.is_clean
    assert len(result.rows) == 7


@needs_docs
def test_every_question_maps_to_that_skill_alone(brief, skills):
    """The whole point. No choice for the model to get wrong."""
    result = _gen(brief, skills[3], _payload())
    assert len(result.skill_map) == 7
    assert {m.micro_skill_id for m in result.skill_map} == {skills[3].micro_skill_id}
    assert all(m.is_primary and m.weight == 1.0 for m in result.skill_map)


@needs_docs
def test_difficulty_comes_from_the_slot_not_the_model(brief, skills):
    """The model is not asked for a difficulty, so it cannot get it wrong."""
    result = _gen(brief, skills[0], _payload())
    got = sorted(r.difficulty for r in result.rows)
    assert got == [1, 1, 2, 2, 2, 3, 3]


@needs_docs
def test_the_phase_of_every_question_is_known_not_inferred(brief, skills):
    """plan_phases and its heuristic are gone. This is why."""
    result = _gen(brief, skills[0], _payload())
    phases = sorted(p.value for p in result.phases.values())
    assert phases.count("PHASE_0_DIAGNOSTIC") == 1
    assert phases.count("PHASE_2_GUIDED_LEARNING") == 3
    assert phases.count("PHASE_3_INDEPENDENT_PRACTICE") == 3


@needs_docs
def test_ids_run_in_slot_order_not_the_order_the_model_replied(brief, skills):
    payload = {"questions": list(reversed(_payload()["questions"]))}
    result = _gen(brief, skills[0], payload)
    assert result.phases[result.rows[0].question_id] is P0


@needs_docs
def test_rows_carry_the_house_defaults(brief, skills):
    row = _gen(brief, skills[0], _payload()).rows[0]
    assert row.status is QuestionStatus.GENERATED
    assert row.topic_id == brief.topic_id
    assert row.source_provenance_id == "SRC-NABLIX-T01-001"
    assert row.answer_spec_id == "ANS-" + row.question_id[2:]


# ──────────────────────────────────────────────────────────────────────
# Coverage, which is what the rewrite is for
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_a_missing_slot_is_refused(brief, skills):
    """The failure the old generator could not even see."""
    payload = {"questions": [e for e in _payload()["questions"] if e["slot"] != 4]}
    result = _gen(brief, skills[0], payload, retry=False)
    assert result.is_complete is False
    assert [str(s) for s in result.missing] == ["PHASE_2_GUIDED_LEARNING D3"]


@needs_docs
def test_the_missing_slot_is_named_with_its_phase_and_difficulty(brief, skills):
    payload = {"questions": [e for e in _payload()["questions"] if e["slot"] != 1]}
    result = _gen(brief, skills[0], payload, retry=False)
    assert any("PHASE_0_DIAGNOSTIC D2" in i.message and "below minimum" in i.message
               for i in result.issues)


@needs_docs
def test_two_questions_for_one_slot_is_refused(brief, skills):
    payload = _payload()
    payload["questions"].append(_entry(2))
    result = _gen(brief, skills[0], payload, retry=False)
    assert any("same slot" in i.message for i in result.issues)


@needs_docs
def test_a_slot_number_that_does_not_exist_is_refused(brief, skills):
    payload = _payload()
    payload["questions"][0]["slot"] = 99
    result = _gen(brief, skills[0], payload, retry=False)
    assert any("not one of the 7 offered" in i.message for i in result.issues)


# ──────────────────────────────────────────────────────────────────────
# Phase rules
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_a_diagnostic_that_is_not_single_choice_is_refused(brief, skills):
    payload = _payload({1: _entry(1, "SHORT_RESPONSE",
                                   "Write the general rule for the pattern using n.")})
    _rejected(brief, skills[0], payload, slot=1, reason="not allowed in PHASE_0")


@needs_docs
def test_an_explanation_type_in_phase_three_is_refused(brief, skills):
    """PHASE_RULES already forbids it; this proves the check reaches it."""
    _rejected(brief, skills[0],
              _payload({5: _entry(5, "CHOICE_WITH_EXPLANATION", CHOICE_TEXT)}),
              slot=5, reason="not allowed in PHASE_3")


@needs_docs
@pytest.mark.parametrize("text", [
    "Explain in one short sentence why n + 2 is not always even.",
    "In your own words, what does 3n mean?",
    "Describe why the letter can change. Write your answer below.",
    "Write one or two short phrases about what n stands for here.",
])
def test_open_prose_in_phase_three_is_refused(brief, skills, text):
    """The review's hard rule: no support is available, so nothing that needs
    a sentence interpreted can be marked."""
    _rejected(brief, skills[0], _payload({6: _entry(6, "SHORT_RESPONSE", text)}),
              slot=6, reason="forbids open prose")


@needs_docs
@pytest.mark.parametrize("text", [
    CANVAS_TEXT,
    "Write a rule for the total cost using n for the number of tickets.",
    "Complete the expression: 4n + ___ = 4n + 7",
    "Transform 3 x n into its shorter algebraic form.",
])
def test_canvas_work_in_phase_three_is_accepted(brief, skills, text):
    """A check that refused legitimate questions would empty Phase 3."""
    result = _gen(brief, skills[0], _payload({6: _entry(6, "SHORT_RESPONSE", text)}))
    assert result.is_clean


@needs_docs
def test_prose_in_phase_two_is_allowed(brief, skills):
    """The tutor is present there. The rule is Phase 3's alone."""
    result = _gen(brief, skills[0], _payload(
        {3: _entry(3, "SHORT_RESPONSE",
                   "Explain in one sentence why the letter can change.")}))
    assert result.is_clean


# ──────────────────────────────────────────────────────────────────────
# Question quality
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_a_choice_question_with_no_options_is_refused(brief, skills):
    _rejected(brief, skills[0],
              _payload({1: _entry(1, "SINGLE_CHOICE",
                                  "Which rule works for every step?")}),
              slot=1, reason="fewer than two labelled options")


@needs_docs
def test_a_select_all_question_is_refused(brief, skills):
    text = "Which are terms? a) 4x b) 9 c) + Write the letters of all correct options."
    _rejected(brief, skills[0], _payload({1: _entry(1, "SINGLE_CHOICE", text)}),
              slot=1, reason="more than one option")


@needs_docs
def test_a_question_citing_an_absent_asset_is_refused(brief, skills):
    """From the review: Q-T02-015 referenced a support card that did not
    exist. This generator writes no assets, so it cannot cite one."""
    text = "Using the supporting card, write the rule for the total."
    _rejected(brief, skills[0], _payload({3: _entry(3, "SHORT_RESPONSE", text)}),
              slot=3, reason="cannot see")


@needs_docs
def test_a_multi_part_question_typed_short_response_is_refused(brief, skills):
    text = ("In the expression n + 4, write down:\n- the letter used,\n"
            "- the number used,\n- the operation symbol used.")
    _rejected(brief, skills[0], _payload({3: _entry(3, "SHORT_RESPONSE", text)}),
              slot=3, reason="MULTI_PART_SHORT_RESPONSE")


@needs_docs
def test_a_too_short_question_is_refused(brief, skills):
    _rejected(brief, skills[0],
              _payload({3: _entry(3, "SHORT_RESPONSE", "Solve.")}),
              slot=3, reason="too short")


@needs_docs
def test_an_unusable_item_family_is_refused(brief, skills):
    _rejected(brief, skills[0], _payload({3: _entry(3, family="!!!")}),
              slot=3, reason="item_family")


# ──────────────────────────────────────────────────────────────────────
# Warnings
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_all_phase_three_multiple_choice_warns(brief, skills):
    """The review asks for a mix of recognition and canvas work."""
    payload = _payload({n: _entry(n, "SINGLE_CHOICE", CHOICE_TEXT)
                       for n in (5, 6, 7)})
    result = _gen(brief, skills[0], payload)
    assert result.is_clean
    assert any("mix of recognition" in i.message for i in result.issues)


@needs_docs
def test_one_family_for_all_seven_questions_warns(brief, skills):
    payload = _payload({n: _entry(n, family="SAME-THING") for n in range(1, 8)})
    result = _gen(brief, skills[0], payload)
    assert result.is_clean
    assert any("should still vary" in i.message for i in result.issues)


# ──────────────────────────────────────────────────────────────────────
# A whole topic
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_every_skill_in_a_topic_gets_its_own_questions(brief, skills):
    client = FakeLLMClient([_payload() for _ in skills])
    sets = generate_for_topic(brief, skills, client,
                              source_provenance_id="SRC-NABLIX-T01-001")

    assert len(sets) == len(skills)
    assert all(s.is_clean for s in sets)
    assert sum(len(s.rows) for s in sets) == 7 * len(skills)


@needs_docs
def test_no_micro_skill_is_left_without_questions(brief, skills):
    """The review's headline finding, made structurally impossible."""
    client = FakeLLMClient([_payload() for _ in skills])
    sets = generate_for_topic(brief, skills, client,
                              source_provenance_id="SRC-NABLIX-T01-001")
    covered = {m.micro_skill_id for s in sets for m in s.skill_map}
    assert covered == {s.micro_skill_id for s in skills}


@needs_docs
def test_question_ids_do_not_collide_across_skills(brief, skills):
    client = FakeLLMClient([_payload() for _ in skills])
    sets = generate_for_topic(brief, skills, client,
                              source_provenance_id="SRC-NABLIX-T01-001")
    ids = [r.question_id for s in sets for r in s.rows]
    assert len(ids) == len(set(ids))


@needs_docs
def test_one_failing_skill_does_not_take_the_topic_with_it(brief, skills):
    """Under the old generator one bad question lost all eighteen. Here it
    loses seven and names the skill that is short."""
    payloads = [_payload() for _ in skills]
    payloads[2] = {"questions": [e for e in _payload()["questions"] if e["slot"] != 1]}

    sets = generate_for_topic(brief, skills, FakeLLMClient(payloads),
                              source_provenance_id="SRC-NABLIX-T01-001",
                              retry=False)

    # Every skill still produces questions. The short one is short, not empty,
    # and it is the only one flagged.
    assert all(s.rows for s in sets), "no skill loses everything"
    assert [s.is_complete for s in sets].count(False) == 1
    assert sets[2].is_complete is False
    assert len(sets[2].rows) == 6


@needs_docs
def test_an_api_failure_propagates(brief, skills):
    with pytest.raises(LLMError, match="fell over"):
        generate_for_skill(brief, skills[0], FakeLLMClient([LLMError("the api fell over")]),
                           source_provenance_id="SRC-NABLIX-T01-001")


# ──────────────────────────────────────────────────────────────────────
# Recovery: retry the gaps once, then keep and declare
#
# Dropping a question would leave a hole in the coverage this rewrite exists
# to guarantee. Refusing outright would cost all seven over one bad question,
# which is the failure the review flagged. So: retry once, then keep what is
# sound and record the skill as below its minimum -- which the review itself
# asks for ("generation should be marked incomplete").
# ──────────────────────────────────────────────────────────────────────

def _two(first, second):
    return FakeLLMClient([first, second])


@needs_docs
def test_a_gap_is_retried_and_filled(brief, skills):
    first = {"questions": [e for e in _payload()["questions"] if e["slot"] != 4]}
    second = {"questions": [_entry(4)]}

    result = generate_for_skill(brief, skills[0], _two(first, second),
                                source_provenance_id="SRC-NABLIX-T01-001")

    assert result.is_complete
    assert len(result.rows) == 7
    assert any("retry filled [4]" in i.message for i in result.issues)


@needs_docs
def test_the_retry_asks_only_for_the_missing_slots(brief, skills):
    prompt = build_user_prompt(brief, skills[0], plan_for_skill(), only={4, 6})
    assert "slot 4:" in prompt and "slot 6:" in prompt
    assert "slot 1:" not in prompt and "slot 2:" not in prompt
    assert "still needed, and they keep their original numbers" in prompt


@needs_docs
def test_the_retry_keeps_the_original_slot_numbers(brief, skills):
    """So the two passes merge without translating anything."""
    first = {"questions": [e for e in _payload()["questions"] if e["slot"] != 6]}
    second = {"questions": [_entry(6, "SHORT_RESPONSE", CANVAS_TEXT)]}

    result = generate_for_skill(brief, skills[0], _two(first, second),
                                source_provenance_id="SRC-NABLIX-T01-001")

    assert result.is_complete
    recovered = [r for r in result.rows
                 if result.phases[r.question_id] is P3 and r.difficulty == 2]
    assert len(recovered) == 1


@needs_docs
def test_a_retry_that_also_fails_keeps_what_is_good(brief, skills):
    """Six sound questions are better than none, provided the gap is said."""
    first = {"questions": [e for e in _payload()["questions"] if e["slot"] != 4]}
    second = {"questions": []}

    result = generate_for_skill(brief, skills[0], _two(first, second),
                                source_provenance_id="SRC-NABLIX-T01-001")

    assert result.is_clean, "the six that are here are fine"
    assert not result.is_complete, "and the run must not call that complete"
    assert len(result.rows) == 6
    assert [str(s) for s in result.missing] == ["PHASE_2_GUIDED_LEARNING D3"]


@needs_docs
def test_the_shortfall_is_reported_with_the_original_reason(brief, skills):
    """'Slot 6 is missing' is far less useful than why it is missing."""
    bad = _payload({6: _entry(6, "SHORT_RESPONSE",
                              "Explain in your own words what n means.")})
    result = generate_for_skill(brief, skills[0], _two(bad, {"questions": []}),
                                source_provenance_id="SRC-NABLIX-T01-001")

    assert not result.is_complete
    messages = " ".join(i.message for i in result.issues)
    assert "forbids open prose" in messages
    assert "below minimum" in messages


@needs_docs
def test_is_clean_and_is_complete_are_different_facts(brief, skills):
    """A skill can produce sound questions and still be short. Calling that
    dirty would imply the questions are suspect; calling it clean and nothing
    else would hide the gap."""
    first = {"questions": [e for e in _payload()["questions"] if e["slot"] != 2]}
    result = generate_for_skill(brief, skills[0], _two(first, {"questions": []}),
                                source_provenance_id="SRC-NABLIX-T01-001")
    assert result.is_clean is True
    assert result.is_complete is False


@needs_docs
def test_nothing_usable_at_all_is_still_an_error(brief, skills):
    """The one case that is genuinely fatal."""
    empty = {"questions": []}
    with pytest.raises(SkillQuestionError, match="no usable question"):
        generate_for_skill(brief, skills[0], _two(empty, empty),
                           source_provenance_id="SRC-NABLIX-T01-001")


@needs_docs
def test_only_one_retry_is_attempted(brief, skills):
    """A second attempt is the same roll of the same dice. Three scripted
    responses, and the third must go unused."""
    first = {"questions": [e for e in _payload()["questions"] if e["slot"] != 4]}
    client = FakeLLMClient([first, {"questions": []}, {"questions": [_entry(4)]}])

    result = generate_for_skill(brief, skills[0], client,
                                source_provenance_id="SRC-NABLIX-T01-001")

    assert not result.is_complete, "the unused third response would have filled it"
    assert len(result.rows) == 6


@needs_docs
def test_retry_can_be_turned_off(brief, skills):
    first = {"questions": [e for e in _payload()["questions"] if e["slot"] != 4]}
    result = generate_for_skill(brief, skills[0], FakeLLMClient([first]),
                                source_provenance_id="SRC-NABLIX-T01-001",
                                retry=False)
    assert len(result.rows) == 6
    assert not result.is_complete


@needs_docs
def test_a_clean_first_pass_does_not_retry(brief, skills):
    """One response scripted; a retry would raise for want of a second."""
    result = generate_for_skill(brief, skills[0], FakeLLMClient([_payload()]),
                                source_provenance_id="SRC-NABLIX-T01-001")
    assert result.is_complete
    assert not [i for i in result.issues if "retry" in i.message]


# ──────────────────────────────────────────────────────────────────────
# A type we choose not to generate
#
# TRUE_FALSE_WITH_EXPLANATION is in the enum and in PHASE_RULES and in none of
# the approved reference's 54 rows. A six-topic run produced three-statement
# questions answered "True; False; True" -- a MULTI_PART answer wearing a
# true/false label -- and 9 of that run's 25 dropped answers were this.
# ──────────────────────────────────────────────────────────────────────

from skill_question_generator import (               # noqa: E402
    SUPPRESSED_QUESTION_TYPES,
    allowed_types,
)


def test_true_false_is_not_offered_to_the_model():
    assert "TRUE_FALSE_WITH_EXPLANATION" in SUPPRESSED_QUESTION_TYPES
    for phase in (P0, P2, P3):
        assert "TRUE_FALSE_WITH_EXPLANATION" not in allowed_types(phase)


def test_the_phase_rules_table_is_left_alone():
    """It records the spec. The suppression is our decision about what to
    generate, kept separate so reversing it is one line."""
    from table_schemas import PHASE_RULES
    assert "TRUE_FALSE_WITH_EXPLANATION" in \
        PHASE_RULES[P2.value]["allowed_question_types"]


def test_every_other_type_is_still_offered():
    """Suppressing one type must not quietly narrow the rest."""
    assert set(allowed_types(P2)) == {
        "SINGLE_CHOICE", "SHORT_RESPONSE", "MULTI_PART_SHORT_RESPONSE",
        "CHOICE_WITH_EXPLANATION",
    }


@needs_docs
def test_a_true_false_question_is_refused_if_the_model_writes_one_anyway(brief, skills):
    payload = _payload({3: _entry(3, "TRUE_FALSE_WITH_EXPLANATION",
                                  "True or false: a letter always means one number?")})
    _rejected(brief, skills[0], payload, slot=3, reason="is not allowed in")


@needs_docs
def test_the_prompt_never_names_the_suppressed_type(brief, skills):
    prompt = build_user_prompt(brief, skills[0], plan_for_skill())
    assert "TRUE_FALSE_WITH_EXPLANATION" not in prompt
