"""CG-020 tests.

The danger with a validator is not that a check is wrong. It is that a check
never runs and reports success. That has happened twice on this project: an
empty folder that shadowed the sources directory so 279 tests skipped while
reporting green, and a fixture that wrote both 'a)' and 'a' into accepted
answers so the bug it existed to catch passed.

So the shape here is one clean case and one broken case per rule. The clean
case proves the rule does not fire on good data; the broken case proves it
fires at all. A rule with only the first is a rule that might be checking
nothing.

Two tests run against the platform's own export, which is the only way to
find out whether a rule agrees with reality rather than with my reading of
the specification.

No network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import validator as v                                # noqa: E402
from coverage_plan import plan_for_skill             # noqa: E402
from sources import SCHEMA_TEMPLATE                  # noqa: E402

needs_template = pytest.mark.skipif(
    SCHEMA_TEMPLATE is None, reason="platform export not available",
)


# ──────────────────────────────────────────────────────────────────────
# A workbook that passes everything, for the broken cases to break
# ──────────────────────────────────────────────────────────────────────

TOPIC = "ALG-ORI-01"
SKILL = "T01.M1"


def clean_tables() -> dict[str, list[dict]]:
    """One topic, one micro-skill, its seven questions, all rules satisfied.

    Built from plan_for_skill rather than a hand-written list of seven, so it
    cannot drift away from what COVERAGE_PLAN requires.
    """
    questions, usage, mappings, answers = [], [], [], []

    for n, slot in enumerate(plan_for_skill(), start=1):
        question_id = f"Q-T01-{n:03d}"
        phase = slot.phase.value
        guided = phase == "PHASE_2_GUIDED_LEARNING"
        question_type = (slot.required_type.value if slot.required_type
                         else "SHORT_RESPONSE")

        questions.append({
            "question_id": question_id, "topic_id": TOPIC,
            "question_text": "Write the rule for 3+5, 9+5, 14+5 using n.",
            "question_type": question_type, "difficulty": slot.difficulty,
            "answer_spec_id": f"ANS-T01-{n:03d}",
            "item_family_id": "FAM-T01-X",
            "source_provenance_id": "SRC-T01-001",
            "status": "GENERATED", "version": "1.0",
        })
        usage.append({
            "question_usage_id": f"QU-T01-{n:03d}",
            "question_id": question_id, "phase": phase,
            "question_role": slot.role.value if slot.role else "DIAGNOSTIC",
            "sequence_order": n,
            "support_allowed": ("ADAPTIVE_SUPPORT" if guided
                                else "NO_SUPPORT_DURING_ATTEMPT"),
            "max_attempts": 2 if guided else 1, "active": True,
        })
        mappings.append({
            "question_id": question_id, "micro_skill_id": SKILL,
            "weight": 1.0, "is_primary": True,
        })
        answers.append({
            "answer_spec_id": f"ANS-T01-{n:03d}", "question_id": question_id,
            "answer_type": "ALGEBRAIC_EXPRESSION", "canonical_answer": "n + 5",
            "accepted_answers": "n+5 | 5+n", "common_wrong_answers": "5n | n-5",
            "verification_method": "SYMBOLIC_EQUIVALENCE",
            "required_units": None, "explanation_required": False,
            "answer_steps": "1. Compare the cases.\n2. Write n + 5.",
        })

    return {
        "Topics": [{
            "topic_id": TOPIC, "topic_code": "T01",
            "topic_title": "What Is Algebra?", "ks_stage": "KS3",
            "sequence_no": 1, "learning_goal": "Understand what algebra is.",
            "core_message": "A letter stands for a number that can change.",
            "status": "DRAFT", "version": "1.0",
            "created_at": None, "updated_at": None,
        }],
        "Topic_Scope": [
            {"scope_item_id": "SC-T01-001", "topic_id": TOPIC,
             "scope_type": "INCLUDED", "item_text": "Using letters for numbers",
             "active": True},
            {"scope_item_id": "SC-T01-002", "topic_id": TOPIC,
             "scope_type": "EXCLUDED",
             "item_text": "Solving equations to find a variable",
             "active": True},
        ],
        "Source_Provenance": [{"source_provenance_id": "SRC-T01-001"}],
        "Micro_Skills": [{
            "micro_skill_id": SKILL, "topic_id": TOPIC, "skill_code": "M1",
            "skill_name": "Distinguish arithmetic from algebra",
            "description": "The student tells the two apart.",
            "prerequisite_micro_skill_id": None,
            "assessment_priority": "HIGH", "status": "DRAFT", "version": "1.0",
        }],
        "Questions": questions,
        "Question_Usage": usage,
        "Question_MicroSkills": mappings,
        "Answer_Specs": answers,
        "Worked_Examples": [{
            "worked_example_id": "WE-T01-01", "topic_id": TOPIC,
            "title": "Finding the rule", "phase": "PHASE_1_WORKED_EXAMPLE",
            "problem_statement": "3+5, 9+5, 14+5", "final_answer": "n + 5",
            "status": "GENERATED", "version": "1.0",
        }],
        "Worked_Example_Steps": [
            {"worked_example_step_id": f"WES-T01-{i}",
             "worked_example_id": "WE-T01-01", "step_no": i,
             "screen_content": f"step {i}", "narration_text": "Watch this.",
             "must_show": None, "must_not_show": None}
            for i in (1, 2, 3)
        ],
        "Worked_Example_MicroSkills": [{
            "worked_example_id": "WE-T01-01", "micro_skill_id": SKILL,
            "weight": 1.0, "is_primary": True,
        }],
        "Error_Types": [{
            "error_code": "ERR-T01-A", "error_name": "Reads add as multiply",
            "description": "The student multiplies.",
            "related_micro_skill_id": SKILL, "severity": "HIGH",
            "detection_method": "SYMBOLIC_PATTERN", "active": True,
        }],
        "Question_Error_Map": [{
            "question_id": "Q-T01-001", "response_pattern": "5n",
            "error_code": "ERR-T01-A", "micro_skill_id": SKILL,
        }],
    }


def findings_for(tables, code: str, *, generated: bool = True):
    report = v.validate_tables(tables, generated=generated)
    return [f for f in report.findings
            if f.rule_code == code and f.severity != v.INFO]


def blocking_codes(tables) -> set[str]:
    return {f.rule_code for f in v.validate_tables(tables).blocking}


# ──────────────────────────────────────────────────────────────────────
# The fixture itself
# ──────────────────────────────────────────────────────────────────────

def test_the_clean_fixture_passes_every_rule():
    """If this ever fails, every broken case below is testing the wrong thing:
    it would be finding the fixture's own faults rather than the one planted."""
    report = v.validate_tables(clean_tables())
    assert report.passed, [str(f) for f in report.blocking]
    assert not report.warnings, [str(f) for f in report.warnings]


