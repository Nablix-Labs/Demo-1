"""The plan every micro-skill must be filled against.

The review's finding this exists to prevent: 109 questions were generated and
17 of 53 micro-skills still owned none, because coverage was never planned,
only counted afterwards.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coverage_plan import (                          # noqa: E402
    DIAGNOSTIC_DIFFICULTY,
    PRACTICE_DIFFICULTIES,
    Slot,
    coverage_report,
    missing_slots,
    plan_for_skill,
    questions_per_skill,
)
from models import Phase, QuestionType               # noqa: E402

P0 = Phase.PHASE_0_DIAGNOSTIC
P2 = Phase.PHASE_2_GUIDED_LEARNING
P3 = Phase.PHASE_3_INDEPENDENT_PRACTICE


def _full() -> list[tuple[Phase, int]]:
    return [(s.phase, s.difficulty) for s in plan_for_skill()]


# ──────────────────────────────────────────────────────────────────────
# The plan itself
# ──────────────────────────────────────────────────────────────────────

def test_seven_questions_per_micro_skill():
    """Her revised figure. The first draft asked for 18, which came to 954
    questions for six topics and made a full run take hours."""
    assert questions_per_skill() == 7


def test_the_phase_split_is_one_three_three():
    plan = plan_for_skill()
    counts = {P0: 0, P2: 0, P3: 0}
    for slot in plan:
        counts[slot.phase] += 1
    assert counts == {P0: 1, P2: 3, P3: 3}


def test_each_practice_phase_covers_all_three_difficulties():
    plan = plan_for_skill()
    for phase in (P2, P3):
        got = sorted(s.difficulty for s in plan if s.phase is phase)
        assert got == list(PRACTICE_DIFFICULTIES) == [1, 2, 3]


def test_the_diagnostic_must_be_single_choice():
    """Her rule, and PHASE_RULES already agrees."""
    diagnostic = next(s for s in plan_for_skill() if s.phase is P0)
    assert diagnostic.required_type is QuestionType.SINGLE_CHOICE


def test_the_practice_phases_do_not_force_a_question_type():
    """Phase 3 forbids prose but still wants a mix of MCQ and canvas work, so
    the type is the generator's choice within what the phase allows."""
    assert all(s.required_type is None
               for s in plan_for_skill() if s.phase is not P0)


def test_the_diagnostic_is_not_difficulty_one():
    """Inferred rather than specified: a question nearly everyone gets right
    separates nobody, and a diagnostic exists to separate."""
    assert DIAGNOSTIC_DIFFICULTY == 2
    diagnostic = next(s for s in plan_for_skill() if s.phase is P0)
    assert diagnostic.difficulty != 1


def test_the_plan_reads_in_the_order_a_student_meets_it():
    phases = [s.phase for s in plan_for_skill()]
    assert phases[0] is P0
    assert phases.index(P2) < phases.index(P3)


def test_a_slot_describes_itself_readably():
    """These end up in warnings a person has to act on."""
    plan = plan_for_skill()
    assert str(plan[0]) == "PHASE_0_DIAGNOSTIC D2 (SINGLE_CHOICE)"
    assert "PHASE_2_GUIDED_LEARNING D1" == str(
        next(s for s in plan if s.phase is P2 and s.difficulty == 1))


# ──────────────────────────────────────────────────────────────────────
# Finding the gaps
# ──────────────────────────────────────────────────────────────────────

def test_a_complete_set_has_nothing_missing():
    assert missing_slots(_full()) == []


def test_an_empty_set_is_missing_everything():
    assert len(missing_slots([])) == 7


def test_a_missing_diagnostic_is_named():
    produced = [x for x in _full() if x[0] is not P0]
    gaps = missing_slots(produced)
    assert len(gaps) == 1
    assert gaps[0].phase is P0


def test_the_right_count_at_the_wrong_difficulty_is_still_a_gap():
    """The failure the old generator could hide: three guided questions all at
    difficulty 1 look like full phase coverage and leave 2 and 3 untested."""
    produced = [(P0, 2), (P2, 1), (P2, 1), (P2, 1)] + \
               [(P3, d) for d in (1, 2, 3)]
    gaps = missing_slots(produced)

    assert {(g.phase, g.difficulty) for g in gaps} == {(P2, 2), (P2, 3)}


def test_duplicates_do_not_fill_two_slots():
    """Two questions at the same phase and difficulty satisfy one slot, not
    two. The plan holds a single (Phase 2, difficulty 1), so the second is
    surplus and the other six slots are still open."""
    gaps = missing_slots([(P2, 1), (P2, 1)])
    assert len(gaps) == 6
    assert (P2, 1) not in {(g.phase, g.difficulty) for g in gaps}


def test_extra_questions_beyond_the_plan_are_not_a_gap():
    """The plan is a minimum. More is fine."""
    assert missing_slots(_full() + [(P2, 2), (P3, 3)]) == []


# ──────────────────────────────────────────────────────────────────────
# Across every skill
# ──────────────────────────────────────────────────────────────────────

def test_only_short_skills_appear_in_the_report():
    report = coverage_report({
        "T01.M1": _full(),
        "T01.M2": [(P0, 2)],
        "T01.M3": [],
    })
    assert set(report) == {"T01.M2", "T01.M3"}
    assert len(report["T01.M3"]) == 7


def test_a_large_total_cannot_hide_an_empty_skill():
    """Straight from the review: 'Do not allow a large overall question count
    to hide a missing micro-skill.' The last run produced 109 questions with
    17 skills holding none."""
    report = coverage_report({
        "T01.M1": _full() * 20,     # 140 questions on one skill
        "T01.M2": [],
    })
    assert "T01.M2" in report
    assert len(report["T01.M2"]) == 7


def test_a_fully_covered_set_of_skills_reports_nothing():
    assert coverage_report({f"T01.M{i}": _full() for i in range(1, 10)}) == {}


def test_the_plan_can_be_overridden_without_touching_the_generator():
    """Held as data so raising the diagnostic to 2 is a change in one place."""
    plan = [Slot(P0, 2, QuestionType.SINGLE_CHOICE), Slot(P0, 3,
                                                          QuestionType.SINGLE_CHOICE)]
    assert len(missing_slots([(P0, 2)], plan)) == 1
    assert missing_slots([(P0, 2), (P0, 3)], plan) == []
