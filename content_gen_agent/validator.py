"""CG-020: the deterministic validator.

Task Specification section 12.1 lists 17 blocking checks. This module runs
them against a written workbook and reports in the shape section 12.3 asks
for. It absorbs CG-019's integrity checker, which did five of them, so there
is one place to look and no way for two checkers to disagree.

Why it reads the file rather than the objects
----------------------------------------------

The workbook is what the platform imports. A generator can be correct and the
file still wrong, which is how the dangling Micro_Skills.topic_id in the run
of 6 September got through: every generator was right on its own. So the
validator opens the finished file, exactly as an importer would.

Three of the seventeen are not deterministic
---------------------------------------------

ANSWER_CORRECT, ANSWER_STEPS_COMPLETE and WORKED_EXAMPLE_CORRECT all reduce to
"is the mathematics right", which no amount of schema knowledge can settle.
They sit in a table headed "deterministic blocking checks" and they are not
deterministic.

Rather than quietly pass them, every rule declares how much of itself this
module can actually decide:

    FULL      the rule is entirely checkable here
    PARTIAL   the mechanical half is checked, the judgement half is not
    NONE      nothing here can decide it

A PARTIAL or NONE rule emits an INFO finding naming what was not checked, so
the report enumerates all 17 and is honest about 5 of them. CG-021 is where
the rest belongs, and a workbook that passes everything here can still teach
a student something false. That is why nothing is marked APPROVED.

Some rules are ours, not the spec's
------------------------------------

Everything in LOCAL_RULES was added after a real run produced something the
specification's seventeen would have let through:

    COVERAGE_PLAN               26 of 53 micro-skills with no primary
                                question, which was the content review's
                                headline finding
    UNREACHABLE_ROW             rows written that nothing can ever reach
    NOTHING_APPROVED            generated content claiming to be reviewed
    NO_DELIBERATION_IN_CONTENT  the model's working-out left in a field the
                                platform imports
    STANDARD_NOTATION           an answer key accepting both 4b and b4

They are marked local so nobody mistakes them for section 12.1, and they are
skipped when validating a workbook we did not write.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from openpyxl import load_workbook

from answer_generator import _normalise
from coverage_plan import coverage_report
from models import Phase, QuestionType, ScopeType, SupportAllowed
from skill_question_generator import PROSE_RE as _PROSE_RE
from table_schemas import PHASE_RULES, TABLE_SCHEMAS, export_name

#: Weights must total this, within the tolerance below. The review settled the
#: value: one primary skill per question, at 1.0.
REQUIRED_WEIGHT = 1.0

#: "1.0 +/- configured tolerance", section 12.1. Floats read back from a
#: spreadsheet are not exact, so the comparison needs slack even when every
#: value written was literally 1.0.
WEIGHT_TOLERANCE = 0.001

#: Tables nothing generates yet. Empty is correct, not a fault.
NOT_GENERATED = frozenset({
    "Orientation_Videos", "Orientation_Video_Scenes", "Orientation_Support_Cards",
})

#: A question demanding prose. Phase 3 is canvas-only, so a question whose
#: answer is a sentence cannot be marked by anything in the platform.
#:
#: Imported rather than copied. This module had its own near-identical version
#: until 8 September, which is two places to fix and one of them always gets
#: forgotten. The generator refuses to write these; the validator refuses to
#: pass them; they have to be the same pattern or the file can hold a question
#: the generator would have rejected.
PROSE_RE = _PROSE_RE

#: Words too ordinary to prove a scope violation on their own. An excluded
#: scope item reading "solving linear equations" should not flag every
#: question containing the word "the".
SCOPE_STOP_WORDS = frozenset("""
a an and are as at be but by for from has have how in into is it its of on or
that the their them then there these this to was were what when where which
with without not no any all more most one two three use using used student
students question questions answer answers example examples simple basic
""".split())

#: How long a term must be before a bare mention counts as evidence.
MIN_SCOPE_TERM_LENGTH = 5


# ──────────────────────────────────────────────────────────────────────
# What a rule is, and how much of it we can decide
# ──────────────────────────────────────────────────────────────────────

FULL = "FULL"
PARTIAL = "PARTIAL"
NONE = "NONE"


@dataclass(frozen=True)
class Rule:
    """One row of Task Specification 12.1, plus what we can do about it."""

    code: str
    condition: str
    coverage: str
    #: For PARTIAL and NONE: the part no schema check can settle.
    undecidable: str = ""
    #: False for the rules we added ourselves.
    from_spec: bool = True


RULES: dict[str, Rule] = {rule.code: rule for rule in [
    # -- section 12.1, in the order the specification lists them --------
    Rule("SOURCE_REQUIRED_SECTION",
         "Topic ID, title, goal, included scope and excluded scope are present.",
         FULL),
    Rule("UNIQUE_ID", "Every generated ID is unique.", FULL),
    Rule("FOREIGN_KEY", "Every referenced ID exists.", FULL),
    Rule("ONE_PRIMARY_SKILL",
         "Each question and worked example has exactly one primary skill.",
         FULL),
    Rule("WEIGHT_SUM",
         f"Skill weights total {REQUIRED_WEIGHT} +/- {WEIGHT_TOLERANCE}.",
         FULL),
    Rule("QUESTION_HAS_ANSWER",
         "Every question has exactly one Answer_Specs row.", FULL),
    Rule("ANSWER_CORRECT", "Canonical answer is mathematically correct.",
         NONE,
         "Whether an answer is right. Needs a person or an independent "
         "model; CG-021 owns it."),
    Rule("ACCEPTED_WRONG_DISJOINT",
         "Accepted answers and common wrong answers do not overlap.", FULL),
    Rule("ANSWER_STEPS_COMPLETE",
         "answer_steps exist and lead to the canonical answer.",
         PARTIAL,
         "Whether the steps actually reach the answer. Their presence and "
         "numbering are checked; their arithmetic is not."),
    Rule("PHASE0_FORMAT",
         "Phase 0 questions use SINGLE_CHOICE and no support.", FULL),
    Rule("PHASE3_CANVAS_ONLY",
         "Phase 3 question does not require free-form spoken explanation.",
         FULL),
    Rule("PHASE3_NO_SUPPORT",
         "Phase 3 has NO_SUPPORT_DURING_ATTEMPT and no scaffold mapping.",
         FULL),
    Rule("SCAFFOLD_MATCH",
         "Question-specific scaffold uses the correct symbols, numbers, "
         "context and final answer.",
         PARTIAL,
         "Whether the scaffold's symbols and numbers match the question. "
         "Note the design changed under this rule: scaffolds are now written "
         "per micro-skill rather than per question, so what is checked here "
         "is that a scaffold is attached to the skill the question tests."),
    Rule("SCOPE_EXCLUSION",
         "No generated content violates excluded scope.",
         PARTIAL,
         "Whether content genuinely crosses a boundary. A term from the "
         "excluded list appearing in a question is evidence, not proof, so "
         "these are raised as warnings for a person to read."),
    Rule("NO_ERROR_CONFLICT",
         "No question response pattern maps to incompatible errors.", FULL),
    Rule("MAPPING_COMPLETE",
         "All mapping records reference valid active/draft parents.", FULL),
    Rule("WORKED_EXAMPLE_CORRECT",
         "All worked-example steps are mathematically valid and ordered.",
         PARTIAL,
         "Whether the steps are mathematically valid. Their ordering is "
         "checked; their content is not."),

    # -- ours, from CG-019 and the content review -----------------------
    Rule("COVERAGE_PLAN",
         "Every micro-skill has the seven questions the plan requires.",
         FULL, from_spec=False),
    Rule("UNREACHABLE_ROW",
         "No row is written that nothing can ever reach.",
         FULL, from_spec=False),
    Rule("NOTHING_APPROVED",
         "No generated row claims to have been reviewed.",
         FULL, from_spec=False),
    Rule("NO_DELIBERATION_IN_CONTENT",
         "No row contains the model's working-out rather than its answer.",
         FULL, from_spec=False),
    Rule("STANDARD_NOTATION",
         "No answer key accepts a variable written before its coefficient.",
         FULL, from_spec=False),
]}

SPEC_RULES = [code for code, rule in RULES.items() if rule.from_spec]
LOCAL_RULES = [code for code, rule in RULES.items() if not rule.from_spec]


# ──────────────────────────────────────────────────────────────────────
# What a finding is
# ──────────────────────────────────────────────────────────────────────

ERROR, WARNING, INFO = "ERROR", "WARNING", "INFO"


@dataclass(frozen=True)
class Finding:
    """One validation result, in the shape of Task Specification 12.3."""

    rule_code: str
    severity: str
    table: str
    record_id: Optional[str]
    issue: str
    recommended_action: str
    blocking: bool

    def as_dict(self, validation_id: str) -> dict:
        return {
            "validation_id": validation_id,
            "severity": self.severity,
            "table": self.table,
            "record_id": self.record_id,
            "rule_code": self.rule_code,
            "issue": self.issue,
            "recommended_action": self.recommended_action,
            "blocking": self.blocking,
        }

    def __str__(self) -> str:
        where = f" {self.record_id}" if self.record_id else ""
        return f"[{self.rule_code}] {self.table}{where}: {self.issue}"


@dataclass
class Report:
    """Everything one validation run found."""

    findings: list[Finding] = field(default_factory=list)
    source: Optional[str] = None

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings
                if not f.blocking and f.severity == WARNING]

    @property
    def passed(self) -> bool:
        """No blocking failure. Deliberately not called 'valid'."""
        return not self.blocking

    def as_dicts(self, topic_code: str = "ALL") -> list[dict]:
        return [
            f.as_dict(f"VAL-{topic_code}-{n:03d}")
            for n, f in enumerate(self.findings, start=1)
        ]


def _fail(rule_code, table, record_id, issue, action) -> Finding:
    return Finding(rule_code, ERROR, table, record_id, issue, action,
                   blocking=True)


def _warn(rule_code, table, record_id, issue, action) -> Finding:
    return Finding(rule_code, WARNING, table, record_id, issue, action,
                   blocking=False)


# ──────────────────────────────────────────────────────────────────────
# Reading
# ──────────────────────────────────────────────────────────────────────

def read_tables(path: str | Path) -> dict[str, list[dict]]:
    """Every sheet as rows, keyed by the INTERNAL table name."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        by_export = {export_name(name): name for name in TABLE_SCHEMAS}
        tables: dict[str, list[dict]] = {}
        for sheet in workbook.sheetnames:
            internal = by_export.get(sheet)
            if internal is None:
                continue
            worksheet = workbook[sheet]
            rows = worksheet.iter_rows(values_only=True)
            header = [h for h in (next(rows, ()) or ()) if h is not None]
            tables[internal] = [
                dict(zip(header, values)) for values in rows
                if any(v is not None for v in values)
            ]
        return tables
    finally:
        workbook.close()


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _split(value) -> list[str]:
    """A pipe-delimited cell as a list."""
    return [p.strip() for p in _text(value).split("|") if p.strip()]