# ──────────────────────────────────────────────────────────────────────
# The registry
# ──────────────────────────────────────────────────────────────────────

SPEC_CODES = [
    "SOURCE_REQUIRED_SECTION", "UNIQUE_ID", "FOREIGN_KEY", "ONE_PRIMARY_SKILL",
    "WEIGHT_SUM", "QUESTION_HAS_ANSWER", "ANSWER_CORRECT",
    "ACCEPTED_WRONG_DISJOINT", "ANSWER_STEPS_COMPLETE", "PHASE0_FORMAT",
    "PHASE3_CANVAS_ONLY", "PHASE3_NO_SUPPORT", "SCAFFOLD_MATCH",
    "SCOPE_EXCLUSION", "NO_ERROR_CONFLICT", "MAPPING_COMPLETE",
    "WORKED_EXAMPLE_CORRECT",
]


def test_all_seventeen_specification_rules_are_present():
    """Typed out from section 12.1 rather than read from the module, so a rule
    quietly dropped during a refactor fails here."""
    assert len(SPEC_CODES) == 17
    assert set(v.SPEC_RULES) == set(SPEC_CODES)


def test_every_rule_has_a_check_or_says_why_not():
    for code, rule in v.RULES.items():
        if code in v.CHECKS:
            continue
        assert rule.coverage == v.NONE, f"{code} has no check but claims {rule.coverage}"
        assert rule.undecidable, f"{code} is unchecked and does not say why"


def test_no_check_exists_for_a_rule_nobody_declared():
    assert set(v.CHECKS) <= set(v.RULES)


def test_the_undecidable_rules_are_named_in_the_report():
    """Silence must not read as a pass."""
    report = v.validate_tables(clean_tables())
    declared = {f.rule_code for f in report.findings if f.severity == v.INFO}
    assert "ANSWER_CORRECT" in declared
    for code in declared:
        assert v.RULES[code].coverage in (v.PARTIAL, v.NONE)


