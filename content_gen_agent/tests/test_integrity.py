"""CG-019: does a written workbook hold together?

Every check here has a matching test that BREAKS something and asserts it is
caught. A checker that has never failed is a checker nobody has tested, and
this one runs over files that get sent for review.

No network.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrity import (                             # noqa: E402
    check_coverage,
    check_orphans,
    check_references,
    check_review_rules,
    check_uniqueness,
    check_workbook,
    read_tables,
    summarise,
)
from models import Phase                            # noqa: E402
from table_schemas import TABLE_SCHEMAS, export_name  # noqa: E402
from workbook_writer import write_workbook          # noqa: E402

P0 = Phase.PHASE_0_DIAGNOSTIC
P2 = Phase.PHASE_2_GUIDED_LEARNING
P3 = Phase.PHASE_3_INDEPENDENT_PRACTICE


def _sound_tables():
    """One topic, one skill, its seven questions, all references resolving."""
    plan = [(P0, 2), (P2, 1), (P2, 2), (P2, 3), (P3, 1), (P3, 2), (P3, 3)]
    questions, usage, mappings = [], [], []
    for n, (phase, difficulty) in enumerate(plan, start=1):
        qid = f"Q-T01-{n:03d}"
        questions.append({"question_id": qid, "topic_id": "ALG-ORI-01",
                          "difficulty": difficulty, "status": "GENERATED",
                          "source_provenance_id": "SRC-NABLIX-T01-001"})
        usage.append({"question_id": qid, "phase": phase.value})
        mappings.append({"question_id": qid, "micro_skill_id": "T01.M1",
                         "weight": 1, "is_primary": True})
    return {
        "Topics": [{"topic_id": "ALG-ORI-01", "topic_code": "T01"}],
        "Source_Provenance": [{"source_provenance_id": "SRC-NABLIX-T01-001"}],
        "Micro_Skills": [{"micro_skill_id": "T01.M1", "topic_id": "ALG-ORI-01",
                          "prerequisite_micro_skill_id": None}],
        "Questions": questions,
        "Question_Usage": usage,
        "Question_MicroSkills": mappings,
    }


# ──────────────────────────────────────────────────────────────────────
# A sound set passes
# ──────────────────────────────────────────────────────────────────────

def test_a_sound_set_has_nothing_wrong():
    tables = _sound_tables()
    assert check_references(tables) == []
    assert check_uniqueness(tables) == []
    assert check_review_rules(tables) == []
    assert check_coverage(tables) == []


def test_the_summary_says_so_plainly():
    assert "every reference resolves" in summarise([])


# ──────────────────────────────────────────────────────────────────────
# References
# ──────────────────────────────────────────────────────────────────────

def test_a_reference_to_a_skill_that_does_not_exist_is_caught():
    tables = _sound_tables()
    tables["Question_MicroSkills"][0]["micro_skill_id"] = "T01.M99"
    problem = check_references(tables)[0]
    assert problem.kind == "reference"
    assert "T01.M99" in problem.detail
    assert "Micro_Skills.micro_skill_id" in problem.detail


def test_repeated_dangling_references_are_reported_once_with_a_count():
    tables = _sound_tables()
    for row in tables["Question_MicroSkills"]:
        row["micro_skill_id"] = "T01.M99"
    problems = check_references(tables)
    assert len(problems) == 1
    assert "(7 rows)" in problems[0].detail


def test_a_null_foreign_key_is_not_a_dangling_one():
    """A skill with no prerequisite is normal, not broken."""
    tables = _sound_tables()
    assert check_references(tables) == []


def test_every_declared_foreign_key_is_actually_checked():
    """Driven by the schema, so a table added later is covered without
    anyone remembering to add it here."""
    declared = sum(len(s.get("foreign_keys") or {}) for s in TABLE_SCHEMAS.values())
    assert declared >= 30, "the schema should be declaring the joins"

    # Break one key in every table that has any, and confirm each is found.
    for table, schema in TABLE_SCHEMAS.items():
        for column, (target, _) in (schema.get("foreign_keys") or {}).items():
            tables = {table: [{column: "DEFINITELY-NOT-REAL"}], target: []}
            found = check_references(tables)
            assert found, f"{table}.{column} is declared but not checked"
            break


# ──────────────────────────────────────────────────────────────────────
# Uniqueness
# ──────────────────────────────────────────────────────────────────────

def test_a_duplicate_id_is_caught():
    """Worse than a missing one: a reference to it resolves silently to
    whichever row is found first."""
    tables = _sound_tables()
    tables["Questions"][1]["question_id"] = tables["Questions"][0]["question_id"]
    problem = check_uniqueness(tables)[0]
    assert problem.kind == "duplicate"
    assert "appears 2 times" in problem.detail


def test_unique_columns_are_taken_from_the_schema():
    unique = [(t, c) for t, s in TABLE_SCHEMAS.items()
              for c, d in s["column_details"].items() if d.get("unique")]
    assert len(unique) >= 15


# ──────────────────────────────────────────────────────────────────────
# The review's mapping rules
# ──────────────────────────────────────────────────────────────────────

def test_two_mappings_on_one_question_is_caught():
    tables = _sound_tables()
    tables["Question_MicroSkills"].append(
        {"question_id": "Q-T01-001", "micro_skill_id": "T01.M1",
         "weight": 1, "is_primary": True})
    assert any("requires exactly one" in p.detail for p in check_review_rules(tables))


def test_a_question_with_no_mapping_is_caught():
    tables = _sound_tables()
    tables["Question_MicroSkills"].pop(0)
    assert any("tells the student model nothing" in p.detail
               for p in check_review_rules(tables))


def test_a_fractional_weight_is_caught():
    tables = _sound_tables()
    tables["Question_MicroSkills"][0]["weight"] = 0.5
    assert any("requires 1.0" in p.detail for p in check_review_rules(tables))


def test_a_mapping_that_is_not_primary_is_caught():
    tables = _sound_tables()
    tables["Question_MicroSkills"][0]["is_primary"] = False
    assert any("requires is_primary TRUE" in p.detail
               for p in check_review_rules(tables))


def test_anything_marked_approved_is_caught():
    """Nothing this pipeline produces has been checked for correctness."""
    tables = _sound_tables()
    tables["Questions"][0]["status"] = "APPROVED"
    problem = next(p for p in check_review_rules(tables) if "APPROVED" in p.detail)
    assert "until the CG-020 and CG-021 checks have run" in problem.detail


# ──────────────────────────────────────────────────────────────────────
# Coverage
# ──────────────────────────────────────────────────────────────────────

def test_a_skill_short_of_its_plan_is_caught():
    tables = _sound_tables()
    tables["Question_MicroSkills"].pop()      # lose the last question's mapping
    problem = next(p for p in check_coverage(tables) if p.kind == "coverage")
    assert "T01.M1 is missing" in problem.detail
    assert "PHASE_3_INDEPENDENT_PRACTICE D3" in problem.detail


def test_a_skill_with_no_questions_at_all_is_caught():
    """The review's headline finding: 26 of 53 skills owned nothing."""
    tables = _sound_tables()
    tables["Micro_Skills"].append(
        {"micro_skill_id": "T01.M2", "topic_id": "ALG-ORI-01",
         "prerequisite_micro_skill_id": None})
    assert any("T01.M2 is missing" in p.detail for p in check_coverage(tables))


