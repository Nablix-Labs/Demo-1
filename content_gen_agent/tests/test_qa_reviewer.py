"""CG-021 tests.

The roadmap's acceptance criterion is in its own words: "QA catches
intentionally planted errors in test data." So the centre of this file is a
set of deliberately faulty rows and the assertion that each is reported and
attributed to the right rule.

There is a limit worth stating plainly. These tests use FakeLLMClient, so
what they prove is that a reported fault is carried through to a finding with
the right rule code, severity and record id. They cannot prove the model
NOTICES a wrong answer -- only a live run can, and that is what the smoke run
is for. What they can prove, and what matters more for correctness, is the
opposite direction: that a review which fails, returns nothing, or skips an
item is never mistaken for approval.

No network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import qa_reviewer as qa                              # noqa: E402
from llm_client import FakeLLMClient, LLMError        # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Test data, with faults planted where each test needs one
# ──────────────────────────────────────────────────────────────────────

def tables(**overrides) -> dict[str, list[dict]]:
    base = {
        "Questions": [{
            "question_id": "Q-T01-001", "topic_id": "ALG-ORI-01",
            "question_text": "Write the rule for 3+5, 9+5, 14+5 using n.",
            "question_type": "SHORT_RESPONSE", "difficulty": 2,
            "status": "GENERATED",
        }],
        "Question_MicroSkills": [{
            "question_id": "Q-T01-001", "micro_skill_id": "T01.M1",
            "weight": 1.0, "is_primary": True,
        }],
        "Question_Usage": [{
            "question_id": "Q-T01-001", "phase": "PHASE_2_GUIDED_LEARNING",
        }],
        "Micro_Skills": [{
            "micro_skill_id": "T01.M1", "skill_name": "Represent a pattern",
            "description": "The student writes a rule with a letter.",
        }],
        "Topic_Scope": [{
            "topic_id": "ALG-ORI-01", "scope_type": "EXCLUDED",
            "item_text": "Solving equations to find a variable",
        }],
        "Answer_Specs": [{
            "answer_spec_id": "ANS-T01-001", "question_id": "Q-T01-001",
            "canonical_answer": "n + 5", "accepted_answers": "n+5 | 5+n",
            "common_wrong_answers": "5n | n-5",
            "answer_steps": "1. Compare the cases.\n2. Write n + 5.",
        }],
        "Misconceptions": [{
            "misconception_id": "MIS-T01-ADD", "description":
            "The student reads a fixed change as multiplication.",
        }],
        "Hints": [{
            "hint_id": "HINT-T01-01", "hint_level": 1,
            "hint_type": "ATTENTION",
            "content": "Look at what changes between the cases.",
        }],
        "Misconception_Hints": [{
            "hint_id": "HINT-T01-01", "misconception_id": "MIS-T01-ADD",
        }],
        "Visual_Cues": [],
        "Misconception_VisualCues": [],
        "Parallel_Examples": [],
    }
    base.update(overrides)
    return base


def reviews(*entries):
    return {"reviews": list(entries)}


def _answer_review(payloads, data=None, **kw):
    return qa.review_answers(data or tables(), FakeLLMClient(list(payloads)), **kw)


def _question_review(payloads, data=None, **kw):
    return qa.review_questions(data or tables(), FakeLLMClient(list(payloads)), **kw)


def _support_review(payloads, data=None, **kw):
    return qa.review_support(data or tables(), FakeLLMClient(list(payloads)), **kw)


# ──────────────────────────────────────────────────────────────────────
# Planted errors, one per fault the reviewer is asked to find
# ──────────────────────────────────────────────────────────────────────

def test_a_wrong_answer_key_is_caught_and_blocks():
    """The worst thing this pipeline can produce. A student who answered
    correctly is told they are wrong and then taught against."""
    report = _answer_review([reviews({
        "answer_spec_id": "ANS-T01-001", "verdict": "WRONG",
        "problem": "ANSWER", "should_be": "n + 5",
        "why": "The pattern adds 5, so the rule is n + 5, not 5n.",
    })])
    finding = report.findings[0]
    assert finding.rule_code == "ANSWER_CORRECT"
    assert finding.blocking
    assert finding.severity == qa.ERROR
    assert finding.record_id == "ANS-T01-001"
    assert "n + 5" in finding.issue


def test_steps_that_do_not_reach_the_answer_are_caught():
    report = _answer_review([reviews({
        "answer_spec_id": "ANS-T01-001", "verdict": "WRONG",
        "problem": "STEPS", "should_be": "n + 5",
        "why": "Step 2 multiplies where it should add.",
    })])
    assert report.findings[0].rule_code == "ANSWER_STEPS_COMPLETE"


def test_a_correct_answer_listed_as_wrong_is_caught():
    """Manjusha's example: a question asking for the shorter form of y added
    to itself three times listed 'y + y + y' as a wrong answer. It is not
    wrong, it just is not shorter."""
    report = _answer_review([reviews({
        "answer_spec_id": "ANS-T01-001", "verdict": "WRONG",
        "problem": "WRONG_ANSWERS", "should_be": "y + y + y is correct",
        "why": "It is listed as wrong but it is a correct expression.",
    })])
    assert report.findings[0].rule_code == "ANSWER_CORRECT"
    assert report.findings[0].blocking


def test_an_accepted_form_that_is_not_correct_is_caught():
    report = _answer_review([reviews({
        "answer_spec_id": "ANS-T01-001", "verdict": "WRONG",
        "problem": "ACCEPTED", "should_be": "n + 5",
        "why": "'5n' is listed as accepted and is not correct.",
    })])
    assert report.findings[0].rule_code == "ANSWER_CORRECT"
    assert report.findings[0].blocking


def test_a_phase_3_question_needing_speech_is_caught():
    """Phase 3 is worked on the canvas with no help, so an answer that is a
    spoken explanation cannot be marked by anything in the platform."""
    data = tables(Question_Usage=[{
        "question_id": "Q-T01-001", "phase": "PHASE_3_INDEPENDENT_PRACTICE",
    }])
    report = _question_review([reviews({
        "question_id": "Q-T01-001", "verdict": "WRONG",
        "problem": "NOT_CANVAS", "why": "It asks the student to explain aloud.",
    })], data=data)
    assert report.findings[0].rule_code == "PHASE3_CANVAS_ONLY"


def test_not_canvas_is_discarded_for_a_phase_2_question():
    """Five of the smoke run's seven canvas findings were Phase 2 questions,
    where asking for an explanation is legitimate: the tutor is there to hear
    it. The phase is known here, so the verdict is dropped rather than the
    model being trusted to remember which rule applies where."""
    report = _question_review([reviews({
        "question_id": "Q-T01-001", "verdict": "WRONG",
        "problem": "NOT_CANVAS", "why": "It asks for a written reason.",
    })])                      # the default fixture is PHASE_2_GUIDED_LEARNING
    assert not report.findings
    assert report.discarded == 1


def test_other_complaints_about_a_phase_2_question_still_stand():
    """The gate is narrow on purpose. Only NOT_CANVAS is phase-specific."""
    report = _question_review([reviews({
        "question_id": "Q-T01-001", "verdict": "WRONG",
        "problem": "WRONG_SKILL", "why": "It tests substitution.",
    })])
    assert report.findings
    assert not report.discarded


def test_discarded_verdicts_are_counted_not_hidden():
    """A number climbing here means the prompt is misleading the reviewer,
    which is worth knowing rather than quietly absorbing."""
    report = _question_review([reviews(
        {"question_id": "Q-T01-001", "verdict": "WRONG",
         "problem": "NOT_CANVAS", "why": "prose"},
    )])
    assert "discarded as inapplicable" in qa.summarise(report)


def test_a_question_testing_the_wrong_skill_is_caught():
    report = _question_review([reviews({
        "question_id": "Q-T01-001", "verdict": "WRONG",
        "problem": "WRONG_SKILL",
        "why": "It asks for substitution, not for representing a pattern.",
    })])
    assert report.findings[0].rule_code == "QUESTION_TESTS_ITS_SKILL"


def test_content_past_the_topic_boundary_is_caught():
    report = _question_review([reviews({
        "question_id": "Q-T01-001", "verdict": "WRONG",
        "problem": "OUT_OF_SCOPE",
        "why": "It requires solving an equation, which this topic excludes.",
    })])
    assert report.findings[0].rule_code == "SCOPE_EXCLUSION"


def test_language_too_hard_for_the_age_is_caught():
    report = _question_review([reviews({
        "question_id": "Q-T01-001", "verdict": "WRONG",
        "problem": "LANGUAGE", "why": "The sentence is 60 words long.",
    })])
    assert report.findings[0].rule_code == "AGE_APPROPRIATE_LANGUAGE"


def test_a_repetitive_question_is_caught():
    report = _question_review([reviews({
        "question_id": "Q-T01-001", "verdict": "WRONG",
        "problem": "REPETITIVE", "why": "Same as Q-T01-004 with new numbers.",
    })])
    assert report.findings[0].rule_code == "NOT_REPETITIVE"


def test_a_hint_that_gives_the_answer_away_is_caught():
    report = _support_review([reviews({
        "record_id": "HINT-T01-01", "verdict": "WRONG",
        "problem": "GIVES_ANSWER", "why": "It states the rule is n + 5.",
    })])
    finding = report.findings[0]
    assert finding.rule_code == "HINT_REVEALS_TOO_MUCH"
    assert finding.table == "Hints"


def test_a_hint_too_vague_to_help_is_caught():
    report = _support_review([reviews({
        "record_id": "HINT-T01-01", "verdict": "WRONG",
        "problem": "TOO_VAGUE", "why": "'Think about it' moves nobody on.",
    })])
    assert report.findings[0].rule_code == "HINT_REVEALS_TOO_LITTLE"


def test_a_hint_that_does_not_match_its_level_is_caught():
    """Three hints revealing the same amount are one hint written three
    times, and the tutor has nothing to escalate through."""
    report = _support_review([reviews({
        "record_id": "HINT-T01-01", "verdict": "WRONG",
        "problem": "WRONG_LEVEL",
        "why": "An ATTENTION hint that already restates the concept.",
    })])
    assert report.findings[0].rule_code == "HINT_REVEALS_TOO_MUCH"


def test_a_parallel_example_of_the_wrong_shape_is_caught():
    data = tables(Parallel_Examples=[{
        "parallel_example_id": "PAR-01", "misconception_id": "MIS-T01-ADD",
        "problem_statement": "Work out 7 x 3.", "worked_steps": "1. Multiply.",
        "final_answer": "21",
    }])
    report = _support_review([reviews({
        "record_id": "PAR-01", "verdict": "WRONG", "problem": "NOT_PARALLEL",
        "why": "It practises multiplication, not reading a fixed change.",
    })], data=data)
    finding = next(f for f in report.findings if f.record_id == "PAR-01")
    assert finding.rule_code == "PARALLEL_EXAMPLE_IS_PARALLEL"
    assert finding.table == "Parallel_Examples"


def test_a_visual_cue_that_does_not_fit_its_belief_is_caught():
    data = tables(
        Visual_Cues=[{"visual_cue_id": "VC-01",
                      "image_generation_prompt": "A pie chart of fractions."}],
        Misconception_VisualCues=[{"visual_cue_id": "VC-01",
                                   "misconception_id": "MIS-T01-ADD"}],
    )
    report = _support_review([reviews({
        "record_id": "VC-01", "verdict": "WRONG", "problem": "CUE_MISMATCH",
        "why": "Fractions have nothing to do with repeated addition.",
    })], data=data)
    finding = next(f for f in report.findings if f.record_id == "VC-01")
    assert finding.rule_code == "CUE_SUPPORTS_MISCONCEPTION"
    assert finding.table == "Visual_Cues"


def test_a_parallel_example_is_never_reported_for_showing_its_answer():
    """The whole of the smoke run's support report was this mistake.

    All seven findings were parallel examples flagged for "giving away the
    answer". A parallel example is a worked example of a DIFFERENT problem;
    showing its answer is the point, and final_answer is a column the schema
    asks for. Seven findings, none of them real.
    """
    data = tables(Parallel_Examples=[{
        "parallel_example_id": "PAR-01", "misconception_id": "MIS-T01-ADD",
        "problem_statement": "A lift starts on floor f and goes up 5.",
        "worked_steps": "changing floor f | fixed change +5",
        "final_answer": "f + 5",
    }])
    report = _support_review([reviews(
        {"record_id": "PAR-01", "verdict": "WRONG", "problem": "GIVES_ANSWER",
         "why": "It ends with 'answer: f + 5'."},
    )], data=data)
    assert not [f for f in report.findings if f.record_id == "PAR-01"]
    assert report.discarded == 1


def test_a_hint_reported_as_not_parallel_is_discarded_too():
    """The gate runs both ways. A complaint that belongs to another kind is
    the reviewer losing track of what it is looking at."""
    report = _support_review([reviews(
        {"record_id": "HINT-T01-01", "verdict": "WRONG",
         "problem": "NOT_PARALLEL", "why": "Not the same shape."},
    )])
    assert not report.findings
    assert report.discarded == 1


def test_a_parallel_example_that_is_the_students_own_question_is_reported():
    """The complaint that IS valid for a parallel example. Handing back the
    same question does give away the answer they needed."""
    data = tables(Parallel_Examples=[{
        "parallel_example_id": "PAR-01", "misconception_id": "MIS-T01-ADD",
        "problem_statement": "Write the rule for 3+5, 9+5, 14+5 using n.",
        "worked_steps": "1. Add 5.", "final_answer": "n + 5",
    }])
    report = _support_review([reviews(
        {"record_id": "PAR-01", "verdict": "WRONG", "problem": "SAME_QUESTION",
         "why": "This is the question the student is stuck on."},
    )], data=data)
    finding = next(f for f in report.findings if f.record_id == "PAR-01")
    assert finding.rule_code == "PARALLEL_EXAMPLE_IS_PARALLEL"
    assert not report.discarded


def test_the_prompt_says_a_parallel_example_is_meant_to_show_its_answer():
    text = " ".join(qa.SUPPORT_SYSTEM_PROMPT.split())
    assert "IT IS SUPPOSED TO SHOW ITS ANSWER" in text
    assert "Never report a parallel example for giving away an answer" in text


def test_every_kind_has_at_least_one_complaint_that_applies_to_it():
    """A kind with no valid problem code is a kind nothing can ever be
    reported about, which would be a silent hole in the review."""
    for kind, problems in qa.PROBLEMS_FOR_KIND.items():
        assert problems, f"{kind} has no applicable complaint"
        for problem in problems:
            assert problem in qa.RULE_FOR_SUPPORT_PROBLEM


def test_a_scaffold_doing_the_work_for_the_student_is_caught():
    """This test failed when first written, because scaffold steps were never
    collected for review at all. TAKES_OVER sat in the mapping and could never
    fire, so specification 12.2's question about preserving student agency was
    never actually asked of anything."""
    data = tables(
        Scaffolds=[{"scaffold_id": "SCF-01", "scaffold_name": "Find the rule"}],
        Scaffold_Steps=[{
            "scaffold_step_id": "SCF-01-S1", "scaffold_id": "SCF-01",
            "stage_no": 1, "prompt": "I will write n + 5 for you.",
            "partial_content": "n + 5", "expected_response": "n + 5",
        }],
    )
    report = _support_review([reviews({
        "record_id": "SCF-01-S1", "verdict": "WRONG",
        "problem": "TAKES_OVER", "why": "The stage performs the step.",
    })], data=data)
    finding = next(f for f in report.findings if f.record_id == "SCF-01-S1")
    assert finding.rule_code == "SCAFFOLD_PRESERVES_AGENCY"
    assert finding.table == "Scaffold_Steps"


def test_scaffold_steps_are_collected_for_review():
    data = tables(
        Scaffolds=[{"scaffold_id": "SCF-01", "scaffold_name": "Find the rule"}],
        Scaffold_Steps=[{
            "scaffold_step_id": "SCF-01-S1", "scaffold_id": "SCF-01",
            "stage_no": 1, "prompt": "What changes between the cases?",
            "partial_content": "", "expected_response": "the first number",
        }],
    )
    step = next(i for i in qa.support_items(data) if i[0] == "SCF-01-S1")
    assert "What changes" in step[2]
    assert "the first number" in step[2]
    assert "Find the rule" in step[3]


# ──────────────────────────────────────────────────────────────────────
# Silence must never read as approval
# ──────────────────────────────────────────────────────────────────────

def test_a_key_the_reviewer_skipped_is_reported_not_approved():
    """The failure mode this project has already had once. On 7 September a
    whole topic's error map came back empty and was accepted in silence."""
    report = _answer_review([reviews()])
    assert len(report.findings) == 1
    assert "unreviewed rather than approved" in report.findings[0].issue
    assert report.findings[0].record_id == "ANS-T01-001"