def test_a_declared_limit_is_never_blocking():
    """A rule we cannot decide must not fail every run forever."""
    for finding in v.declared_limits():
        assert not finding.blocking


# ──────────────────────────────────────────────────────────────────────
# One broken case per rule
# ──────────────────────────────────────────────────────────────────────

def test_source_required_section_fires_on_a_missing_goal():
    tables = clean_tables()
    tables["Topics"][0]["learning_goal"] = ""
    assert findings_for(tables, "SOURCE_REQUIRED_SECTION")


def test_source_required_section_fires_when_excluded_scope_is_absent():
    """Without it, SCOPE_EXCLUSION silently has nothing to check."""
    tables = clean_tables()
    tables["Topic_Scope"] = [s for s in tables["Topic_Scope"]
                             if s["scope_type"] != "EXCLUDED"]
    assert any("EXCLUDED" in f.issue
               for f in findings_for(tables, "SOURCE_REQUIRED_SECTION"))


def test_unique_id_fires_on_a_repeated_id():
    tables = clean_tables()
    tables["Questions"].append(dict(tables["Questions"][0]))
    assert findings_for(tables, "UNIQUE_ID")


def test_foreign_key_fires_on_an_invented_reference():
    tables = clean_tables()
    tables["Micro_Skills"][0]["topic_id"] = "ALG-ORI-99"
    assert findings_for(tables, "FOREIGN_KEY")


def test_a_missing_target_sheet_is_one_finding_not_one_per_row():
    """The platform's export has no topics sheet. As one finding per
    referencing row that reads like 18 bad ids and is one missing table."""
    tables = clean_tables()
    del tables["Topics"]
    found = findings_for(tables, "FOREIGN_KEY")
    assert found
    assert all("not in this workbook at all" in f.issue for f in found)
    # One per referencing table, not one per row: 7 questions all point at
    # the same absent sheet and must not produce 7 findings.
    from_questions = [f for f in found if f.table == "Questions"]
    assert len(from_questions) == 1


def test_a_null_foreign_key_is_not_a_dangling_one():
    """An optional reference left empty is allowed. Treating it as dangling
    would flag every micro-skill with no prerequisite."""
    tables = clean_tables()
    tables["Micro_Skills"][0]["prerequisite_micro_skill_id"] = None
    assert not findings_for(tables, "FOREIGN_KEY")


def test_repeated_dangling_references_are_counted_not_repeated():
    tables = clean_tables()
    for mapping in tables["Question_MicroSkills"]:
        mapping["micro_skill_id"] = "T01.M99"
    found = findings_for(tables, "FOREIGN_KEY")
    from_mappings = [f for f in found if f.table == "Question_MicroSkills"]
    assert len(from_mappings) == 1
    assert "7 rows" in from_mappings[0].issue


def test_every_declared_foreign_key_is_actually_checked():
    """The guard that makes the schema the single source of truth.

    Breaking one reference at a time and asserting each is caught proves the
    check is driven by the declarations rather than by a list somebody
    maintains by hand and forgets.
    """
    from table_schemas import TABLE_SCHEMAS

    base = clean_tables()
    checked = 0
    for table, schema in TABLE_SCHEMAS.items():
        if not base.get(table):
            continue
        for column in (schema.get("foreign_keys") or {}):
            if base[table][0].get(column) is None:
                continue
            tables = clean_tables()
            tables[table][0][column] = "DEFINITELY-NOT-A-REAL-ID"
            assert findings_for(tables, "FOREIGN_KEY"), \
                f"{table}.{column} is declared a foreign key and not checked"
            checked += 1
    assert checked >= 8, f"only exercised {checked} foreign keys"


def test_unique_columns_are_taken_from_the_schema():
    from table_schemas import TABLE_SCHEMAS

    declared = {
        (table, column)
        for table, schema in TABLE_SCHEMAS.items()
        for column, details in schema["column_details"].items()
        if details.get("unique")
    }
    assert len(declared) >= 20
    for table, column in declared:
        if not clean_tables().get(table):
            continue
        tables = clean_tables()
        tables[table].append(dict(tables[table][0]))
        found = findings_for(tables, "UNIQUE_ID")
        assert any(f.table == table for f in found), \
            f"{table}.{column} is declared unique and duplicates pass"


