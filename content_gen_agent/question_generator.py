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

from dataclasses import dataclass, field
from typing import Optional

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
DEFAULT_STATUS = QuestionStatus.APPROVED

# The reference runs 16 to 21 per topic. The bounds are wider than that
# because three topics is a thin basis for a hard rule.
MIN_QUESTIONS = 8
MAX_QUESTIONS = 30

VALID_DIFFICULTIES = (1, 2)

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

5. difficulty is 1 or 2. 1 is a direct application of one idea. 2 combines
   two ideas, or applies one in an unfamiliar context. Use both.

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


def _check(
    name: str,
    questions: list,
    skill_count: int,
) -> list[ValidationIssue]:
    """Everything wrong with the model's questions, in one pass."""
    issues: list[ValidationIssue] = []

    def error(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, name, field_name, message))

    def warn(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.WARNING, name, field_name, message))

    if not isinstance(questions, list) or not questions:
        error("questions", "model returned no questions")
        return issues

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
            body = str(text or "").lower()
            if not any(marker in body for marker in ("a)", "a.", "(a", "option")):
                error(where,
                      f"{qtype} but question_text carries no visible options")

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

    return issues


def generate_questions(
    brief: NormalizedTopicBrief,
    client: LLMClient,
    *,
    micro_skills: Optional[list] = None,
    source_provenance_id: Optional[str] = None,
    strict: bool = True,
    id_service: Optional[IdService] = None,
    version: str = DEFAULT_VERSION,
) -> QuestionSet:
    """Generate one topic's questions. Ids are assigned here, not by the model."""
    name = brief.source_file_name
    skills = micro_skills or []

    payload = client.complete_json(
        SYSTEM_PROMPT,
        build_user_prompt(brief, skills),
        purpose=f"CG-011 questions for {name}",
    )

    questions = payload.get("questions")
    issues = _check(name, questions, len(skills))

    errors = [i for i in issues if i.is_error]
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