# ──────────────────────────────────────────────────────────────────────
# SOURCE_REQUIRED_SECTION
# ──────────────────────────────────────────────────────────────────────

def check_source_required_section(tables) -> list[Finding]:
    """A topic missing its goal or its excluded scope is a topic nobody can
    judge the rest of the package against."""
    findings: list[Finding] = []
    scope_by_topic: dict[str, set[str]] = defaultdict(set)
    for row in tables.get("Topic_Scope", []):
        scope_by_topic[_text(row.get("topic_id"))].add(_text(row.get("scope_type")))

    for row in tables.get("Topics", []):
        topic_id = _text(row.get("topic_id"))
        for column in ("topic_id", "topic_title", "learning_goal"):
            if not _text(row.get(column)):
                findings.append(_fail(
                    "SOURCE_REQUIRED_SECTION", "Topics", topic_id or None,
                    f"{column} is empty",
                    "Re-parse the topic document; the section it comes from "
                    "is missing or was not recognised",
                ))
        for scope_type in (ScopeType.INCLUDED.value, ScopeType.EXCLUDED.value):
            if scope_type not in scope_by_topic.get(topic_id, set()):
                findings.append(_fail(
                    "SOURCE_REQUIRED_SECTION", "Topic_Scope", topic_id or None,
                    f"no {scope_type} scope items",
                    f"Without {scope_type} scope the SCOPE_EXCLUSION check "
                    f"cannot run for this topic",
                ))
    return findings