def test_one_primary_skill_fires_on_two_primaries():
    tables = clean_tables()
    tables["Question_MicroSkills"].append({
        "question_id": "Q-T01-001", "micro_skill_id": SKILL,
        "weight": 0.0, "is_primary": True,
    })
    assert findings_for(tables, "ONE_PRIMARY_SKILL")


def test_one_primary_skill_fires_on_none():
    tables = clean_tables()
    tables["Question_MicroSkills"][0]["is_primary"] = False
    assert findings_for(tables, "ONE_PRIMARY_SKILL")


def test_one_primary_skill_fires_on_a_question_mapped_to_nothing_at_all():
    """The case a per-mapping-row count cannot see.

    Counting primaries across mapping rows only ever visits things that have
    a mapping row, so a question mapped to nothing scores zero visits and
    passes. The owners have to come from Questions, not from the mapping.
    """
    tables = clean_tables()
    orphaned = tables["Questions"][0]["question_id"]
    tables["Question_MicroSkills"] = [m for m in tables["Question_MicroSkills"]
                                      if m["question_id"] != orphaned]
    found = findings_for(tables, "ONE_PRIMARY_SKILL")
    assert [f.record_id for f in found] == [orphaned]


def test_one_primary_skill_covers_worked_examples_too():
    """The specification says question AND worked example. The CG-019 version
    only looked at questions, which is the gap this rule closes."""
    tables = clean_tables()
    tables["Worked_Example_MicroSkills"][0]["is_primary"] = False
    found = findings_for(tables, "ONE_PRIMARY_SKILL")
    assert any(f.table == "Worked_Example_MicroSkills" for f in found)


def test_weight_sum_fires_when_the_total_is_not_one():
    tables = clean_tables()
    tables["Question_MicroSkills"][0]["weight"] = 0.5
    assert findings_for(tables, "WEIGHT_SUM")


def test_weight_sum_accepts_several_skills_that_add_up():
    """The rule is about the total, not about how many rows make it."""
    tables = clean_tables()
    tables["Question_MicroSkills"][0]["weight"] = 0.6
    tables["Question_MicroSkills"].append({
        "question_id": "Q-T01-001", "micro_skill_id": SKILL,
        "weight": 0.4, "is_primary": False,
    })
    assert not findings_for(tables, "WEIGHT_SUM")


def test_weight_sum_tolerates_spreadsheet_float_drift():
    tables = clean_tables()
    tables["Question_MicroSkills"][0]["weight"] = 1.0 - v.WEIGHT_TOLERANCE / 2
    assert not findings_for(tables, "WEIGHT_SUM")


def test_question_has_answer_fires_when_there_is_none():
    tables = clean_tables()
    tables["Answer_Specs"].pop()
    assert findings_for(tables, "QUESTION_HAS_ANSWER")


def test_question_has_answer_fires_on_two_keys_for_one_question():
    tables = clean_tables()
    duplicate = dict(tables["Answer_Specs"][0])
    duplicate["answer_spec_id"] = "ANS-T01-999"
    tables["Answer_Specs"].append(duplicate)
    assert findings_for(tables, "QUESTION_HAS_ANSWER")


def test_accepted_wrong_disjoint_fires_on_overlap():
    tables = clean_tables()
    tables["Answer_Specs"][0]["common_wrong_answers"] = "n+5 | 5n"
    assert findings_for(tables, "ACCEPTED_WRONG_DISJOINT")


def test_accepted_wrong_disjoint_sees_through_operator_spelling():
    """The same bug that lost Q-T04-034: a Unicode minus and a hyphen are one
    answer, so accepting one while calling the other wrong is a contradiction
    a plain string comparison would miss."""
    tables = clean_tables()
    tables["Answer_Specs"][0]["accepted_answers"] = "x-6"
    tables["Answer_Specs"][0]["common_wrong_answers"] = "x − 6 | 6-x"
    assert findings_for(tables, "ACCEPTED_WRONG_DISJOINT")


def test_answer_steps_complete_fires_on_empty_steps():
    tables = clean_tables()
    tables["Answer_Specs"][0]["answer_steps"] = ""
    assert findings_for(tables, "ANSWER_STEPS_COMPLETE")


def test_answer_steps_complete_fires_on_a_gap_in_the_numbering():
    tables = clean_tables()
    tables["Answer_Specs"][0]["answer_steps"] = "1. First.\n3. Third."
    assert findings_for(tables, "ANSWER_STEPS_COMPLETE")


