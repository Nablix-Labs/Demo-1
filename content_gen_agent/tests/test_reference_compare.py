"""CG-023 tests.

The trap this module has to avoid is specific and quiet. The approved
reference names its sheets in TitleCase and the platform export in
snake_case. A reader that knows only one convention returns an empty dict for
the other, every measure comes back "0 versus 0", and a comparison of nothing
against nothing reports as agreement. So the first tests here are about
reading, not comparing.

The second thing worth testing is the classification. A decision recorded
under a name that is not a real measure is a decision that never applies, and
the divergence it was meant to explain reports as unexplained forever. Nothing
would fail; the report would just be wrong.

No network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import reference_compare as rc                        # noqa: E402
from sources import REFERENCE_WORKBOOK                # noqa: E402

needs_reference = pytest.mark.skipif(
    REFERENCE_WORKBOOK is None, reason="reference workbook not available",
)


def tables(questions=6, skills=2, mappings_per_question=1, **overrides):
    data = {
        "Topics": [{"topic_id": "ALG-ORI-01"}],
        "Micro_Skills": [{"micro_skill_id": f"T01.M{i}"} for i in range(1, skills + 1)],
        "Questions": [
            {"question_id": f"Q-{i:03d}", "question_type": "SINGLE_CHOICE",
             "difficulty": 1 + i % 3}
            for i in range(questions)
        ],
        "Question_Usage": [
            {"question_id": f"Q-{i:03d}", "phase": "PHASE_2_GUIDED_LEARNING",
             "support_allowed": "ADAPTIVE_SUPPORT"}
            for i in range(questions)
        ],
        "Question_MicroSkills": [
            {"question_id": f"Q-{i:03d}", "micro_skill_id": "T01.M1",
             "is_primary": n == 0}
            for i in range(questions) for n in range(mappings_per_question)
        ],
        "Topic_Scope": [
            {"topic_id": "ALG-ORI-01", "scope_type": "INCLUDED"},
            {"topic_id": "ALG-ORI-01", "scope_type": "EXCLUDED"},
        ],
        "Worked_Examples": [{"worked_example_id": "WE-01"}],
        "Worked_Example_Steps": [{"worked_example_id": "WE-01", "step_no": 1}],
        "Misconceptions": [{"misconception_id": "MIS-01"}],
        "Misconception_Hints": [{"misconception_id": "MIS-01", "hint_id": "H-1"}],
        "Hints": [{"hint_id": "H-1", "hint_level": 1}],
        "Scaffolds": [{"scaffold_id": "SCF-01"}],
        "Scaffold_Steps": [{"scaffold_id": "SCF-01", "stage_no": 1}],
        "Question_Error_Map": [{"question_id": "Q-000"}],
        "Error_Types": [{"error_code": "ERR-01"}],
    }
    data.update(overrides)
    return data


def status_of(comparison, name):
    return next(m.status for m in comparison.measures if m.name == name)


# ──────────────────────────────────────────────────────────────────────
# Reading, where the quiet failure lives
# ──────────────────────────────────────────────────────────────────────

@needs_reference
def test_the_titlecase_reference_is_read():
    """The reference sheets are named Micro_Skills, not micro_skills. A reader
    that only knew the export convention would return nothing here."""
    found = rc.read_any(REFERENCE_WORKBOOK)
    assert found.get("Questions"), "read nothing from the reference"
    assert len(found["Questions"]) == 54
    assert len(found["Micro_Skills"]) == 22


def test_the_snakecase_export_is_read(tmp_path):
    from workbook_writer import write_workbook

    destination = tmp_path / "export.xlsx"
    write_workbook({}, destination)
    found = rc.read_any(destination)
    assert "Question_MicroSkills" in found


@needs_reference
def test_comparing_the_reference_with_itself_finds_nothing_unexplained():
    """The property that catches a reader returning nothing: if read_any were
    broken, both sides would be empty, every measure would be None versus
    None, and this would still pass. So it also asserts there was something
    to compare."""
    comparison = rc.compare(REFERENCE_WORKBOOK, REFERENCE_WORKBOOK)
    assert not comparison.unexplained()
    assert not comparison.intentional()
    matched = [m for m in comparison.measures if m.status == rc.MATCH]
    assert len(matched) == len(comparison.measures)
    ratio = next(m for m in comparison.measures
                 if m.name == "questions per micro-skill")
    assert ratio.reference == 2.45, "nothing was actually measured"


def test_two_empty_workbooks_do_not_report_as_agreeing_on_content():
    """Nothing compared to nothing is not a match worth trusting."""
    comparison = rc.compare_tables({}, {})
    ratio = next(m for m in comparison.measures
                 if m.name == "questions per micro-skill")
    assert ratio.reference is None and ratio.generated is None
    assert "no rows to measure" in ratio.detail


# ──────────────────────────────────────────────────────────────────────
# Classification
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [n for n, _measure, _kind in rc.MEASURES])
def test_every_measure_reaches_the_report(name):
    """Deleting a measure should break something.

    Written after checking: eight of the seventeen could be removed and every
    test still passed, because most are only asserted about indirectly. A
    measure nothing would miss is a measure that can quietly stop being taken.
    """
    comparison = rc.compare_tables(tables(), tables())
    assert name in {m.name for m in comparison.measures}


@needs_reference
@pytest.mark.parametrize("name", [n for n, _measure, _kind in rc.MEASURES])
def test_every_measure_actually_measures_something(name):
    """A measure returning None on real approved content is not measuring; it
    is reading a column that is not there, and it would report as a match
    against anything."""
    comparison = rc.compare(REFERENCE_WORKBOOK, REFERENCE_WORKBOOK)
    measure = next(m for m in comparison.measures if m.name == name)
    assert measure.reference is not None, f"{name} read nothing"
    assert measure.reference != {} and measure.reference != []


def test_a_per_topic_average_ignores_topics_the_table_does_not_cover():
    """The bug this caught in the run of 9 September.

    The reference has no Topic_Scope rows for topic 1 at all. Dividing 27 rows
    by 3 topics gave 9 per topic when it is 13.5 across the two it covers, and
    our scope reported 41% adrift when for those two topics it matches
    exactly. A comparison that manufactures a difference out of a gap in the
    reference sends someone to fix content that was already right.
    """
    reference = tables(Topics=[{"topic_id": "T1"}, {"topic_id": "T2"},
                               {"topic_id": "T3"}])
    reference["Topic_Scope"] = [{"topic_id": "T2", "scope_type": "INCLUDED"},
                                {"topic_id": "T2", "scope_type": "EXCLUDED"},
                                {"topic_id": "T3", "scope_type": "INCLUDED"},
                                {"topic_id": "T3", "scope_type": "EXCLUDED"}]
    generated = tables(Topics=reference["Topics"])
    generated["Topic_Scope"] = reference["Topic_Scope"] + [
        {"topic_id": "T1", "scope_type": "INCLUDED"},
        {"topic_id": "T1", "scope_type": "EXCLUDED"},
    ]
    assert rc.m_scope_items_per_topic(reference) == 2.0
    assert rc.m_scope_items_per_topic(generated) == 2.0

    comparison = rc.compare_tables(reference, generated)
    assert status_of(comparison, "scope items per topic") == rc.MATCH


def test_a_per_topic_average_falls_back_when_there_is_no_topic_column():
    """Error_Types carries no topic_id. Falling back to the workbook's topic
    count is right there, because both sides cover the same topics."""
    data = tables(Error_Types=[{"error_code": f"E{i}"} for i in range(6)])
    assert rc.m_errors_per_topic(data) == 6.0


def test_every_recorded_decision_names_a_real_measure():
    """A decision under a name no measure produces is a decision that never
    applies, and nothing would fail to tell you."""
    names = {name for name, _measure, _kind in rc.MEASURES}
    for recorded in rc.DECIDED:
        assert recorded in names, f"{recorded!r} is not a measure"


def test_every_decision_says_where_it_was_decided():
    for name, decision in rc.DECIDED.items():
        assert decision.reason.strip(), f"{name} has no reason"
        assert decision.source.strip(), f"{name} does not say where"


def test_a_decided_difference_is_intentional_not_a_divergence():
    comparison = rc.compare_tables(tables(questions=5, skills=2),
                                   tables(questions=14, skills=2))
    assert status_of(comparison, "questions per micro-skill") == rc.INTENTIONAL


def test_an_undecided_difference_is_a_divergence():
    comparison = rc.compare_tables(
        tables(), tables(Scaffold_Steps=[{"scaffold_id": "SCF-01"}] * 20))
    assert status_of(comparison, "steps per scaffold") == rc.DIVERGES


def test_unexplained_returns_only_the_divergences():
    comparison = rc.compare_tables(tables(questions=5),
                                   tables(questions=14, Scaffold_Steps=[{}] * 20))
    assert {m.status for m in comparison.unexplained()} == {rc.DIVERGES}


def test_a_difference_inside_tolerance_is_a_match():
    """Generated content is not deterministic. Demanding equality of an
    average would report noise as news."""
    comparison = rc.compare_tables(tables(questions=10, skills=2),
                                   tables(questions=11, skills=2))
    assert status_of(comparison, "questions per micro-skill") == rc.MATCH


def test_the_tolerance_can_be_tightened():
    comparison = rc.compare_tables(tables(questions=10, skills=2),
                                   tables(questions=11, skills=2),
                                   tolerance=0.01)
    assert status_of(comparison, "questions per micro-skill") == rc.INTENTIONAL


# ──────────────────────────────────────────────────────────────────────
# Schema, which has no tolerance
# ──────────────────────────────────────────────────────────────────────

def test_a_missing_sheet_is_a_divergence():
    generated = tables()
    del generated["Questions"]
    comparison = rc.compare_tables(tables(), generated)
    measure = next(m for m in comparison.measures
                   if m.name == "sheets present in the reference")
    assert measure.status == rc.DIVERGES
    assert "Questions" in measure.detail


def test_column_order_out_of_schema_order_is_a_divergence():
    """The platform reads by name and position. A workbook that gets this
    wrong does not import at all, whatever its content is like."""
    generated = tables()
    generated["Questions"] = [{"difficulty": 1, "question_id": "Q-000"}]
    comparison = rc.compare_tables(tables(), generated)
    assert status_of(comparison, "column order matches the schema") == rc.DIVERGES


# ──────────────────────────────────────────────────────────────────────
# Comparing sets of keys, after a precedence bug in the first version
# ──────────────────────────────────────────────────────────────────────

def test_a_phase_support_pairing_we_do_not_produce_is_reported():
    generated = tables(Question_Usage=[
        {"question_id": "Q-000", "phase": "PHASE_2_GUIDED_LEARNING",
         "support_allowed": "NO_SUPPORT_DURING_ATTEMPT"},
    ])
    comparison = rc.compare_tables(tables(), generated)
    measure = next(m for m in comparison.measures
                   if m.name == "support allowed by phase")
    assert measure.status == rc.DIVERGES
    assert "not present" in measure.detail and "only ours" in measure.detail


def test_identical_pairings_report_no_detail():
    comparison = rc.compare_tables(tables(), tables())
    measure = next(m for m in comparison.measures
                   if m.name == "support allowed by phase")
    assert measure.status == rc.MATCH
    assert measure.detail == ""


# ──────────────────────────────────────────────────────────────────────
# The finding this module exists to produce
# ──────────────────────────────────────────────────────────────────────

@needs_reference
def test_the_worked_example_shape_difference_is_reported():
    """The useful output of CG-023, pinned so it cannot go quiet.

    The reference writes one worked example PER STEP -- 22 examples, 22 steps,
    exactly one each. We write one per topic with several steps. Same content,
    different shape, and it will matter when the platform imports it. Nobody
    has decided this, so it must report as unexplained rather than intentional.
    """
    reference = rc.read_any(REFERENCE_WORKBOOK)
    assert len(reference["Worked_Examples"]) == len(reference["Worked_Example_Steps"])

    generated = tables(
        Worked_Examples=[{"worked_example_id": "WE-01"}],
        Worked_Example_Steps=[{"worked_example_id": "WE-01", "step_no": i}
                              for i in range(1, 9)],
    )
    comparison = rc.compare_tables(reference, generated)
    assert status_of(comparison, "steps per worked example") == rc.DIVERGES


@needs_reference
def test_the_review_decisions_never_read_as_failures():
    """Three of them are large disagreements with approved content, made on
    purpose. Reported as failures, the first reader concludes the generator is
    broken and the second stops reading."""
    reference = rc.read_any(REFERENCE_WORKBOOK)
    generated = tables(questions=14, skills=2, mappings_per_question=1)
    comparison = rc.compare_tables(reference, generated)
    for name in ("questions per micro-skill",
                 "micro-skills credited per question",
                 "share of mappings that are primary"):
        assert status_of(comparison, name) == rc.INTENTIONAL


# ──────────────────────────────────────────────────────────────────────
# The report
# ──────────────────────────────────────────────────────────────────────

def test_the_summary_leads_with_what_to_look_at():
    comparison = rc.compare_tables(
        tables(questions=5), tables(questions=14, Scaffold_Steps=[{}] * 20))
    text = rc.summarise(comparison)
    assert text.index("UNEXPLAINED") < text.index("INTENTIONAL")


def test_the_summary_gives_the_reason_and_where_it_was_decided():
    comparison = rc.compare_tables(tables(questions=5), tables(questions=14))
    text = rc.summarise(comparison)
    assert "decided in:" in text
    assert "coverage_plan" in text


def test_the_counts_add_up_to_every_measure():
    comparison = rc.compare_tables(tables(), tables())
    assert sum(comparison.by_status().values()) == len(comparison.measures)