# ──────────────────────────────────────────────────────────────────────
# UNIQUE_ID and FOREIGN_KEY, driven by the schema itself
# ──────────────────────────────────────────────────────────────────────

def check_unique_id(tables) -> list[Finding]:
    """A duplicate id is worse than a missing one: a reference to it resolves,
    silently, to whichever row is found first."""
    findings: list[Finding] = []
    for table, schema in TABLE_SCHEMAS.items():
        rows = tables.get(table, [])
        for column, details in schema["column_details"].items():
            if not details.get("unique"):
                continue
            counts = Counter(row[column] for row in rows
                             if row.get(column) is not None)
            for value, count in counts.items():
                if count > 1:
                    findings.append(_fail(
                        "UNIQUE_ID", table, str(value),
                        f"{column} appears {count} times",
                        "Two rows share an id; references to it resolve to "
                        "whichever comes first",
                    ))
    return findings


def check_foreign_key(tables) -> list[Finding]:
    """Every declared foreign key resolves.

    The schema declares 34 of them, so a table added later is checked without
    anyone remembering to add it here.
    """
    findings: list[Finding] = []
    for table, schema in TABLE_SCHEMAS.items():
        rows = tables.get(table, [])
        for column, (target_table, target_column) in (
            schema.get("foreign_keys") or {}
        ).items():
            target_rows = tables.get(target_table)

            # A sheet that is not in the file at all is one problem, not one
            # per referencing row. The platform's export has no topics sheet,
            # which as 18 separate dangling-id findings reads like 18 bad ids
            # and is actually one missing table.
            if target_rows is None and rows:
                findings.append(_fail(
                    "FOREIGN_KEY", table, None,
                    f"{column} points at {target_table}, which is not in this "
                    f"workbook at all",
                    f"Nothing here can resolve; either the sheet was omitted "
                    f"from the export or {table} should not have been written",
                ))
                continue

            known = {row.get(target_column)
                     for row in (target_rows or [])
                     if row.get(target_column) is not None}
            dangling = Counter(row[column] for row in rows
                               if row.get(column) is not None
                               and row[column] not in known)
            for value, count in dangling.items():
                findings.append(_fail(
                    "FOREIGN_KEY", table, str(value),
                    f"{column}={value!r} does not exist in "
                    f"{target_table}.{target_column}"
                    + (f" ({count} rows)" if count > 1 else ""),
                    f"Either the {target_table} row was dropped after this "
                    f"one was written, or the id was invented",
                ))
    return findings


# ──────────────────────────────────────────────────────────────────────
# ONE_PRIMARY_SKILL and WEIGHT_SUM
# ──────────────────────────────────────────────────────────────────────

#: Both mapping tables, not just the question one. The specification says
#: "each question AND WORKED EXAMPLE", and Worked_Example_MicroSkills carries
#: its own weight and is_primary columns.
#: (mapping table, its owner column, the table the owners come FROM).
#:
#: That third element is the whole point. Counting primaries per mapping row
#: only ever sees things that HAVE a mapping row, so a question mapped to
#: nothing at all is invisible to the count and passes. The owners have to be
#: taken from the parent table, not from the mapping.
SKILL_MAPPINGS = (
    ("Question_MicroSkills", "question_id", "Questions"),
    ("Worked_Example_MicroSkills", "worked_example_id", "Worked_Examples"),
)


def check_one_primary_skill(tables) -> list[Finding]:
    findings: list[Finding] = []
    for table, owner_column, owner_table in SKILL_MAPPINGS:
        primaries: Counter = Counter()
        for row in tables.get(table, []):
            owner = _text(row.get(owner_column))
            if owner and row.get("is_primary") is True:
                primaries[owner] += 1

        owners = {_text(row.get(owner_column))
                  for row in tables.get(owner_table, [])
                  if _text(row.get(owner_column))}

        for owner in sorted(owners):
            count = primaries[owner]
            if count != 1:
                findings.append(_fail(
                    "ONE_PRIMARY_SKILL", table, owner,
                    f"has {count} primary micro-skill(s); exactly one is "
                    f"required",
                    "With none, answering it tells the student model "
                    "nothing; with several, no skill is credited cleanly",
                ))
    return findings