def test_phase0_format_fires_on_a_non_choice_diagnostic():
    tables = clean_tables()
    for question, usage in zip(tables["Questions"], tables["Question_Usage"]):
        if usage["phase"] == "PHASE_0_DIAGNOSTIC":
            question["question_type"] = "SHORT_RESPONSE"
    assert findings_for(tables, "PHASE0_FORMAT")


def test_phase0_format_fires_when_a_diagnostic_offers_support():
    tables = clean_tables()
    for usage in tables["Question_Usage"]:
        if usage["phase"] == "PHASE_0_DIAGNOSTIC":
            usage["support_allowed"] = "ADAPTIVE_SUPPORT"
    assert findings_for(tables, "PHASE0_FORMAT")


def test_phase3_canvas_only_fires_on_a_question_asking_for_prose():
    tables = clean_tables()
    for question, usage in zip(tables["Questions"], tables["Question_Usage"]):
        if usage["phase"] == "PHASE_3_INDEPENDENT_PRACTICE":
            question["question_text"] = "Explain why a letter is not an answer."
    assert findings_for(tables, "PHASE3_CANVAS_ONLY")


def test_phase3_canvas_only_leaves_guided_questions_alone():
    """Phase 2 may ask for an explanation; the tutor is there to hear it."""
    tables = clean_tables()
    for question, usage in zip(tables["Questions"], tables["Question_Usage"]):
        if usage["phase"] == "PHASE_2_GUIDED_LEARNING":
            question["question_text"] = "Explain why a letter is not an answer."
    assert not findings_for(tables, "PHASE3_CANVAS_ONLY")


def test_phase3_no_support_fires_on_adaptive_support():
    tables = clean_tables()
    for usage in tables["Question_Usage"]:
        if usage["phase"] == "PHASE_3_INDEPENDENT_PRACTICE":
            usage["support_allowed"] = "ADAPTIVE_SUPPORT"
    assert findings_for(tables, "PHASE3_NO_SUPPORT")


def test_phase3_no_support_fires_on_an_attached_scaffold():
    tables = clean_tables()
    independent = next(u["question_id"] for u in tables["Question_Usage"]
                       if u["phase"] == "PHASE_3_INDEPENDENT_PRACTICE")
    tables["Scaffolds"] = [{"scaffold_id": "SCF-T01-01",
                            "scaffold_name": "Walk through", "active": True}]
    tables["Question_Scaffolds"] = [{
        "question_id": independent, "micro_skill_id": SKILL,
        "scaffold_id": "SCF-T01-01", "priority": 1,
    }]
    assert findings_for(tables, "PHASE3_NO_SUPPORT")


def test_scaffold_match_fires_when_the_scaffold_is_for_another_skill():
    tables = clean_tables()
    guided = next(u["question_id"] for u in tables["Question_Usage"]
                  if u["phase"] == "PHASE_2_GUIDED_LEARNING")
    tables["Scaffolds"] = [{"scaffold_id": "SCF-T01-01",
                            "scaffold_name": "Walk through", "active": True}]
    tables["Question_Scaffolds"] = [{
        "question_id": guided, "micro_skill_id": "T01.M9",
        "scaffold_id": "SCF-T01-01", "priority": 1,
    }]
    assert findings_for(tables, "SCAFFOLD_MATCH")


def test_scope_exclusion_warns_rather_than_blocks():
    """A shared word is evidence, not proof. Blocking on a keyword would
    train everyone to ignore the rule."""
    tables = clean_tables()
    tables["Questions"][0]["question_text"] = (
        "Try solving these equations to find the variable."
    )
    found = findings_for(tables, "SCOPE_EXCLUSION")
    assert found
    assert all(not f.blocking for f in found)
    assert all(f.severity == v.WARNING for f in found)


def test_scope_exclusion_needs_more_than_one_shared_word():
    """One ordinary word in common is how a check earns its way into being
    ignored."""
    tables = clean_tables()
    tables["Questions"][0]["question_text"] = "Which of these is a variable?"
    assert not findings_for(tables, "SCOPE_EXCLUSION")


def test_scope_terms_drops_ordinary_words():
    terms = v.scope_terms("Solving an equation to find the variable")
    assert "the" not in terms and "an" not in terms and "to" not in terms
    assert "solving" in terms and "equation" in terms


