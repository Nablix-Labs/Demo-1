"""CG-011: generate the Questions table for a topic.

The largest task in M3, and the first where being wrong is worse than being
absent: a question whose maths does not work teaches the student something
false, and it will be marked against an answer key generated from the same
flawed premise in CG-013.

What the reference workbook contains
------------------------------------

54 questions across three topics -- 16, 21 and 17 -- so roughly 16 to 21 each.

    SINGLE_CHOICE               28
    SHORT_RESPONSE              14
    MULTI_PART_SHORT_RESPONSE    9
    CHOICE_WITH_EXPLANATION      3

    difficulty 1   22
    difficulty 2   32

`TRUE_FALSE_WITH_EXPLANATION` exists in the enum and is unused in the
reference. It is allowed here rather than forbidden, because absence from
three topics is not proof it is wrong.

Ids, and why the model does not choose them
--------------------------------------------

Three ids per question, and only one is a free choice:

    question_id       Q-T01-001, minted in order by IdService
    answer_spec_id    ANS-T01-001, DERIVED from the question id so the
                      QUESTION_HAS_ANSWER check cannot fail through two
                      counters drifting apart
    item_family_id    FAM-T01-CONTEXT-ADD, from a descriptor the model
                      supplies

The family is the only one the model has any say in, and even then it hands
over a descriptor rather than an id. Same reasoning as micro-skills: a model
that numbers its own rows will eventually skip one.

The family is a grouping, not a row identity. Variants of the same question
are meant to share one, so two questions returning the same descriptor is
allowed and produces the same family id.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from answer_generator import question_options
from id_service import IdError, IdService, slugify
from llm_client import LLMClient
from models import (
    NormalizedTopicBrief,
    QuestionRow,
    QuestionStatus,
    QuestionType,
)
from validation import Severity, ValidationIssue

DEFAULT_VERSION = "1.0"
# Not APPROVED. APPROVED is a claim that the mathematics is right, and no
# generator can make it: CG-020's structural checks and CG-021's independent
# QA pass are what earn it. Stamping it here made every generated question
# look reviewed when none of it had been.
DEFAULT_STATUS = QuestionStatus.GENERATED

# The reference runs 16 to 21 per topic. The bounds are wider than that
# because three topics is a thin basis for a hard rule.
MIN_QUESTIONS = 8
MAX_QUESTIONS = 30

#: The reference is 52% SINGLE_CHOICE. This is the floor the prompt states,
#: set below the target rather than at it: the point is to catch a bank that
#: has drifted somewhere useless, not to nag about a topic that came in at 45%
#: because its content genuinely suits written answers.
MIN_CHOICE_SHARE = 1 / 3

# 3 is new in the reviewed spec; the approved reference uses only 1 and 2.
VALID_DIFFICULTIES = (1, 2, 3)

# Shortest text that could plausibly be a question. Anything under this is a
# fragment, not a task.
MIN_QUESTION_CHARS = 20


class QuestionError(Exception):
    """The model's questions could not be trusted for this topic."""


