"""CG-021: the semantic QA pass.

CG-020 checks whether a workbook holds together. This checks whether it is any
good, which is a different question and needs a different kind of answer.

It owns exactly what CG-020 declared it could not decide:

    ANSWER_CORRECT           is the canonical answer right
    ANSWER_STEPS_COMPLETE    do the steps actually reach it
    WORKED_EXAMPLE_CORRECT   is the worked example's mathematics valid
    SCAFFOLD_MATCH           does the scaffold fit its question
    SCOPE_EXCLUSION          does anything cross the topic boundary

plus the pedagogical checks of Task Specification 12.2: does a question test
the skill it claims, is the language right for the age, do hints reveal the
right amount, is the parallel example parallel, is the bank repetitive.

What makes it independent
--------------------------

"Independent LLM pass" is only worth anything if the reviewer can disagree
with the generator. Three things are done to make that possible:

  It reads the WRITTEN WORKBOOK, not the objects in memory. The reviewer sees
  what the platform would import.

  It never sees a generation prompt. If it were shown the instructions the
  content was written to, it would grade against those instructions rather
  than against the mathematics, and agree by construction.

  It is asked to JUDGE, not to produce. Every prompt below asks for a verdict
  on something that already exists. A reviewer asked to write a better version
  will always find the existing one wanting.

Running it on a different model is worth doing and is one argument away
(QA_MODEL), but it is not what makes the pass independent. The framing is.

A verdict is evidence, not proof
---------------------------------

A model saying an answer is wrong can itself be wrong. So every finding has to
be adjudicable by a person in seconds, which is why the prompts demand a
specific claim -- what the answer SHOULD be -- rather than a grade. "This is
wrong, it should be n + 5" can be checked. "Quality: 6/10" cannot.

Mathematics is blocking, judgement is not. A wrong answer key tells a correct
student they are wrong and then teaches against them, which is the worst thing
this pipeline can produce, and the specification lists it as blocking. Opinions
about pedagogy are surfaced and never block, because a run that stops on a
matter of taste is a run people learn to override.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from llm_client import LLMClient
from models import Phase
from validator import ERROR, WARNING, Finding, read_tables

#: The only phase NOT_CANVAS can apply to.
PHASE_3 = Phase.PHASE_3_INDEPENDENT_PRACTICE.value

#: A different model for the review is one argument away. Not what makes the
#: pass independent -- the framing is -- but it removes one shared blind spot.
QA_MODEL = os.getenv("CONTENT_GEN_QA_MODEL")

#: How many rows go into one call. Small enough that the model attends to each
#: item, large enough that a topic is not hundreds of requests. Answer keys get
#: the smallest batch because they are the highest-cost thing to get wrong.
ANSWER_BATCH = 10
QUESTION_BATCH = 15
SUPPORT_BATCH = 12

#: Verdicts a reviewer may return. Anything else is a malformed response.
OK, WRONG, UNSURE = "OK", "WRONG", "UNSURE"
VERDICTS = frozenset({OK, WRONG, UNSURE})

#: Mathematics blocks; judgement does not.
BLOCKING_RULES = frozenset({"ANSWER_CORRECT", "WORKED_EXAMPLE_CORRECT"})


class QAError(Exception):
    """The review could not be carried out."""


@dataclass
class QAReport:
    """What one review pass found."""

    findings: list[Finding] = field(default_factory=list)
    reviewed: int = 0
    unsure: int = 0
    calls: int = 0
    #: Verdicts dropped because the complaint cannot apply to what was being
    #: judged. Counted rather than hidden: a number climbing here means the
    #: prompt is misleading the reviewer.
    discarded: int = 0

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    def extend(self, other: "QAReport") -> None:
        self.findings.extend(other.findings)
        self.reviewed += other.reviewed
        self.unsure += other.unsure
        self.calls += other.calls
        self.discarded += other.discarded


def _batched(rows: list, size: int) -> Iterable[list]:
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _finding(rule_code: str, table: str, record_id: Optional[str],
             issue: str, action: str) -> Finding:
    return Finding(
        rule_code=rule_code,
        severity=ERROR if rule_code in BLOCKING_RULES else WARNING,
        table=table, record_id=record_id, issue=issue,
        recommended_action=action,
        blocking=rule_code in BLOCKING_RULES,
    )


# ──────────────────────────────────────────────────────────────────────
# Reading a verdict back
# ──────────────────────────────────────────────────────────────────────

def _verdicts(payload: dict, key: str = "reviews") -> list[dict]:
    """The reviewed items, or a clear failure.

    A malformed review is refused rather than treated as approval. Silence
    from a reviewer must never read as a pass -- that is how a whole topic's
    error map went missing on 7 September.
    """
    entries = payload.get(key)
    if not isinstance(entries, list):
        raise QAError(
            f"the reviewer returned no {key!r} list, so nothing was reviewed. "
            f"Treating that as approval would make a failed call look like a "
            f"clean bill of health"
        )
    return [e for e in entries if isinstance(e, dict)]


def _verdict_of(entry: dict) -> str:
    verdict = _text(entry.get("verdict")).upper()
    return verdict if verdict in VERDICTS else UNSURE


# ──────────────────────────────────────────────────────────────────────
# Answer keys: the thing most worth a second opinion
# ──────────────────────────────────────────────────────────────────────

ANSWER_SYSTEM_PROMPT = """\
You are checking the answer keys of a maths question bank for 11 to 14 year
olds. Someone else wrote them. Your job is to find the ones that are wrong.