def check_weight_sum(tables) -> list[Finding]:
    findings: list[Finding] = []
    for table, owner_column, _owner_table in SKILL_MAPPINGS:
        totals: dict[str, float] = defaultdict(float)
        for row in tables.get(table, []):
            owner = _text(row.get(owner_column))
            if not owner:
                continue
            try:
                totals[owner] += float(row.get("weight") or 0)
            except (TypeError, ValueError):
                findings.append(_fail(
                    "WEIGHT_SUM", table, owner,
                    f"weight {row.get('weight')!r} is not a number",
                    "Write weight as a number, not text",
                ))
        for owner, total in sorted(totals.items()):
            if abs(total - REQUIRED_WEIGHT) > WEIGHT_TOLERANCE:
                findings.append(_fail(
                    "WEIGHT_SUM", table, owner,
                    f"weights total {total:g}, not {REQUIRED_WEIGHT}",
                    "Credit for one answer must add up to exactly one skill's "
                    "worth",
                ))
    return findings


# ──────────────────────────────────────────────────────────────────────
# The answer key
# ──────────────────────────────────────────────────────────────────────

def check_question_has_answer(tables) -> list[Finding]:
    """Exactly one. Zero is unmarkable; two is ambiguous."""
    findings: list[Finding] = []
    per_question = Counter(_text(row.get("question_id"))
                           for row in tables.get("Answer_Specs", [])
                           if _text(row.get("question_id")))

    for row in tables.get("Questions", []):
        question_id = _text(row.get("question_id"))
        if not question_id:
            continue
        count = per_question.get(question_id, 0)
        if count != 1:
            findings.append(_fail(
                "QUESTION_HAS_ANSWER", "Answer_Specs", question_id,
                f"has {count} answer specs; exactly one is required",
                "A question with no key cannot be marked; one with two can "
                "be marked two ways",
            ))
    return findings


def check_accepted_wrong_disjoint(tables) -> list[Finding]:
    """Zero violations in 54 approved reference rows, so this is an invariant
    rather than a preference. Compared on normalised forms, so a hyphen and a
    Unicode minus are recognised as the same answer."""
    findings: list[Finding] = []
    for row in tables.get("Answer_Specs", []):
        accepted = {_normalise(a) for a in _split(row.get("accepted_answers"))}
        wrong = {_normalise(w) for w in _split(row.get("common_wrong_answers"))}
        overlap = accepted & wrong
        if overlap:
            findings.append(_fail(
                "ACCEPTED_WRONG_DISJOINT", "Answer_Specs",
                _text(row.get("answer_spec_id")),
                f"{sorted(overlap)} appear as both accepted and wrong",
                "A marker would contradict itself; a student giving this "
                "answer could be marked either way",
            ))
    return findings


def check_answer_steps_complete(tables) -> list[Finding]:
    """The half that is checkable: steps exist and are numbered in order.

    Whether they reach the canonical answer is arithmetic, and belongs to
    CG-021.
    """
    findings: list[Finding] = []
    step_re = re.compile(r"^\s*(\d+)\s*[.)]")

    for row in tables.get("Answer_Specs", []):
        spec_id = _text(row.get("answer_spec_id"))
        steps = [s for s in _text(row.get("answer_steps")).splitlines()
                 if s.strip()]
        if not steps:
            findings.append(_fail(
                "ANSWER_STEPS_COMPLETE", "Answer_Specs", spec_id,
                "answer_steps is empty",
                "The tutor reads these aloud when a student asks how; with "
                "none it has nothing to say",
            ))
            continue

        numbers = [int(m.group(1)) for m in
                   (step_re.match(s) for s in steps) if m]
        if numbers and numbers != list(range(1, len(numbers) + 1)):
            findings.append(_fail(
                "ANSWER_STEPS_COMPLETE", "Answer_Specs", spec_id,
                f"steps are numbered {numbers}, not 1..{len(numbers)}",
                "A gap or repeat means a step was lost or duplicated",
            ))
    return findings


# ──────────────────────────────────────────────────────────────────────
# Phase rules
# ──────────────────────────────────────────────────────────────────────

def _usage_with_questions(tables):
    """Each usage row paired with its question, skipping any that dangle.

    A missing question is FOREIGN_KEY's finding to report, not this one's.
    Two rules reporting the same row twice makes a report harder to act on.
    """
    questions = {_text(r.get("question_id")): r
                 for r in tables.get("Questions", [])}
    for usage in tables.get("Question_Usage", []):
        question = questions.get(_text(usage.get("question_id")))
        if question is not None:
            yield usage, question


def check_phase0_format(tables) -> list[Finding]:
    """A diagnostic exists to measure, so it must be markable with certainty
    and must not be helped."""
    findings: list[Finding] = []
    for usage, question in _usage_with_questions(tables):
        if _text(usage.get("phase")) != Phase.PHASE_0_DIAGNOSTIC.value:
            continue
        question_id = _text(question.get("question_id"))

        if _text(question.get("question_type")) != QuestionType.SINGLE_CHOICE.value:
            findings.append(_fail(
                "PHASE0_FORMAT", "Questions", question_id,
                f"Phase 0 question is {question.get('question_type')!r}, not "
                f"SINGLE_CHOICE",
                "A diagnostic must be markable with certainty before any "
                "teaching has happened",
            ))
        if _text(usage.get("support_allowed")) != \
                SupportAllowed.NO_SUPPORT_DURING_ATTEMPT.value:
            findings.append(_fail(
                "PHASE0_FORMAT", "Question_Usage", question_id,
                f"Phase 0 allows support ({usage.get('support_allowed')!r})",
                "Support during a diagnostic measures the support, not the "
                "student",
            ))
    return findings