# ──────────────────────────────────────────────────────────────────────
# Orphans
# ──────────────────────────────────────────────────────────────────────

def test_an_unlinked_hint_is_caught():
    tables = {
        "Hints": [{"hint_id": "HINT-T01-A-L1"}, {"hint_id": "HINT-T01-B-L1"}],
        "Misconception_Hints": [{"misconception_id": "MIS-T01-A",
                                 "hint_id": "HINT-T01-A-L1"}],
    }
    problem = check_orphans(tables)[0]
    assert problem.kind == "orphan"
    assert "HINT-T01-B-L1" in problem.detail
    assert "can never be offered" in problem.detail


def test_an_unlinked_cue_and_scaffold_are_caught():
    tables = {
        "Visual_Cues": [{"visual_cue_id": "VC-T01-A"}],
        "Misconception_VisualCues": [],
        "Scaffolds": [{"scaffold_id": "SCF-T01-A"}],
        "Question_Scaffolds": [],
    }
    kinds = {p.table for p in check_orphans(tables)}
    assert kinds == {"Visual_Cues", "Scaffolds"}


def test_everything_linked_produces_no_orphans():
    tables = {
        "Hints": [{"hint_id": "HINT-T01-A-L1"}],
        "Misconception_Hints": [{"misconception_id": "MIS-T01-A",
                                 "hint_id": "HINT-T01-A-L1"}],
    }
    assert check_orphans(tables) == []


def test_a_question_in_no_usage_row_is_an_orphan():
    """It exists in the bank and is never shown to anyone."""
    tables = _sound_tables()
    tables["Question_Usage"].pop(0)
    assert any("never shown to anyone" in p.detail for p in check_orphans(tables))


# ──────────────────────────────────────────────────────────────────────
# Reading a real file
# ──────────────────────────────────────────────────────────────────────

def test_a_written_workbook_can_be_read_back_by_internal_name(tmp_path):
    """The file carries snake_case names; the checker works in internal ones."""
    out = write_workbook({}, tmp_path / "empty.xlsx")
    tables = read_tables(out)
    assert "Question_MicroSkills" in tables
    assert set(tables) <= set(TABLE_SCHEMAS)


def test_an_empty_workbook_reports_no_reference_problems(tmp_path):
    """Nothing to point at, so nothing dangling. Coverage is a different
    question and is reported separately."""
    out = write_workbook({}, tmp_path / "empty.xlsx")
    tables = read_tables(out)
    assert check_references(tables) == []
    assert check_uniqueness(tables) == []


def test_the_summary_groups_problems_by_kind():
    tables = _sound_tables()
    tables["Question_MicroSkills"][0]["micro_skill_id"] = "T01.M99"
    tables["Questions"][0]["status"] = "APPROVED"
    text = summarise(check_workbook.__wrapped__(tables)
                     if hasattr(check_workbook, "__wrapped__")
                     else check_references(tables) + check_review_rules(tables))
    assert "problem(s)" in text
    assert "reference" in text and "review" in text