Return a single JSON object and nothing else. No prose, no markdown.

{
  "reviews": [
    {"answer_spec_id": "ANS-T01-004",
     "verdict": "WRONG",
     "problem": "ANSWER",
     "should_be": "n + 5",
     "why": "The pattern adds 5 each time, so the rule is n + 5, not 5n."},
    {"answer_spec_id": "ANS-T01-005", "verdict": "OK"}
  ]
}

Give a verdict for EVERY answer spec listed. Missing one is not the same as
approving it.

verdict is one of:

  OK       the canonical answer is correct and the steps reach it
  WRONG    something is definitely wrong. Say what it should be.
  UNSURE   you cannot tell from what you were given. Use this rather than
           guessing; an unsure verdict is read by a person, a wrong guess
           sends someone to fix content that was already right.

problem, only when the verdict is WRONG, is one of:

  ANSWER          the canonical answer is not correct for the question
  STEPS           the answer is right but the steps do not lead to it, or
                  a step contains an arithmetic mistake
  ACCEPTED        a form listed as accepted is not actually correct
  WRONG_ANSWERS   something listed as a common wrong answer is actually
                  correct, so a student who wrote it would be marked wrong

That last one matters more than it looks. A question asking for the shorter
form of "y added to itself three times" listed "y + y + y" as a wrong answer.
It is not wrong, it just is not shorter, and a student writing it would be
told they had made a mistake.

Rules:

1. Judge the mathematics, not the wording. You are not being asked whether
   this is a good question.

2. Several accepted forms of one answer is correct and normal. "n+5" and
   "5+n" are the same answer.

3. Do not mark something WRONG because you would have phrased it differently.
   Only mark WRONG if a competent teacher would call it an error.

4. When you say WRONG, "should_be" must contain the actual correct answer,
   not a description of it. A person will read that field and compare.
