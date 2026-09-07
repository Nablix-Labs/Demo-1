"""What must exist for every micro-skill, and what is missing.

The review changed the unit of generation. The agent used to write about 18
questions for a topic and afterwards work out which skill each one happened to
assess. That produced exactly the failure the review found: 17 of 53
micro-skills owned no question at all, while T06.M1 owned 16 of its topic's 20,
and only 7 diagnostics existed across six topics because the phase was decided
by a heuristic reading of questions that already existed.

Coverage cannot be checked after the fact if it was never planned. So the plan
comes first and generation is asked to fill it:

    Phase 0 Diagnostic     1    SINGLE_CHOICE, one good discriminator
    Phase 2 Guided         3    one each at difficulty 1, 2, 3
    Phase 3 Independent    3    one each at difficulty 1, 2, 3
                           -
                           7    per micro-skill

53 micro-skills gives 371 questions. An earlier draft of the review asked for
18 per skill, which came to 954; the reduction to 7 is what makes a full run
take tens of minutes rather than hours, and so keeps the run-check-fix loop
usable.

These are minimums, not targets, and they are held as data rather than
hard-coded so that raising the diagnostic to 2 is a change here and not a
rewrite of the generator.

Why the diagnostic has no difficulty of its own
------------------------------------------------

The review gives difficulty targets "for Phase 2 and Phase 3" and none for
Phase 0. A diagnostic exists to separate students who have the skill from
those who do not, and a difficulty 1 question that nearly everyone answers
correctly separates nobody. DIAGNOSTIC_DIFFICULTY is therefore 2, and is
marked here as inference rather than instruction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from models import Phase, QuestionRole, QuestionType

#: Inferred, not specified. See the module docstring.
DIAGNOSTIC_DIFFICULTY = 2

#: Difficulties every practice phase must cover, one question each.
PRACTICE_DIFFICULTIES = (1, 2, 3)

#: Phase 2 allows five roles and the schema requires the caller to pick one.
#: The three guided questions sit at difficulty 1, 2 and 3, and the roles
#: describe increasing distance from the taught example, so the two line up
#: without being forced:
#:
#:     1  CLOSE_PRACTICE       the same thing again, right after teaching
#:     2  PARTIAL_APPLICATION  the idea applied with a choice to make
#:     3  NEAR_TRANSFER        the idea somewhere it was not taught
#:
#: MISCONCEPTION_PROBE and FINAL_GUIDED_CHECK are left unused. With only three
#: guided questions per skill, the three that form a progression are worth
#: more than a spread across all five, and a probe belongs with the
#: misconception work in M4 rather than here.
GUIDED_ROLE_BY_DIFFICULTY = {
    1: QuestionRole.CLOSE_PRACTICE,
    2: QuestionRole.PARTIAL_APPLICATION,
    3: QuestionRole.NEAR_TRANSFER,
}


@dataclass(frozen=True)
class Slot:
    """One question that must exist: a phase, a difficulty, for one skill."""

    phase: Phase
    difficulty: int

    #: Set where the phase allows only one type. Phase 0 is SINGLE_CHOICE
    #: only; the practice phases leave the choice to the generator.
    required_type: Optional[QuestionType] = None

    #: Left None where the phase allows exactly one role and the usage
    #: builder can infer it. Phase 2 allows five, so it is decided here.
    role: Optional[QuestionRole] = None

    def __str__(self) -> str:
        label = f"{self.phase.value} D{self.difficulty}"
        return f"{label} ({self.required_type.value})" if self.required_type else label


def plan_for_skill() -> list[Slot]:
    """The 7 questions every micro-skill needs.

    Ordered diagnostic first, then guided, then independent, so a generated
    set reads in the order a student would meet it.
    """
    slots = [
        Slot(Phase.PHASE_0_DIAGNOSTIC, DIAGNOSTIC_DIFFICULTY,
             QuestionType.SINGLE_CHOICE),
    ]
    for phase in (Phase.PHASE_2_GUIDED_LEARNING,
                  Phase.PHASE_3_INDEPENDENT_PRACTICE):
        slots += [
            Slot(phase, d,
                 role=GUIDED_ROLE_BY_DIFFICULTY[d]
                 if phase is Phase.PHASE_2_GUIDED_LEARNING else None)
            for d in PRACTICE_DIFFICULTIES
        ]
    return slots


def questions_per_skill() -> int:
    return len(plan_for_skill())


def missing_slots(
    produced: Iterable[tuple[Phase, int]],
    plan: Optional[list[Slot]] = None,
) -> list[Slot]:
    """Which planned slots are not covered by what was produced.

    Counts matter, not just presence: three guided questions all at difficulty
    1 leave difficulty 2 and 3 uncovered even though the phase has its three.
    That is precisely how the old generator could look busy and still leave a
    skill untested at the level that mattered.
    """
    plan = plan if plan is not None else plan_for_skill()
    remaining = list(produced)
    missing: list[Slot] = []

    for slot in plan:
        key = (slot.phase, slot.difficulty)
        if key in remaining:
            remaining.remove(key)
        else:
            missing.append(slot)
    return missing


def coverage_report(
    by_skill: dict[str, list[tuple[Phase, int]]],
    plan: Optional[list[Slot]] = None,
) -> dict[str, list[Slot]]:
    """Every skill that falls short, and what it is short of.

    The review's own warning: "Do not allow a large overall question count to
    hide a missing micro-skill." A total says nothing, because the previous
    run produced 109 questions and still left 17 skills with none.
    """
    return {
        skill_id: gaps
        for skill_id, produced in by_skill.items()
        if (gaps := missing_slots(produced, plan))
    }