def test_a_response_with_no_reviews_list_is_refused():
    with pytest.raises(qa.QAError, match="nothing was reviewed"):
        _answer_review([{"something_else": []}])


def test_a_refused_response_says_why_silence_is_not_a_pass():
    with pytest.raises(qa.QAError, match="clean bill of health"):
        _answer_review([{}])


def test_an_unknown_verdict_is_treated_as_unsure_not_as_ok():
    """A malformed verdict is the reviewer failing to answer. Reading it as
    approval would let a garbled response bless the whole batch."""
    report = _answer_review([reviews(
        {"answer_spec_id": "ANS-T01-001", "verdict": "probably fine"},
    )])
    assert report.unsure == 1


def test_unsure_is_counted_and_does_not_become_a_fault():
    """An unsure verdict is read by a person. Turning it into a finding would
    train people to ignore findings."""
    report = _answer_review([reviews(
        {"answer_spec_id": "ANS-T01-001", "verdict": "UNSURE"},
    )])
    assert report.unsure == 1
    assert not report.findings


def test_an_ok_verdict_produces_nothing():
    report = _answer_review([reviews(
        {"answer_spec_id": "ANS-T01-001", "verdict": "OK"},
    )])
    assert not report.findings
    assert report.reviewed == 1


# ──────────────────────────────────────────────────────────────────────
# Mathematics blocks, judgement does not
# ──────────────────────────────────────────────────────────────────────