"""


def build_answer_prompt(specs: list[dict], questions: dict[str, dict]) -> str:
    lines = ["Answer keys to check:"]
    for spec in specs:
        question = questions.get(_text(spec.get("question_id")), {})
        lines += [
            "",
            f"  {_text(spec.get('answer_spec_id'))}"
            f"  [{_text(question.get('question_type'))}]",
            f"    question: {' '.join(_text(question.get('question_text')).split())}",
            f"    canonical answer: {_text(spec.get('canonical_answer'))}",
            f"    also accepted: {_text(spec.get('accepted_answers'))}",
            f"    marked wrong: {_text(spec.get('common_wrong_answers'))}",
            f"    steps: {' '.join(_text(spec.get('answer_steps')).split())}",
        ]
    return "\n".join(lines)


#: Which rule code a reported problem belongs to. ACCEPTED and WRONG_ANSWERS
#: are answer-correctness faults too: both mean a student is marked against a
#: key that disagrees with the mathematics.
RULE_FOR_PROBLEM = {
    "ANSWER": "ANSWER_CORRECT",
    "STEPS": "ANSWER_STEPS_COMPLETE",
    "ACCEPTED": "ANSWER_CORRECT",
    "WRONG_ANSWERS": "ANSWER_CORRECT",
}


def review_answers(tables: dict[str, list[dict]], client: LLMClient,
                   *, batch: int = ANSWER_BATCH,
                   progress: Optional[Callable[[str], None]] = None) -> QAReport:
    """A second opinion on every answer key."""
    specs = tables.get("Answer_Specs", [])
    questions = {_text(q.get("question_id")): q
                 for q in tables.get("Questions", [])}
    report = QAReport()

    for number, group in enumerate(_batched(specs, batch), start=1):
        if progress:
            progress(f"    answer keys {number}: {len(group)} spec(s)")
        payload = client.complete_json(
            ANSWER_SYSTEM_PROMPT, build_answer_prompt(group, questions),
            purpose=f"CG-021 answer review, batch {number}",
        )
        report.calls += 1
        seen: set[str] = set()

        for entry in _verdicts(payload):
            spec_id = _text(entry.get("answer_spec_id"))
            seen.add(spec_id)
            verdict = _verdict_of(entry)
            if verdict == OK:
                continue
            if verdict == UNSURE:
                report.unsure += 1
                continue

            problem = _text(entry.get("problem")).upper()
            rule = RULE_FOR_PROBLEM.get(problem, "ANSWER_CORRECT")
            should_be = _text(entry.get("should_be"))
            report.findings.append(_finding(
                rule, "Answer_Specs", spec_id,
                f"{_text(entry.get('why')) or 'reported wrong by review'}"
                + (f" Should be: {should_be}" if should_be else ""),
                "Check this against the question before changing anything; a "
                "review verdict is evidence, not proof",
            ))

        # A spec nobody gave a verdict on has not been reviewed, and must not
        # be counted as one.
        report.reviewed += len(seen & {_text(s.get("answer_spec_id"))
                                       for s in group})
        for spec in group:
            spec_id = _text(spec.get("answer_spec_id"))
            if spec_id not in seen:
                report.unsure += 1
                report.findings.append(_finding(
                    "ANSWER_CORRECT", "Answer_Specs", spec_id,
                    "the reviewer returned no verdict for this key, so it is "
                    "unreviewed rather than approved",
                    "Re-run the review for this batch",
                ))
    return report


# ──────────────────────────────────────────────────────────────────────
# Questions: does it test what it claims, and is it fit for the reader
# ──────────────────────────────────────────────────────────────────────

QUESTION_SYSTEM_PROMPT = """\
You are reviewing maths questions for 11 to 14 year olds against the skill
each one claims to test and the boundary of its topic.

Return a single JSON object and nothing else. No prose, no markdown.

