"""How a run reports what it recovered from.

This file exists because of one number. The six-topic run of 7 September
printed "3 problem(s)" and looked close to clean. Underneath it, 134 of 368
questions had no error mapped to any of their wrong answers, so a third of the
bank could not diagnose a student mistake. The generator had raised a warning
for every one of them. None reached the screen, because the print filter was a
list of four keywords and that warning's wording contained none of them.

So the tests here are not about formatting. They are about the property that
failed: a warning nobody thought to name in advance must still be visible.

No network, no model, no workbook.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import MAX_NOTES_PER_KIND, _report, _shape   # noqa: E402
from validation import Severity, ValidationIssue           # noqa: E402


def _warning(message: str, field: str = "f") -> ValidationIssue:
    return ValidationIssue(Severity.WARNING, "test", field, message)


def _error(message: str, field: str = "f") -> ValidationIssue:
    return ValidationIssue(Severity.ERROR, "test", field, message)


def _printed(issues) -> list[str]:
    lines: list[str] = []
    _report(lines.append, issues)
    return lines


# ──────────────────────────────────────────────────────────────────────
# The property that failed
# ──────────────────────────────────────────────────────────────────────

def test_a_warning_nobody_predicted_is_still_printed():
    """The whole point. Reporting must not depend on a keyword list that
    somebody has to remember to extend."""
    issues = [_warning("a complaint no keyword list would have anticipated")]
    assert _printed(issues) == [
        "    note: a complaint no keyword list would have anticipated",
    ]


def test_the_warning_that_was_suppressed_in_the_september_run():
    """Verbatim wording from mapping_generator, which contains none of the
    four keywords the old filter looked for."""
    message = ("none of its 4 wrong answer(s) is mapped to an error, so a "
               "student who makes one gets no diagnosis")
    assert _printed([_warning(message)]) == [f"    note: {message}"]


def test_errors_are_not_printed_here():
    """Errors are raised or reported by the caller. This function is only for
    the things a run survived."""
    assert _printed([_error("this stopped a generator")]) == []


# ──────────────────────────────────────────────────────────────────────
# Repeats are counted, not hidden
# ──────────────────────────────────────────────────────────────────────

def test_repeats_of_one_complaint_are_summarised_rather_than_listed():
    """The reason the old filter existed was real: 134 near-identical lines
    bury the three that are different. Counting keeps both facts."""
    issues = [
        _warning(f"none of its 2 wrong answer(s) is mapped, so Q-T01-{i:03d} "
                 f"gets no diagnosis")
        for i in range(1, 21)
    ]
    lines = _printed(issues)
    assert len(lines) == MAX_NOTES_PER_KIND + 1
    assert lines[-1] == ("    note: ... and 17 more of the same (20 in total)")


def test_the_count_names_the_true_total_not_the_remainder():
    """A reader needs the number that matters, which is how many questions are
    undiagnosable, not how many lines were omitted."""
    issues = [_warning(f"question {i} has no diagnosis") for i in range(50)]
    assert "(50 in total)" in _printed(issues)[-1]


def test_different_complaints_are_never_collapsed_into_each_other():
    issues = [
        _warning("every question is difficulty 1; the reference uses both"),
        _warning("accepted_answers repeats a form"),
        _warning("3 HIGH-priority skill(s) have no error type: T01.M2"),
    ]
    assert len(_printed(issues)) == 3


def test_a_rare_complaint_survives_a_flood_of_a_common_one():
    """The failure mode this design has to avoid: the one line that matters
    pushed off the screen by two hundred that do not."""
    flood = [_warning(f"question {i} has no diagnosis") for i in range(200)]
    rare = _warning("dropped 1 question(s) whose answer could not be trusted")
    lines = _printed(flood + [rare])
    assert any("could not be trusted" in line for line in lines)
    assert len(lines) == MAX_NOTES_PER_KIND + 1 + 1


def test_order_follows_first_appearance():
    """Stable output, so two runs can be diffed against each other."""
    issues = [_warning("first kind"), _warning("second kind"),
              _warning("first kind again")]
    lines = _printed(issues)
    assert lines[0].endswith("first kind")
    assert lines[1].endswith("second kind")


# ──────────────────────────────────────────────────────────────────────
# What counts as "the same complaint"
# ──────────────────────────────────────────────────────────────────────

def test_the_same_complaint_about_different_rows_has_one_shape():
    assert _shape("Q-T01-001 has no diagnosis") == \
           _shape("Q-T01-047 has no diagnosis")


def test_quoted_values_do_not_make_two_complaints_different():
    assert _shape("response_pattern 'a' is not one of its wrong answers") == \
           _shape("response_pattern 'A' is not one of its wrong answers")


def test_two_genuinely_different_complaints_have_different_shapes():
    assert _shape("accepted_answers repeats a form") != \
           _shape("every question is difficulty 1")


def test_a_long_message_is_grouped_on_its_opening():
    """Long warnings tend to differ only in the explanation at the end, which
    is the same explanation every time."""
    stem = "x" * 200
    assert _shape(stem + " tail one") == _shape(stem + " tail two")
