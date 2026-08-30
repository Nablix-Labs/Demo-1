"""CG-013: generate the Answer_Specs table.

The answer key. If a question is merely bad, a student wastes a minute; if the
key is wrong, a student who answered correctly is told they are wrong, and the
tutor then teaches against them. That asymmetry is why this module refuses more
than it warns.

Nothing here can verify that the mathematics is right. That needs a person or
an independent model, and CG-021 is where the second opinion belongs. What can
be enforced is everything that makes a key *coherent*, and the reference gave
up four rules that turn out to be strong.

What the 54 approved rows establish
------------------------------------

**accepted and wrong never overlap.** Not once in 54. This is the invariant
that matters most: an answer in both lists means the marker's verdict depends
on which list it consults first. Enforced as an error.

**answer_type is decided by question_type.** Three of the four map one to one:

    SINGLE_CHOICE              -> SINGLE_CHOICE
    MULTI_PART_SHORT_RESPONSE  -> MULTI_PART
    CHOICE_WITH_EXPLANATION    -> CHOICE_WITH_EXPLANATION
    SHORT_RESPONSE             -> ALGEBRAIC_EXPRESSION or TEXT_MEANING

Only SHORT_RESPONSE is a real choice, between an expression and a description.

**verification_method is decided by answer_type**, three of five with no
choice at all. A SINGLE_CHOICE answer verified by SYMBOLIC_EQUIVALENCE would be
comparing option letters as algebra.

**canonical is among accepted, for the literal-match types only.** True for all
45 ALGEBRAIC_EXPRESSION, SINGLE_CHOICE and CHOICE_WITH_EXPLANATION rows, and
false for 8 of 9 MULTI_PART and 1 TEXT_MEANING, where canonical is a compact
form and accepted are its prose variants:

    canonical  c x d
    accepted   c times d | c multiplied by d | product of c and d

So it is enforced for the first group and not the second, rather than being
applied uniformly and generating false failures on a third of the table.

Choice questions get one extra check
-------------------------------------

For SINGLE_CHOICE the answer is an option letter -- canonical "B", accepted
"B", wrong "A | C | D". That makes it checkable against the question's own
text: a key whose answer letter does not appear among the options is wrong
about the question it is marking, and that is worth catching here rather than
in front of a student.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from id_service import IdService
from llm_client import LLMClient
from models import (
    AnswerSpecRow,
    AnswerType,
    QuestionRow,
    QuestionType,
    VerificationMethod,
)
from validation import Severity, ValidationIssue

# The workbook stores these as pipe-delimited strings.
LIST_SEPARATOR = " | "

# Derived from the reference. TRUE_FALSE_WITH_EXPLANATION appears in the enum
# but in none of the 54 rows, so its mapping is inferred from its shape rather
# than observed, and is marked as such.
ANSWER_TYPES_FOR_QUESTION: dict[str, list[str]] = {
    "SINGLE_CHOICE": ["SINGLE_CHOICE"],
    "MULTI_PART_SHORT_RESPONSE": ["MULTI_PART"],
    "CHOICE_WITH_EXPLANATION": ["CHOICE_WITH_EXPLANATION"],
    "SHORT_RESPONSE": ["ALGEBRAIC_EXPRESSION", "TEXT_MEANING"],
    # Inferred: same shape as CHOICE_WITH_EXPLANATION, pick one then justify.
    "TRUE_FALSE_WITH_EXPLANATION": ["CHOICE_WITH_EXPLANATION"],
}

VERIFICATION_FOR_ANSWER_TYPE: dict[str, list[str]] = {
    "SINGLE_CHOICE": ["EXACT_CHOICE_MATCH"],
    "CHOICE_WITH_EXPLANATION": ["CHOICE_AND_CONCEPT_MATCH"],
    "TEXT_MEANING": ["CONCEPT_TEXT_MATCH"],
    "ALGEBRAIC_EXPRESSION": ["SYMBOLIC_EQUIVALENCE", "EXACT_NOTATION_MATCH"],
    "MULTI_PART": [
        "STRUCTURED_TEXT_MATCH",
        "CONCEPT_TEXT_MATCH",
        "STRUCTURED_TEXT_AND_SYMBOLIC_MATCH",
    ],
}

# Types where the canonical answer is itself an acceptable response. Excludes
# MULTI_PART and TEXT_MEANING, where canonical is a compact form.
CANONICAL_MUST_BE_ACCEPTED = {
    "ALGEBRAIC_EXPRESSION", "SINGLE_CHOICE", "CHOICE_WITH_EXPLANATION",
}

# Types whose answer is an option letter.
LETTER_ANSWER_TYPES = {"SINGLE_CHOICE"}

MIN_WRONG_ANSWERS = 2      # reference minimum
MIN_ANSWER_STEPS = 2

OPTION_RE = re.compile(r"(?:^|[\s(])([A-Ha-h])[).:]")


class AnswerError(Exception):
    """The model's answer key could not be trusted for this question."""


