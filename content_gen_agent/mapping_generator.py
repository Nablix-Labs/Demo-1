"""CG-016: the three tables that join questions, errors and misconceptions.

    Question_Error_Map          a wrong answer -> the error it shows
    Misconception_Errors        a belief -> the errors it causes
    Misconception_MicroSkills   a belief -> the skills it damages

Two of the three are DERIVED rather than generated, which is the main design
decision here and worth stating plainly.

Misconception_Errors is derived from prose
-------------------------------------------

CG-015 writes a diagnosis_rule that names its error codes in text:

    "Trigger after ERR-T01-ADD-AS-MULTIPLY when the intended rule uses
     addition but the response uses multiplication."

That prose is the only thing joining the two tables, and CG-015 already
refuses a rule naming an error that does not exist. Checking the template: all
19 pairs named in a rule appear in misconception_errors, and none is missing.

So this table is built by reading the codes back out of the rule. Asking a
model to restate a relationship it has already written invites the two to
disagree, and a disagreement here means a misconception that fires on an error
nothing produces. Derivation makes them consistent by construction.

Misconception_MicroSkills is derived where it can be
-----------------------------------------------------

DIRECT_FAILURE is 21 of the template's 28 rows, and it is not a judgement: a
misconception causes errors, each error already records the skill it shows a
gap in, so the skills a misconception directly breaks are exactly the skills
of its errors.

UNDERLYING_GAP and AFFECTED_SKILL are judgements -- what a belief rests on and
what it spills into -- and those are asked for.

Question_Error_Map needs a model, but not a creative one
---------------------------------------------------------

The wrong answers already exist. CG-013 wrote common_wrong_answers for every
question, drawn from the topic's misconceptions and checked not to overlap the
accepted answers. Asking a model to invent wrong answers again would produce a
second, different set and no way to say which is right.

So it is given the wrong answers and asked only which error each one shows.
micro_skill_id is not asked for at all: under the reviewed design a question
maps to exactly one skill, so the answer is already known.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from diagnosis_generator import referenced_error_codes
from llm_client import LLMClient
from models import (
    ErrorTypeRow,
    MisconceptionErrorRow,
    MisconceptionMicroSkillRow,
    MisconceptionRow,
    QuestionErrorMapRow,
    RelationshipType,
)
from validation import Severity, ValidationIssue

#: The template puts 1.0 on 19 of 21 rows. The two exceptions are alternatives
#: within one rule ("trigger after A or B"), where the pair is offered as
#: equally plausible rather than ranked. Nothing in the data supports inventing
#: finer gradations, so every derived pair is full confidence.
DEFAULT_CONFIDENCE = 1.0


class MappingError(Exception):
    """The mapping tables could not be built."""


# ──────────────────────────────────────────────────────────────────────
# Derived: misconception -> error
# ──────────────────────────────────────────────────────────────────────

def build_misconception_errors(
    misconceptions: list[MisconceptionRow],
    error_types: list[ErrorTypeRow],
    name: str = "misconception errors",
) -> tuple[list[MisconceptionErrorRow], list[ValidationIssue]]:
    """One row per error a diagnosis_rule names.

    No model call. The relationship was decided when the rule was written; this
    reads it back out so the prose and the foreign key cannot disagree.
    """
    issues: list[ValidationIssue] = []
    known = {row.error_code for row in error_types}
    rows: list[MisconceptionErrorRow] = []
    seen: set[tuple[str, str]] = set()

    for misconception in misconceptions:
        codes = referenced_error_codes(misconception.diagnosis_rule)
        usable = [c for c in codes if c in known]

        if not usable:
            # CG-015 refuses this, so reaching it means the two ran against
            # different error sets.
            issues.append(ValidationIssue(
                Severity.ERROR, name, misconception.misconception_id,
                f"diagnosis_rule names no error that exists in this topic "
                f"({codes or 'no code at all'}), so nothing can trigger it",
            ))
            continue

        for code in usable:
            pair = (misconception.misconception_id, code)
            if pair in seen:
                continue
            seen.add(pair)
            rows.append(MisconceptionErrorRow(
                misconception_id=misconception.misconception_id,
                error_code=code,
                confidence_weight=DEFAULT_CONFIDENCE,
            ))

    orphans = known - {r.error_code for r in rows}
    if orphans:
        issues.append(ValidationIssue(
            Severity.WARNING, name, "error_code",
            f"{len(orphans)} error(s) resolve to no misconception "
            f"({', '.join(sorted(orphans))}); the review asks that every error "
            f"resolve to one, so the tutor has something to re-teach",
        ))

    return rows, issues


# ──────────────────────────────────────────────────────────────────────
# Derived: misconception -> the skills its errors already point at
# ──────────────────────────────────────────────────────────────────────

def direct_failures(
    misconception_errors: list[MisconceptionErrorRow],
    error_types: list[ErrorTypeRow],
) -> list[MisconceptionMicroSkillRow]:
    """The skills a misconception directly breaks.

    Not a judgement. A misconception causes errors; every error records the
    skill it shows a gap in; so these are exactly the skills of its errors.
    Asking a model would be asking it to rediscover a join.
    """
    skill_of = {row.error_code: row.related_micro_skill_id for row in error_types}
    seen: set[tuple[str, str]] = set()
    rows: list[MisconceptionMicroSkillRow] = []

    for link in misconception_errors:
        skill = skill_of.get(link.error_code)
        if skill is None:
            continue
        pair = (link.misconception_id, skill)
        if pair in seen:
            continue
        seen.add(pair)
        rows.append(MisconceptionMicroSkillRow(
            misconception_id=link.misconception_id,
            micro_skill_id=skill,
            relationship_type=RelationshipType.DIRECT_FAILURE,
        ))
    return rows


# ──────────────────────────────────────────────────────────────────────
# Generated: which error each wrong answer shows
# ──────────────────────────────────────────────────────────────────────

ERROR_MAP_SYSTEM_PROMPT = """\
You label wrong answers with the error each one shows. Return a single JSON
object and nothing else. No prose, no markdown.