def check_phase3_canvas_only(tables) -> list[Finding]:
    """Phase 3 is worked on the canvas with no help, so the answer has to be
    something the platform can mark: a calculation, an expression or a chosen
    option. Never a sentence."""
    findings: list[Finding] = []
    for usage, question in _usage_with_questions(tables):
        if _text(usage.get("phase")) != Phase.PHASE_3_INDEPENDENT_PRACTICE.value:
            continue
        text = _text(question.get("question_text"))
        match = PROSE_RE.search(text)
        if match:
            findings.append(_fail(
                "PHASE3_CANVAS_ONLY", "Questions",
                _text(question.get("question_id")),
                f"asks for free-form prose ({match.group(0)!r})",
                "Convert to a structured classification, a calculation or a "
                "chosen option",
            ))
    return findings


def check_phase3_no_support(tables) -> list[Finding]:
    findings: list[Finding] = []
    scaffolded = {_text(r.get("question_id"))
                  for r in tables.get("Question_Scaffolds", [])}

    for usage, question in _usage_with_questions(tables):
        if _text(usage.get("phase")) != Phase.PHASE_3_INDEPENDENT_PRACTICE.value:
            continue
        question_id = _text(question.get("question_id"))

        if _text(usage.get("support_allowed")) != \
                SupportAllowed.NO_SUPPORT_DURING_ATTEMPT.value:
            findings.append(_fail(
                "PHASE3_NO_SUPPORT", "Question_Usage", question_id,
                f"Phase 3 allows support ({usage.get('support_allowed')!r})",
                "Independent practice is where we find out whether the "
                "teaching worked, which requires no help",
            ))
        if question_id in scaffolded:
            findings.append(_fail(
                "PHASE3_NO_SUPPORT", "Question_Scaffolds", question_id,
                "Phase 3 question has a scaffold attached",
                "A scaffold walks the student through the method, which is "
                "the opposite of independent practice",
            ))
    return findings


def check_scaffold_match(tables) -> list[Finding]:
    """The mechanical half: a scaffold is attached to the skill its question
    actually tests, and it exists in a phase that permits scaffolding."""
    findings: list[Finding] = []
    primary_skill = {
        _text(r.get("question_id")): _text(r.get("micro_skill_id"))
        for r in tables.get("Question_MicroSkills", [])
        if r.get("is_primary") is True
    }
    phase_of = {_text(r.get("question_id")): _text(r.get("phase"))
                for r in tables.get("Question_Usage", [])}

    for row in tables.get("Question_Scaffolds", []):
        question_id = _text(row.get("question_id"))
        attached = _text(row.get("micro_skill_id"))
        expected = primary_skill.get(question_id)

        if expected and attached and attached != expected:
            findings.append(_fail(
                "SCAFFOLD_MATCH", "Question_Scaffolds", question_id,
                f"scaffold is for {attached}, but the question's primary "
                f"skill is {expected}",
                "The scaffold would teach a method for a skill this question "
                "does not test",
            ))

        phase = phase_of.get(question_id)
        if phase and not PHASE_RULES.get(phase, {}).get("scaffold_allowed", True):
            findings.append(_fail(
                "SCAFFOLD_MATCH", "Question_Scaffolds", question_id,
                f"scaffold attached to a {phase} question, which forbids "
                f"scaffolding",
                "Remove the scaffold mapping or move the question to a phase "
                "that permits support",
            ))
    return findings


# ──────────────────────────────────────────────────────────────────────
# SCOPE_EXCLUSION
# ──────────────────────────────────────────────────────────────────────

def scope_terms(item_text: str) -> set[str]:
    """The distinctive words of one excluded scope item.

    Ordinary words are dropped, because an excluded item reading "solving
    linear equations" must not flag every question containing "the".
    """
    words = re.findall(r"[a-z]+", _text(item_text).lower())
    return {w for w in words
            if len(w) >= MIN_SCOPE_TERM_LENGTH and w not in SCOPE_STOP_WORDS}


def check_scope_exclusion(tables) -> list[Finding]:
    """Warnings, not blocking failures.

    A term from the excluded list appearing in a question is evidence that
    something crossed a boundary, not proof: "equation" appears in "this is an
    expression, not an equation", which is squarely in scope. Blocking on a
    keyword would train everyone to ignore the rule. A person reads these, and
    CG-021 gets the judgement version.
    """
    findings: list[Finding] = []
    excluded: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)
    for row in tables.get("Topic_Scope", []):
        if _text(row.get("scope_type")) != ScopeType.EXCLUDED.value:
            continue
        terms = scope_terms(row.get("item_text"))
        if terms:
            excluded[_text(row.get("topic_id"))].append(
                (_text(row.get("item_text")), terms))

    for row in tables.get("Questions", []):
        topic_id = _text(row.get("topic_id"))
        if topic_id not in excluded:
            continue
        words = set(re.findall(r"[a-z]+", _text(row.get("question_text")).lower()))
        for item_text, terms in excluded[topic_id]:
            hits = terms & words
            if len(hits) >= 2:
                findings.append(_warn(
                    "SCOPE_EXCLUSION", "Questions", _text(row.get("question_id")),
                    f"mentions {sorted(hits)}, which appear in the excluded "
                    f"scope item {item_text!r}",
                    "Read the question; a shared word is not proof it "
                    "crosses the boundary",
                ))
    return findings


# ──────────────────────────────────────────────────────────────────────
# The mapping tables
# ──────────────────────────────────────────────────────────────────────

def check_no_error_conflict(tables) -> list[Finding]:
    """One response, one diagnosis.

    If the same wrong answer to the same question maps to two errors, the
    tutor cannot know which misconception to re-teach, so it will pick one
    arbitrarily and may teach against a belief the student does not hold.
    """
    findings: list[Finding] = []
    codes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in tables.get("Question_Error_Map", []):
        key = (_text(row.get("question_id")), _text(row.get("response_pattern")))
        if all(key):
            codes[key].add(_text(row.get("error_code")))

    for (question_id, pattern), found in sorted(codes.items()):
        if len(found) > 1:
            findings.append(_fail(
                "NO_ERROR_CONFLICT", "Question_Error_Map", question_id,
                f"response {pattern!r} maps to {sorted(found)}",
                "The tutor cannot know which misconception to re-teach, so "
                "it will pick one arbitrarily",
            ))
    return findings