{
  "reviews": [
    {"question_id": "Q-T01-004",
     "verdict": "WRONG",
     "problem": "WRONG_SKILL",
     "why": "It asks the student to substitute a value, which is topic 6. The
             skill claimed is recognising a pattern."},
    {"question_id": "Q-T01-005", "verdict": "OK"}
  ]
}

Give a verdict for EVERY question listed.

problem, only when the verdict is WRONG, is one of:

  WRONG_SKILL   answering it correctly does not demonstrate the micro-skill
                it is mapped to, or a student could get it right without
                having that skill at all
  OUT_OF_SCOPE  it needs something the topic explicitly excludes, or teaches
                past its own boundary
  LANGUAGE      the wording is too hard for the age, or the maths is buried
                in reading difficulty rather than in the mathematics
  NOT_CANVAS    a Phase 3 question that cannot be answered on the canvas -- it
                needs spoken explanation or free-form prose
  REPETITIVE    it is materially the same question as another in this batch,
                differing only in numbers or names

Rules:

1. A question may legitimately USE earlier skills. Only report OUT_OF_SCOPE
   when it requires something the excluded list names, not when it touches an
   idea from another topic in passing.

2. Judge the skill mapping by what a student must DO to answer, not by which
   words appear in the question.

3. REPETITIVE means a student learns nothing new from the second one. Several
   questions practising the same skill at different difficulties is the design
   working, not repetition.

4. Do not report LANGUAGE for mathematical vocabulary the topic is teaching.
   A topic about coefficients is allowed to say "coefficient".
"""


def build_question_prompt(questions: list[dict], skill_of: dict[str, str],
                          skills: dict[str, dict], phase_of: dict[str, str],
                          excluded: list[str]) -> str:
    lines = []
    if excluded:
        lines += ["This topic EXCLUDES:"]
        lines += [f"  {item}" for item in excluded]
        lines.append("")
    lines.append("Questions to review:")

    for question in questions:
        question_id = _text(question.get("question_id"))
        skill = skills.get(skill_of.get(question_id, ""), {})
        lines += [
            "",
            f"  {question_id}  [{_text(question.get('question_type'))}] "
            f"difficulty {question.get('difficulty')} "
            f"{phase_of.get(question_id, '')}",
            f"    {' '.join(_text(question.get('question_text')).split())}",
            f"    claims to test: {_text(skill.get('skill_name')) or 'nothing'}"
            f" -- {_text(skill.get('description'))}",
        ]
    return "\n".join(lines)


RULE_FOR_QUESTION_PROBLEM = {
    "WRONG_SKILL": "QUESTION_TESTS_ITS_SKILL",
    "OUT_OF_SCOPE": "SCOPE_EXCLUSION",
    "LANGUAGE": "AGE_APPROPRIATE_LANGUAGE",
    "NOT_CANVAS": "PHASE3_CANVAS_ONLY",
    "REPETITIVE": "NOT_REPETITIVE",
}


def review_questions(tables: dict[str, list[dict]], client: LLMClient,
                     *, batch: int = QUESTION_BATCH,
                     progress: Optional[Callable[[str], None]] = None) -> QAReport:
    """Whether each question tests what it claims and stays inside its topic."""
    questions = tables.get("Questions", [])
    skill_of = {_text(m.get("question_id")): _text(m.get("micro_skill_id"))
                for m in tables.get("Question_MicroSkills", [])
                if m.get("is_primary") is True}
    skills = {_text(s.get("micro_skill_id")): s
              for s in tables.get("Micro_Skills", [])}
    phase_of = {_text(u.get("question_id")): _text(u.get("phase"))
                for u in tables.get("Question_Usage", [])}
    excluded = [_text(s.get("item_text")) for s in tables.get("Topic_Scope", [])
                if _text(s.get("scope_type")) == "EXCLUDED"]

    report = QAReport()
    for number, group in enumerate(_batched(questions, batch), start=1):
        if progress:
            progress(f"    questions {number}: {len(group)} question(s)")
        payload = client.complete_json(
            QUESTION_SYSTEM_PROMPT,
            build_question_prompt(group, skill_of, skills, phase_of, excluded),
            purpose=f"CG-021 question review, batch {number}",
        )
        report.calls += 1
        report.reviewed += len(group)

        for entry in _verdicts(payload):
            verdict = _verdict_of(entry)
            if verdict == OK:
                continue
            if verdict == UNSURE:
                report.unsure += 1
                continue
            problem = _text(entry.get("problem")).upper()
            question_id = _text(entry.get("question_id"))

            # NOT_CANVAS is a Phase 3 rule. Phase 2 may ask for an
            # explanation -- the tutor is there to hear it -- and on the
            # smoke run of 8 September five of seven canvas findings were
            # Phase 2 questions. The phase is known here, so the verdict is
            # dropped rather than the model being trusted to remember.
            if problem == "NOT_CANVAS" and phase_of.get(question_id) != PHASE_3:
                report.discarded += 1
                continue

            report.findings.append(_finding(
                RULE_FOR_QUESTION_PROBLEM.get(problem, "QUESTION_TESTS_ITS_SKILL"),
                "Questions", question_id,
                _text(entry.get("why")) or f"reported {problem or 'faulty'}",
                "Read the question against the skill it is mapped to",
            ))
    return report


# ──────────────────────────────────────────────────────────────────────
# Support: hints, cues, parallel examples, scaffolds
# ──────────────────────────────────────────────────────────────────────

SUPPORT_SYSTEM_PROMPT = """\
You are reviewing the material a tutor uses when a student is stuck on a maths
question. Return a single JSON object and nothing else.

{
  "reviews": [
    {"record_id": "HINT-T01-003",
     "verdict": "WRONG",
     "problem": "GIVES_ANSWER",
     "why": "It states the rule is n + 5, which is the answer."},
    {"record_id": "HINT-T01-004", "verdict": "OK"}
  ]
}

Give a verdict for EVERY item listed.

THE THREE KINDS DO DIFFERENT JOBS. Judge each against its own job, which is
given in brackets after its id.

  hint              Nudges a stuck student WITHOUT answering. It must leave
                    the work to them.

  parallel example  A DIFFERENT problem of the same shape, worked through to
                    its answer, so the student can see the method and then
                    apply it to their own question. IT IS SUPPOSED TO SHOW
                    ITS ANSWER. That is what a worked example is. Never
                    report a parallel example for giving away an answer --
                    the answer it gives away is to another question.

  visual cue        A picture prompt. Judge whether the picture described
                    would help a student holding THIS belief.

  scaffold step     One stage of walking a student through a method. It may
                    break the work into smaller pieces; it may not perform
                    them. The student still does the thinking.

problem, only when the verdict is WRONG:

  For a hint:

  GIVES_ANSWER    it answers the student's own question, leaving nothing
                  for them to do
  TOO_VAGUE       so general it would not move any student forward
  WRONG_LEVEL     it does not do what its level says. ATTENTION points at
                  WHERE to look without saying what is wrong.
                  CONCEPT_REMINDER restates the missing idea in general
                  terms. PARTIAL_STEP does part of the work, leaving the rest

  For a parallel example:

  NOT_PARALLEL    it is not the same shape as the misconception it addresses,
                  so working through it teaches something else
  SAME_QUESTION   it is the student's own question again rather than a
                  different one, so it hands over the answer they needed

  For a visual cue:

  CUE_MISMATCH    the picture described would not help a student holding
                  this particular belief

  For a scaffold step:

  TAKES_OVER      it does the work for the student rather than reducing how
                  much they have to hold in mind at once

Rules:

1. Judge against the misconception each item is attached to, which is given.
   Something fine in general but not addressing THIS belief is wrong here.

2. The three hint levels are meant to give away different amounts. Three
   hints that reveal the same amount are one hint written three times, and
   the tutor has nothing to escalate through. Report the second and third as
   WRONG_LEVEL when that happens.

3. Use only a problem code listed for that item's kind. A complaint that does
   not apply to the kind of thing you are looking at will be discarded.
"""


def build_support_prompt(items: list[tuple[str, str, str, str]]) -> str:
    """items: (record_id, kind, what it says, the belief it addresses)."""
    lines = ["Support to review:"]
    for record_id, kind, content, belief in items:
        lines += [
            "",
            f"  {record_id}  [{kind}]",
            f"    says: {' '.join(_text(content).split())}",
            f"    for the belief: {' '.join(_text(belief).split())}",
        ]
    return "\n".join(lines)


RULE_FOR_SUPPORT_PROBLEM = {
    "GIVES_ANSWER": "HINT_REVEALS_TOO_MUCH",
    "TOO_VAGUE": "HINT_REVEALS_TOO_LITTLE",
    "WRONG_LEVEL": "HINT_REVEALS_TOO_MUCH",
    "NOT_PARALLEL": "PARALLEL_EXAMPLE_IS_PARALLEL",
    "SAME_QUESTION": "PARALLEL_EXAMPLE_IS_PARALLEL",
    "CUE_MISMATCH": "CUE_SUPPORTS_MISCONCEPTION",
    "TAKES_OVER": "SCAFFOLD_PRESERVES_AGENCY",
}

TABLE_FOR_SUPPORT_KIND = {
    "hint": "Hints",
    "visual cue": "Visual_Cues",
    "parallel example": "Parallel_Examples",
    "scaffold step": "Scaffold_Steps",
}

#: Which complaints can sensibly be made about which kind of support.
#:
#: This is a deterministic gate on a model's verdict, and it exists because of
#: a specific failure. On the smoke run of 8 September every one of the seven
#: support findings was a parallel example reported for "giving away the
#: answer" -- which is what a worked example is for, and final_answer is a
#: column the schema asks for. Seven findings, none of them real.
#:
#: The prompt now explains the difference, but a prompt is a request. This is
#: the guarantee: a complaint that cannot apply to the kind of thing being
#: judged is dropped rather than reported.
PROBLEMS_FOR_KIND = {
    "hint": frozenset({"GIVES_ANSWER", "TOO_VAGUE", "WRONG_LEVEL"}),
    "parallel example": frozenset({"NOT_PARALLEL", "SAME_QUESTION"}),
    "visual cue": frozenset({"CUE_MISMATCH"}),
    "scaffold step": frozenset({"TAKES_OVER"}),
}


def support_items(tables: dict[str, list[dict]]) -> list[tuple[str, str, str, str]]:
    """Every piece of support, paired with the belief it is attached to."""
    beliefs = {_text(m.get("misconception_id")): _text(m.get("description"))
               for m in tables.get("Misconceptions", [])}
    belief_of_hint = {_text(link.get("hint_id")): _text(link.get("misconception_id"))
                      for link in tables.get("Misconception_Hints", [])}
    belief_of_cue = {_text(link.get("visual_cue_id")):
                     _text(link.get("misconception_id"))
                     for link in tables.get("Misconception_VisualCues", [])}

    items: list[tuple[str, str, str, str]] = []
    for hint in tables.get("Hints", []):
        hint_id = _text(hint.get("hint_id"))
        items.append((
            hint_id, f"hint, level {hint.get('hint_level')} "
                     f"{_text(hint.get('hint_type'))}",
            _text(hint.get("content")),
            beliefs.get(belief_of_hint.get(hint_id, ""), "unknown"),
        ))
    for cue in tables.get("Visual_Cues", []):
        cue_id = _text(cue.get("visual_cue_id"))
        items.append((
            cue_id, "visual cue",
            _text(cue.get("image_generation_prompt")),
            beliefs.get(belief_of_cue.get(cue_id, ""), "unknown"),
        ))
    for example in tables.get("Parallel_Examples", []):
        # A parallel example is three columns, not one. Reading a single
        # "content" field here sent all 44 of them to the reviewer as empty
        # strings on the first attempt, which would have produced 44 confident
        # verdicts about nothing.
        content = " ".join(part for part in (
            _text(example.get("problem_statement")),
            _text(example.get("worked_steps")),
            f"answer: {_text(example.get('final_answer'))}"
            if _text(example.get("final_answer")) else "",
        ) if part)
        items.append((
            _text(example.get("parallel_example_id")), "parallel example",
            content,
            beliefs.get(_text(example.get("misconception_id")), "unknown"),
        ))

    # Scaffold steps. These were missing until 8 September, which meant the
    # TAKES_OVER complaint existed in the mapping and could never fire, and
    # Task Specification 12.2's question -- does the scaffold preserve student
    # agency -- was never actually asked. A test using a scaffold complaint on
    # a hint is what surfaced it.
    #
    # A scaffold is attached to a micro-skill rather than to a belief, so the
    # context given is the scaffold's own trigger rather than a misconception.
    scaffold_names = {_text(s.get("scaffold_id")): _text(s.get("scaffold_name"))
                      for s in tables.get("Scaffolds", [])}
    for step in tables.get("Scaffold_Steps", []):
        content = " ".join(part for part in (
            _text(step.get("prompt")),
            f"[shows: {_text(step.get('partial_content'))}]"
            if _text(step.get("partial_content")) else "",
            f"[expects: {_text(step.get('expected_response'))}]"
            if _text(step.get("expected_response")) else "",
        ) if part)
        items.append((
            _text(step.get("scaffold_step_id")),
            f"scaffold step, stage {step.get('stage_no')}",
            content,
            f"part of the scaffold "
            f"{scaffold_names.get(_text(step.get('scaffold_id')), 'unknown')!r}",
        ))
    return items


def reviewable(items: list[tuple[str, str, str, str]]) -> tuple[list, list[Finding]]:
    """Split the items with something to judge from the ones without.

    Sending an empty string to a reviewer gets a verdict on nothing, and the
    verdict will usually be OK. Anything blank is reported as unreviewable
    instead, which is a finding a person can act on.
    """
    usable, findings = [], []
    for item in items:
        record_id, kind, content, _belief = item
        if content.strip():
            usable.append(item)
            continue
        findings.append(_finding(
            "SUPPORT_HAS_CONTENT",
            TABLE_FOR_SUPPORT_KIND.get(kind.split(",")[0], "Hints"),
            record_id,
            f"this {kind.split(',')[0]} has no text, so there is nothing to "
            f"review and nothing to show a student",
            "Check the generator wrote the fields this row needs",
        ))
    return usable, findings


def review_support(tables: dict[str, list[dict]], client: LLMClient,
                   *, batch: int = SUPPORT_BATCH,
                   progress: Optional[Callable[[str], None]] = None) -> QAReport:
    """Whether hints, cues and parallel examples do their job."""
    items, blank = reviewable(support_items(tables))
    kind_of = {record_id: kind.split(",")[0] for record_id, kind, _, _ in items}
    report = QAReport(findings=list(blank))

    for number, group in enumerate(_batched(items, batch), start=1):
        if progress:
            progress(f"    support {number}: {len(group)} item(s)")
        payload = client.complete_json(
            SUPPORT_SYSTEM_PROMPT, build_support_prompt(group),
            purpose=f"CG-021 support review, batch {number}",
        )
        report.calls += 1
        report.reviewed += len(group)

        for entry in _verdicts(payload):
            verdict = _verdict_of(entry)
            if verdict == OK:
                continue
            if verdict == UNSURE:
                report.unsure += 1
                continue
            record_id = _text(entry.get("record_id"))
            problem = _text(entry.get("problem")).upper()
            kind = kind_of.get(record_id, "")

            # The gate. A parallel example reported for showing its answer is
            # not a finding, it is the reviewer forgetting what it is looking
            # at, and reporting it teaches people to distrust the report.
            if problem and problem not in PROBLEMS_FOR_KIND.get(kind, frozenset()):
                report.discarded += 1
                continue

            report.findings.append(_finding(
                RULE_FOR_SUPPORT_PROBLEM.get(problem, "HINT_REVEALS_TOO_MUCH"),
                TABLE_FOR_SUPPORT_KIND.get(kind, "Hints"),
                record_id,
                _text(entry.get("why")) or f"reported {problem or 'faulty'}",
                "Read it against the belief it is attached to",
            ))
    return report


# ──────────────────────────────────────────────────────────────────────
# The whole pass
# ──────────────────────────────────────────────────────────────────────

REVIEWS = (
    ("answer keys", review_answers),
    ("questions", review_questions),
    ("support", review_support),
)


def review_tables(tables: dict[str, list[dict]], client: LLMClient, *,
                  progress: Optional[Callable[[str], None]] = None,
                  parts: Optional[Iterable[str]] = None) -> QAReport:
    """Every review, against tables already read."""
    wanted = set(parts) if parts else {name for name, _ in REVIEWS}
    report = QAReport()
    for name, review in REVIEWS:
        if name not in wanted:
            continue
        if progress:
            progress(f"  reviewing {name}...")
        report.extend(review(tables, client, progress=progress))
    return report


def review_workbook(path, client: LLMClient, *,
                    progress: Optional[Callable[[str], None]] = None,
                    parts: Optional[Iterable[str]] = None) -> QAReport:
    """Every review, against a written workbook."""
    return review_tables(read_tables(path), client, progress=progress,
                         parts=parts)


def summarise(report: QAReport, limit: int = 30) -> str:
    """A short account of what the review found."""
    from collections import Counter

    if not report.findings:
        return (f"QA: {report.reviewed} item(s) reviewed in {report.calls} "
                f"call(s), nothing reported."
                + (f" {report.discarded} verdict(s) discarded as inapplicable."
                   if report.discarded else ""))

    counts = Counter(f.rule_code for f in report.findings)
    lines = [
        f"QA: {report.reviewed} item(s) reviewed in {report.calls} call(s). "
        f"{len(report.blocking)} blocking, "
        f"{len(report.findings) - len(report.blocking)} advisory"
        + (f", {report.unsure} unsure" if report.unsure else "")
        + (f", {report.discarded} discarded as inapplicable"
           if report.discarded else "") + ".",
        "  " + ", ".join(f"{code} x{n}" for code, n in counts.most_common()),
        "",
    ]
    ordered = report.blocking + [f for f in report.findings if not f.blocking]
    lines += [f"  {f}" for f in ordered[:limit]]
    if len(ordered) > limit:
        lines.append(f"  ... and {len(ordered) - limit} more")
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import sys

    from llm_client import default_client, is_configured

    if len(sys.argv) < 2:
        print("usage: python qa_reviewer.py <workbook.xlsx> [--json] "
              "[--only answer keys|questions|support]")
        raise SystemExit(2)
    if not is_configured():
        print("No OpenAI API key found.", file=sys.stderr)
        raise SystemExit(2)

    only = None
    if "--only" in sys.argv:
        only = [sys.argv[sys.argv.index("--only") + 1]]

    result = review_workbook(sys.argv[1], default_client(),
                             progress=lambda m: print(m, flush=True),
                             parts=only)
    print()
    if "--json" in sys.argv:
        print(json.dumps(
            [f.as_dict(f"QA-{n:03d}")
             for n, f in enumerate(result.findings, start=1)], indent=2))
    else:
        print(summarise(result))
    raise SystemExit(1 if result.blocking else 0)