def test_judgement_findings_never_block():
    """A run that stops on a matter of taste is a run people learn to
    override, and then the blocking ones stop working too."""
    report = _question_review([reviews({
        "question_id": "Q-T01-001", "verdict": "WRONG",
        "problem": "LANGUAGE", "why": "Too wordy.",
    })])
    assert not report.blocking
    assert report.findings[0].severity == qa.WARNING


def test_only_mathematics_is_in_the_blocking_set():
    assert qa.BLOCKING_RULES == {"ANSWER_CORRECT", "WORKED_EXAMPLE_CORRECT"}


def test_every_finding_carries_something_a_person_can_act_on():
    report = _answer_review([reviews({
        "answer_spec_id": "ANS-T01-001", "verdict": "WRONG",
        "problem": "ANSWER", "should_be": "n + 5", "why": "Adds 5.",
    })])
    for finding in report.findings:
        assert finding.recommended_action.strip()
        assert "evidence, not proof" in finding.recommended_action


# ──────────────────────────────────────────────────────────────────────
# Nothing blank is ever sent for review
# ──────────────────────────────────────────────────────────────────────

def test_a_parallel_example_is_built_from_all_three_of_its_columns():
    """The bug the first version had: Parallel_Examples has no 'content'
    column, so all 44 of them went to the reviewer as empty strings."""
    data = tables(Parallel_Examples=[{
        "parallel_example_id": "PAR-01", "misconception_id": "MIS-T01-ADD",
        "problem_statement": "There are p pencils.",
        "worked_steps": "1. Multiply p by 3.", "final_answer": "3p",
    }])
    content = next(c for r, k, c, _ in qa.support_items(data) if r == "PAR-01")
    assert "p pencils" in content and "Multiply" in content and "3p" in content