def check_mapping_complete(tables) -> list[Finding]:
    """Mapping rows must point at parents that are switched on.

    FOREIGN_KEY already proves the parent exists. This is the other half: a
    row referencing an inactive parent resolves and still does nothing, which
    is harder to notice than a dangling id.
    """
    findings: list[Finding] = []
    inactive: dict[str, set[str]] = {}
    for table, schema in TABLE_SCHEMAS.items():
        if "active" not in schema["columns"]:
            continue
        key = next((c for c, d in schema["column_details"].items()
                    if d.get("unique")), None)
        if key is None:
            continue
        inactive[table] = {_text(r.get(key)) for r in tables.get(table, [])
                           if r.get("active") is False}

    for table, schema in TABLE_SCHEMAS.items():
        if not table.count("_"):
            continue
        for column, (target_table, _column) in (
            schema.get("foreign_keys") or {}
        ).items():
            switched_off = inactive.get(target_table)
            if not switched_off:
                continue
            for row in tables.get(table, []):
                value = _text(row.get(column))
                if value and value in switched_off:
                    findings.append(_fail(
                        "MAPPING_COMPLETE", table, value,
                        f"{column} points at {target_table}.{value}, which is "
                        f"inactive",
                        "The reference resolves but the parent is switched "
                        "off, so this mapping can never fire",
                    ))
    return findings


# ──────────────────────────────────────────────────────────────────────
# WORKED_EXAMPLE_CORRECT, the ordering half
# ──────────────────────────────────────────────────────────────────────

def check_worked_example_correct(tables) -> list[Finding]:
    """Step numbering. Whether the mathematics holds is CG-021's.

    Two conventions are in play and the check has to survive both. We write
    one worked example per topic with its steps numbered 1..N. The platform's
    own export writes one worked example PER STEP: T01 has seven of them,
    each holding a single step, numbered by its position in the topic rather
    than within the example.

    So a single-step example numbered 5 is the platform being itself, not a
    fault, and checking "starts at 1" against it would fail 19 rows of
    approved data. What is always wrong, under either convention, is a repeat
    or a gap inside a multi-step example.

    The shape difference is real and is not this rule's to settle. It is
    recorded for CG-023, the golden reference comparison.
    """
    findings: list[Finding] = []
    steps: dict[str, list[int]] = defaultdict(list)
    for row in tables.get("Worked_Example_Steps", []):
        example_id = _text(row.get("worked_example_id"))
        try:
            steps[example_id].append(int(row.get("step_no")))
        except (TypeError, ValueError):
            findings.append(_fail(
                "WORKED_EXAMPLE_CORRECT", "Worked_Example_Steps", example_id,
                f"step_no {row.get('step_no')!r} is not a number",
                "Steps are played in order, which needs a number",
            ))

    for example_id, numbers in sorted(steps.items()):
        repeated = sorted(n for n, count in Counter(numbers).items() if count > 1)
        if repeated:
            findings.append(_fail(
                "WORKED_EXAMPLE_CORRECT", "Worked_Example_Steps", example_id,
                f"step_no {repeated} used more than once",
                "Two steps claiming the same position play in an order "
                "nothing decides",
            ))
            continue

        if len(numbers) > 1 and sorted(numbers) != list(
            range(min(numbers), min(numbers) + len(numbers))
        ):
            findings.append(_fail(
                "WORKED_EXAMPLE_CORRECT", "Worked_Example_Steps", example_id,
                f"steps are numbered {sorted(numbers)}, which has a gap",
                "A gap means a step was lost between generation and writing",
            ))
    return findings


# ──────────────────────────────────────────────────────────────────────
# Ours: coverage, reachability, approval
# ──────────────────────────────────────────────────────────────────────

def check_coverage_plan(tables) -> list[Finding]:
    """Every micro-skill has its seven questions.

    Not in section 12.1. It is here because the content review's headline
    finding was 26 of 53 micro-skills with no primary question, and no rule in
    the specification would have caught that.
    """
    usage = {_text(r.get("question_id")): r
             for r in tables.get("Question_Usage", [])
             if _text(r.get("question_id"))}
    difficulty = {_text(r.get("question_id")): r.get("difficulty")
                  for r in tables.get("Questions", [])}

    by_skill: dict[str, list] = {
        _text(row.get("micro_skill_id")): []
        for row in tables.get("Micro_Skills", [])
        if _text(row.get("micro_skill_id"))
    }
    for row in tables.get("Question_MicroSkills", []):
        question_id = _text(row.get("question_id"))
        skill_id = _text(row.get("micro_skill_id"))
        if skill_id not in by_skill or question_id not in usage:
            continue
        try:
            phase = Phase(_text(usage[question_id].get("phase")))
        except ValueError:
            continue
        by_skill[skill_id].append((phase, difficulty.get(question_id)))

    return [
        _fail("COVERAGE_PLAN", "Questions", skill_id,
              f"missing {', '.join(str(s) for s in gaps)}",
              "The skill cannot be measured at that phase and difficulty")
        for skill_id, gaps in coverage_report(by_skill).items()
    ]


