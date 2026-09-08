"""CG-018: the guided walk-through for a stuck student.

The review says one scaffold per Phase-2 question. The template writes one per
pattern and reuses it across questions, which is what these tests pin: one
scaffold per micro-skill, linked to all of that skill's guided questions, so
every Phase-2 question has one without three near-identical copies existing.

No network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coverage_plan import Slot                      # noqa: E402
from llm_client import FakeLLMClient, LLMError      # noqa: E402
from models import (                                # noqa: E402
    AssessmentPriority,
    HintRow,
    HintType,
    MicroSkillRow,
    MicroSkillStatus,
    Phase,
    QuestionRow,
    QuestionStatus,
    QuestionType,
    VisualCueReviewStatus,
    VisualCueRow,
    EmbeddingStatus,
)
from scaffold_generator import (                    # noqa: E402
    MAX_STEPS,
    MIN_STEPS,
    SYSTEM_PROMPT,
    TYPICAL_STEPS,
    ScaffoldError,
    build_user_prompt,
    generate_scaffolds,
    guided_by_skill,
)

SKILL = "T01.M4"
P2 = Phase.PHASE_2_GUIDED_LEARNING
P3 = Phase.PHASE_3_INDEPENDENT_PRACTICE


def _skill(sid=SKILL):
    return MicroSkillRow(
        micro_skill_id=sid, topic_id="ALG-ORI-01", skill_code=sid.split(".")[1],
        skill_name="Use letter for changing number",
        description="Use a letter for a number that changes from case to case.",
        prerequisite_micro_skill_id=None,
        assessment_priority=AssessmentPriority.HIGH,
        status=MicroSkillStatus.ACTIVE, version="1.0",
    )


def _question(i=1):
    return QuestionRow(
        question_id=f"Q-T01-{i:03d}", topic_id="ALG-ORI-01",
        question_text="Write the rule that works for every step.",
        question_type=QuestionType.SHORT_RESPONSE, difficulty=1,
        answer_spec_id=f"ANS-T01-{i:03d}", item_family_id="FAM-T01-X",
        source_provenance_id="SRC-NABLIX-T01-001",
        status=QuestionStatus.GENERATED, version="1.0",
    )


def _hint(hid="HINT-T01-GENERAL-L1"):
    return HintRow(hint_id=hid, hint_level=1, hint_type=HintType.ATTENTION,
                   content="Look at what changes.", active=True)


def _cue(cid="VC-T01-ADD-NOT-MULTIPLY"):
    return VisualCueRow(
        visual_cue_id=cid, cue_name="Adding Is Not Multiplying",
        cue_purpose="Show the contrast.",
        image_generation_prompt="Premium 2D educational infographic.",
        negative_prompt="No text.", tutor_explanation_template="Compare them.",
        retrieval_text="Use when a student multiplies a fixed change.",
        retrieval_keywords="fixed change", asset_url=None,
        embedding_status=EmbeddingStatus.PENDING,
        review_status=VisualCueReviewStatus.PENDING_REVIEW, version="1.0",
    )


def _step(n=1, **kw):
    base = {"prompt": f"What changes at step {n}?",
            "partial_content": "3+5 | 9+5",
            "expected_response": "The starting number",
            "next_on_incorrect": "Use HINT-T01-GENERAL-L1"}
    base.update(kw)
    return base


def _scaffold(skill=SKILL, steps=None, **kw):
    base = {
        "micro_skill_id": skill,
        "scaffold_name": "Cases to General Rule",
        "trigger_rule": "Activate after hints and cues have not worked.",
        "completion_rule": "Write the full rule unaided.",
        "steps": steps if steps is not None else [_step(n) for n in range(1, 4)],
    }
    base.update(kw)
    return base


def _gen(payload, skills=None, guided=None, hints=None, cues=None, **kw):
    skills = skills or [_skill()]
    guided = guided if guided is not None else {SKILL: [_question(1), _question(2)]}
    return generate_scaffolds(
        skills, guided, hints or [_hint()], cues or [_cue()],
        FakeLLMClient([payload]), "T01", **kw)


def _prompt_text() -> str:
    return " ".join(SYSTEM_PROMPT.split())


# ──────────────────────────────────────────────────────────────────────
# The prompt
# ──────────────────────────────────────────────────────────────────────

def test_the_prompt_anchors_on_the_number_the_reference_actually_uses():
    """All 12 approved scaffolds have exactly four steps -- not an average,
    the same number every time. Offering "3 to 5" and nothing else got 5 in
    every scaffold of the 9 September run: a range is read as a licence to
    take its ceiling, the same failure as the optional third hint."""
    text = _prompt_text()
    assert "exactly FOUR" in text
    assert f"Write {TYPICAL_STEPS} unless" in text
    assert f"Do not reach for {MAX_STEPS} because it is permitted" in text


def test_the_typical_count_sits_inside_the_permitted_range():
    assert MIN_STEPS <= TYPICAL_STEPS <= MAX_STEPS


def test_the_range_is_still_allowed():
    """Anchoring is not narrowing. A method with three parts should get three
    steps, not a padded fourth."""
    text = _prompt_text()
    assert f"{MIN_STEPS} to {MAX_STEPS} is allowed" in text


def test_the_prompt_says_a_scaffold_breaks_thinking_into_steps():
    """Not: solve it and show the answer."""
    text = _prompt_text()
    assert "A SCAFFOLD BREAKS THE THINKING INTO STEPS" in text
    assert "It does not solve the question and then show the answer" in text


def test_the_prompt_says_the_scaffold_serves_every_question_on_the_skill():
    """Which is why prompts cannot name specific numbers."""
    text = _prompt_text()
    assert "THE SCAFFOLD SERVES EVERY GUIDED QUESTION ON THIS SKILL" in text
    assert "Put example values in partial_content, never in prompt" in text


def test_the_prompt_forbids_writing_the_forward_route():
    """It is derived, so asking would create a second source of truth."""
    assert "Do not write next_on_correct" in _prompt_text()


def test_the_prompt_says_a_scaffold_is_a_last_resort():
    assert "It is a last resort, after hints and cues have not worked" in _prompt_text()


def test_the_prompt_distinguishes_finishing_from_learning():
    text = _prompt_text()
    assert "Finishing the scaffold is not the same as having learned the skill" in text


def test_the_available_support_reaches_the_prompt():
    prompt = build_user_prompt([_skill()], [_hint()], [_cue()])
    assert "HINT-T01-GENERAL-L1" in prompt
    assert "VC-T01-ADD-NOT-MULTIPLY" in prompt
    assert "Copy an id exactly" in prompt


# ──────────────────────────────────────────────────────────────────────
# Building
# ──────────────────────────────────────────────────────────────────────

def test_one_scaffold_serves_every_guided_question_on_the_skill():
    """The review asks that each Phase-2 question have a scaffold. It does,
    without three near-identical copies existing."""
    result = _gen({"scaffolds": [_scaffold()]})

    assert result.is_clean
    assert len(result.scaffolds) == 1
    assert len(result.links) == 2, "one per guided question"
    assert {l.question_id for l in result.links} == {"Q-T01-001", "Q-T01-002"}


def test_the_link_carries_the_questions_own_skill():
    """A question has exactly one skill, so this is never asked for."""
    result = _gen({"scaffolds": [_scaffold()]})
    assert {l.micro_skill_id for l in result.links} == {SKILL}


def test_the_forward_route_is_derived():
    """Every template row does this, so asking would only add a way to
    disagree."""
    result = _gen({"scaffolds": [_scaffold(steps=[_step(n) for n in range(1, 4)])]})
    routes = [s.next_on_correct for s in sorted(result.steps, key=lambda s: s.stage_no)]
    assert routes == ["Stage 2", "Stage 3", "Complete"]


def test_stages_are_numbered_from_one_in_order():
    result = _gen({"scaffolds": [_scaffold(steps=[_step(n) for n in range(1, 5)])]})
    assert [s.stage_no for s in result.steps] == [1, 2, 3, 4]


def test_a_step_with_no_partial_content_is_allowed():
    """Some steps are purely a question."""
    result = _gen({"scaffolds": [_scaffold(
        steps=[_step(1, partial_content=""), _step(2), _step(3)])]})
    assert result.steps[0].partial_content is None


# ──────────────────────────────────────────────────────────────────────
# Routing to support that exists
# ──────────────────────────────────────────────────────────────────────

def test_a_route_to_a_real_hint_is_kept():
    result = _gen({"scaffolds": [_scaffold(
        steps=[_step(1, next_on_incorrect="Use HINT-T01-GENERAL-L1"),
               _step(2), _step(3)])]})
    assert result.steps[0].next_on_incorrect == "Use HINT-T01-GENERAL-L1"


def test_a_route_to_a_hint_that_does_not_exist_is_replaced():
    """Routing to a missing hint strands the student at the moment they
    needed help most."""
    result = _gen({"scaffolds": [_scaffold(
        steps=[_step(1, next_on_incorrect="Use HINT-T01-GHOST-L1"),
               _step(2), _step(3)])]})

    assert result.is_clean, "the scaffold is still usable"
    assert result.steps[0].next_on_incorrect == "Repeat this stage"
    assert any("HINT-T01-GHOST-L1" in i.message and "does not exist" in i.message
               for i in result.issues)


def test_a_route_to_a_missing_cue_is_replaced():
    result = _gen({"scaffolds": [_scaffold(
        steps=[_step(1, next_on_incorrect="Repeat this stage with VC-T01-NOPE"),
               _step(2), _step(3)])]})
    assert result.steps[0].next_on_incorrect == "Repeat this stage"


def test_a_route_described_in_words_is_left_alone():
    """Rule 6 allows it when nothing listed fits."""
    result = _gen({"scaffolds": [_scaffold(
        steps=[_step(1, next_on_incorrect="Go back to the worked example"),
               _step(2), _step(3)])]})
    assert result.steps[0].next_on_incorrect == "Go back to the worked example"


# ──────────────────────────────────────────────────────────────────────
# Refusing what cannot be used
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("count", [0, MIN_STEPS - 1, MAX_STEPS + 1])
def test_a_step_count_outside_the_range_is_dropped(count):
    result = _gen({"scaffolds": [_scaffold(steps=[_step(n) for n in range(count)])]})
    assert result.scaffolds == []
    assert any("the review asks for 3 to 5" in i.message for i in result.issues)


def test_a_scaffold_for_a_skill_with_no_guided_question_is_dropped():
    """It would never be shown."""
    result = _gen({"scaffolds": [_scaffold(skill="T01.M9")]},
                  skills=[_skill(), _skill("T01.M9")])
    assert result.scaffolds == []
    assert any("no Phase 2 question" in i.message for i in result.issues)


def test_a_second_scaffold_for_one_skill_is_dropped():
    result = _gen({"scaffolds": [_scaffold(), _scaffold(scaffold_name="Another")]})
    assert len(result.scaffolds) == 1
    assert any("already has a scaffold" in i.message for i in result.issues)


def test_a_missing_trigger_rule_is_dropped():
    result = _gen({"scaffolds": [_scaffold(trigger_rule="")]})
    assert result.scaffolds == []


def test_a_step_with_no_prompt_is_dropped_with_its_scaffold():
    """Half a walk-through is worse than none: the student stops mid-way."""
    result = _gen({"scaffolds": [_scaffold(
        steps=[_step(1), _step(2, prompt=""), _step(3)])]})
    assert result.scaffolds == []
    assert result.steps == []


def test_a_skill_left_without_a_scaffold_is_reported():
    result = _gen({"scaffolds": []})
    warning = next(i for i in result.issues if "below minimum" in i.message)
    assert "no walk-through when a student is stuck" in warning.message


def test_generating_with_nothing_to_scaffold_is_refused():
    with pytest.raises(ScaffoldError, match="nothing to scaffold"):
        generate_scaffolds([_skill()], {}, [], [], FakeLLMClient([{}]), "T01")


def test_an_api_failure_propagates():
    with pytest.raises(LLMError, match="fell over"):
        generate_scaffolds([_skill()], {SKILL: [_question()]}, [], [],
                           FakeLLMClient([LLMError("the api fell over")]), "T01")


# ──────────────────────────────────────────────────────────────────────
# Choosing what to scaffold
# ──────────────────────────────────────────────────────────────────────

def test_only_phase_two_questions_are_scaffolded():
    """PHASE_RULES sets scaffold_allowed False elsewhere: the diagnostic and
    independent phases are meant to run without support."""
    questions = [_question(1), _question(2), _question(3)]
    slots = {
        "Q-T01-001": Slot(P2, 1),
        "Q-T01-002": Slot(P3, 1),
        "Q-T01-003": Slot(Phase.PHASE_0_DIAGNOSTIC, 2),
    }
    skill_of = {q.question_id: SKILL for q in questions}

    grouped = guided_by_skill(questions, slots, skill_of)

    assert list(grouped) == [SKILL]
    assert [q.question_id for q in grouped[SKILL]] == ["Q-T01-001"]


def test_questions_are_grouped_by_the_skill_they_assess():
    questions = [_question(1), _question(2)]
    slots = {q.question_id: Slot(P2, 1) for q in questions}
    grouped = guided_by_skill(
        questions, slots,
        {"Q-T01-001": "T01.M1", "Q-T01-002": "T01.M4"})
    assert set(grouped) == {"T01.M1", "T01.M4"}


def test_a_question_with_no_slot_is_skipped():
    assert guided_by_skill([_question(1)], {}, {"Q-T01-001": SKILL}) == {}
