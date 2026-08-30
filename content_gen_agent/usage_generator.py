"""CG-012: Question_Usage and Question_MicroSkills.

Where a question is used, and what it measures. Two tables, and neither needs
a model call: everything here is derivable from what CG-010 and CG-011 already
produced plus the phase rules extracted in CG-001.

That is a deliberate choice, not a shortcut. The exit condition is "phase rules
enforced, one primary skill per question, weights valid" -- three properties a
model can only be asked to respect and then checked for, or computed correctly
in the first place. Asking a model to divide 1.00 into five weights invites
0.9999999 and a failed validation for no gain.

Phase rules, from the reference
--------------------------------

PHASE_RULES in table_schemas already encodes these and the reference agrees
exactly:

    PHASE_0_DIAGNOSTIC             DIAGNOSTIC role, no support, 1 attempt,
                                   SINGLE_CHOICE only
    PHASE_2_GUIDED_LEARNING        five roles, adaptive support, 2 or 3
                                   attempts, any question type
    PHASE_3_INDEPENDENT_PRACTICE   INDEPENDENT_VERIFICATION, no support,
                                   1 attempt

`sequence_order` restarts at 1 within each phase, which the reference confirms:
Phase 2 runs 1..6, Phase 3 runs 1..7, Phase 0 runs 1..8 across the three topics.

One defect in the reference
----------------------------

Q-T01-002 carries TWO primary skills, T01.M2 and T01.M3, both at weight 0.4.
Its weights sum to 1.00 correctly, so only the primary rule catches it. Every
other one of the 54 questions has exactly one.

This module enforces exactly one, which means it will not reproduce that row.
That is recorded in KNOWN_USAGE_DIVERGENCES rather than special-cased, for the
same reason as Topic 1's other oddities: its rows predate the convention, and
generating a second defect to match the first would be the wrong fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from id_service import IdService
from models import (
    Phase,
    QuestionMicroSkillRow,
    QuestionRole,
    QuestionRow,
    QuestionUsageRow,
    SupportAllowed,
)
from table_schemas import PHASE_RULES
from validation import Severity, ValidationIssue

# Weights are rounded to this many places before the sum is checked. Five
# skills at 1/5 is exact; three at 1/3 is not, and 0.9999999999 failing a
# "must sum to 1.00" check would be an arithmetic artefact, not a defect.
WEIGHT_PLACES = 2

# The reference's Q-T01-002 has two primary skills. Recorded rather than
# reproduced. See the module docstring.
KNOWN_USAGE_DIVERGENCES: dict[str, str] = {
    "Q-T01-002": (
        "Reference marks both T01.M2 and T01.M3 as primary. Every other "
        "question has exactly one, and section 12.1 requires exactly one, so "
        "the reference row is the outlier. Topic 1's rows predate the "
        "convention."
    ),
}


class UsageError(Exception):
    """Usage or skill-mapping rows could not be built."""


def _rule(phase: Phase) -> dict:
    rules = PHASE_RULES.get(phase.value)
    if rules is None:
        raise UsageError(f"no phase rules for {phase.value}")
    return rules


def default_max_attempts(phase: Phase) -> int:
    """The attempts a phase allows.

    Phase 2 permits 2 or 3 and the reference uses both, so the caller may
    override; the default is the more generous, since guided practice is where
    a student is meant to be allowed to struggle.
    """
    allowed = _rule(phase)["max_attempts"]
    return max(allowed) if isinstance(allowed, list) else int(allowed)


def default_role(phase: Phase) -> QuestionRole:
    """The role a phase implies when only one is possible.

    Phases 0 and 3 allow exactly one role each, so it is not a choice. Phase 2
    allows five and the caller must say which.
    """
    allowed = _rule(phase)["allowed_roles"]
    if len(allowed) != 1:
        raise UsageError(
            f"{phase.value} allows {len(allowed)} roles; the caller must choose"
        )
    return QuestionRole(allowed[0])


def split_weights(count: int) -> list[float]:
    """Divide 1.00 across `count` skills so the total is exactly 1.00.

    Equal shares, rounded to two places, with any rounding remainder pushed
    onto the last skill. Three skills become 0.33, 0.33, 0.34 rather than
    three 0.33s that sum to 0.99 and fail validation.
    """
    if count < 1:
        raise UsageError("cannot split weights across no skills")
    share = round(1.0 / count, WEIGHT_PLACES)
    weights = [share] * (count - 1)
    weights.append(round(1.0 - sum(weights), WEIGHT_PLACES))
    return weights


@dataclass
class UsagePlan:
    """Where one question is used."""

    question_id: str
    phase: Phase
    role: Optional[QuestionRole] = None
    max_attempts: Optional[int] = None


@dataclass
class UsageSet:
    """Both tables for one topic."""

    topic_code: str
    usage: list[QuestionUsageRow] = field(default_factory=list)
    skill_map: list[QuestionMicroSkillRow] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_error]

    @property
    def is_clean(self) -> bool:
        return not self.errors


def build_usage_rows(
    plans: list[UsagePlan],
    questions: list[QuestionRow],
    topic_code: str,
    id_service: Optional[IdService] = None,
) -> tuple[list[QuestionUsageRow], list[ValidationIssue]]:
    """One Question_Usage row per plan, with the phase rules applied."""
    name = f"{topic_code} usage"
    issues: list[ValidationIssue] = []

    def error(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, name, field_name, message))

    by_id = {q.question_id: q for q in questions}
    if id_service is None:
        id_service = IdService(topic_code)

    # sequence_order restarts within each phase, as the reference does.
    next_in_phase: dict[Phase, int] = {}
    rows: list[QuestionUsageRow] = []

    for plan in plans:
        question = by_id.get(plan.question_id)
        if question is None:
            error(plan.question_id, "no such question in this topic")
            continue

        rules = _rule(plan.phase)

        # A phase that forbids a question type cannot host that question. The
        # diagnostic phase is SINGLE_CHOICE only, so a short-response question
        # placed there would be unanswerable as a diagnostic.
        allowed_types = rules["allowed_question_types"]
        if question.question_type.value not in allowed_types:
            error(plan.question_id,
                  f"{question.question_type.value} is not allowed in "
                  f"{plan.phase.value}")
            continue

        try:
            role = plan.role or default_role(plan.phase)
        except UsageError as exc:
            error(plan.question_id, str(exc))
            continue

        if role.value not in rules["allowed_roles"]:
            error(plan.question_id,
                  f"role {role.value} is not allowed in {plan.phase.value}")
            continue

        attempts = plan.max_attempts or default_max_attempts(plan.phase)
        allowed_attempts = rules["max_attempts"]
        permitted = (
            allowed_attempts if isinstance(allowed_attempts, list)
            else [allowed_attempts]
        )
        if attempts not in permitted:
            error(plan.question_id,
                  f"max_attempts {attempts} is not permitted in "
                  f"{plan.phase.value}; allowed {permitted}")
            continue

        order = next_in_phase.get(plan.phase, 0) + 1
        next_in_phase[plan.phase] = order

        rows.append(
            QuestionUsageRow(
                question_usage_id=id_service.question_usage_id(
                    plan.question_id, plan.phase.value
                ),
                question_id=plan.question_id,
                phase=plan.phase,
                question_role=role,
                sequence_order=order,
                support_allowed=SupportAllowed(rules["support_allowed"]),
                max_attempts=attempts,
                active=True,
            )
        )

    return rows, issues


def build_skill_map(
    skill_links: dict[str, list[str]],
    primary: Optional[dict[str, str]] = None,
    topic_code: str = "",
) -> tuple[list[QuestionMicroSkillRow], list[ValidationIssue]]:
    """Question_MicroSkills rows, weights summing to 1.00, one primary each.

    `skill_links` comes from CG-011: question id -> the skills it exercises.
    `primary` optionally names which skill is primary for a question; without
    it the first listed skill is used, since CG-011 asks the model to list the
    skill a question mainly tests first.
    """
    name = f"{topic_code} skill map"
    issues: list[ValidationIssue] = []

    def error(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, name, field_name, message))

    primary = primary or {}
    rows: list[QuestionMicroSkillRow] = []

    for question_id, skills in skill_links.items():
        if not skills:
            error(question_id, "exercises no micro-skill, so nothing to weight")
            continue

        unique = list(dict.fromkeys(skills))
        if len(unique) != len(skills):
            error(question_id, "the same micro-skill is listed more than once")
            continue

        chosen = primary.get(question_id, unique[0])
        if chosen not in unique:
            error(question_id,
                  f"primary skill {chosen!r} is not one of this question's skills")
            continue

        weights = split_weights(len(unique))
        for skill_id, weight in zip(unique, weights):
            rows.append(
                QuestionMicroSkillRow(
                    question_id=question_id,
                    micro_skill_id=skill_id,
                    weight=weight,
                    is_primary=(skill_id == chosen),
                )
            )

    return rows, issues


def check_skill_map(
    rows: list[QuestionMicroSkillRow],
    name: str = "skill map",
) -> list[ValidationIssue]:
    """The two invariants section 12.1 requires, checked on the built rows.

    Checked after building rather than trusted, because these are the exact
    properties the exit condition names and the reference violates one of them.
    """
    issues: list[ValidationIssue] = []
    by_question: dict[str, list[QuestionMicroSkillRow]] = {}
    for row in rows:
        by_question.setdefault(row.question_id, []).append(row)

    for question_id, group in by_question.items():
        total = round(sum(r.weight for r in group), WEIGHT_PLACES)
        if abs(total - 1.0) > 10 ** -WEIGHT_PLACES / 2:
            issues.append(ValidationIssue(
                Severity.ERROR, name, question_id,
                f"weights sum to {total}, not 1.00",
            ))
        primaries = [r for r in group if r.is_primary]
        if len(primaries) != 1:
            issues.append(ValidationIssue(
                Severity.ERROR, name, question_id,
                f"{len(primaries)} primary skills; exactly one is required",
            ))
    return issues


def build_usage_and_skills(
    plans: list[UsagePlan],
    questions: list[QuestionRow],
    skill_links: dict[str, list[str]],
    topic_code: str,
    *,
    primary: Optional[dict[str, str]] = None,
    strict: bool = True,
    id_service: Optional[IdService] = None,
) -> UsageSet:
    """Both tables for one topic, with every rule enforced."""
    usage, usage_issues = build_usage_rows(plans, questions, topic_code, id_service)
    skills, skill_issues = build_skill_map(skill_links, primary, topic_code)
    issues = usage_issues + skill_issues + check_skill_map(skills, f"{topic_code} skill map")

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise UsageError(
            f"{topic_code}: usage rows could not be built.\n"
            + "\n".join(f"  {i}" for i in errors)
        )
    if errors:
        return UsageSet(topic_code, [], [], issues)

    return UsageSet(topic_code, usage, skills, issues)