#: Which table MUST point at a row, not merely whether SOME table does. A
#: question with a micro-skill mapping but no usage row is referenced by
#: something and still never shown to anyone, so "is anything referencing
#: this?" would call it reachable and be wrong.
REACHABILITY = (
    ("Questions", "question_id", "Question_Usage", "question_id",
     "a question in no usage row is never shown to anyone"),
    ("Hints", "hint_id", "Misconception_Hints", "hint_id",
     "a hint linked to no misconception can never be offered"),
    ("Visual_Cues", "visual_cue_id", "Misconception_VisualCues", "visual_cue_id",
     "a cue linked to no misconception can never be shown"),
    ("Scaffolds", "scaffold_id", "Question_Scaffolds", "scaffold_id",
     "a scaffold attached to no question can never start"),
)


def check_unreachable_row(tables) -> list[Finding]:
    findings: list[Finding] = []
    for table, column, by_table, by_column, why in REACHABILITY:
        pointed_at = {_text(r.get(by_column)) for r in tables.get(by_table, [])
                      if _text(r.get(by_column))}
        for row in tables.get(table, []):
            value = _text(row.get(column))
            if value and value not in pointed_at:
                findings.append(_fail(
                    "UNREACHABLE_ROW", table, value, why,
                    f"Either add the {by_table} row or drop this one; as "
                    f"written it is content nobody will ever see",
                ))
    return findings


#: The model reasoning out loud, left in a field the platform imports.
#:
#: Three of these reached the file on the smoke run of 8 September:
#:
#:    answer_steps      "...14 + 3 = 17? Recheck options: a)15 b)17 c)19..."
#:    answer_steps      "...Wait, the difference is..."
#:    accepted_answers  "50,60 | 50 60 | 50 and 60 | 60, 70? (incorrect)"
#:
#: The last one is the dangerous kind. A student who types
#: "60, 70? (incorrect)" is marked CORRECT, because the string sits in the
#: accepted list. The other two are a tutor reading the model's second
#: thoughts aloud to a child.
#:
#: Each pattern is anchored so ordinary prose does not trip it: "wait" needs
#: its comma, "(incorrect)" its brackets. A question may legitimately say
#: "wait at the bus stop".
#: The bracketed form was too tight at first. It required the brackets to hold
#: nothing but the word, so it caught "(incorrect)" on 8 September and missed
#: "(incorrect variant not accepted)" on 9 September -- the same annotation,
#: sitting in the same field, doing the same damage. Now any bracket
#: containing the word counts.
DELIBERATION_RE = re.compile(
    r"(?:"
    r"\([^)]*\b(?:in)?correct\b[^)]*\)"
    r"|\([^)]*\bnot accepted\b[^)]*\)"
    r"|\bwait\s*,"
    r"|\brecheck\b"
    r"|\blet me (?:re)?(?:check|think|reconsider)"
    r"|\bon second thought"
    r"|\bactually\s*,\s*(?:no|wait|the)"
    r"|\bhmm+\b"
    r"|\bi (?:think|should|need to) (?:re)?check"
    r"|\bcorrection\s*:"
    r"|\bignore (?:that|the above)"
    r")",
    re.IGNORECASE,
)

#: Where it would do damage. Every one of these is either shown to a student
#: or used to mark their work.
DELIBERATION_FIELDS = (
    ("Answer_Specs", "answer_spec_id",
     ("canonical_answer", "accepted_answers", "common_wrong_answers",
      "answer_steps")),
    ("Questions", "question_id", ("question_text",)),
    ("Hints", "hint_id", ("content",)),
    ("Worked_Example_Steps", "worked_example_step_id",
     ("screen_content", "narration_text")),
    ("Scaffold_Steps", "scaffold_step_id",
     ("prompt", "partial_content", "expected_response")),
    ("Parallel_Examples", "parallel_example_id",
     ("problem_statement", "worked_steps", "final_answer")),
)


def check_no_deliberation_in_content(tables) -> list[Finding]:
    """The model's working-out, left in a field the platform imports."""
    findings: list[Finding] = []
    for table, key_column, columns in DELIBERATION_FIELDS:
        for row in tables.get(table, []):
            for column in columns:
                match = DELIBERATION_RE.search(_text(row.get(column)))
                if not match:
                    continue
                findings.append(_fail(
                    "NO_DELIBERATION_IN_CONTENT", table,
                    _text(row.get(key_column)),
                    f"{column} contains {match.group(0)!r}, which is the "
                    f"model thinking rather than content",
                    "A student either reads this or is marked against it. "
                    "Regenerate the row",
                ))
                break          # one finding per row is enough to act on
    return findings


#: "b4" -- a single variable with digits after it.
REVERSED_NOTATION_RE = re.compile(r"^([a-z])(\d+)$")


def check_standard_notation(tables) -> list[Finding]:
    """An answer key that accepts the coefficient written after the variable.

    In standard algebraic notation the coefficient comes first: 4b, not b4.
    "b4" reads as a two-digit numeral, and a marker that accepts it teaches a
    student the convention does not matter.

    The run of 9 September accepted BOTH forms in ten answer keys -- 'b4'
    alongside '4b', 'x5' alongside '5x'. Listing both is the model hedging,
    and one of the two is wrong. That pairing is the condition checked here,
    because it is unambiguous: a lone "b4" might conceivably be a variable
    name, but "4b or b4, either is fine" cannot be right.

    The semantic reviewer found six of the ten. This finds all ten, free, on
    every run.
    """
    findings: list[Finding] = []
    for row in tables.get("Answer_Specs", []):
        accepted = _split(row.get("accepted_answers"))
        forms = {_normalise(a) for a in accepted}
        forms.add(_normalise(row.get("canonical_answer")))

        for entry in accepted:
            match = REVERSED_NOTATION_RE.match(_normalise(entry))
            if not match:
                continue
            letter, digits = match.group(1), match.group(2)
            if f"{digits}{letter}" not in forms:
                continue
            findings.append(_fail(
                "STANDARD_NOTATION", "Answer_Specs",
                _text(row.get("answer_spec_id")),
                f"accepts {entry!r} as well as {(digits + letter)!r}; the "
                f"coefficient belongs before the variable",
                f"Remove {entry!r} from accepted_answers. A marker that takes "
                f"both teaches the convention does not matter",
            ))
            break
    return findings


