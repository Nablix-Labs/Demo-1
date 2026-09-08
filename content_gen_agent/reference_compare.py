"""CG-023: compare a generated workbook with the approved reference.

The roadmap asks for a golden reference test on Topics 1 to 3, with the
acceptance criterion "schema, scope, phase rules, relationships match
reference". So the comparison is of SHAPE, not of rows.

Row equality is not available and would not be wanted. Our questions are
different questions with different ids; a generator that reproduced the
reference exactly would be a copier, not a generator. What can be compared is
everything about the shape of the output: which sheets exist and in what
column order, how many questions a micro-skill gets, how many skills a
question credits, how the phases and difficulties are spread, how many steps
a worked example has.

Not every difference is a defect
--------------------------------

This is the same problem CG-008 has with parsed topic fields, and it is
handled the same way, because the alternative is worse. A comparison that
reports every difference equally means the first reader concludes the
generator is broken, and the second reader stops reading.

    MATCH        the same, within the tolerance stated for that measure
    INTENTIONAL  different on purpose, with the decision recorded below
    DIVERGES     different and nobody has explained why -- the only kind
                 worth investigating

`unexplained()` returns the last kind, and that is the number to watch.

The intentional ones matter most
---------------------------------

Three of them come straight from the content review, and they are large. The
reference gives a micro-skill 2.45 questions; we give it 7. The reference maps
a question to 1.87 micro-skills; we map it to exactly 1. The reference uses
two difficulty levels; we use three.

On those measures we deliberately disagree with approved content, because the
review told us to. Recording that here, with the reason, is the difference
between a comparison that documents a decision and one that reads as 3
failures against the gold standard.

One divergence is NOT intentional and is the useful output of this module: the
reference writes one worked example PER STEP -- 22 examples, 22 steps, exactly
one each -- and we write one per topic with several steps. Same content,
different shape, and it will matter when the platform imports it.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from openpyxl import load_workbook

from table_schemas import TABLE_SCHEMAS, export_name

MATCH, INTENTIONAL, DIVERGES = "MATCH", "INTENTIONAL", "DIVERGES"

#: How far a ratio may drift before it counts as a difference. Generated
#: content is not deterministic, so demanding equality of an average would
#: report noise as news.
DEFAULT_TOLERANCE = 0.15


@dataclass(frozen=True)
class Decision:
    """A difference we chose, and why."""

    reason: str
    source: str


#: Divergences that are decisions, not defects. Each names where it was
#: decided, so the next person can go and check rather than take it on trust.
DECIDED: dict[str, Decision] = {
    "questions per micro-skill": Decision(
        "The review set a minimum of seven questions per micro-skill: one "
        "diagnostic, three guided, three independent. The reference predates "
        "it and averages 2.45.",
        "Manjusha's content review, and coverage_plan.plan_for_skill",
    ),
    "micro-skills credited per question": Decision(
        "Exactly one, primary, at weight 1.0. The reference's 1.87 average "
        "comes from 46 secondary mappings, which the review named as a "
        "finding: a question crediting several skills at partial weight "
        "credits none of them cleanly.",
        "Manjusha's content review; enforced by validator ONE_PRIMARY_SKILL",
    ),
    "share of mappings that are primary": Decision(
        "The same decision seen from the other side. If a question credits "
        "exactly one skill, every mapping row is that skill and the share is "
        "1.0. The reference's 0.54 is 46 secondary rows among 101.",
        "Manjusha's content review; enforced by validator ONE_PRIMARY_SKILL",
    ),
    "difficulty levels used": Decision(
        "The plan places one question at each of difficulties 1, 2 and 3 in "
        "guided practice. The reference only ever uses 1 and 2, so the third "
        "level existed in the schema and nowhere in the data.",
        "coverage_plan.GUIDED_ROLE_BY_DIFFICULTY",
    ),
    "phase spread": Decision(
        "Follows from the plan's 1 diagnostic, 3 guided, 3 independent per "
        "skill. The reference is weighted towards diagnostics because it was "
        "assembled per topic rather than per skill.",
        "coverage_plan.plan_for_skill",
    ),
    "TRUE_FALSE_WITH_EXPLANATION used": Decision(
        "Suppressed in generation because it appears nowhere in the approved "
        "reference. Agreeing with the reference here is the point, and it is "
        "an open question for Manjusha rather than a settled one.",
        "skill_question_generator.SUPPRESSED_QUESTION_TYPES",
    ),
}


@dataclass(frozen=True)
class Measure:
    """One thing compared, and what came of it."""

    name: str
    reference: object
    generated: object
    status: str
    detail: str = ""

    @property
    def decision(self) -> Optional[Decision]:
        return DECIDED.get(self.name)

    def __str__(self) -> str:
        return (f"[{self.status:11}] {self.name}: reference {self.reference}, "
                f"generated {self.generated}"
                + (f" -- {self.detail}" if self.detail else ""))


@dataclass
class Comparison:
    """Everything one comparison found."""

    measures: list[Measure] = field(default_factory=list)
    reference_source: Optional[str] = None
    generated_source: Optional[str] = None

    def unexplained(self) -> list[Measure]:
        """The only kind worth investigating."""
        return [m for m in self.measures if m.status == DIVERGES]

    def intentional(self) -> list[Measure]:
        return [m for m in self.measures if m.status == INTENTIONAL]

    def by_status(self) -> Counter:
        return Counter(m.status for m in self.measures)


# ──────────────────────────────────────────────────────────────────────
# Reading either naming convention
# ──────────────────────────────────────────────────────────────────────

def read_any(path: str | Path) -> dict[str, list[dict]]:
    """Rows keyed by internal table name, whichever convention the file uses.

    The approved reference names its sheets in TitleCase (Micro_Skills) and
    the platform export in snake_case (micro_skills). A reader that knew only
    one of them would return an empty dict for the other and every comparison
    would come back as "0 versus 0", which reads as agreement.
    """
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        wanted: dict[str, str] = {}
        for internal in TABLE_SCHEMAS:
            wanted[export_name(internal).lower()] = internal
            wanted[internal.lower()] = internal

        tables: dict[str, list[dict]] = {}
        for sheet in workbook.sheetnames:
            internal = wanted.get(sheet.lower())
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


def _ratio(numerator: int, denominator: int) -> Optional[float]:
    return round(numerator / denominator, 2) if denominator else None


def _share(counts: Counter, total: int) -> dict:
    return {k: round(v / total, 2) for k, v in sorted(counts.items())} if total else {}


# ──────────────────────────────────────────────────────────────────────
# The measures
# ──────────────────────────────────────────────────────────────────────

def m_questions_per_skill(tables) -> Optional[float]:
    return _ratio(len(tables.get("Questions", [])),
                  len(tables.get("Micro_Skills", [])))


def m_mappings_per_question(tables) -> Optional[float]:
    return _ratio(len(tables.get("Question_MicroSkills", [])),
                  len(tables.get("Questions", [])))


def m_primary_share(tables) -> Optional[float]:
    mappings = tables.get("Question_MicroSkills", [])
    primary = sum(1 for r in mappings if r.get("is_primary") is True)
    return _ratio(primary, len(mappings))


def m_phase_spread(tables) -> dict:
    counts = Counter(_text(r.get("phase")) for r in tables.get("Question_Usage", []))
    return _share(counts, sum(counts.values()))


def m_difficulty_levels(tables) -> list:
    return sorted({r.get("difficulty") for r in tables.get("Questions", [])
                   if r.get("difficulty") is not None})


def m_question_types(tables) -> dict:
    counts = Counter(_text(r.get("question_type"))
                     for r in tables.get("Questions", []))
    return _share(counts, sum(counts.values()))


def m_true_false_used(tables) -> bool:
    return any(_text(r.get("question_type")) == "TRUE_FALSE_WITH_EXPLANATION"
               for r in tables.get("Questions", []))


def m_steps_per_worked_example(tables) -> Optional[float]:
    return _ratio(len(tables.get("Worked_Example_Steps", [])),
                  len(tables.get("Worked_Examples", [])))


def m_worked_examples_per_topic(tables) -> Optional[float]:
    return _ratio(len(tables.get("Worked_Examples", [])),
                  len(tables.get("Topics", [])))


def m_hints_per_misconception(tables) -> Optional[float]:
    return _ratio(len(tables.get("Misconception_Hints", [])),
                  len(tables.get("Misconceptions", [])))


def m_hint_levels(tables) -> list:
    return sorted({r.get("hint_level") for r in tables.get("Hints", [])
                   if r.get("hint_level") is not None})


def m_scaffold_steps_per_scaffold(tables) -> Optional[float]:
    return _ratio(len(tables.get("Scaffold_Steps", [])),
                  len(tables.get("Scaffolds", [])))


def m_error_patterns_per_question(tables) -> Optional[float]:
    return _ratio(len(tables.get("Question_Error_Map", [])),
                  len(tables.get("Questions", [])))


def m_scope_items_per_topic(tables) -> Optional[float]:
    return _ratio(len(tables.get("Topic_Scope", [])),
                  len(tables.get("Topics", [])))


def m_scope_has_both_kinds(tables) -> bool:
    kinds = {_text(r.get("scope_type")) for r in tables.get("Topic_Scope", [])}
    return {"INCLUDED", "EXCLUDED"} <= kinds


def m_errors_per_topic(tables) -> Optional[float]:
    return _ratio(len(tables.get("Error_Types", [])),
                  len(tables.get("Topics", [])))


def m_support_allowed_by_phase(tables) -> dict:
    pairs = Counter(
        (_text(r.get("phase")), _text(r.get("support_allowed")))
        for r in tables.get("Question_Usage", [])
    )
    return {f"{phase} -> {support}": n for (phase, support), n in sorted(pairs.items())}


#: (name, how to measure it, how to compare two values).
#:
#: Numbers are compared with a tolerance because generated content is not
#: deterministic; sets and booleans are compared exactly because "uses
#: difficulty 3" is not a matter of degree.
MEASURES: tuple[tuple[str, Callable, str], ...] = (
    ("questions per micro-skill", m_questions_per_skill, "ratio"),
    ("micro-skills credited per question", m_mappings_per_question, "ratio"),
    ("share of mappings that are primary", m_primary_share, "ratio"),
    ("phase spread", m_phase_spread, "shares"),
    ("difficulty levels used", m_difficulty_levels, "exact"),
    ("question type mix", m_question_types, "shares"),
    ("TRUE_FALSE_WITH_EXPLANATION used", m_true_false_used, "exact"),
    ("worked examples per topic", m_worked_examples_per_topic, "ratio"),
    ("steps per worked example", m_steps_per_worked_example, "ratio"),
    ("hints per misconception", m_hints_per_misconception, "ratio"),
    ("hint levels used", m_hint_levels, "exact"),
    ("steps per scaffold", m_scaffold_steps_per_scaffold, "ratio"),
    ("error patterns per question", m_error_patterns_per_question, "ratio"),
    ("scope items per topic", m_scope_items_per_topic, "ratio"),
    ("scope declares both included and excluded", m_scope_has_both_kinds, "exact"),
    ("error types per topic", m_errors_per_topic, "ratio"),
    ("support allowed by phase", m_support_allowed_by_phase, "keys"),
)


def _same(reference, generated, kind: str, tolerance: float) -> tuple[bool, str]:
    """Whether two readings agree, and what to say if they do not."""
    if reference is None or generated is None:
        return reference == generated, "one side has no rows to measure"

    if kind == "ratio":
        if reference == 0:
            return generated == 0, ""
        drift = abs(generated - reference) / reference
        return drift <= tolerance, f"{drift:.0%} apart"

    if kind == "shares":
        keys = set(reference) | set(generated)
        worst = max((abs(generated.get(k, 0) - reference.get(k, 0)) for k in keys),
                    default=0.0)
        return worst <= tolerance, f"largest gap {worst:.0%}"

    if kind == "keys":
        missing = set(reference) - set(generated)
        added = set(generated) - set(reference)
        parts = []
        if missing:
            parts.append(f"not present: {sorted(missing)}")
        if added:
            parts.append(f"only ours: {sorted(added)}")
        return not missing and not added, ", ".join(parts)

    return reference == generated, ""


def compare_tables(reference: dict[str, list[dict]],
                   generated: dict[str, list[dict]],
                   *, tolerance: float = DEFAULT_TOLERANCE) -> Comparison:
    """Every measure, against tables already read."""
    comparison = Comparison()

    comparison.measures.extend(compare_schema(reference, generated))

    for name, measure, kind in MEASURES:
        left, right = measure(reference), measure(generated)
        agrees, detail = _same(left, right, kind, tolerance)
        if agrees:
            status = MATCH
        elif name in DECIDED:
            status = INTENTIONAL
            detail = DECIDED[name].reason
        else:
            status = DIVERGES
        comparison.measures.append(Measure(name, left, right, status, detail))

    return comparison


def compare_schema(reference, generated) -> list[Measure]:
    """Sheets and column order, which must match exactly.

    This is the one part of the comparison with no tolerance. The platform
    reads by position and name; a workbook that gets this wrong does not
    import at all, whatever its content is like.
    """
    measures: list[Measure] = []
    missing = sorted(set(reference) - set(generated))
    measures.append(Measure(
        "sheets present in the reference", len(reference), len(generated),
        MATCH if not missing else DIVERGES,
        f"absent from ours: {missing}" if missing else "",
    ))

    mismatched = []
    for table in sorted(set(reference) & set(generated)):
        expected = TABLE_SCHEMAS[table]["columns"]
        for side, rows in (("reference", reference[table]),
                           ("generated", generated[table])):
            if rows and list(rows[0]) != list(expected)[:len(rows[0])]:
                mismatched.append(f"{table} ({side})")
    measures.append(Measure(
        "column order matches the schema", "as declared",
        "as declared" if not mismatched else "differs",
        MATCH if not mismatched else DIVERGES,
        f"differs in: {sorted(set(mismatched))}" if mismatched else "",
    ))
    return measures


def compare(reference_path, generated_path, *,
            tolerance: float = DEFAULT_TOLERANCE) -> Comparison:
    """Every measure, against two written workbooks."""
    comparison = compare_tables(read_any(reference_path), read_any(generated_path),
                                tolerance=tolerance)
    comparison.reference_source = str(reference_path)
    comparison.generated_source = str(generated_path)
    return comparison


def summarise(comparison: Comparison) -> str:
    """The report CG-023 asks for: differences, documented."""
    counts = comparison.by_status()
    lines = [
        f"{counts[MATCH]} match, {counts[INTENTIONAL]} intentional, "
        f"{counts[DIVERGES]} unexplained.",
    ]

    unexplained = comparison.unexplained()
    if unexplained:
        lines += ["", "UNEXPLAINED -- these are what to look at:"]
        lines += [f"  {m}" for m in unexplained]

    intentional = comparison.intentional()
    if intentional:
        lines += ["", "INTENTIONAL -- decided, with the reason:"]
        for measure in intentional:
            lines.append(f"  {measure.name}: reference {measure.reference}, "
                         f"generated {measure.generated}")
            decision = measure.decision
            if decision:
                lines.append(f"      {decision.reason}")
                lines.append(f"      decided in: {decision.source}")

    matched = [m for m in comparison.measures if m.status == MATCH]
    if matched:
        lines += ["", "MATCHES:"]
        lines += [f"  {m.name}: {m.generated}" for m in matched]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    from sources import REFERENCE_WORKBOOK

    if len(sys.argv) < 2:
        print("usage: python reference_compare.py <generated.xlsx> "
              "[reference.xlsx]")
        raise SystemExit(2)

    reference_path = Path(sys.argv[2]) if len(sys.argv) > 2 else REFERENCE_WORKBOOK
    if reference_path is None:
        print("No reference workbook found.", file=sys.stderr)
        raise SystemExit(2)

    result = compare(reference_path, sys.argv[1])
    print(f"reference: {Path(reference_path).name}")
    print(f"generated: {Path(sys.argv[1]).name}")
    print()
    print(summarise(result))
    raise SystemExit(1 if result.unexplained() else 0)