def test_no_error_conflict_fires_on_one_response_two_errors():
    tables = clean_tables()
    tables["Error_Types"].append({
        "error_code": "ERR-T01-B", "error_name": "Other",
        "description": "Something else.", "related_micro_skill_id": SKILL,
        "severity": "MEDIUM", "detection_method": "SYMBOLIC_PATTERN",
        "active": True,
    })
    tables["Question_Error_Map"].append({
        "question_id": "Q-T01-001", "response_pattern": "5n",
        "error_code": "ERR-T01-B", "micro_skill_id": SKILL,
    })
    assert findings_for(tables, "NO_ERROR_CONFLICT")


def test_no_error_conflict_allows_two_responses_mapping_separately():
    tables = clean_tables()
    tables["Question_Error_Map"].append({
        "question_id": "Q-T01-001", "response_pattern": "n-5",
        "error_code": "ERR-T01-A", "micro_skill_id": SKILL,
    })
    assert not findings_for(tables, "NO_ERROR_CONFLICT")


def test_mapping_complete_fires_on_an_inactive_parent():
    """FOREIGN_KEY already proves the parent exists. This is the other half:
    a reference that resolves to something switched off."""
    tables = clean_tables()
    tables["Error_Types"][0]["active"] = False
    assert findings_for(tables, "MAPPING_COMPLETE")


def test_worked_example_correct_fires_on_a_repeated_step_number():
    tables = clean_tables()
    tables["Worked_Example_Steps"][1]["step_no"] = 1
    assert findings_for(tables, "WORKED_EXAMPLE_CORRECT")


def test_worked_example_correct_fires_on_a_gap():
    tables = clean_tables()
    tables["Worked_Example_Steps"][2]["step_no"] = 9
    assert findings_for(tables, "WORKED_EXAMPLE_CORRECT")


def test_a_single_step_example_may_be_numbered_anything():
    """The platform writes one worked example per step, numbered by position
    in the topic. Nineteen rows of approved data look like this, so a check
    demanding every example start at 1 would be wrong about their data."""
    tables = clean_tables()
    tables["Worked_Example_Steps"] = [{
        "worked_example_step_id": "WES-T01-5", "worked_example_id": "WE-T01-01",
        "step_no": 5, "screen_content": "n + 4", "narration_text": "Here.",
        "must_show": None, "must_not_show": None,
    }]
    assert not findings_for(tables, "WORKED_EXAMPLE_CORRECT")


def test_coverage_plan_fires_on_a_missing_slot():
    tables = clean_tables()
    dropped = tables["Questions"].pop()["question_id"]
    tables["Question_Usage"] = [u for u in tables["Question_Usage"]
                                if u["question_id"] != dropped]
    tables["Question_MicroSkills"] = [m for m in tables["Question_MicroSkills"]
                                      if m["question_id"] != dropped]
    tables["Answer_Specs"] = [a for a in tables["Answer_Specs"]
                              if a["question_id"] != dropped]
    assert findings_for(tables, "COVERAGE_PLAN")


def test_unreachable_row_fires_on_a_question_in_no_usage_row():
    tables = clean_tables()
    tables["Question_Usage"].pop()
    assert findings_for(tables, "UNREACHABLE_ROW")


def test_nothing_approved_fires_on_an_approved_row():
    tables = clean_tables()
    tables["Questions"][0]["status"] = "APPROVED"
    assert findings_for(tables, "NOTHING_APPROVED")


# ──────────────────────────────────────────────────────────────────────
# The model's working-out, left in the file
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("leaked", [
    "50,60 | 50 60 | 60, 70? (incorrect)",     # seen in the smoke run
    "50,60 | 50 60 | 40, 50 (correct)",
])
def test_deliberation_in_an_accepted_answer_is_caught(leaked):
    """The dangerous one. A student typing '60, 70? (incorrect)' is marked
    CORRECT, because the string sits in the accepted list."""
    tables = clean_tables()
    tables["Answer_Specs"][0]["accepted_answers"] = leaked
    found = findings_for(tables, "NO_DELIBERATION_IN_CONTENT")
    assert found
    assert found[0].table == "Answer_Specs"


