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

# A MULTI_PART canonical answer joins its parts inside a single cell. Taken
# from the reference, where all 9 use it: "m; 7; addition".
MULTI_PART_SEPARATOR = "; "

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

# Question types whose answer is an option letter. Keyed on the QUESTION type,
# not the answer type, because CHOICE_WITH_EXPLANATION and
# TRUE_FALSE_WITH_EXPLANATION share one answer_type but not one answer shape:
# the first stores a letter, the second stores True or False. Keying on
# answer_type could not tell them apart.
#
# CHOICE_WITH_EXPLANATION belongs here on the reference's evidence: all 3 of
# its rows store the letter alone ("B") and carry the justification in
# explanation_required, not in canonical_answer. Leaving it out is what let a
# canonical of "a) n + 4, because it means..." through to the weaker
# canonical-in-accepted check, which reported a confusing error.
LETTER_ANSWER_QUESTIONS = {"SINGLE_CHOICE", "CHOICE_WITH_EXPLANATION"}

# Inferred, not observed: no TRUE_FALSE_WITH_EXPLANATION row exists in the
# reference. Treated as a two-option choice whose options are words.
TRUE_FALSE_QUESTIONS = {"TRUE_FALSE_WITH_EXPLANATION"}
TRUE_FALSE_ANSWERS = {"true", "false"}

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

5. Whenever the student picks a lettered option, the answer is the OPTION
   LETTER ALONE. That covers SINGLE_CHOICE, CHOICE_WITH_EXPLANATION and
   TRUE_FALSE_WITH_EXPLANATION alike: canonical_answer is "B", never "B)
   n + 4" and never "B, because...". Do not restate the option text and do
   not put the explanation in canonical_answer.

   For the two ...WITH_EXPLANATION types the student must also justify the
   choice, but that is recorded by setting explanation_required to true, not
   by writing the justification into canonical_answer. accepted_answers may
   hold the letter plus short correct phrasings of the reason:

     "answer_type": "CHOICE_WITH_EXPLANATION",
     "verification_method": "CHOICE_AND_CONCEPT_MATCH",
     "canonical_answer": "B",
     "accepted_answers": ["B", "a x a", "a multiplied by itself"],
     "common_wrong_answers": ["A", "2a", "a + a"],
     "explanation_required": true

   For TRUE_FALSE_WITH_EXPLANATION, canonical_answer is "True" or "False".

6. A MULTI_PART_SHORT_RESPONSE question asks for several things at once, so
   its key has a shape of its own. canonical_answer is every part in the
   question's own order, joined with "; " in ONE string. It is never blank
   and never a list:

     "answer_type": "MULTI_PART",
     "verification_method": "STRUCTURED_TEXT_MATCH",
     "canonical_answer": "m; 7; addition",
     "accepted_answers": ["m is the changing quantity", "7 is the fixed value",
                          "+ is the addition operation"]

   Note what accepted_answers holds here: an acceptable wording of an
   INDIVIDUAL part, not a rewrite of the whole answer. So for this type
   canonical_answer will usually not appear in accepted_answers, which is
   correct and expected.

   Give one part for each thing the question asks. If it asks for the
   variable, the constant and the operation, canonical_answer has three parts.

7. answer_steps is the worked reasoning, two to five short numbered steps,
   each one action. This is what the tutor walks a stuck student through, so
   it must reach the canonical answer and not skip the step that is hard.

8. answer_type and verification_method are constrained by the question type.
   Each question below lists the exact PAIRS it allows. Choose one pair and
   use both halves of it. Do not mix an answer_type from one pair with a
   verification_method from another.