def test_an_item_with_no_text_is_reported_rather_than_reviewed():
    """Sending an empty string gets a confident verdict about nothing, and
    the verdict is usually OK."""
    data = tables(Parallel_Examples=[{
        "parallel_example_id": "PAR-EMPTY", "misconception_id": "MIS-T01-ADD",
        "problem_statement": "", "worked_steps": "", "final_answer": "",
    }])
    usable, blank = qa.reviewable(qa.support_items(data))
    assert "PAR-EMPTY" not in [record_id for record_id, *_ in usable]
    assert [f.record_id for f in blank] == ["PAR-EMPTY"]
    assert blank[0].rule_code == "SUPPORT_HAS_CONTENT"
    assert blank[0].table == "Parallel_Examples"
    assert not blank[0].blocking


def test_a_blank_item_never_reaches_the_model():
    data = tables(Parallel_Examples=[{
        "parallel_example_id": "PAR-EMPTY", "misconception_id": "MIS-T01-ADD",
        "problem_statement": "", "worked_steps": "", "final_answer": "",
    }])
    client = FakeLLMClient([reviews(
        {"record_id": "HINT-T01-01", "verdict": "OK"},
    )])
    qa.review_support(data, client)
    assert "PAR-EMPTY" not in client.calls[0]["user"]