SYSTEM_PROMPT = """\
You write practice questions for a maths tutoring system. Return a single JSON
object and nothing else. No prose, no markdown.

Return exactly this shape:

{
  "questions": [
    {
      "question_text": "3 + 5, 9 + 5, 14 + 5. Use n for the changing starting number. Write the general rule.",
      "question_type": "SHORT_RESPONSE",
      "difficulty": 1,
      "item_family": "GENERAL-ADD",
      "micro_skill_positions": [1, 2]
    }
  ]
}

Rules, in order of importance:

1. THE MATHS MUST BE CORRECT. A question with a wrong premise, an impossible
   answer, or an ambiguous one teaches the student something false. If you are
   not certain a question is sound, do not write it. Fewer good questions is
   the better outcome.

2. ONE CLEAR TASK PER QUESTION. The student must be able to tell exactly what
   is being asked. "Write the general rule" is one task. "Write the rule and
   explain why it works and give an example" is three, and belongs in
   MULTI_PART_SHORT_RESPONSE or as separate questions.

3. Stay inside the topic's scope. Every question must exercise something in
   the included scope. Nothing may require anything from the excluded scope,
   even in passing: a question about writing a rule must not need the student
   to expand brackets if brackets are excluded.

4. question_type is one of:
     SINGLE_CHOICE                 pick one option
     SHORT_RESPONSE                a word, number or expression
     MULTI_PART_SHORT_RESPONSE     two or three linked short answers
     CHOICE_WITH_EXPLANATION       pick one, then say why
     TRUE_FALSE_WITH_EXPLANATION   true or false, then say why
   For SINGLE_CHOICE and CHOICE_WITH_EXPLANATION, write the options into
   question_text, labelled a), b), c). Wrong options must be plausible: base
   them on the misconceptions listed in the brief, not on absurdities.

   SINGLE_CHOICE means EXACTLY ONE option is correct. There is no
   select-all-that-apply type, so never write "write the letters of all
   correct options", "choose all that apply", or any question with two or
   more correct options. To ask which of several things are terms or
   factors, keep it SINGLE_CHOICE and make each option a complete candidate
   set: a) 4x only  b) x only  c) both 4x and 9. Only fall back to
   SHORT_RESPONSE if that genuinely cannot be phrased as one correct option.

   USE ROUGHLY THIS MIX. For a topic of 18 questions the approved reference
   holds:

     SINGLE_CHOICE                 9   about half of every topic
     SHORT_RESPONSE                5
     MULTI_PART_SHORT_RESPONSE     3
     CHOICE_WITH_EXPLANATION       1

   Scale those to the number of questions you write, and treat the first row
   as a floor rather than a suggestion: AT LEAST A THIRD of your questions
   must be SINGLE_CHOICE.

   This matters for a reason that is not visible from one question. A
   free-text answer can only be marked by judging what the student meant,
   which the tutor gets wrong sometimes and which costs a model call every
   time. An option letter is a string comparison. A bank that is mostly
   free text is slower and less reliable for every student who uses it, so
   reach for SHORT_RESPONSE when the answer really is prose, not because it
   is quicker to write.

5. difficulty is 1, 2 or 3, and means COGNITIVE DEMAND, not bigger numbers.
   Substituting n = 47 instead of n = 4 is the same question.

     1  Direct recognition or application. Familiar representation, usually
        one obvious step.
     2  Independent application or interpretation that needs a meaningful
        choice, or a distinction a common misconception would get wrong.
     3  Transfer: an unfamiliar representation, multi-step reasoning, or
        telling apart two ideas that look alike.

   Use all three.

6. item_family is a SHORT UPPERCASE HYPHENATED descriptor of what the
   question is testing, three words or fewer: GENERAL-ADD,
   INTERPRET-RULE, CONTEXT-SUBTRACT. Questions testing the same thing in the
   same way share a family. Do not number them.

7. micro_skill_positions lists which of the topic's micro-skills the question
   exercises, by their 1-based position in the list given below. At least one,
   rarely more than three. This is what makes a question markable against a
   skill rather than just against an answer.

8. Write 12 to 20 questions, ordered from most foundational to most demanding.
   Use the misconceptions in the brief to decide what needs testing: a
   misconception nobody is ever asked about will never be caught.
"""


def build_user_prompt(
    brief: NormalizedTopicBrief,
    micro_skills: Optional[list] = None,
) -> str:
    """Render one topic's brief and its micro-skills for the model."""
    lines = [
        f"Topic {brief.sequence_no}: {brief.topic_title}",
        f"Key stage: {brief.ks_stage.value}",
        "",
        f"Learning goal: {brief.learning_goal}",
        f"Core message: {brief.core_message}",
        "",
        "In scope, questions must exercise these:",
        *(f"  - {item}" for item in brief.included_scope),
        "",
        "OUT of scope, no question may require these:",
        *(f"  - {item}" for item in brief.excluded_scope),
        "",
        "Misconceptions to test for. Wrong options should come from these:",
        *(f"  - {item}" for item in brief.misconceptions_to_prevent),
    ]

    if micro_skills:
        lines += [
            "",
            "Micro-skills for this topic. Reference them by position:",
            *(
                f"  {position}. {row.skill_name} -- {row.description}"
                for position, row in enumerate(micro_skills, start=1)
            ),
        ]

    return "\n".join(lines)


@dataclass
class QuestionSet:
    """The questions generated for one topic."""

    topic_code: str
    rows: list[QuestionRow] = field(default_factory=list)
    # question_id -> the micro-skill ids it exercises. Not a Questions column;
    # CG-012 turns it into Question_MicroSkills rows.
    skill_links: dict[str, list[str]] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_error]

    @property
    def is_clean(self) -> bool:
        return not self.errors