def check_nothing_approved(tables) -> list[Finding]:
    """Nothing this pipeline produces has been read by a person, so nothing
    may claim it has."""
    findings: list[Finding] = []
    for table in ("Questions", "Worked_Examples", "Micro_Skills", "Topics"):
        approved = [r for r in tables.get(table, [])
                    if _text(r.get("status")) == "APPROVED"]
        if approved:
            findings.append(_fail(
                "NOTHING_APPROVED", table, None,
                f"{len(approved)} row(s) marked APPROVED",
                "Nothing may be approved until CG-021 and a human review "
                "have run",
            ))
    return findings


# ──────────────────────────────────────────────────────────────────────
# Running them all
# ──────────────────────────────────────────────────────────────────────

CHECKS = {
    "SOURCE_REQUIRED_SECTION": check_source_required_section,
    "UNIQUE_ID": check_unique_id,
    "FOREIGN_KEY": check_foreign_key,
    "ONE_PRIMARY_SKILL": check_one_primary_skill,
    "WEIGHT_SUM": check_weight_sum,
    "QUESTION_HAS_ANSWER": check_question_has_answer,
    "ACCEPTED_WRONG_DISJOINT": check_accepted_wrong_disjoint,
    "ANSWER_STEPS_COMPLETE": check_answer_steps_complete,
    "PHASE0_FORMAT": check_phase0_format,
    "PHASE3_CANVAS_ONLY": check_phase3_canvas_only,
    "PHASE3_NO_SUPPORT": check_phase3_no_support,
    "SCAFFOLD_MATCH": check_scaffold_match,
    "SCOPE_EXCLUSION": check_scope_exclusion,
    "NO_ERROR_CONFLICT": check_no_error_conflict,
    "MAPPING_COMPLETE": check_mapping_complete,
    "WORKED_EXAMPLE_CORRECT": check_worked_example_correct,
    "COVERAGE_PLAN": check_coverage_plan,
    "UNREACHABLE_ROW": check_unreachable_row,
    "NOTHING_APPROVED": check_nothing_approved,
    "NO_DELIBERATION_IN_CONTENT": check_no_deliberation_in_content,
    "STANDARD_NOTATION": check_standard_notation,
}


def declared_limits() -> list[Finding]:
    """One INFO finding per rule this module cannot fully decide.

    The report then enumerates all 17 and says out loud which of them were
    not settled here, rather than a reader assuming silence means pass.
    """
    return [
        Finding(rule.code, INFO, "-", None,
                f"not fully checked here: {rule.undecidable}",
                "CG-021's semantic pass, or a human reviewer",
                blocking=False)
        for rule in RULES.values()
        if rule.coverage in (PARTIAL, NONE) and rule.undecidable
    ]


#: Local rules that describe what OUR pipeline owes, not what any workbook
#: must be. The approved reference legitimately breaks both: it predates the
#: seven-question plan, and it is approved content, which is the one thing we
#: are never allowed to claim. Running them against it would report 24
#: failures that are all correct behaviour by the other party.
ONLY_FOR_GENERATED = frozenset({
    "COVERAGE_PLAN", "NOTHING_APPROVED", "NO_DELIBERATION_IN_CONTENT",
    "STANDARD_NOTATION",
})


def validate_tables(tables: dict[str, list[dict]], *,
                    generated: bool = True) -> Report:
    """Every rule, against tables already read.

    Set generated=False for a workbook we did not produce, which skips the
    rules that only make sense about our own output.
    """
    findings: list[Finding] = []
    for code, check in CHECKS.items():
        if not generated and code in ONLY_FOR_GENERATED:
            continue
        findings.extend(check(tables))
    findings.extend(declared_limits())
    return Report(findings)


def validate(path: str | Path, *, generated: bool = True) -> Report:
    """Every rule, against a written workbook."""
    report = validate_tables(read_tables(path), generated=generated)
    report.source = str(path)
    return report


def summarise(report: Report, limit: int = 40) -> str:
    """A short account of what a validation run found."""
    header = f"{Path(report.source).name}: " if report.source else ""
    blocking = report.blocking
    warnings = report.warnings

    if not blocking and not warnings:
        return (f"{header}all {len(SPEC_RULES)} specification checks and "
                f"{len(LOCAL_RULES)} local checks pass.")

    counts = Counter(f.rule_code for f in blocking)
    lines = [
        f"{header}{len(blocking)} blocking, {len(warnings)} warning(s)."
    ]
    if counts:
        lines.append("  " + ", ".join(f"{code} x{n}"
                                      for code, n in counts.most_common()))
    lines.append("")
    for finding in (blocking + warnings)[:limit]:
        lines.append(f"  {finding}")
    if len(blocking) + len(warnings) > limit:
        lines.append(f"  ... and {len(blocking) + len(warnings) - limit} more")

    not_checked = [r.code for r in RULES.values() if r.coverage == NONE]
    if not_checked:
        lines.append("")
        lines.append(f"  not decidable here: {', '.join(not_checked)}")
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("usage: python validator.py <workbook.xlsx> [--json]")
        raise SystemExit(2)

    result = validate(sys.argv[1])
    if "--json" in sys.argv:
        print(json.dumps(result.as_dicts(), indent=2))
    else:
        print(summarise(result))
    raise SystemExit(1 if result.blocking else 0)