{
  "mappings": [
    {"question_id": "Q-T01-004", "response_pattern": "5n",
     "error_code": "ERR-T01-ADD-AS-MULTIPLY"}
  ]
}

You are NOT inventing wrong answers. Every wrong answer below was written with
its question and is already known to be wrong. Your only job is to say which
error each one demonstrates.

Rules:

1. Use only the error codes listed for this topic, copied EXACTLY. Never invent
   one. If a wrong answer does not match any error in the list, leave it out
   rather than forcing it into the nearest code.

2. Copy response_pattern exactly as it is given. It is what the student
   actually types, so an approximation will never match.

   MANY WRONG ANSWERS ARE OPTION LETTERS. A letter is not a mistake. What
   shows the error is what that option SAYS, which is given to you in
   brackets after the letter. Diagnose the option's content and return the
   LETTER as response_pattern, because the letter is what the student types.

     wrong: B   (option B says: 3 divided by y)
       -> {"response_pattern": "B", "error_code": "ERR-T01-DIV-FOR-MULT"}

   A question where every wrong answer is a letter still needs mapping. Do
   not skip it because the letters look meaningless; look at what they say.

3. EVERY QUESTION NEEDS AT LEAST ONE MAPPING. A question whose wrong answers
   are all unmapped is a question where a student makes a mistake and the
   tutor has nothing to say. Returning an empty list, or leaving whole
   questions out, is the one outcome that is never right: if you genuinely
   cannot match one wrong answer, match the others.

4. Different wrong answers usually show DIFFERENT errors. Two options in the
   same question landing on the same code is possible, but if every wrong
   answer in a question gets the same code you have probably not looked at
   what distinguishes them. Do not force unrelated mistakes into one generic
   error to simplify the work.

5. A wrong answer shows the error a student who made THAT mistake would have.
   "5n" where the rule adds 5 shows multiplication read for addition. The same
   student writing "n5" shows a missing operator. They are not the same error
   even though both are wrong.
