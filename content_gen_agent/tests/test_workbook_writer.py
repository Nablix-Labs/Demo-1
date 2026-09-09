"""CG-022 tests, plus an end-to-end pipeline run.

The exit condition is "generated workbook has same sheet names and column
order as reference", which is checked directly against the real workbook.

The last test is the more valuable one: it drives the whole pipeline with a
scripted model and asserts a workbook comes out. That is the first test in the
project that exercises every generator together, and it needs no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import (                                 # noqa: E402
    KSStage,
    QuestionMicroSkillRow,
    QuestionRow,
    QuestionStatus,
    QuestionType,
    TopicRow,
    TopicStatus,
)
from sources import (                               # noqa: E402
    REFERENCE_WORKBOOK,
    SCHEMA_TEMPLATE,
    find_topic_documents,
)
from table_schemas import TABLE_SCHEMAS              # noqa: E402
from workbook_writer import (                        # noqa: E402
    WorkbookWriteError,
    row_counts,
    serialise_row,
    summarise,
    verify_written,
    write_workbook,
)

TOPIC_DOCS = find_topic_documents()
needs_reference = pytest.mark.skipif(
    REFERENCE_WORKBOOK is None, reason="reference workbook not available",
)
needs_template = pytest.mark.skipif(
    SCHEMA_TEMPLATE is None, reason="schema template not available",
)


def _topic():
    return TopicRow(
        topic_id="ALG-ORI-01", topic_code="T01", topic_title="What Is Algebra?",
        ks_stage=KSStage.KS3, sequence_no=1,
        learning_goal="Understand that a letter can represent a changing number.",
        core_message="A letter can represent a changing quantity.",
        status=TopicStatus.ACTIVE, version="1.0",
        created_at="2026-08-31", updated_at="2026-08-31",
    )


def _question(i=1):
    return QuestionRow(
        question_id=f"Q-T01-{i:03d}", topic_id="ALG-ORI-01",
        question_text="Write the general rule.",
        question_type=QuestionType.SHORT_RESPONSE, difficulty=1,
        answer_spec_id=f"ANS-T01-{i:03d}", item_family_id="FAM-T01-GENERAL-ADD",
        source_provenance_id="SRC-NABLIX-T01-001",
        status=QuestionStatus.APPROVED, version="1.0",
    )


# ──────────────────────────────────────────────────────────────────────
# Serialising one row
# ──────────────────────────────────────────────────────────────────────

def test_cells_follow_the_schema_order_not_the_model_order():
    """A model declares fields readably; the sheet has its own order."""
    cells = serialise_row(_question(), "Questions")
    assert cells == [
        "Q-T01-001", "ALG-ORI-01", "Write the general rule.", "SHORT_RESPONSE",
        1, "ANS-T01-001", "FAM-T01-GENERAL-ADD", "SRC-NABLIX-T01-001",
        "APPROVED", "1.0",
    ]
    assert len(cells) == len(TABLE_SCHEMAS["Questions"]["columns"])


def test_enums_are_written_as_their_value():
    assert "SHORT_RESPONSE" in serialise_row(_question(), "Questions")


def test_booleans_stay_booleans():
    """The reference stores real booleans; strings would break readers."""
    row = QuestionMicroSkillRow(question_id="Q-T01-001", micro_skill_id="T01.M1",
                                weight=1.0, is_primary=True)
    cells = serialise_row(row, "Question_MicroSkills")
    assert cells[3] is True
    assert not isinstance(cells[3], str)


def test_none_becomes_an_empty_cell_not_the_text_none():
    row = {"answer_spec_id": "ANS-T01-001", "question_id": "Q-T01-001",
           "answer_type": "ALGEBRAIC_EXPRESSION", "canonical_answer": "n + 5",
           "accepted_answers": "n+5", "common_wrong_answers": "5n",
           "verification_method": "SYMBOLIC_EQUIVALENCE", "required_units": None,
           "explanation_required": False, "answer_steps": "1. Do it."}
    cells = serialise_row(row, "Answer_Specs")
    index = TABLE_SCHEMAS["Answer_Specs"]["columns"].index("required_units")
    assert cells[index] is None


def test_a_list_is_joined_rather_than_written_as_a_repr():
    row = dict(zip(TABLE_SCHEMAS["Answer_Specs"]["columns"], [None] * 10))
    row["accepted_answers"] = ["n+5", "5+n"]
    cells = serialise_row(row, "Answer_Specs")
    index = TABLE_SCHEMAS["Answer_Specs"]["columns"].index("accepted_answers")
    assert cells[index] == "n+5 | 5+n"


def test_a_missing_column_is_written_empty_not_refused():
    """While the pipeline is partial, an absent field is a blank cell."""
    cells = serialise_row({"topic_id": "ALG-ORI-01"}, "Topics")
    assert cells[TABLE_SCHEMAS["Topics"]["columns"].index("topic_id")] == "ALG-ORI-01"
    assert cells[TABLE_SCHEMAS["Topics"]["columns"].index("version")] is None


def test_a_field_the_sheet_has_no_column_for_is_refused():
    """It means a generator is producing something with nowhere to go."""
    with pytest.raises(WorkbookWriteError, match="no column for"):
        serialise_row({"topic_id": "x", "invented": 1}, "Topics")


def test_an_unknown_sheet_is_refused():
    with pytest.raises(WorkbookWriteError, match="no schema"):
        serialise_row({}, "Made_Up_Sheet")


def test_an_unreadable_row_type_is_refused():
    with pytest.raises(WorkbookWriteError, match="cannot read a row"):
        serialise_row("just a string", "Topics")


# ──────────────────────────────────────────────────────────────────────
# Writing the file
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def written(tmp_path):
    out = tmp_path / "generated.xlsx"
    write_workbook(
        {"Topics": [_topic()], "Questions": [_question(1), _question(2)]}, out,
    )
    return out


def test_every_sheet_exists_even_when_it_has_no_rows(written):
    """Gaps should be visible in the file, not absent from it."""
    assert len(load_workbook(written).sheetnames) == 27


def test_rows_land_in_the_right_sheets(written):
    counts = row_counts(written)
    assert counts["topics"] == 1
    assert counts["questions"] == 2
    assert counts["micro_skills"] == 0


def test_headers_survive_the_data_write(written):
    ws = load_workbook(written)["questions"]
    assert [c.value for c in ws[1]] == TABLE_SCHEMAS["Questions"]["columns"]


def test_values_round_trip_through_the_file(written):
    ws = load_workbook(written)["questions"]
    assert [c.value for c in ws[2]][:4] == [
        "Q-T01-001", "ALG-ORI-01", "Write the general rule.", "SHORT_RESPONSE",
    ]


def test_writing_an_unknown_sheet_is_refused(tmp_path):
    with pytest.raises(WorkbookWriteError, match="no schema"):
        write_workbook({"Nonsense": []}, tmp_path / "x.xlsx")


def test_the_summary_shows_populated_and_empty_sheets(written):
    text = summarise(written)
    assert "27 sheets, 2 populated" in text
    assert "Questions" in text and "Micro_Skills" in text
    assert "Orientation_Videos" in text, "declared but empty, so visible"


# ──────────────────────────────────────────────────────────────────────
# The exit condition
# ──────────────────────────────────────────────────────────────────────

@needs_template
def test_the_written_workbook_matches_the_platform_template(written):
    """The exit condition, now measured against the platform's own export.

    The older reference workbook no longer has the right shape: it predates
    the three orientation tables and the three added columns, and its sheets
    are TitleCase where the platform uses snake_case.
    """
    assert verify_written(written) == []


@needs_template
def test_the_structure_check_can_actually_fail(tmp_path):
    """A check that never fails proves nothing."""
    from workbook_builder import REFERENCE_SHEET_ORDER
    order = list(REFERENCE_SHEET_ORDER)
    order[0], order[1] = order[1], order[0]
    out = write_workbook({}, tmp_path / "swapped.xlsx", sheet_order=order)
    assert verify_written(out) != []


# ──────────────────────────────────────────────────────────────────────
# The whole pipeline, with a scripted model
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not TOPIC_DOCS, reason="topic documents not available")
@needs_template
def test_the_pipeline_runs_end_to_end_and_writes_a_workbook(tmp_path, monkeypatch):
    """Every generator, in order, with no network.

    The first test that exercises the whole chain together. It catches the
    class of bug no single-module test can: a generator whose output does not
    fit the next one's input.
    """
    import pipeline
    from llm_client import FakeLLMClient

    def skills_payload(n=7):
        return {"micro_skills": [
            {"skill_name": f"Skill {i}", "description": f"The student does {i}.",
             "prerequisite_position": (i - 1) if i > 1 else None,
             "prerequisite_micro_skill_id": None,
             "assessment_priority": "HIGH" if i % 2 else "MEDIUM"}
            for i in range(1, n + 1)
        ]}

    def topic_payload(brief):
        return {
            "topic_id": brief.topic_id, "topic_title": brief.topic_title,
            "ks_stage": brief.ks_stage.value, "sequence_no": brief.sequence_no,
            "learning_goal": "Understand that algebra represents change.",
            "core_message": "A letter can represent a changing quantity.",
            "included_scope": list(brief.included_scope),
            "excluded_scope": list(brief.excluded_scope),
            "misconceptions_to_prevent": list(brief.misconceptions_to_prevent),
        }

    def questions_payload():
        """Seven slots for one micro-skill, as CG-011 now asks for them."""
        from coverage_plan import plan_for_skill
        out = []
        for number, slot in enumerate(plan_for_skill(), start=1):
            # Only the diagnostic must be SINGLE_CHOICE. Phase 3 is written as
            # canvas work, which is what the review asks for and also avoids
            # the "every Phase 3 question is multiple choice" warning.
            diagnostic = slot.phase.value == "PHASE_0_DIAGNOSTIC"
            qtype = "SINGLE_CHOICE" if diagnostic else "SHORT_RESPONSE"
            text = ("Which rule works for every step? a) n + 3 b) 3n c) n - 3"
                    if diagnostic else
                    f"Work out the value of the expression for slot {number}.")
            out.append({"slot": number, "question_type": qtype,
                        "question_text": text, "item_family": f"FAM-{number}"})
        return {"questions": out}

    def answers_payload(question_ids):
        """One answer per question, typed to match the question.

        A diagnostic is SINGLE_CHOICE and its answer is an option letter; the
        rest are expressions. Getting this wrong is what the answer generator
        catches, so the scripted data has to be as disciplined as real output.
        """
        out = []
        for i, qid in enumerate(question_ids, start=1):
            if "-D" in qid:
                out.append({
                    "question_id": qid, "answer_type": "SINGLE_CHOICE",
                    "canonical_answer": "A", "accepted_answers": ["A"],
                    "common_wrong_answers": ["B", "C"],
                    "verification_method": "EXACT_CHOICE_MATCH",
                    "required_units": None, "explanation_required": False,
                    "answer_steps": ["Read each option.", "Only a) works for every step."],
                })
            else:
                out.append({
                    "question_id": qid, "answer_type": "ALGEBRAIC_EXPRESSION",
                    "canonical_answer": f"n + {i}",
                    "accepted_answers": [f"n+{i}", f"{i}+n"],
                    "common_wrong_answers": [f"{i}n", f"n-{i}"],
                    "verification_method": "SYMBOLIC_EQUIVALENCE",
                    "required_units": None, "explanation_required": False,
                    "answer_steps": ["Compare the cases.", f"Write n + {i}."],
                })
        return {"answers": out}

    def example_payload():
        return {
            "title": "Many Cases, One Rule",
            "problem_statement": "Study 2 + 4, 7 + 4 and 12 + 4.",
            "final_answer": "n + 4",
            "steps": [
                {"screen_content": f"screen {i}",
                 "narration_text": f"Notice thing {i} about what is shown.",
                 "must_show": f"structure {i}", "must_not_show": f"wrong thing {i}",
                 "micro_skill_positions": [min(i, 7)]}
                for i in range(1, 6)
            ],
        }

    def errors_payload(n=5):
        return {"error_types": [
            {"descriptor": f"ERROR-KIND-{i}", "error_name": f"Error {i}",
             "description": f"Student writes the wrong thing in way {i}.",
             "micro_skill_position": (i % 7) + 1,
             "severity": "HIGH" if i % 2 else "MEDIUM",
             "detection_method": "SYMBOLIC_PATTERN"}
            for i in range(1, n + 1)
        ]}

    def misconceptions_payload(n=3):
        # Between them these must name every error code, or the generator
        # warns that an error has nothing to re-teach.
        rules = [
            "Trigger after ERR-T01-ERROR-KIND-1 or ERR-T01-ERROR-KIND-2 when repeated.",
            "Trigger after ERR-T01-ERROR-KIND-3 when repeated.",
            "Trigger after ERR-T01-ERROR-KIND-4 or ERR-T01-ERROR-KIND-5 when repeated.",
        ]
        return {"misconceptions": [
            {"descriptor": f"BELIEF-KIND-{i}", "name": f"Belief {i}",
             "description": f"Student believes the wrong thing in way {i}.",
             "diagnosis_rule": rules[i - 1]}
            for i in range(1, n + 1)
        ]}

    def related_skills_payload():
        """UNDERLYING_GAP / AFFECTED_SKILL. DIRECT_FAILURE is derived, so it
        must not appear here."""
        return {"links": [
            {"misconception_id": "MIS-T01-BELIEF-KIND-1",
             "micro_skill_id": "T01.M6",
             "relationship_type": "UNDERLYING_GAP"},
        ]}

    def error_map_payload(question_ids):
        """Label one wrong answer per question with an error it shows.

        The pattern has to be copied from the answer key exactly, which is
        what the generator checks: a paraphrase never matches a real response.
        """
        out = []
        for i, qid in enumerate(question_ids, start=1):
            pattern = "B" if "-D" in qid else f"{i}n"
            out.append({"question_id": qid, "response_pattern": pattern,
                        "error_code": f"ERR-T01-ERROR-KIND-{(i % 5) + 1}"})
        return {"mappings": out}

    def hints_payload():
        """Two per misconception. The level and the join are derived."""
        out = []
        for i in range(1, 4):
            mid = f"MIS-T01-BELIEF-KIND-{i}"
            out += [
                {"misconception_id": mid, "hint_type": "ATTENTION",
                 "content": "Look at what changes between the cases."},
                {"misconception_id": mid, "hint_type": "CONCEPT_REMINDER",
                 "content": "A letter stands for a number that can change."},
            ]
        return {"hints": out}

    def cues_payload():
        return {"cues": [
            {"misconception_id": f"MIS-T01-BELIEF-KIND-{i}",
             "cue_name": f"Cue {i}",
             "cue_purpose": "Show the contrast between the two readings.",
             "image_generation_prompt": "Premium 2D educational infographic, 16:9 landscape. Two panels.",
             "tutor_explanation_template": "Compare the two panels.",
             "retrieval_text": "Use when a student confuses the two.",
             "retrieval_keywords": "contrast, two readings"}
            for i in range(1, 4)
        ]}

    def examples_payload():
        return {"examples": [
            {"misconception_id": f"MIS-T01-BELIEF-KIND-{i}",
             "problem_statement": f"A robot starts at any position r and moves {i} spaces.",
             "worked_steps": ["changing value r", f"fixed action +{i}", f"rule r + {i}"],
             "final_answer": f"r + {i}"}
            for i in range(1, 4)
        ]}

    def scaffolds_payload(skill_count=7):
        """One per skill. Steps route to the hints CG-017 just wrote."""
        return {"scaffolds": [
            {"micro_skill_id": f"T01.M{i}",
             "scaffold_name": f"Walk Through Skill {i}",
             "trigger_rule": "Activate after hints and cues have not worked.",
             "completion_rule": "Complete the step unaided afterwards.",
             "steps": [
                 {"prompt": "What changes between the cases?",
                  "partial_content": "case 1 | case 2",
                  "expected_response": "The starting number",
                  "next_on_incorrect": "Repeat this stage"},
                 {"prompt": "What stays the same?",
                  "partial_content": "+ 4",
                  "expected_response": "Add 4",
                  "next_on_incorrect": "Repeat this stage"},
                 {"prompt": "Put them together as a rule.",
                  "partial_content": "",
                  "expected_response": "n + 4",
                  "next_on_incorrect": "Repeat this stage"},
             ]}
            for i in range(1, skill_count + 1)
        ]}

    from brief_mapper import map_all
    brief = map_all()[0]

    # One topic, in pipeline order. Questions are now ONE CALL PER
    # MICRO-SKILL, so seven skills means seven question calls before the
    # answer key is asked for.
    skill_count = 7
    # Diagnostics get their own id series, so the ids are not one run of
    # numbers: seven Q-T01-Dnn and forty-two Q-T01-nnn.
    question_ids = (
        [f"Q-T01-D{n:02d}" for n in range(1, skill_count + 1)]
        + [f"Q-T01-{n:03d}" for n in range(1, skill_count * 6 + 1)]
    )
    scripted = [
        skills_payload(),
        topic_payload(brief),
        *[questions_payload() for _ in range(skill_count)],
        answers_payload(question_ids),
        example_payload(),
        errors_payload(),
        misconceptions_payload(),
        related_skills_payload(),
        error_map_payload(question_ids),
        hints_payload(),
        cues_payload(),
        examples_payload(),
        scaffolds_payload(skill_count),
    ]
    client = FakeLLMClient(scripted)
    monkeypatch.setattr(pipeline, "default_client", lambda: client)

    out = tmp_path / "pipeline.xlsx"
    code = pipeline.run(out, limit=1, verbose=False)

    assert code == 0, "the pipeline reported a problem"
    assert out.exists()

    counts = row_counts(out)
    assert counts["topics"] == 1
    assert counts["micro_skills"] == 7
    # Seven skills x seven slots. Coverage is now planned, not incidental.
    assert counts["questions"] == 49
    assert counts["answer_specs"] == 49
    assert counts["question_usage"] == 49
    assert counts["question_micro_skills"] == 49, "exactly one mapping each"
    assert counts["worked_examples"] == 1
    assert counts["worked_example_steps"] == 5
    assert counts["error_types"] == 5
    assert counts["misconceptions"] == 3
    # CG-016. Derived from the diagnosis rules rather than generated, so the
    # count follows from what CG-015 wrote.
    assert counts["misconception_errors"] == 5
    assert counts["misconception_micro_skills"] > 0
    assert counts["question_error_map"] > 0
    # CG-017. Two hints per misconception, one cue, one parallel example.
    assert counts["hints"] == 6
    assert counts["misconception_hints"] == 6
    assert counts["visual_cues"] == 3
    assert counts["misconception_visual_cues"] == 3
    assert counts["parallel_examples"] == 3
    # CG-018. One scaffold per skill, three steps each, linked to that
    # skill's three guided questions.
    assert counts["scaffolds"] == 7
    assert counts["scaffold_steps"] == 21
    assert counts["question_scaffolds"] == 21
    assert counts["topic_scope"] == len(brief.included_scope) + len(brief.excluded_scope)
    assert verify_written(out) == []


@pytest.mark.skipif(not TOPIC_DOCS, reason="topic documents not available")
def test_the_pipeline_needs_a_key_and_says_so(monkeypatch, capsys):
    import pipeline
    monkeypatch.setattr(pipeline, "is_configured", lambda: False)
    assert pipeline.main(["--out", "/tmp/unused.xlsx"]) == 2
    assert "No OpenAI API key" in capsys.readouterr().err