#: Wordings that ask for more than one option. Taken from the three real
#: cases plus the usual phrasings around them. Deliberately narrow: it looks
#: for a plural demand for options, so an ordinary question mentioning
#: "all the terms" in its stem is not caught.
MULTI_SELECT_RE = re.compile(
    r"(?:"
    r"letters?\s+of\s+all"
    r"|all\s+(?:that|which)\s+apply"
    r"|(?:select|choose|write|circle|tick|give|list|state)\s+"
    r"(?:the\s+)?(?:letters|all\s+(?:the\s+)?(?:correct|right)\s+"
    r"(?:options?|answers?|letters?))"
    r"|which\s+(?:two|three|of\s+these\s+are)\b"
    r")",
    re.IGNORECASE,
)


def _multi_select_phrase(text: str) -> Optional[str]:
    """The phrase asking for several options, if the question asks for any."""
    found = MULTI_SELECT_RE.search(" ".join(text.split()))
    return found.group(0) if found else None


#: A stem that introduces a list of separate things to produce, as in
#: "write down:" followed by bulleted or numbered parts. This is the shape a
#: real run produced while typed SHORT_RESPONSE.
LIST_STEM_RE = re.compile(r":\s*$|:\s*[\n\r]", re.MULTILINE)
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*•]|\(?[a-d][).]|\d+[).])\s+\S", re.MULTILINE)

#: Asking for three or more named things in one sentence, as the reference's
#: own multi-part questions do: "identify the variable, the constant and the
#: operation".
MULTI_ASK_RE = re.compile(
    r"\b(?:identify|state|name|write down|give|list|find)\b"
    r"[^.?!]*?,[^.?!]*?\band\b",
    re.IGNORECASE,
)


def multi_part_shape(text: str) -> Optional[str]:
    """Why this question looks like it asks for several separate answers.

    A real run produced this, typed SHORT_RESPONSE:

        In the expression n + 4, write down:
        - the letter used,
        - the number used,
        - the operation symbol used.

    That is three answers, so the answer generator reached for MULTI_PART,
    which SHORT_RESPONSE does not allow, and the topic lost all 18 of its
    keys. The answer generator was right and the question was mistyped, so
    the check belongs here.

    Deliberately narrow. It wants either an explicit list of parts, or the
    "identify A, B and C" phrasing the reference's own multi-part questions
    use. A question that merely contains a comma is not caught.
    """
    body = str(text or "")
    if LIST_STEM_RE.search(body) and len(LIST_ITEM_RE.findall(body)) >= 2:
        return "a stem ending in a colon followed by a list of parts"
    found = MULTI_ASK_RE.search(" ".join(body.split()))
    if found:
        return f"asks for three things at once: {found.group(0)[:60]!r}"
    return None


def _retype_multi_part(
    name: str,
    questions: list,
) -> tuple[list, list[ValidationIssue]]:
    """Relabel a SHORT_RESPONSE question that plainly asks for several answers.

    The question itself is fine. Only its label is wrong, so dropping it would
    throw away good content to fix a one-word mistake. Retyping keeps it and
    lets the answer generator use MULTI_PART, which is what it reached for
    anyway when this happened for real and cost a topic all 18 of its keys.

    Reported as a warning every time. A silent retype would hide the fact that
    the question prompt is producing mislabelled questions, which is the thing
    that actually needs fixing.
    """
    notes: list[ValidationIssue] = []
    out: list = []

    for position, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            out.append(question)
            continue

        if question.get("question_type") == "SHORT_RESPONSE":
            reason = multi_part_shape(str(question.get("question_text") or ""))
            if reason:
                question = dict(question)
                question["question_type"] = "MULTI_PART_SHORT_RESPONSE"
                notes.append(ValidationIssue(
                    Severity.WARNING, name, f"questions[{position}]",
                    f"retyped SHORT_RESPONSE to MULTI_PART_SHORT_RESPONSE: "
                    f"{reason}",
                ))
        out.append(question)

    return out, notes