@pytest.mark.parametrize("steps", [
    "1. The difference is 3. 2. Wait, recheck the options.",
    "1. Step 5 is 17? Recheck options: a)15 b)17.",
    "1. Let me check that again.",
    "2. Hmm, that does not look right.",
    "1. Actually, no, the rule adds 5.",
    "1. Correction: the answer is 17.",
    "1. On second thought the pattern is +3.",
])
def test_deliberation_in_answer_steps_is_caught(steps):
    """A tutor reads answer_steps aloud. These are the model's second
    thoughts being read to a child."""
    tables = clean_tables()
    tables["Answer_Specs"][0]["answer_steps"] = steps
    assert findings_for(tables, "NO_DELIBERATION_IN_CONTENT")


@pytest.mark.parametrize("innocent", [
    "Wait at the bus stop for 5 minutes, then count the cars.",
    "The correct answer uses a letter.",
    "Check your working by substituting a value.",
    "Actually measuring the garden gives 12 metres.",
    "1. Compare the cases. 2. Write n + 5.",
])
def test_ordinary_wording_is_not_mistaken_for_deliberation(innocent):
    """Anchored deliberately: 'wait' needs its comma, '(incorrect)' its
    brackets. A question may legitimately say 'wait at the bus stop'."""
    tables = clean_tables()
    tables["Questions"][0]["question_text"] = innocent
    tables["Answer_Specs"][0]["answer_steps"] = innocent
    assert not findings_for(tables, "NO_DELIBERATION_IN_CONTENT")


def test_the_check_covers_every_field_a_student_reads_or_is_marked_against():
    from validator import DELIBERATION_FIELDS

    covered = {table for table, _key, _columns in DELIBERATION_FIELDS}
    assert {"Answer_Specs", "Questions", "Hints", "Worked_Example_Steps",
            "Scaffold_Steps", "Parallel_Examples"} <= covered


def test_one_finding_per_row_however_many_fields_leaked():
    """Two findings about one row is one row to fix reported twice."""
    tables = clean_tables()
    tables["Answer_Specs"][0]["accepted_answers"] = "n+5 | 5+n (incorrect)"
    tables["Answer_Specs"][0]["answer_steps"] = "1. Wait, recheck this."
    assert len(findings_for(tables, "NO_DELIBERATION_IN_CONTENT")) == 1


# ──────────────────────────────────────────────────────────────────────
# One prose pattern, not two
# ──────────────────────────────────────────────────────────────────────

def test_the_validator_and_the_generator_share_one_prose_pattern():
    """Two near-identical copies is two places to fix, and one of them always
    gets forgotten. The generator refuses to write these and the validator
    refuses to pass them, so they have to be the same pattern."""
    from skill_question_generator import PROSE_RE as GENERATOR_PATTERN

    assert v.PROSE_RE is GENERATOR_PATTERN


@pytest.mark.parametrize("text", [
    "Write a single sentence in words that describes the rule.",
    "Describe this in one sentence.",
])
def test_the_phrasings_that_escaped_the_smoke_run_are_now_caught(text):
    """Both reached a Phase 3 question in the run of 8 September and were
    found by the semantic reviewer rather than by this pattern."""
    tables = clean_tables()
    for question, usage in zip(tables["Questions"], tables["Question_Usage"]):
        if usage["phase"] == "PHASE_3_INDEPENDENT_PRACTICE":
            question["question_text"] = text
    assert findings_for(tables, "PHASE3_CANVAS_ONLY")


@pytest.mark.parametrize("text", [
    "Write an expression for the total cost.",
    "Write the rule for 3+5, 9+5 using n.",
    "Which sentence best describes the pattern? a) ... b) ...",
    "Write 4n as a repeated addition.",
])
def test_widening_the_pattern_did_not_catch_legitimate_questions(text):
    """The risk of loosening a regex is that it starts refusing good content.
    'Which sentence best describes' is a choice question, not a prose one."""
    tables = clean_tables()
    for question, usage in zip(tables["Questions"], tables["Question_Usage"]):
        if usage["phase"] == "PHASE_3_INDEPENDENT_PRACTICE":
            question["question_text"] = text
    assert not findings_for(tables, "PHASE3_CANVAS_ONLY")


# ──────────────────────────────────────────────────────────────────────
# Local rules apply to us, not to everyone
# ──────────────────────────────────────────────────────────────────────