# ──────────────────────────────────────────────────────────────────────
# Independence
# ──────────────────────────────────────────────────────────────────────

def test_the_reviewer_is_asked_to_judge_not_to_rewrite():
    """A reviewer asked to write a better version always finds the existing
    one wanting, and the report fills with preferences."""
    for prompt in (qa.ANSWER_SYSTEM_PROMPT, qa.QUESTION_SYSTEM_PROMPT,
                   qa.SUPPORT_SYSTEM_PROMPT):
        text = " ".join(prompt.split())
        assert "verdict" in text
        assert "Give a verdict for EVERY" in text


def test_no_generation_instruction_leaks_into_a_review_prompt():
    """If the reviewer saw the rules the content was written to, it would
    grade against those rules rather than against the mathematics, and agree
    by construction."""
    from answer_generator import SYSTEM_PROMPT as GENERATION_PROMPT

    distinctive = [line.strip() for line in GENERATION_PROMPT.splitlines()
                   if len(line.strip()) > 40]
    for prompt in (qa.ANSWER_SYSTEM_PROMPT, qa.QUESTION_SYSTEM_PROMPT,
                   qa.SUPPORT_SYSTEM_PROMPT):
        for line in distinctive:
            assert line not in prompt


def test_the_answer_prompt_forbids_marking_wrong_on_preference():
    text = " ".join(qa.ANSWER_SYSTEM_PROMPT.split())
    assert "Do not mark something WRONG because you would have phrased it" in text
    assert "Several accepted forms of one answer is correct and normal" in text