def _check(
    name: str,
    questions: list,
    skill_count: int,
) -> tuple[list[ValidationIssue], set[int]]:
    """Everything wrong with the model's questions, in one pass.

    Returns the issues and the 1-based positions of questions that are
    individually unusable. Tracking positions is what lets a caller drop one
    bad question instead of discarding the whole batch: a model that writes
    twelve good questions and one malformed one has still done most of the
    work, and on a six-topic run that difference decides whether anything
    reaches the workbook at all.
    """
    issues: list[ValidationIssue] = []
    bad: set[int] = set()

    def error(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, name, field_name, message))
        # "questions[4]" -> 4. Batch-level errors have no index and so mark
        # nothing droppable, which is correct: a count problem is not fixed by
        # removing a question.
        if field_name.startswith("questions["):
            bad.add(int(field_name[len("questions["):-1]))

    def warn(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.WARNING, name, field_name, message))

    if not isinstance(questions, list) or not questions:
        error("questions", "model returned no questions")
        return issues, bad

    if len(questions) < MIN_QUESTIONS:
        error("questions", f"only {len(questions)} questions; expected at least {MIN_QUESTIONS}")
    if len(questions) > MAX_QUESTIONS:
        error("questions", f"{len(questions)} questions; expected at most {MAX_QUESTIONS}")

    valid_types = {t.value for t in QuestionType}
    texts_seen: set[str] = set()

    for position, question in enumerate(questions, start=1):
        where = f"questions[{position}]"
        if not isinstance(question, dict):
            error(where, "not an object")
            continue

        text = question.get("question_text")
        if not isinstance(text, str) or not text.strip():
            error(where, "question_text is missing or empty")
        elif len(text.strip()) < MIN_QUESTION_CHARS:
            error(where, f"question_text is too short to be a task: {text.strip()!r}")
        else:
            key = " ".join(text.lower().split())
            if key in texts_seen:
                error(where, f"duplicate question_text: {text.strip()[:50]!r}")
            texts_seen.add(key)

        qtype = question.get("question_type")
        if qtype not in valid_types:
            error(where, f"question_type {qtype!r} is not one of {sorted(valid_types)}")
        elif qtype in ("SINGLE_CHOICE", "CHOICE_WITH_EXPLANATION"):
            # A choice question with no options in the text cannot be answered.
            # Detected with the same regex the answer generator uses to read
            # option letters back, so the two cannot disagree about what
            # counts as an option.
            if len(question_options(str(text or ""))) < 2:
                error(where,
                      f"{qtype} but question_text carries fewer than two "
                      f"labelled options; it cannot be answered")

            # Select-all-that-apply, mistyped as a single choice. The
            # six-topic run produced three of these; the answer generator
            # correctly returned "AB" and "ABCD" and the answer key was
            # then refused for not being one letter, which pointed at the
            # wrong module. The schema has no multi-select type, so the
            # question is what has to change.
            phrase = _multi_select_phrase(str(text or ""))
            if phrase:
                error(where,
                      f"{qtype} asks for more than one option ({phrase!r}); "
                      f"exactly one option must be correct, and there is no "
                      f"select-all question type")

        difficulty = question.get("difficulty")
        if difficulty not in VALID_DIFFICULTIES:
            error(where, f"difficulty {difficulty!r} is not 1 or 2")

        family = question.get("item_family")
        if not isinstance(family, str) or not family.strip():
            error(where, "item_family is missing or empty")
        else:
            try:
                slugify(family)
            except IdError as exc:
                error(where, f"item_family {family!r} is unusable: {exc}")

        positions = question.get("micro_skill_positions")
        if not isinstance(positions, list) or not positions:
            error(where, "micro_skill_positions is missing or empty; a question "
                         "that exercises no skill cannot be marked against one")
        elif skill_count:
            for value in positions:
                if not isinstance(value, int) or isinstance(value, bool):
                    error(where, f"micro_skill_positions entry {value!r} is not a number")
                elif value < 1 or value > skill_count:
                    error(where,
                          f"micro_skill_positions {value} is outside the "
                          f"{skill_count} skills offered")

    difficulties = {
        q.get("difficulty") for q in questions if isinstance(q, dict)
    }
    if len(difficulties) == 1:
        warn("difficulty",
             f"every question is difficulty {difficulties.pop()!r}; the "
             f"reference uses both")

    types = {q.get("question_type") for q in questions if isinstance(q, dict)}
    if len(types) == 1:
        warn("question_type",
             f"every question is {types.pop()!r}; the reference uses four kinds")

    # The mix drifted from 52% multiple choice in the reference to 25% and
    # then 11% across two runs, taking the share of the bank that can be
    # marked by exact comparison from 76% down to 39%. Nothing caught it,
    # because every individual question was fine. Only the proportions were
    # wrong, so only a check on the proportions can see it.
    usable = [q for q in questions if isinstance(q, dict)]
    if len(usable) >= MIN_QUESTIONS:
        choice = sum(1 for q in usable if q.get("question_type") == "SINGLE_CHOICE")
        share = choice / len(usable)
        if share < MIN_CHOICE_SHARE:
            warn("question_type",
                 f"only {choice} of {len(usable)} questions ({share:.0%}) are "
                 f"SINGLE_CHOICE; the reference is about half. A free-text "
                 f"answer costs a model call to mark and is sometimes marked "
                 f"wrong, so a bank this far from the reference is slower and "
                 f"less reliable for every student")

    return issues, bad