def test_our_own_rules_are_skipped_for_a_workbook_we_did_not_write():
    """The approved reference breaks both, correctly: it predates the
    seven-question plan and it is genuinely approved."""
    tables = clean_tables()
    tables["Questions"][0]["status"] = "APPROVED"
    assert not findings_for(tables, "NOTHING_APPROVED", generated=False)
    assert findings_for(tables, "NOTHING_APPROVED", generated=True)


def test_specification_rules_are_never_skipped():
    tables = clean_tables()
    tables["Questions"].append(dict(tables["Questions"][0]))
    assert findings_for(tables, "UNIQUE_ID", generated=False)


# ──────────────────────────────────────────────────────────────────────
# The report shape of section 12.3
# ──────────────────────────────────────────────────────────────────────

def test_a_finding_serialises_to_the_specifications_fields():
    tables = clean_tables()
    tables["Questions"][0]["status"] = "APPROVED"
    payload = v.validate_tables(tables).as_dicts("T01")[0]
    assert set(payload) == {
        "validation_id", "severity", "table", "record_id", "rule_code",
        "issue", "recommended_action", "blocking",
    }
    assert payload["validation_id"].startswith("VAL-T01-")
    assert payload["severity"] in {v.ERROR, v.WARNING, v.INFO}
    assert isinstance(payload["blocking"], bool)


def test_validation_ids_are_unique_within_a_report():
    tables = clean_tables()
    tables["Questions"].append(dict(tables["Questions"][0]))
    ids = [p["validation_id"] for p in v.validate_tables(tables).as_dicts()]
    assert len(ids) == len(set(ids))


def test_every_finding_says_what_to_do_about_it():
    """A finding a reader cannot act on is a finding they will learn to
    scroll past."""
    tables = clean_tables()
    tables["Questions"][0]["status"] = "APPROVED"
    tables["Answer_Specs"][0]["answer_steps"] = ""
    for finding in v.validate_tables(tables).findings:
        assert finding.recommended_action.strip()


def test_passed_is_about_blocking_failures_only():
    tables = clean_tables()
    tables["Questions"][0]["question_text"] = (
        "Try solving these equations to find the variable."
    )
    report = v.validate_tables(tables)
    assert report.warnings
    assert report.passed


# ──────────────────────────────────────────────────────────────────────
# Against the platform's own data
# ──────────────────────────────────────────────────────────────────────

def test_an_empty_workbook_produces_no_reference_failures():
    """Nothing to check is not the same as something wrong. A run that fell
    over before writing anything must not read as 34 broken joins."""
    report = v.validate_tables({}, generated=False)
    assert not report.blocking


def test_a_written_workbook_reads_back_by_internal_name(tmp_path):
    """read_tables keys on the internal name while the file uses the export
    name, and everything downstream depends on that translation."""
    from workbook_writer import write_workbook

    destination = tmp_path / "roundtrip.xlsx"
    write_workbook({}, destination)
    tables = v.read_tables(destination)
    assert "Question_MicroSkills" in tables
    assert "question_micro_skills" not in tables


@needs_template
def test_the_platform_export_does_not_trip_our_phase_or_answer_rules():
    """The roadmap's acceptance criterion, narrowed to what it can mean.

    The export omits its topics sheet, so FOREIGN_KEY fires for structural
    reasons that say nothing about our rules. What is worth asserting is that
    the rules encoding a judgement of ours agree with approved content.
    """
    report = v.validate(SCHEMA_TEMPLATE, generated=False)
    tripped = {f.rule_code for f in report.blocking}
    for code in ("PHASE0_FORMAT", "PHASE3_CANVAS_ONLY", "PHASE3_NO_SUPPORT",
                 "ACCEPTED_WRONG_DISJOINT", "QUESTION_HAS_ANSWER",
                 "WEIGHT_SUM", "UNIQUE_ID", "NO_ERROR_CONFLICT",
                 "WORKED_EXAMPLE_CORRECT", "ANSWER_STEPS_COMPLETE"):
        assert code not in tripped, f"{code} disagrees with approved content"


@needs_template
def test_the_export_really_does_have_two_primary_skills_on_one_question():
    """Not a validator bug, a finding about their data. Pinned so that if the
    export is corrected later this test tells us rather than going quiet."""
    report = v.validate(SCHEMA_TEMPLATE, generated=False)
    found = [f for f in report.blocking if f.rule_code == "ONE_PRIMARY_SKILL"]
    assert [f.record_id for f in found] == ["Q-T01-002"]