"""


#: A wrong answer that is nothing but an option letter.
BARE_LETTER_RE = re.compile(r"^[A-Ha-h]$")

#: "b) 3 divided by y" -> ("b", "3 divided by y"), up to the next option.
OPTION_TEXT_RE = re.compile(
    r"(?:^|[\s(])([A-Ha-h])[).:]\s*(.+?)(?=(?:[\s(][A-Ha-h][).:])|$)",
    re.DOTALL,
)


def option_texts(question_text: str) -> dict[str, str]:
    """What each lettered option actually says, keyed by upper-case letter.

    The reason this exists: for a choice question the wrong answers are stored
    as option letters, and a letter is not a mistake. "B" demonstrates nothing
    on its own -- what demonstrates an error is whatever option B says.

    Asking a model to diagnose a bare letter makes it hunt through the
    question text for the option, and on the run of 7 September T01 gave up
    and returned nothing at all: 69 per cent of its wrong answers were bare
    letters, the highest of the six topics, and it produced zero mappings.
    Resolving the letter here means the model is shown the thing it is
    actually being asked about.
    """
    found: dict[str, str] = {}
    for match in OPTION_TEXT_RE.finditer(" ".join(str(question_text or "").split())):
        letter = match.group(1).upper()
        text = match.group(2).strip()
        if text and letter not in found:
            found[letter] = text
    return found


def build_error_map_prompt(
    answers,
    questions,
    error_types: list[ErrorTypeRow],
) -> str:
    """Every wrong answer that needs labelling, and the codes available.

    A wrong answer that is a bare option letter is shown with what that
    option says, so the model diagnoses the mistake rather than the label.
    """
    by_id = {q.question_id: q for q in questions}
    lines = ["Error codes for this topic. Use only these, copied exactly:"]
    lines += [
        f"  {row.error_code}  {row.error_name}: {row.description}"
        for row in error_types
    ]
    lines += ["", "Wrong answers to label:"]

    for answer in answers:
        question = by_id.get(answer.question_id)
        if question is None:
            continue
        wrong = [w.strip() for w in str(answer.common_wrong_answers or "").split("|")
                 if w.strip()]
        if not wrong:
            continue
        options = option_texts(question.question_text)
        lines += [
            "",
            f"  {answer.question_id}  [{question.question_type.value}]",
            f"    {' '.join(str(question.question_text).split())[:300]}",
            f"    correct answer: {answer.canonical_answer}",
        ]
        for w in wrong:
            said = options.get(w.upper()) if BARE_LETTER_RE.match(w) else None
            lines.append(f"    wrong: {w}"
                         + (f"   (option {w.upper()} says: {said})" if said else ""))

    return "\n".join(lines)


@dataclass
class MappingSet:
    """The three joining tables for one topic."""

    topic_code: str
    question_errors: list[QuestionErrorMapRow] = field(default_factory=list)
    misconception_errors: list[MisconceptionErrorRow] = field(default_factory=list)
    misconception_skills: list[MisconceptionMicroSkillRow] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_error]

    @property
    def is_clean(self) -> bool:
        return not self.errors


def _check_error_map(
    name: str,
    entries: list,
    answers,
    known_codes: set[str],
) -> tuple[list[ValidationIssue], set[int]]:
    """Everything wrong with the labelling, and which rows are individually bad."""
    issues: list[ValidationIssue] = []
    bad: set[int] = set()

    def error(field_name: str, message: str, position: Optional[int] = None) -> None:
        issues.append(ValidationIssue(Severity.ERROR, name, field_name, message))
        if position is not None:
            bad.add(position)

    def warn(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.WARNING, name, field_name, message))

    if not isinstance(entries, list):
        error("mappings", "model returned no mappings")
        return issues, bad

    # What each question's wrong answers actually are. A pattern that is not
    # one of them can never match a student's response, so it is dead weight
    # in the table and a sign the model paraphrased instead of copying.
    wrong_by_question = {
        a.question_id: {
            w.strip() for w in str(a.common_wrong_answers or "").split("|") if w.strip()
        }
        for a in answers
    }

    seen: set[tuple[str, str]] = set()
    for position, entry in enumerate(entries, start=1):
        where = f"mappings[{position}]"
        if not isinstance(entry, dict):
            error(where, "not an object", position)
            continue

        question_id = str(entry.get("question_id") or "")
        pattern = str(entry.get("response_pattern") or "").strip()
        code = str(entry.get("error_code") or "").strip()

        if question_id not in wrong_by_question:
            error(where, f"question_id {question_id!r} is not one of this "
                         f"topic's answered questions", position)
            continue
        if not pattern:
            error(where, "response_pattern is missing or empty", position)
            continue
        if pattern not in wrong_by_question[question_id]:
            error(where,
                  f"response_pattern {pattern!r} is not one of "
                  f"{question_id}'s wrong answers, so no student response will "
                  f"ever match it", position)
            continue
        if code not in known_codes:
            error(where,
                  f"error_code {code!r} does not exist in this topic", position)
            continue

        pair = (question_id, pattern)
        if pair in seen:
            error(where, f"{question_id} maps {pattern!r} twice", position)
            continue
        seen.add(pair)

    # -- coverage, which the review asks for explicitly ----------------
    #
    # Both cases are reported. The earlier version warned only when EVERY
    # wrong answer went unmapped, so on 7 September the 134 questions with no
    # diagnosis produced a warning each and the 97 with partial cover produced
    # nothing at all. A question where two of five mistakes are diagnosed is
    # three mistakes the tutor cannot respond to.
    mapped = set(seen)
    for question_id, wrong in sorted(wrong_by_question.items()):
        unmapped = {w for w in wrong if (question_id, w) not in mapped}
        if not unmapped:
            continue
        if len(unmapped) == len(wrong):
            warn(question_id,
                 f"none of its {len(wrong)} wrong answer(s) is mapped to an "
                 f"error, so a student who makes one gets no diagnosis")
        else:
            warn(question_id,
                 f"{len(unmapped)} of its {len(wrong)} wrong answer(s) are "
                 f"unmapped, so those mistakes get no diagnosis")

    return issues, bad


def unmapped_by_question(rows, answers) -> dict[str, set[str]]:
    """Which wrong answers still have no error, per question.

    Used to decide whether a retry is worth making and what to put in it.
    """
    mapped: dict[str, set[str]] = {}
    for row in rows:
        mapped.setdefault(row.question_id, set()).add(row.response_pattern.strip())

    missing: dict[str, set[str]] = {}
    for answer in answers:
        wrong = {w.strip() for w in
                 str(answer.common_wrong_answers or "").split("|") if w.strip()}
        gap = wrong - mapped.get(answer.question_id, set())
        if gap:
            missing[answer.question_id] = gap
    return missing


def _map_once(
    answers,
    questions,
    error_types,
    client,
    topic_code,
    name,
    known,
    skill_of_question,
    purpose,
) -> tuple[list[QuestionErrorMapRow], list[ValidationIssue], dict]:
    """One call, checked and turned into rows."""
    payload = client.complete_json(
        ERROR_MAP_SYSTEM_PROMPT,
        build_error_map_prompt(answers, questions, error_types),
        purpose=purpose,
    )
    entries = payload.get("mappings")
    issues, bad = _check_error_map(name, entries, answers, known)

    # A bad label is dropped, not fatal. The table is additive: a wrong answer
    # with no error attached means one less diagnosis, while refusing the whole
    # topic means none at all.
    usable = [
        e for position, e in enumerate(entries or [], start=1)
        if position not in bad and isinstance(e, dict)
    ]
    issues = [
        i if not i.is_error else ValidationIssue(
            Severity.WARNING, i.source_file_name, i.field, f"dropped: {i.message}")
        for i in issues
    ]

    rows = [
        QuestionErrorMapRow(
            question_id=e["question_id"],
            response_pattern=str(e["response_pattern"]).strip(),
            error_code=str(e["error_code"]).strip(),
            # Never asked for: a question has exactly one skill, so this is
            # already known and asking would only create a way to get it wrong.
            micro_skill_id=skill_of_question.get(e["question_id"]),
        )
        for e in usable
    ]
    return rows, issues, payload


def generate_question_error_map(
    answers,
    questions,
    error_types: list[ErrorTypeRow],
    client: LLMClient,
    topic_code: str,
    *,
    skill_of_question: Optional[dict[str, str]] = None,
    strict: bool = True,
    retry: bool = True,
) -> tuple[list[QuestionErrorMapRow], list[ValidationIssue], dict]:
    """Label each question's wrong answers with the error it shows.

    A question left with no diagnosis at all is asked about again. On the run
    of 7 September the first call for T01 returned an empty list and that was
    the end of it: 69 questions, zero mappings, and the pipeline moved on. A
    second pass costs one request and is the difference between a topic whose
    mistakes can be diagnosed and one whose cannot.

    Only the questions that came back with nothing go into the retry. Asking
    again about work already done wastes tokens and invites the model to
    contradict its first answer.
    """
    name = f"{topic_code} error map"
    known = {row.error_code for row in error_types}
    skill_of_question = skill_of_question or {}

    if not known:
        raise MappingError(
            f"{topic_code}: cannot map wrong answers with no error types to "
            f"map them to"
        )

    rows, issues, payload = _map_once(
        answers, questions, error_types, client, topic_code, name, known,
        skill_of_question, f"CG-016 error map for {topic_code}",
    )

    if retry:
        missing = unmapped_by_question(rows, answers)
        # Only the questions with NOTHING. A partially mapped question has a
        # diagnosis for at least one mistake, which is worth a warning but not
        # worth a second request.
        blank = {
            question_id for question_id, gap in missing.items()
            if len(gap) == len({
                w.strip() for a in answers if a.question_id == question_id
                for w in str(a.common_wrong_answers or "").split("|") if w.strip()
            })
        }
        if blank:
            issues.append(ValidationIssue(
                Severity.WARNING, name, "mappings",
                f"{len(blank)} question(s) came back with no diagnosis at "
                f"all; asking again for those only",
            ))
            again_answers = [a for a in answers if a.question_id in blank]
            again_questions = [q for q in questions if q.question_id in blank]
            try:
                more, more_issues, _ = _map_once(
                    again_answers, again_questions, error_types, client,
                    topic_code, name, known, skill_of_question,
                    f"CG-016 error map retry for {topic_code}",
                )
            except Exception as exc:                      # noqa: BLE001
                # A failed retry leaves the first pass intact. It was never
                # going to make things worse than the gap it was fixing.
                issues.append(ValidationIssue(
                    Severity.WARNING, name, "mappings",
                    f"the retry failed ({exc}); keeping the first pass",
                ))
            else:
                rows.extend(more)
                # The first pass's coverage warnings are now stale for
                # anything the retry filled in, so they are replaced wholesale
                # rather than added to.
                issues = [i for i in issues if i.field not in blank]
                issues.extend(i for i in more_issues if i.field in blank
                              or i.field == "mappings")

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise MappingError(
            f"{topic_code}: the error map cannot be used.\n"
            + "\n".join(f"  {i}" for i in errors)
        )

    return rows, issues, payload


# ──────────────────────────────────────────────────────────────────────
# Generated: the skills a misconception reaches beyond its own errors
# ──────────────────────────────────────────────────────────────────────

RELATED_SKILL_SYSTEM_PROMPT = """\
You say which OTHER micro-skills a misconception touches. Return a single JSON
object and nothing else. No prose, no markdown.