SYSTEM_PROMPT = """\
You write the answer key for maths questions. Return a single JSON object and
nothing else. No prose, no markdown.

{
  "answers": [
    {
      "question_id": "Q-T01-001",
      "answer_type": "ALGEBRAIC_EXPRESSION",
      "canonical_answer": "n + 5",
      "accepted_answers": ["n+5", "5+n"],
      "common_wrong_answers": ["5n", "n5", "n-5"],
      "verification_method": "SYMBOLIC_EQUIVALENCE",
      "required_units": null,
      "explanation_required": false,
      "answer_steps": [
        "Compare the three cases.",
        "Identify the starting number as the changing part.",
        "Write the rule as n + 5."
      ]
    }
  ]
}

Rules, in order of importance:

1. THE ANSWER MUST BE CORRECT. A wrong key tells a student who answered
   correctly that they are wrong, and the tutor then teaches against them.
   That is worse than having no question at all. If you are not certain, say
   so by leaving the question out rather than guessing.

2. accepted_answers and common_wrong_answers MUST NOT OVERLAP. Not even in a
   different spelling or spacing. If a form is acceptable it cannot also be a
   known error, and a marker seeing it in both lists will contradict itself.

3. accepted_answers holds every form a correct student might reasonably write:
   different orderings (n+5 and 5+n), spacing, and common equivalent notations.
   Be generous here. Every form you omit is a correct student marked wrong.

4. common_wrong_answers holds what a student who has the MISCONCEPTION would
   write. Give at least two. Base them on the misconceptions supplied with the
   topic: "5n" for reading addition as multiplication, not an arbitrary wrong
   number. A wrong answer nobody would produce catches nobody.

5. For a multiple-choice question, the answer is the OPTION LETTER alone.
   canonical_answer is "B", accepted_answers is ["B"], and
   common_wrong_answers lists the other letters. Do not restate the option
   text.

6. answer_steps is the worked reasoning, two to five short numbered steps,
   each one action. This is what the tutor walks a stuck student through, so
   it must reach the canonical answer and not skip the step that is hard.

7. answer_type and verification_method are constrained by the question type
   and are given per question below. Use one of the values offered.
"""


def allowed_answer_types(question_type: QuestionType) -> list[str]:
    return ANSWER_TYPES_FOR_QUESTION.get(question_type.value, [])


def allowed_verifications(answer_type: str) -> list[str]:
    return VERIFICATION_FOR_ANSWER_TYPE.get(answer_type, [])


def build_user_prompt(
    questions: list[QuestionRow],
    misconceptions: Optional[list[str]] = None,
) -> str:
    """Render the questions needing a key, with the choices each one allows."""
    lines: list[str] = []

    if misconceptions:
        lines += [
            "Misconceptions for this topic. Wrong answers should come from "
            "these:",
            *(f"  - {item}" for item in misconceptions),
            "",
        ]

    lines.append("Questions needing an answer key:")
    for question in questions:
        types = allowed_answer_types(question.question_type)
        verifications = sorted({
            v for t in types for v in allowed_verifications(t)
        })
        lines += [
            "",
            f"  {question.question_id}  [{question.question_type.value}]",
            f"    {question.question_text}",
            f"    answer_type must be one of: {', '.join(types)}",
            f"    verification_method must be one of: {', '.join(verifications)}",
        ]
    return "\n".join(lines)


@dataclass
class AnswerSet:
    """The answer specs generated for one topic."""

    topic_code: str
    rows: list[AnswerSpecRow] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_error]

    @property
    def is_clean(self) -> bool:
        return not self.errors


def _normalise(value: object) -> str:
    """Whitespace and case removed, for comparing answer forms."""
    return "".join(str(value).split()).lower()


def question_options(question_text: str) -> set[str]:
    """The option letters a choice question offers, upper-cased."""
    return {m.group(1).upper() for m in OPTION_RE.finditer(question_text or "")}