"""


def allowed_answer_types(question_type: QuestionType) -> list[str]:
    return ANSWER_TYPES_FOR_QUESTION.get(question_type.value, [])


def allowed_verifications(answer_type: str) -> list[str]:
    return VERIFICATION_FOR_ANSWER_TYPE.get(answer_type, [])


def allowed_pairs(question_type: QuestionType) -> list[tuple[str, str]]:
    """The answer_type and verification_method combinations this question allows.

    Offering the two fields as separate lists is what produced three failures
    in the six-topic run. A SHORT_RESPONSE allows two answer types whose
    verification methods do not overlap at all, so the union of the two lists
    contains combinations that no answer type accepts. The model picked
    TEXT_MEANING from one list and EXACT_NOTATION_MATCH from the other -- both
    offered, the pairing invalid -- and the checker then rejected an answer
    that had followed the instructions exactly.

    A prompt that permits what the validator forbids is the prompt's bug.
    """
    return [
        (answer_type, verification)
        for answer_type in allowed_answer_types(question_type)
        for verification in allowed_verifications(answer_type)
    ]


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
        pairs = allowed_pairs(question.question_type)
        lines += [
            "",
            f"  {question.question_id}  [{question.question_type.value}]",
            f"    {question.question_text}",
            "    pick ONE answer_type / verification_method pair from this list:",
            *(f"      {a} + {v}" for a, v in pairs),
        ]
    return "\n".join(lines)


@dataclass
class AnswerSet:
    """The answer specs generated for one topic."""

    topic_code: str
    rows: list[AnswerSpecRow] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)

    #: Questions dropped because their answer could not be trusted. The
    #: caller must remove these from the Questions sheet as well, or the
    #: bank ships a question the tutor has no key for.
    dropped_question_ids: set = field(default_factory=set)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_error]

    @property
    def is_clean(self) -> bool:
        return not self.errors


#: Characters the model uses interchangeably with their ASCII equivalents.
#:
#: This is not a guess. Counting the answer fields of one six-topic run: the
#: MINUS SIGN U+2212 appears in 56 of them and the ASCII hyphen in 19, the
#: MULTIPLICATION SIGN in 104 and the asterisk in 37, the DIVISION SIGN in 35
#: and the slash in 18. Both forms of every operator are in use, so a
#: canonical answer and an accepted answer can be the same answer and differ
#: by one character nobody can see.
#:
#: That is exactly how Q-T04-034 was lost: canonical 'x - 6' written with
#: U+2212 against accepted answers written with a hyphen, reported as
#: "canonical_answer is not among accepted_answers", which reads as a model
#: mistake and was not one.
#:
#: The dashes are here without having been seen yet. They are the same class
#: as the minus sign and a dash is never a distinct operator in an answer.
EQUIVALENT_CHARACTERS = str.maketrans({
    "−": "-",   # MINUS SIGN
    "–": "-",   # EN DASH
    "—": "-",   # EM DASH
    "×": "*",   # MULTIPLICATION SIGN
    "÷": "/",   # DIVISION SIGN
})


def _normalise(value: object) -> str:
    """Whitespace, case and operator spelling removed, for comparing forms.

    Only ever used to compare one answer against another within the same
    question. It is not what a student's response is marked against, so
    treating 3/4 and 3 divided by 4 as one form is what we want here: they
    cannot be one accepted and the other wrong.
    """
    return "".join(str(value).split()).lower().translate(EQUIVALENT_CHARACTERS)


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

        # Strip the label punctuation now, before anything reads it. Doing it
        # at the choice check further down would be too late: the
        # canonical-in-accepted test runs first, and "c)" against an accepted
        # list of ["c"] would fail there with a misleading message.
        if question.question_type.value in LETTER_ANSWER_QUESTIONS:
            canonical = normalise_choice(canonical)

        accepted = answer.get("accepted_answers")
        wrong = answer.get("common_wrong_answers")

        # The same punctuation appears in the accepted and wrong lists, since
        # the model is copying one form throughout. Normalising only the
        # canonical would leave "a" being compared against ["a)"], which fails
        # the canonical-in-accepted test for a reason that has nothing to do
        # with the answer.
        if question.question_type.value in LETTER_ANSWER_QUESTIONS:
            if isinstance(accepted, list):
                accepted = [normalise_choice(a) for a in accepted]
            if isinstance(wrong, list):
                wrong = [normalise_choice(w) for w in wrong]

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
        question_type = question.question_type.value
        if question_type in LETTER_ANSWER_QUESTIONS:
            letters = question_options(question.question_text)
            if not re.fullmatch(r"[A-Ha-h]", canonical.strip()):
                hint = ""
                if question_type == "CHOICE_WITH_EXPLANATION":
                    # The likeliest mistake for this type, and the one the
                    # six-topic run actually produced.
                    hint = ("; the explanation belongs in "
                            "explanation_required, not in canonical_answer")
                error(where,
                      f"canonical_answer {canonical!r} is not an option letter; "
                      f"a choice answer is the letter alone{hint}")
            elif letters and canonical.strip().upper() not in letters:
                error(where,
                      f"canonical_answer {canonical.strip().upper()!r} is not "
                      f"among the options the question offers ({sorted(letters)})")

        elif question_type in TRUE_FALSE_QUESTIONS:
            if canonical.strip().lower() not in TRUE_FALSE_ANSWERS:
                error(where,
                      f"canonical_answer {canonical!r} is not True or False; a "
                      f"true/false answer is the word alone, with the reasoning "
                      f"in explanation_required")

        # -- multi-part: one string, one part per thing asked --------------
        elif answer_type == "MULTI_PART":
            parts = [p for p in canonical.split(MULTI_PART_SEPARATOR.strip())
                     if p.strip()]
            if len(parts) < 2:
                error(where,
                      f"canonical_answer {canonical!r} has one part; a "
                      f"multi-part answer joins each part with "
                      f"{MULTI_PART_SEPARATOR!r} in one string")

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

    # One error PER missing question, keyed on its id. As a single
    # batch-level complaint this was unrecoverable: the drop path only blames
    # errors that name a question, so a partial response lost the whole topic.
    # It cost Topic 1 all 56 of its questions on a six-topic run.
    for question_id in sorted(set(questions) - seen):
        error(question_id, "the model returned no answer key for this question")

    return issues


def _numbered(steps: list[str]) -> str:
    """Newline-separated numbered steps, as the workbook stores them."""
    return "\n".join(f"{n}. {s.strip()}" for n, s in enumerate(steps, start=1))


#: Punctuation a model carries over from the question's own option labels.
CHOICE_PUNCTUATION = ").:"


def normalise_choice(canonical: str) -> str:
    """Strip the label punctuation off a choice answer: "c)" becomes "c".

    Four answers in one six-topic run came back as "a)", "b)" and "c)", and
    the whole topic's key was refused because they were not bare letters. The
    questions themselves end "Choose a), b) or c).", so the model was copying
    the form the question put in front of it. The letter was never in doubt.

    Rejecting that is pedantry with a real cost, so the bracket is removed
    here rather than argued about. This runs before validation and before the
    row is built, so the workbook stores "c" and the check sees "c".
    """
    return str(canonical or "").strip().rstrip(CHOICE_PUNCTUATION).strip()


# A keep-floor used to live here: below 70% surviving, the whole topic was
# refused. That made sense when a TOPIC was the unit and a partial one was a
# stump nobody could use.
#
# It is gone because the unit changed. Coverage is now planned and reported
# per micro-skill, so a topic that keeps 32 of 56 answers is not a mystery --
# the run names exactly which skills are short and by which slots, and exits
# non-zero. Refusing 32 sound answers to avoid shipping something the report
# already describes precisely would lose work for nothing.
#
# The one genuinely fatal case is the same as everywhere else in this
# pipeline: nothing usable at all.


def generate_answers(
    questions: list[QuestionRow],
    client: LLMClient,
    topic_code: str,
    *,
    misconceptions: Optional[list[str]] = None,
    strict: bool = True,
    drop_invalid: bool = False,
    retry: bool = True,
    id_service: Optional[IdService] = None,
) -> AnswerSet:
    """Generate the answer key for one topic's questions.

    With drop_invalid, a question whose answer cannot be trusted is dropped
    ALONGSIDE its answer, and `dropped_question_ids` names it so the caller
    can remove it from the Questions sheet too.

    That pairing is the point. Every other generator drops a bad row and moves
    on, but an answer is not free-standing: dropping only the answer would
    leave a question in the bank that looks complete and has no key, which the
    tutor cannot use and nobody would notice. Dropping only the question is
    equally wrong. They go together or not at all.
    """
    by_id = {q.question_id: q for q in questions}
    name = f"{topic_code} answers"

    payload = client.complete_json(
        SYSTEM_PROMPT,
        build_user_prompt(questions, misconceptions),
        purpose=f"CG-013 answer key for {topic_code}",
    )

    answers = payload.get("answers")
    issues = _check(name, answers, by_id)
    dropped: set[str] = set()

    # A partial response is common at this size: the answer key is asked for
    # every question in a topic at once, which is 56 to 70 of them. Rather
    # than losing what came back, the questions it skipped are asked for
    # again, once. Same reasoning as the question generator's retry: a gap is
    # worth one more call, and only one, because a second attempt is the same
    # roll of the same dice.
    answered = {
        a.get("question_id") for a in (answers or [])
        if isinstance(a, dict)
    }
    outstanding = [q for q in questions if q.question_id not in answered]
    if outstanding and retry and isinstance(answers, list):
        # Held aside, not appended: _check runs again below and its result
        # REPLACES issues, which would silently discard the explanation of
        # why a retry happened at all.
        notes = [ValidationIssue(
            Severity.WARNING, name, "answers",
            f"the model answered {len(answered)} of {len(questions)} "
            f"questions; asking again for the {len(outstanding)} it skipped",
        )]
        second = client.complete_json(
            SYSTEM_PROMPT,
            build_user_prompt(outstanding, misconceptions),
            purpose=f"CG-013 answer key retry for {topic_code}",
        )
        recovered = [
            a for a in (second.get("answers") or [])
            if isinstance(a, dict) and a.get("question_id") not in answered
        ]
        if recovered:
            answers = list(answers) + recovered
            notes.append(ValidationIssue(
                Severity.WARNING, name, "answers",
                f"the retry supplied {len(recovered)} more answer(s)",
            ))
            issues = _check(name, answers, by_id)
        issues = notes + issues

    errors = [i for i in issues if i.is_error]
    if errors and drop_invalid and isinstance(answers, list):
        # Only answers whose problem is their own can be dropped. A
        # batch-level complaint -- "no answer key for 4 questions" -- names no
        # single row, so removing rows cannot resolve it.
        blamed = {i.field for i in errors if i.field in by_id}
        kept_answers = [
            a for a in answers
            if not (isinstance(a, dict) and a.get("question_id") in blamed)
        ]
        if blamed and kept_answers:
            kept_questions = [q for q in questions if q.question_id not in blamed]
            recheck = _check(name, kept_answers,
                             {q.question_id: q for q in kept_questions})
            if not [i for i in recheck if i.is_error]:
                answers = kept_answers
                dropped = blamed
                issues = [
                    ValidationIssue(Severity.WARNING, i.source_file_name, i.field,
                                    f"dropped: {i.message}")
                    for i in errors
                ] + [i for i in recheck if not i.is_error] + [
                    ValidationIssue(
                        Severity.WARNING, name, "answers",
                        f"dropped {len(dropped)} question(s) whose answer could "
                        f"not be trusted: {', '.join(sorted(dropped))}; "
                        f"kept {len(kept_questions)}",
                    )
                ]
                errors = []

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
        # Whatever the check compared, the sheet stores. Otherwise the
        # workbook holds "a)" while validation approved "a".
        clean = (
            normalise_choice
            if question.question_type.value in LETTER_ANSWER_QUESTIONS
            else (lambda v: str(v).strip())
        )
        rows.append(
            AnswerSpecRow(
                # Derived from the question, not counted, so the two cannot
                # drift apart. Reuses the question's own suffix.
                answer_spec_id=question.answer_spec_id,
                question_id=question.question_id,
                answer_type=AnswerType(answer["answer_type"]),
                canonical_answer=clean(answer["canonical_answer"]),
                accepted_answers=LIST_SEPARATOR.join(
                    clean(a) for a in answer["accepted_answers"]
                ),
                common_wrong_answers=LIST_SEPARATOR.join(
                    clean(w) for w in answer["common_wrong_answers"]
                ),
                verification_method=VerificationMethod(
                    answer["verification_method"]
                ),
                required_units=(answer.get("required_units") or None),
                explanation_required=bool(answer["explanation_required"]),
                answer_steps=_numbered(answer["answer_steps"]),
            )
        )

    return AnswerSet(topic_code, rows, issues, payload, dropped)