{
  "links": [
    {"misconception_id": "MIS-T01-ADD-AS-MULTIPLY",
     "micro_skill_id": "T01.M2",
     "relationship_type": "UNDERLYING_GAP"}
  ]
}

The skills a misconception DIRECTLY breaks are already known and are listed
with each misconception below. Do not repeat them. You are adding the two
relationships that cannot be worked out from the errors:

  UNDERLYING_GAP   the skill the student never really had, which is WHY they
                   hold this belief. Usually something the broken skill
                   depends on. A student who thinks a letter is one fixed
                   number often never grasped that a letter stands for a
                   quantity at all.

  AFFECTED_SKILL   a skill this belief will also spoil, even though the
                   student may look fine on it today. It is what gets worse
                   if the misconception is left alone.

Rules:

1. Use only the micro-skill ids listed below, copied EXACTLY. Never invent one.

2. Do not repeat a skill already listed as a direct failure for that
   misconception. It is recorded; saying it again in a weaker relationship
   would contradict it.

3. Add a link only where the relationship is real. Most misconceptions have
   one or two of these, some have none. A misconception linked to every skill
   in the topic says nothing useful, and the tutor would re-teach everything.

4. An UNDERLYING_GAP is a cause and an AFFECTED_SKILL is a consequence. If you
   cannot say which of the two it is, it is probably neither.