def test_the_prompt_tells_the_reviewer_to_say_unsure_rather_than_guess():
    text = " ".join(qa.ANSWER_SYSTEM_PROMPT.split())
    assert "rather than guessing" in text


# ──────────────────────────────────────────────────────────────────────
# Batching and reporting
# ──────────────────────────────────────────────────────────────────────

def test_work_is_split_into_batches():
    specs = [dict(tables()["Answer_Specs"][0],
                  answer_spec_id=f"ANS-T01-{i:03d}") for i in range(25)]
    data = tables(Answer_Specs=specs)
    client = FakeLLMClient([
        reviews(*[{"answer_spec_id": s["answer_spec_id"], "verdict": "OK"}
                  for s in specs[start:start + 10]])
        for start in range(0, 25, 10)
    ])
    report = qa.review_answers(data, client, batch=10)
    assert len(client.calls) == 3
    assert report.calls == 3
    assert report.reviewed == 25
    assert not report.findings


def test_a_report_can_be_merged_with_another():
    first = qa.QAReport(reviewed=3, calls=1)
    second = qa.QAReport(reviewed=2, calls=1, unsure=1)
    first.extend(second)
    assert (first.reviewed, first.calls, first.unsure) == (5, 2, 1)


def test_the_summary_says_nothing_was_found_when_nothing_was():
    assert "nothing reported" in qa.summarise(qa.QAReport(reviewed=4, calls=1))


def test_the_summary_puts_blocking_findings_first():
    report = qa.QAReport(findings=[
        qa._finding("AGE_APPROPRIATE_LANGUAGE", "Questions", "Q-2", "wordy", "read it"),
        qa._finding("ANSWER_CORRECT", "Answer_Specs", "ANS-1", "wrong", "check it"),
    ], reviewed=2, calls=1)
    text = qa.summarise(report)
    assert text.index("ANS-1") < text.index("Q-2")


def test_a_finding_serialises_like_a_validator_finding():
    """The two reports have to merge, so QA emits the same shape."""
    report = _answer_review([reviews({
        "answer_spec_id": "ANS-T01-001", "verdict": "WRONG",
        "problem": "ANSWER", "should_be": "n + 5", "why": "Adds 5.",
    })])
    payload = report.findings[0].as_dict("QA-001")
    assert set(payload) == {
        "validation_id", "severity", "table", "record_id", "rule_code",
        "issue", "recommended_action", "blocking",
    }


def test_parts_can_be_run_on_their_own():
    """A full pass is 80 calls on a six-topic workbook. Being able to run
    only the answer keys is the difference between checking the thing that
    matters most and paying for everything."""
    client = FakeLLMClient([reviews(
        {"answer_spec_id": "ANS-T01-001", "verdict": "OK"},
    )])
    qa.review_tables(tables(), client, parts=["answer keys"])
    assert len(client.calls) == 1


def test_an_upstream_failure_is_not_swallowed():
    with pytest.raises(LLMError):
        _answer_review([LLMError("upstream is down")])