def generate_questions(
    brief: NormalizedTopicBrief,
    client: LLMClient,
    *,
    micro_skills: Optional[list] = None,
    source_provenance_id: Optional[str] = None,
    strict: bool = True,
    drop_invalid: bool = False,
    id_service: Optional[IdService] = None,
    version: str = DEFAULT_VERSION,
) -> QuestionSet:
    """Generate one topic's questions. Ids are assigned here, not by the model.

    `drop_invalid` discards individual malformed questions and keeps the rest,
    provided enough remain. Without it, one bad question out of thirteen loses
    all thirteen, and on a six-topic run that decides whether anything reaches
    the workbook at all. The dropped ones stay in `issues`, so this reports
    rather than hides.

    It does not rescue a batch-level problem. Too few questions, or a response
    that is not a list, is not fixed by removing a question, so those still
    fail.
    """
    name = brief.source_file_name
    skills = micro_skills or []

    payload = client.complete_json(
        SYSTEM_PROMPT,
        build_user_prompt(brief, skills),
        purpose=f"CG-011 questions for {name}",
    )

    questions = payload.get("questions")

    retyped: list[ValidationIssue] = []
    if isinstance(questions, list):
        questions, retyped = _retype_multi_part(name, questions)

    issues, bad_positions = _check(name, questions, len(skills))
    issues = retyped + issues
    errors = [i for i in issues if i.is_error]

    if errors and drop_invalid and bad_positions:
        kept = [q for n, q in enumerate(questions, start=1) if n not in bad_positions]
        # Re-check what survived: dropping may take the batch below the
        # minimum, and a batch-level error is not cured by dropping.
        recheck, still_bad = _check(name, kept, len(skills))
        if not [i for i in recheck if i.is_error]:
            # The batch recovered, so its issues should not still read as
            # errors -- is_clean would say False for a set that is now fine.
            # The detail is kept, downgraded to warnings, because "we dropped
            # question 5" is far less useful than "we dropped question 5
            # because it was a choice question with no options".
            issues = [
                ValidationIssue(Severity.WARNING, i.source_file_name, i.field,
                                f"dropped: {i.message}")
                if i.is_error else i
                for i in issues
            ] + [
                ValidationIssue(
                    Severity.WARNING, name, "questions",
                    f"dropped {len(bad_positions)} unusable question(s) at "
                    f"position(s) {sorted(bad_positions)}; kept {len(kept)}",
                )
            ]
            questions = kept
            errors = []

    if errors and strict:
        raise QuestionError(
            f"{name}: the model's questions cannot be used.\n"
            + "\n".join(f"  {i}" for i in errors)
        )
    if errors:
        return QuestionSet(brief.topic_code, [], {}, issues, payload)

    if id_service is None:
        id_service = IdService(brief.topic_code)

    rows: list[QuestionRow] = []
    links: dict[str, list[str]] = {}

    for question in questions:
        question_id = id_service.question_id()
        rows.append(
            QuestionRow(
                question_id=question_id,
                topic_id=brief.topic_id,
                question_text=str(question["question_text"]).strip(),
                question_type=QuestionType(question["question_type"]),
                difficulty=int(question["difficulty"]),
                answer_spec_id=id_service.answer_spec_id(question_id),
                item_family_id=id_service.item_family_id(question["item_family"]),
                source_provenance_id=source_provenance_id or "",
                status=DEFAULT_STATUS,
                version=version,
            )
        )
        links[question_id] = [
            skills[p - 1].micro_skill_id
            for p in question["micro_skill_positions"]
        ]

    return QuestionSet(brief.topic_code, rows, links, issues, payload)


if __name__ == "__main__":
    import sys

    from brief_mapper import map_all
    from llm_client import default_client, is_configured
    from micro_skill_generator import generate_all_micro_skills

    if not is_configured():
        print("No OpenAI API key found. Set OPENAI_API_KEY in your environment.")
        sys.exit(1)

    client = default_client()
    briefs = map_all()
    skill_sets = generate_all_micro_skills(briefs, client)

    for brief, skills in zip(briefs, skill_sets):
        result = generate_questions(brief, client, micro_skills=skills.rows)
        print(f"\n{result.topic_code}  {len(result.rows)} questions")
        for row in result.rows:
            linked = ",".join(result.skill_links[row.question_id])
            print(f"  {row.question_id}  d{row.difficulty} "
                  f"{row.question_type.value:26} {row.item_family_id}")
            print(f"      {row.question_text[:88]}")
            print(f"      skills: {linked}")
        for issue in result.issues:
            print(f"    {issue}")