def _check(
    name: str,
    answers: list,
    questions: dict[str, QuestionRow],
) -> list[ValidationIssue]:
    """Everything wrong with the model's answer key, in one pass."""
    issues: list[ValidationIssue] = []

    def error(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, name, field_name, message))

    def warn(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.WARNING, name, field_name, message))

    if not isinstance(answers, list) or not answers:
        error("answers", "model returned no answers")
        return issues

    seen: set[str] = set()

    for answer in answers:
        if not isinstance(answer, dict):
            error("answers", "entry is not an object")
            continue

        question_id = str(answer.get("question_id") or "")
        where = question_id or "<no question_id>"

        question = questions.get(question_id)
        if question is None:
            error(where, "no such question in this topic")
            continue
        if question_id in seen:
            error(where, "two answer keys for the same question")
            continue
        seen.add(question_id)

        # -- type and verification, both constrained -------------------
        answer_type = answer.get("answer_type")
        permitted = allowed_answer_types(question.question_type)
        if answer_type not in permitted:
            error(where,
                  f"answer_type {answer_type!r} is not valid for a "
                  f"{question.question_type.value} question; allowed {permitted}")
            continue

        verification = answer.get("verification_method")
        permitted_v = allowed_verifications(answer_type)
        if verification not in permitted_v:
            error(where,
                  f"verification_method {verification!r} cannot verify a "
                  f"{answer_type} answer; allowed {permitted_v}")

        # -- the answers themselves ------------------------------------
        canonical = answer.get("canonical_answer")
        if not isinstance(canonical, str) or not canonical.strip():
            error(where, "canonical_answer is missing or empty")
            continue

        accepted = answer.get("accepted_answers")
        wrong = answer.get("common_wrong_answers")

        if not isinstance(accepted, list) or not accepted:
            error(where, "accepted_answers is missing or empty")
            continue
        if not isinstance(wrong, list) or len(wrong) < MIN_WRONG_ANSWERS:
            error(where,
                  f"common_wrong_answers needs at least {MIN_WRONG_ANSWERS}; "
                  f"a key with no known errors catches nobody")
            continue

        accepted_norm = {_normalise(a) for a in accepted if str(a).strip()}
        wrong_norm = {_normalise(w) for w in wrong if str(w).strip()}

        if len(accepted_norm) != len([a for a in accepted if str(a).strip()]):
            warn(where, "accepted_answers repeats a form")
        if not accepted_norm:
            error(where, "accepted_answers has no usable entries")
            continue

        # THE invariant. Zero violations in 54 reference rows.
        overlap = accepted_norm & wrong_norm
        if overlap:
            error(where,
                  f"these appear as both accepted and wrong: {sorted(overlap)}. "
                  f"A marker would contradict itself")

        if answer_type in CANONICAL_MUST_BE_ACCEPTED:
            if _normalise(canonical) not in accepted_norm:
                error(where,
                      f"canonical_answer {canonical!r} is not among "
                      f"accepted_answers, so the model answer would be "
                      f"marked wrong")

        # -- choice questions: check against the question's own options -
        if answer_type in LETTER_ANSWER_TYPES:
            letters = question_options(question.question_text)
            if not re.fullmatch(r"[A-Ha-h]", canonical.strip()):
                error(where,
                      f"canonical_answer {canonical!r} is not an option letter; "
                      f"a choice answer is the letter alone")
            elif letters and canonical.strip().upper() not in letters:
                error(where,
                      f"canonical_answer {canonical.strip().upper()!r} is not "
                      f"among the options the question offers ({sorted(letters)})")

        # -- worked steps ----------------------------------------------
        steps = answer.get("answer_steps")
        if not isinstance(steps, list) or len(steps) < MIN_ANSWER_STEPS:
            error(where,
                  f"answer_steps needs at least {MIN_ANSWER_STEPS}; this is "
                  f"what a stuck student is walked through")
        elif any(not isinstance(s, str) or not s.strip() for s in steps):
            error(where, "answer_steps contains an empty step")

        if not isinstance(answer.get("explanation_required"), bool):
            error(where, "explanation_required must be true or false")

    missing = set(questions) - seen
    if missing:
        error("answers",
              f"no answer key for {len(missing)} question(s): {sorted(missing)[:5]}")

    return issues


def _numbered(steps: list[str]) -> str:
    """Newline-separated numbered steps, as the workbook stores them."""
    return "\n".join(f"{n}. {s.strip()}" for n, s in enumerate(steps, start=1))


def generate_answers(
    questions: list[QuestionRow],
    client: LLMClient,
    topic_code: str,
    *,
    misconceptions: Optional[list[str]] = None,
    strict: bool = True,
    id_service: Optional[IdService] = None,
) -> AnswerSet:
    """Generate the answer key for one topic's questions."""
    by_id = {q.question_id: q for q in questions}
    name = f"{topic_code} answers"

    payload = client.complete_json(
        SYSTEM_PROMPT,
        build_user_prompt(questions, misconceptions),
        purpose=f"CG-013 answer key for {topic_code}",
    )

    answers = payload.get("answers")
    issues = _check(name, answers, by_id)

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise AnswerError(
            f"{topic_code}: the model's answer key cannot be used.\n"
            + "\n".join(f"  {i}" for i in errors)
        )
    if errors:
        return AnswerSet(topic_code, [], issues, payload)

    if id_service is None:
        id_service = IdService(topic_code)

    rows: list[AnswerSpecRow] = []
    for answer in answers:
        question = by_id[answer["question_id"]]
        rows.append(
            AnswerSpecRow(
                # Derived from the question, not counted, so the two cannot
                # drift apart. Reuses the question's own suffix.
                answer_spec_id=question.answer_spec_id,
                question_id=question.question_id,
                answer_type=AnswerType(answer["answer_type"]),
                canonical_answer=str(answer["canonical_answer"]).strip(),
                accepted_answers=LIST_SEPARATOR.join(
                    str(a).strip() for a in answer["accepted_answers"]
                ),
                common_wrong_answers=LIST_SEPARATOR.join(
                    str(w).strip() for w in answer["common_wrong_answers"]
                ),
                verification_method=VerificationMethod(
                    answer["verification_method"]
                ),
                required_units=(answer.get("required_units") or None),
                explanation_required=bool(answer["explanation_required"]),
                answer_steps=_numbered(answer["answer_steps"]),
            )
        )

    return AnswerSet(topic_code, rows, issues, payload)
