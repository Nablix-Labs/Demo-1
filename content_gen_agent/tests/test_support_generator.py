"""CG-017: hints, visual cues and parallel examples.

Her minimum per misconception: two hints (ATTENTION, CONCEPT_REMINDER, with
PARTIAL_STEP optional), one visual cue, one parallel example.

The joins are derived, so the tests that matter most are the ones checking
that derivation against the template's own data.

No network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_client import FakeLLMClient, LLMError      # noqa: E402
from models import (                                # noqa: E402
    EmbeddingStatus,
    HintType,
    MisconceptionRow,
    VisualCueReviewStatus,
)
from sources import SCHEMA_TEMPLATE                 # noqa: E402
from support_generator import (                     # noqa: E402
    CUE_SYSTEM_PROMPT,
    HINT_SYSTEM_PROMPT,
    LEVEL_FOR_HINT_TYPE,
    NEGATIVE_PROMPT,
    PARALLEL_SYSTEM_PROMPT,
    REQUIRED_HINT_TYPES,
    SupportError,
    generate_hints,
    generate_parallel_examples,
    generate_support,
    generate_visual_cues,
)

needs_template = pytest.mark.skipif(
    SCHEMA_TEMPLATE is None, reason="schema template not available",
)

MID = "MIS-T01-ADD-AS-MULTIPLY"


def _misconception(mid=MID, name="Fixed change confused with multiplication"):
    return MisconceptionRow(
        misconception_id=mid, name=name,
        description="Student treats adding a fixed amount as multiplying by it.",
        diagnosis_rule="Trigger after ERR-T01-ADD-AS-MULTIPLY.",
        active=True, version="1.0",
    )


def _hint(mid=MID, htype="ATTENTION", content="Look at what changes each step."):
    return {"misconception_id": mid, "hint_type": htype, "content": content}


def _both(mid=MID):
    return [_hint(mid, "ATTENTION"),
            _hint(mid, "CONCEPT_REMINDER", "Adding the same amount is not multiplying.")]


def _gen_hints(payload, misconceptions=None, **kw):
    return generate_hints(
        misconceptions or [_misconception()], FakeLLMClient([payload]), "T01", **kw)


# ──────────────────────────────────────────────────────────────────────
# The third hint level, which must stay rare
# ──────────────────────────────────────────────────────────────────────

def test_a_partial_step_hint_comes_from_the_separate_list():
    """The fix for 22 of 22 misconceptions getting one on 9 September.

    The prompt used to say "a PARTIAL_STEP hint is optional; add one only
    where a student would still be stuck". A permission written into prose is
    read as a default, so the third level now costs the model a separate act
    with a reason attached rather than one more row in a list it is already
    writing.
    """
    hints, _links, _issues = _gen_hints({
        "hints": _both(),
        "needs_partial_step": [{
            "misconception_id": MID,
            "content": "Start by writing the part that stays the same: + 4.",
            "why": "After the reminder the student still cannot begin.",
        }],
    })
    partial = [h for h in hints if h.hint_type.value == "PARTIAL_STEP"]
    assert len(partial) == 1
    assert partial[0].hint_level == 3
    assert "stays the same" in partial[0].content


def test_no_partial_step_list_means_no_third_hint():
    """The default path produces two. That is the point."""
    hints, _links, _issues = _gen_hints({"hints": _both()})
    assert {h.hint_type.value for h in hints} == {"ATTENTION", "CONCEPT_REMINDER"}


def test_the_prompt_forbids_a_partial_step_in_the_main_list():
    text = " ".join(HINT_SYSTEM_PROMPT.split())
    assert "Never put a PARTIAL_STEP hint in \"hints\"" in text
    assert "EXACTLY TWO hints for every misconception" in text


def test_the_prompt_states_how_often_the_approved_content_uses_it():
    """A proportion is checkable; "optional" is not."""
    text = " ".join(HINT_SYSTEM_PROMPT.split())
    assert "4 misconceptions out of 25" in text
    assert "\"It might help\" is not a reason" in text


def test_giving_nearly_every_misconception_a_third_hint_is_reported():
    """Reported, not enforced. Dropping the surplus would mean choosing which
    beliefs lose their third hint on no evidence."""
    misconceptions = [_misconception(f"MIS-T01-{i}", f"Belief {i}")
                      for i in range(4)]
    _hints, _links, issues = _gen_hints(
        {
            "hints": [h for m in misconceptions
                      for h in _both(m.misconception_id)],
            "needs_partial_step": [
                {"misconception_id": m.misconception_id,
                 "content": "Start it off.", "why": "stuck"}
                for m in misconceptions
            ],
        },
        misconceptions=misconceptions,
    )
    warning = next(i for i in issues if "PARTIAL_STEP hint" in i.message)
    assert not warning.is_error
    assert "4 of 4" in warning.message


def test_a_reasonable_share_of_third_hints_is_not_reported():
    misconceptions = [_misconception(f"MIS-T01-{i}", f"Belief {i}")
                      for i in range(5)]
    _hints, _links, issues = _gen_hints(
        {
            "hints": [h for m in misconceptions
                      for h in _both(m.misconception_id)],
            "needs_partial_step": [
                {"misconception_id": "MIS-T01-0", "content": "Start it off.",
                 "why": "stuck"},
            ],
        },
        misconceptions=misconceptions,
    )
    assert not [i for i in issues if "PARTIAL_STEP hint" in i.message]


def test_a_partial_step_for_an_unknown_misconception_is_still_refused():
    """The separate list is not a way round the checks."""
    _hints, _links, issues = _gen_hints({
        "hints": _both(),
        "needs_partial_step": [{"misconception_id": "MIS-T01-GHOST",
                                "content": "Start it off.", "why": "stuck"}],
    })
    assert any("does not exist" in i.message for i in issues)


# ──────────────────────────────────────────────────────────────────────
# The derivations
# ──────────────────────────────────────────────────────────────────────

def test_the_level_is_derived_from_the_type():
    """Exact in all 40 template rows. Asking for both would only create a way
    for them to disagree."""
    assert LEVEL_FOR_HINT_TYPE == {
        HintType.ATTENTION: 1,
        HintType.CONCEPT_REMINDER: 2,
        HintType.PARTIAL_STEP: 3,
    }


@needs_template
def test_the_level_derivation_matches_the_platform_data():
    from openpyxl import load_workbook
    wb = load_workbook(SCHEMA_TEMPLATE)
    ws = wb["hints"]
    header = [c.value for c in ws[1] if c.value is not None]
    rows = [dict(zip(header, r)) for r in ws.iter_rows(min_row=2, values_only=True)
            if any(v is not None for v in r)]

    for row in rows:
        expected = LEVEL_FOR_HINT_TYPE[HintType(row["hint_type"])]
        assert row["hint_level"] == expected, row


@needs_template
def test_the_join_order_is_the_hint_level_in_the_platform_data():
    """Zero of the template's 40 join rows differ, which is why the join is
    built rather than asked for."""
    from openpyxl import load_workbook
    wb = load_workbook(SCHEMA_TEMPLATE)

    def rows(sheet):
        ws = wb[sheet]
        header = [c.value for c in ws[1] if c.value is not None]
        return [dict(zip(header, r)) for r in ws.iter_rows(min_row=2, values_only=True)
                if any(v is not None for v in r)]

    levels = {r["hint_id"]: r["hint_level"] for r in rows("hints")}
    mismatched = [r for r in rows("misconception_hints")
                  if r["hint_id"] in levels
                  and r["sequence_order"] != levels[r["hint_id"]]]
    assert mismatched == []


def test_the_hint_join_is_built_with_the_level_as_its_order():
    hints, links, _ = _gen_hints({"hints": _both()})
    by_id = {h.hint_id: h for h in hints}
    assert all(link.sequence_order == by_id[link.hint_id].hint_level
               for link in links)


# ──────────────────────────────────────────────────────────────────────
# Hints
# ──────────────────────────────────────────────────────────────────────

def test_the_prompt_explains_that_the_levels_escalate():
    """Three phrasings of one hint gives the tutor nothing to escalate."""
    text = " ".join(HINT_SYSTEM_PROMPT.split())
    assert "THE THREE LEVELS GIVE AWAY DIFFERENT AMOUNTS" in text
    assert "you have written one hint three times" in text


def test_the_prompt_forbids_a_hint_that_answers_the_question():
    text = " ".join(HINT_SYSTEM_PROMPT.split())
    assert "A hint that answers the question is not a hint" in text


def test_the_prompt_says_hints_attach_to_the_belief_not_one_question():
    """They are shown on any question that triggers the misconception."""
    text = " ".join(HINT_SYSTEM_PROMPT.split())
    assert "A hint addresses the BELIEF, not one question" in text


def test_the_prompt_addresses_the_student():
    assert "Write to the student, not about them" in " ".join(HINT_SYSTEM_PROMPT.split())


def test_two_hints_produce_two_rows_and_two_links():
    hints, links, issues = _gen_hints({"hints": _both()})
    assert len(hints) == 2 and len(links) == 2
    assert {h.hint_type for h in hints} == set(REQUIRED_HINT_TYPES)
    assert not [i for i in issues if i.is_error]


def test_the_hint_id_carries_the_level():
    hints, _, _ = _gen_hints({"hints": _both()})
    assert hints[0].hint_id.endswith("-L1")
    assert hints[1].hint_id.endswith("-L2")


def test_a_missing_required_hint_type_is_reported():
    """Her minimum is two. One is below it."""
    _, _, issues = _gen_hints({"hints": [_hint(htype="ATTENTION")]})
    warning = next(i for i in issues if "below minimum" in i.message)
    assert "CONCEPT_REMINDER" in warning.message
    assert "escalate through" in warning.message


def test_partial_step_is_optional_and_accepted():
    """Her words: the third one is optional."""
    payload = {"hints": _both() + [_hint(htype="PARTIAL_STEP",
                                         content="Start with the part that stays the same.")]}
    hints, _, issues = _gen_hints(payload)
    assert len(hints) == 3
    assert not [i for i in issues if "below minimum" in i.message]


def test_two_hints_of_the_same_type_keep_one():
    payload = {"hints": _both() + [_hint(htype="ATTENTION", content="Another one.")]}
    hints, _, issues = _gen_hints(payload)
    assert len(hints) == 2
    assert any("already has a ATTENTION hint" in i.message for i in issues)


def test_an_unknown_misconception_is_dropped():
    _, _, issues = _gen_hints({"hints": [_hint(mid="MIS-T01-GHOST")]})
    assert any("does not exist" in i.message for i in issues)


def test_an_invented_hint_type_is_dropped():
    _, _, issues = _gen_hints({"hints": [_hint(htype="ENCOURAGEMENT")]})
    assert any("hint_type" in i.message and "dropped" in i.message for i in issues)


def test_empty_content_is_dropped():
    _, _, issues = _gen_hints({"hints": [_hint(content="   ")]})
    assert any("content is empty" in i.message for i in issues)


def test_hints_without_misconceptions_is_refused():
    with pytest.raises(SupportError, match="no misconceptions"):
        generate_hints([], FakeLLMClient([{}]), "T01")


# ──────────────────────────────────────────────────────────────────────
# Visual cues
# ──────────────────────────────────────────────────────────────────────

def _cue(mid=MID, **kw):
    base = {
        "misconception_id": mid,
        "cue_name": "Repeated Adding Is Not Multiplying",
        "cue_purpose": "Show that a fixed change builds a total by steps.",
        "image_generation_prompt": "Premium 2D educational infographic, 16:9 landscape. Two panels...",
        "tutor_explanation_template": "Each step adds the same amount.",
        "retrieval_text": "Use when a student turns a fixed change into multiplication.",
        "retrieval_keywords": "repeated addition, fixed change",
    }
    base.update(kw)
    return base


def _gen_cues(payload, misconceptions=None, **kw):
    return generate_visual_cues(
        misconceptions or [_misconception()], FakeLLMClient([payload]), "T01", **kw)


def test_the_cue_prompt_bans_text_in_the_image():
    """The image model renders text badly and it cannot be translated."""
    text = " ".join(CUE_SYSTEM_PROMPT.split())
    assert "NO TEXT, LETTERS, NUMBERS OR SYMBOLS IN THE IMAGE" in text
    assert "it is not a picture idea" in text


def test_the_cue_prompt_asks_when_to_show_it_not_what_it_shows():
    text = " ".join(CUE_SYSTEM_PROMPT.split())
    assert 'retrieval_text says WHEN to show this cue' in text
    assert "describe the student's mistake, not the picture" in text


def test_a_cue_is_built_with_no_asset_and_pending_embedding():
    """The picture does not exist yet. Left empty rather than invented."""
    cues, links, issues = _gen_cues({"cues": [_cue()]})
    assert len(cues) == 1 and len(links) == 1
    assert cues[0].asset_url is None
    assert cues[0].embedding_status is EmbeddingStatus.PENDING
    assert cues[0].review_status is VisualCueReviewStatus.PENDING_REVIEW
    assert not [i for i in issues if i.is_error]


def test_the_negative_prompt_is_house_style_not_asked_for():
    cues, _, _ = _gen_cues({"cues": [_cue()]})
    assert cues[0].negative_prompt == NEGATIVE_PROMPT
    assert "No generated text" in cues[0].negative_prompt


def test_a_cue_missing_a_field_is_dropped():
    _, _, issues = _gen_cues({"cues": [_cue(retrieval_text="")]})
    assert any("missing retrieval_text" in i.message for i in issues)


def test_a_misconception_with_no_cue_is_reported():
    _, _, issues = _gen_cues({"cues": []})
    assert any("below minimum: no visual cue" in i.message for i in issues)


def test_a_second_cue_for_the_same_misconception_is_dropped():
    _, _, issues = _gen_cues({"cues": [_cue(), _cue(cue_name="Another")]})
    assert any("already has a cue" in i.message for i in issues)


# ──────────────────────────────────────────────────────────────────────
# Parallel examples
# ──────────────────────────────────────────────────────────────────────

def _example(mid=MID, **kw):
    base = {
        "misconception_id": mid,
        "problem_statement": "A robot starts at any position r and moves forward 2 spaces.",
        "worked_steps": ["changing value r", "fixed action +2", "rule r + 2"],
        "final_answer": "r + 2",
    }
    base.update(kw)
    return base


def _gen_examples(payload, misconceptions=None, **kw):
    return generate_parallel_examples(
        misconceptions or [_misconception()], FakeLLMClient([payload]),
        "T01", "ALG-ORI-01", **kw)


def test_the_parallel_prompt_asks_for_a_new_context_not_a_harder_question():
    """The student has just failed. Repeating teaches nothing; escalating
    teaches less."""
    text = " ".join(PARALLEL_SYSTEM_PROMPT.split())
    assert "SAME IDEA IN A DIFFERENT SITUATION" in text
    assert "Change the CONTEXT, not the difficulty" in text


def test_the_parallel_prompt_suggests_a_different_letter():
    text = " ".join(PARALLEL_SYSTEM_PROMPT.split())
    assert "benefits from seeing the same idea with r" in text


def test_an_example_is_built_with_pipe_delimited_steps():
    rows, issues = _gen_examples({"examples": [_example()]})
    assert len(rows) == 1
    assert rows[0].worked_steps == "changing value r | fixed action +2 | rule r + 2"
    assert rows[0].topic_id == "ALG-ORI-01"
    assert not [i for i in issues if i.is_error]


def test_an_example_with_one_step_is_dropped():
    _, issues = _gen_examples({"examples": [_example(worked_steps=["just this"])]})
    assert any("shows no working" in i.message for i in issues)


def test_a_misconception_with_no_example_is_reported():
    _, issues = _gen_examples({"examples": []})
    assert any("below minimum: no parallel example" in i.message for i in issues)


def test_an_example_with_no_answer_is_dropped():
    _, issues = _gen_examples({"examples": [_example(final_answer="")]})
    assert any("final_answer is empty" in i.message for i in issues)


# ──────────────────────────────────────────────────────────────────────
# All five tables together
# ──────────────────────────────────────────────────────────────────────

def test_three_calls_produce_five_tables():
    client = FakeLLMClient([
        {"hints": _both()},
        {"cues": [_cue()]},
        {"examples": [_example()]},
    ])
    result = generate_support([_misconception()], client, "T01", "ALG-ORI-01")

    assert result.is_clean
    assert len(result.hints) == 2
    assert len(result.hint_links) == 2
    assert len(result.visual_cues) == 1
    assert len(result.cue_links) == 1
    assert len(result.parallel_examples) == 1


def test_every_link_points_at_something_that_exists():
    client = FakeLLMClient([
        {"hints": _both()}, {"cues": [_cue()]}, {"examples": [_example()]},
    ])
    result = generate_support([_misconception()], client, "T01", "ALG-ORI-01")

    assert {l.hint_id for l in result.hint_links} == {h.hint_id for h in result.hints}
    assert {l.visual_cue_id for l in result.cue_links} == \
        {c.visual_cue_id for c in result.visual_cues}


def test_an_api_failure_propagates():
    with pytest.raises(LLMError, match="fell over"):
        generate_hints([_misconception()],
                       FakeLLMClient([LLMError("the api fell over")]), "T01")