"""


def build_related_skills_prompt(
    misconceptions: list[MisconceptionRow],
    micro_skills,
    direct: list[MisconceptionMicroSkillRow],
) -> str:
    """Each misconception, what it already breaks, and the skills available."""
    broken: dict[str, list[str]] = {}
    for row in direct:
        broken.setdefault(row.misconception_id, []).append(row.micro_skill_id)

    lines = ["Micro-skills in this topic. Use only these ids:"]
    lines += [
        f"  {row.micro_skill_id}  {row.skill_name}: {row.description}"
        for row in micro_skills
    ]
    lines += ["", "Misconceptions:"]
    for row in misconceptions:
        lines += [
            "",
            f"  {row.misconception_id}  {row.name}",
            f"    {row.description}",
            f"    already recorded as directly breaking: "
            f"{', '.join(broken.get(row.misconception_id, [])) or 'nothing'}",
        ]
    return "\n".join(lines)


def generate_related_skills(
    misconceptions: list[MisconceptionRow],
    micro_skills,
    direct: list[MisconceptionMicroSkillRow],
    client: LLMClient,
    topic_code: str,
    *,
    strict: bool = True,
) -> tuple[list[MisconceptionMicroSkillRow], list[ValidationIssue], dict]:
    """The UNDERLYING_GAP and AFFECTED_SKILL links, which are judgements."""
    name = f"{topic_code} misconception skills"
    issues: list[ValidationIssue] = []
    known_skills = {row.micro_skill_id for row in micro_skills}
    known_misconceptions = {row.misconception_id for row in misconceptions}
    already = {(r.misconception_id, r.micro_skill_id) for r in direct}

    payload = client.complete_json(
        RELATED_SKILL_SYSTEM_PROMPT,
        build_related_skills_prompt(misconceptions, micro_skills, direct),
        purpose=f"CG-016 misconception skills for {topic_code}",
    )
    entries = payload.get("links")

    def drop(position: int, message: str) -> None:
        issues.append(ValidationIssue(
            Severity.WARNING, name, f"links[{position}]", f"dropped: {message}"))

    rows: list[MisconceptionMicroSkillRow] = []
    seen: set[tuple[str, str]] = set()
    allowed = {RelationshipType.UNDERLYING_GAP.value,
               RelationshipType.AFFECTED_SKILL.value}

    if not isinstance(entries, list):
        issues.append(ValidationIssue(
            Severity.WARNING, name, "links",
            "model returned no links; every misconception keeps only its "
            "direct failures, which is usable but thinner"))
        entries = []

    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            drop(position, "not an object")
            continue

        misconception_id = str(entry.get("misconception_id") or "")
        skill_id = str(entry.get("micro_skill_id") or "")
        relationship = str(entry.get("relationship_type") or "")

        if misconception_id not in known_misconceptions:
            drop(position, f"misconception_id {misconception_id!r} does not exist")
            continue
        if skill_id not in known_skills:
            drop(position, f"micro_skill_id {skill_id!r} is not in this topic")
            continue
        if relationship not in allowed:
            drop(position,
                 f"relationship_type {relationship!r} is not one of "
                 f"{sorted(allowed)}; DIRECT_FAILURE is derived, not asked for")
            continue
        if (misconception_id, skill_id) in already:
            drop(position,
                 f"{skill_id} is already a direct failure of {misconception_id}; "
                 f"a weaker relationship on top would contradict it")
            continue
        if (misconception_id, skill_id) in seen:
            drop(position, f"{misconception_id} links {skill_id} twice")
            continue

        seen.add((misconception_id, skill_id))
        rows.append(MisconceptionMicroSkillRow(
            misconception_id=misconception_id,
            micro_skill_id=skill_id,
            relationship_type=RelationshipType(relationship),
        ))

    # A misconception touching most of the topic tells the tutor to re-teach
    # everything, which is the same as telling it nothing.
    per_misconception: dict[str, int] = {}
    for row in rows:
        per_misconception[row.misconception_id] = \
            per_misconception.get(row.misconception_id, 0) + 1
    for misconception_id, count in per_misconception.items():
        if known_skills and count > len(known_skills) / 2:
            issues.append(ValidationIssue(
                Severity.WARNING, name, misconception_id,
                f"linked to {count} of {len(known_skills)} skills beyond its "
                f"direct failures; a belief that touches most of a topic does "
                f"not narrow anything down",
            ))

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise MappingError(
            f"{topic_code}: misconception skill links cannot be used.\n"
            + "\n".join(f"  {i}" for i in errors)
        )
    return rows, issues, payload
