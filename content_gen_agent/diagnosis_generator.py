"""CG-015: the errors a student makes, and the misconceptions behind them.

Two tables, generated in this order because the second refers to the first.

    Error_Types      what a wrong answer LOOKS like, and how to spot it
    Misconceptions   what the student BELIEVES that produced it

The distinction matters and is easy to collapse. An error is observable: the
student wrote "5n" when the rule was "n + 5". A misconception is the belief
underneath: they read a fixed change as multiplication. One misconception
produces several errors, which is why the tables are separate and why the
tutor needs both. It teaches against the belief, not the typo.

What the reference shows
------------------------

17 errors and 16 misconceptions across three topics, so roughly 5 or 6 of
each per topic, against 16 to 21 questions.

Error codes and misconception ids are both per-topic. Topic 1's five codes
have no topic segment (ERR-ADD-AS-MULTIPLY) because it was authored before
the convention settled; every Topic 2 and Topic 3 code carries it. CG-001
established that new topics get the prefix, and id_service already mints
that form, so nothing here needs to know about the legacy shape.

The link between the two tables is prose, not a foreign key. Every one of the
16 misconceptions names at least one error code inside diagnosis_rule:

    "Trigger after ERR-ADD-AS-MULTIPLY when the intended rule uses addition
     or subtraction but the response uses multiplication."

There is no column joining them here. Misconception_Errors (CG-016) adds the
real mapping later, but the rule text stands on its own and the platform reads
it, so a rule naming an error that was never defined is a live defect rather
than an untidy string. _check_misconceptions extracts every ERR- code from the
text and refuses any that does not exist.

Naming is not derived
---------------------

Only 2 of the 16 misconception slugs match an error slug, so this does not try
to name a misconception after the error it follows. MIS-T01-OPERATOR-MISSING
follows ERR-OPERATOR-OMITTED, and forcing them to agree would be inventing a
convention the reference does not have.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from id_service import IdError, IdService, slugify
from llm_client import LLMClient
from models import (
    AssessmentPriority,
    DetectionMethod,
    ErrorTypeRow,
    MicroSkillRow,
    MisconceptionRow,
    Severity,
)
from validation import Severity as IssueSeverity
from validation import ValidationIssue

DEFAULT_VERSION = "1.0"

# The reference holds 5 to 7 of each per topic. The bounds are wider than that
# so a topic with less to go wrong is not forced to invent filler, but a
# response of two errors means the model did not do the work.
MIN_ERRORS, MAX_ERRORS = 4, 10
MIN_MISCONCEPTIONS, MAX_MISCONCEPTIONS = 3, 9

#: Every misconception in the reference names at least one of these in its
#: diagnosis_rule. Used to pull them back out and check they exist.
ERROR_CODE_RE = re.compile(r"ERR-[A-Z0-9-]+")


class DiagnosisError(Exception):
    """The model's errors or misconceptions could not be used."""


def trim_to_cap(
    entries: list,
    cap: int,
    name: str,
    field_name: str,
) -> tuple[list, list[ValidationIssue]]:
    """Keep the first `cap` entries and say what was set aside.

    A six-topic run lost Topic 3's error types AND its misconceptions, which
    depend on them, because the model returned 11 errors against a ceiling of
    10. Nothing was wrong with the eleventh. The ceiling is a guess: the
    reference holds 5 to 7 per topic and 10 was chosen to be generous.

    Refusing a whole topic's diagnosis chain over one surplus row is not a
    trade worth making, and dropping a row cannot fix a count, so the recovery
    paths elsewhere could not help. Too FEW rows is still an error, because
    that means the model did not do the work; too many just means it did more
    than expected.
    """
    if len(entries) <= cap:
        return entries, []

    surplus = len(entries) - cap
    return entries[:cap], [
        ValidationIssue(
            IssueSeverity.WARNING, name, field_name,
            f"model returned {len(entries)}, more than the expected {cap}; "
            f"kept the first {cap} and set aside {surplus}",
        )
    ]


# ──────────────────────────────────────────────────────────────────────
# Error types
# ──────────────────────────────────────────────────────────────────────

# Each detection_method is described by what a marker would have to LOOK at,
# because that is the only thing that distinguishes them. Left undescribed,
# the model picks the vaguest one, exactly as it over-used TEXT_MEANING in the
# answer key once the options were listed without guidance.
DETECTION_METHOD_GUIDE = """\
     SYMBOLIC_PATTERN             the symbols alone give it away, with no
                                  need to read the question. "3 - t" where
                                  "t - 3" was wanted.
     TOKEN_PATTERN                the characters give it away: a letter and
                                  a number pushed together with no operator,
                                  like "n5" or "s6".
     STRUCTURED_EXPRESSION_MATCH  the student's expression has to be compared
                                  with the correct one to see the difference:
                                  multiplication where the rule adds.
     SEMANTIC_AND_SYMBOLIC_MATCH  neither the words nor the symbols are enough
                                  alone. The answer is only wrong given what
                                  the question asked: adding when the context
                                  says the amount decreases.
     STRUCTURED_TEXT_MATCH        the answer is a labelled written answer and
                                  a label sits in the wrong slot: the constant
                                  named as the variable.
     SEMANTIC_CLASSIFICATION      the answer is free writing, judged by what
                                  it means: the student says the letter IS the
                                  books rather than how many books.
     PATTERN_MATCH                the shape of the response is wrong whatever
                                  it says: a single number where a general
                                  rule was asked for.
     CASE_COMPARISON              spotting it needs the given cases compared:
                                  claiming a value changes when it is the same
                                  in every case."""

ERROR_SYSTEM_PROMPT = f"""\
You catalogue the mistakes students make on a maths topic. Return a single
JSON object and nothing else. No prose, no markdown.

{{
  "error_types": [
    {{
      "descriptor": "ADD-AS-MULTIPLY",
      "error_name": "Fixed-change rule written as multiplication",
      "description": "Student writes or interprets adding or subtracting a fixed amount as multiplication by the fixed number.",
      "micro_skill_position": 3,
      "severity": "HIGH",
      "detection_method": "STRUCTURED_EXPRESSION_MATCH"
    }}
  ]
}}

Rules, in order of importance:

1. An error is what a wrong answer LOOKS LIKE, not what the student believes.
   Write what you could see on the page. "Student writes n5 without an
   operation" is an error. "Student does not understand operators" is a
   belief, and belongs in the misconceptions table, not this one.

2. Every error must be one a student on THIS topic would actually make, drawn
   from the misconceptions to prevent that are listed below. An error nobody
   produces catches nobody, and costs the tutor a check on every answer.

3. description says what the student writes or says, concretely, in one
   sentence. Name the actual wrong form where you can: "writes 3 - t instead
   of t - 3" is usable, "makes an ordering mistake" is not.

4. micro_skill_position is the 1-based position, in the list below, of the
   skill this error shows the student has not got. One skill per error.

5. severity is "HIGH" or "MEDIUM". HIGH means the error blocks the topic's
   learning goal and the tutor must stop and address it. MEDIUM means it is
   worth correcting but the student can move on. Use both. The reference runs
   about two HIGH to one MEDIUM.

6. detection_method says how a marker could spot this error, and they are not
   interchangeable. Choose the CHEAPEST one that would actually work, because
   every method below the first two needs the tutor to reason rather than
   pattern-match:

{DETECTION_METHOD_GUIDE}

7. descriptor is a SHORT UPPERCASE HYPHENATED name for the error, three or
   four words at most: ADD-AS-MULTIPLY, OPERATOR-OMITTED, ORDER-REVERSED. It
   becomes the error code, so it must be unique in this list and must describe
   the error rather than the topic.

Give between {MIN_ERRORS} and {MAX_ERRORS} errors, covering different skills
rather than several shades of one mistake.
"""


def build_error_prompt(
    brief,
    micro_skills: list[MicroSkillRow],
) -> str:
    """The topic's skills and the misconceptions its brief asks us to prevent."""
    lines = [
        f"Topic {brief.topic_code}: {brief.topic_title}",
        f"Learning goal: {brief.learning_goal}",
        "",
        "Micro-skills, numbered. Use these positions for micro_skill_position:",
    ]
    lines += [
        f"  {position}. {row.skill_name} -- {row.description}"
        for position, row in enumerate(micro_skills, start=1)
    ]

    if brief.misconceptions_to_prevent:
        lines += [
            "",
            "Misconceptions this topic must prevent. The errors you write "
            "should be what these look like on the page:",
            *(f"  - {item}" for item in brief.misconceptions_to_prevent),
        ]

    if brief.excluded_scope:
        lines += [
            "",
            "Out of scope. Do not write errors about these:",
            *(f"  - {item}" for item in brief.excluded_scope),
        ]

    return "\n".join(lines)


@dataclass
class ErrorTypeSet:
    """The error types generated for one topic."""

    topic_code: str
    rows: list[ErrorTypeRow] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_error]

    @property
    def is_clean(self) -> bool:
        return not self.errors


def _check_errors(
    name: str,
    entries: list,
    micro_skills: list[MicroSkillRow],
) -> tuple[list[ValidationIssue], set[int]]:
    """Everything wrong with the model's error list, and which rows are bad.

    Returns the positions of individually unusable rows alongside the issues,
    so a caller can drop those and keep the rest, the way the question
    generator does. A batch-level problem leaves the set empty because
    dropping a row cannot fix it.
    """
    issues: list[ValidationIssue] = []
    bad: set[int] = set()

    def error(field_name: str, message: str, position: Optional[int] = None) -> None:
        issues.append(ValidationIssue(IssueSeverity.ERROR, name, field_name, message))
        if position is not None:
            bad.add(position)

    def warn(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(IssueSeverity.WARNING, name, field_name, message))

    if not isinstance(entries, list) or not entries:
        error("error_types", "model returned no error types")
        return issues, bad

    if len(entries) < MIN_ERRORS:
        error("error_types",
              f"only {len(entries)} error types; expected at least {MIN_ERRORS}")
    # Deliberately no error for going over. See trim_to_cap: a surplus row is
    # not a defective one, and the ceiling here is a guess rather than a rule.

    severities = {s.value for s in Severity}
    methods = {m.value for m in DetectionMethod}
    descriptors_seen: set[str] = set()

    for position, entry in enumerate(entries, start=1):
        where = f"error_types[{position}]"
        if not isinstance(entry, dict):
            error(where, "not an object", position)
            continue

        for required in ("error_name", "description", "descriptor"):
            value = entry.get(required)
            if not isinstance(value, str) or not value.strip():
                error(where, f"{required} is missing or empty", position)

        descriptor = str(entry.get("descriptor") or "").strip()
        if descriptor:
            # slugify raises rather than returning empty, so a descriptor with
            # no usable characters has to be caught here. Letting it through
            # would surface as an IdFormatError from the minting step below,
            # which reads as an id-service failure rather than what it is: the
            # model returned something unusable.
            try:
                slug = slugify(descriptor)
            except IdError:
                slug = ""
            if not slug:
                error(where,
                      f"descriptor {descriptor!r} has nothing usable in it; it "
                      f"becomes the error code", position)
            elif slug in descriptors_seen:
                error(where, f"duplicate descriptor {descriptor!r}; error codes "
                             f"must be unique", position)
            if slug:
                descriptors_seen.add(slug)

        skill_position = entry.get("micro_skill_position")
        if not isinstance(skill_position, int) or isinstance(skill_position, bool):
            error(where,
                  f"micro_skill_position {skill_position!r} is not a whole "
                  f"number", position)
        elif not 1 <= skill_position <= len(micro_skills):
            error(where,
                  f"micro_skill_position {skill_position} is outside the "
                  f"{len(micro_skills)} skills offered", position)

        severity = entry.get("severity")
        if severity not in severities:
            error(where, f"severity {severity!r} is not HIGH or MEDIUM", position)

        method = entry.get("detection_method")
        if method not in methods:
            error(where,
                  f"detection_method {method!r} is not one of "
                  f"{sorted(methods)}", position)

    # -- shape of the set as a whole ------------------------------------
    usable = [e for e in entries if isinstance(e, dict)]

    seen_severities = {e.get("severity") for e in usable}
    if len(seen_severities) == 1 and seen_severities <= severities:
        warn("severity",
             f"every error is {seen_severities.pop()!r}; the reference uses "
             f"both, and a list where everything is urgent has no priority")

    # Which skills have no recorded way to fail. Error_Types is the entry
    # point to the whole diagnosis chain -- an error leads to a misconception,
    # which leads to a hint (CG-017) and a scaffold (CG-018) -- so a skill with
    # no error attached cannot be diagnosed at all. The tutor can mark an
    # answer wrong and has nothing further to offer, and the gap propagates
    # silently into three later tables.
    #
    # A warning rather than an error. Some skills genuinely have no
    # distinctive failure mode, and losing a topic over one would be wrong.
    hit_positions = {
        e.get("micro_skill_position") for e in usable
        if isinstance(e.get("micro_skill_position"), int)
    }
    uncovered = [
        row for position, row in enumerate(micro_skills, start=1)
        if position not in hit_positions
    ]
    if uncovered and len(usable) >= MIN_ERRORS:
        high = [r for r in uncovered if r.assessment_priority is AssessmentPriority.HIGH]
        # Only HIGH skills are worth the noise. A MEDIUM skill the topic
        # treats as supporting can reasonably have no failure mode of its own.
        if high:
            warn("micro_skill_position",
                 f"{len(high)} HIGH-priority skill(s) have no error type: "
                 f"{', '.join(r.micro_skill_id for r in high)}. A skill with "
                 f"no failure mode cannot be diagnosed, so it gets no hint or "
                 f"scaffold either")

    return issues, bad


def generate_error_types(
    brief,
    client: LLMClient,
    *,
    micro_skills: list[MicroSkillRow],
    strict: bool = True,
    drop_invalid: bool = False,
    id_service: Optional[IdService] = None,
) -> ErrorTypeSet:
    """Generate one topic's Error_Types rows. Codes are minted here."""
    name = brief.source_file_name
    if not micro_skills:
        raise DiagnosisError(
            f"{name}: cannot write error types with no micro-skills to attach "
            f"them to"
        )

    payload = client.complete_json(
        ERROR_SYSTEM_PROMPT,
        build_error_prompt(brief, micro_skills),
        purpose=f"CG-015 error types for {name}",
    )

    entries = payload.get("error_types")
    trimmed: list[ValidationIssue] = []
    if isinstance(entries, list):
        entries, trimmed = trim_to_cap(entries, MAX_ERRORS, name, "error_types")

    issues, bad = _check_errors(name, entries, micro_skills)
    issues = trimmed + issues

    if bad and drop_invalid:
        kept = [e for i, e in enumerate(entries, start=1) if i not in bad]
        if len(kept) >= MIN_ERRORS:
            # Re-check the survivors separately. The original issues must not
            # be overwritten: they hold WHY each row was dropped, and that is
            # the only place that reason exists.
            recheck, still_bad = _check_errors(name, kept, micro_skills)
            if not still_bad and not [i for i in recheck if i.is_error]:
                entries = kept
                issues = _downgrade(
                    issues, recheck, name, "error_types", bad, len(kept),
                )

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise DiagnosisError(
            f"{name}: the model's error types cannot be used.\n"
            + "\n".join(f"  {i}" for i in errors)
        )
    if errors:
        return ErrorTypeSet(brief.topic_code, [], issues, payload)

    if id_service is None:
        id_service = IdService(brief.topic_code)

    rows: list[ErrorTypeRow] = []
    for entry in entries:
        try:
            error_code = id_service.error_code(str(entry["descriptor"]).strip())
        except IdError as exc:
            issues.append(ValidationIssue(
                IssueSeverity.ERROR, name, "error_code", str(exc)))
            if strict:
                raise DiagnosisError(f"{name}: {exc}") from exc
            return ErrorTypeSet(brief.topic_code, [], issues, payload)

        skill = micro_skills[int(entry["micro_skill_position"]) - 1]
        rows.append(
            ErrorTypeRow(
                error_code=error_code,
                error_name=str(entry["error_name"]).strip(),
                description=str(entry["description"]).strip(),
                related_micro_skill_id=skill.micro_skill_id,
                severity=Severity(entry["severity"]),
                detection_method=DetectionMethod(entry["detection_method"]),
                active=True,
            )
        )

    return ErrorTypeSet(brief.topic_code, rows, issues, payload)


# ──────────────────────────────────────────────────────────────────────
# Misconceptions
# ──────────────────────────────────────────────────────────────────────

MISCONCEPTION_SYSTEM_PROMPT = f"""\
You describe what a student BELIEVES that makes them get maths questions
wrong. Return a single JSON object and nothing else. No prose, no markdown.

{{
  "misconceptions": [
    {{
      "descriptor": "ADD-AS-MULTIPLY",
      "name": "Fixed change confused with multiplication",
      "description": "Student treats adding or subtracting a fixed amount as multiplying by that amount.",
      "diagnosis_rule": "Trigger after ERR-T01-ADD-AS-MULTIPLY when the intended rule uses addition or subtraction but the response uses multiplication."
    }}
  ]
}}

Rules, in order of importance:

1. A misconception is a BELIEF, not an observation. The errors table already
   records what the wrong answer looks like. This table records why the
   student produced it. "Student writes 5n instead of n + 5" is an error and
   does not belong here. "Student believes a fixed change means multiply by
   that amount" is a misconception.

2. diagnosis_rule says WHEN the tutor should conclude the student holds this
   belief. It must name at least one error code from the list below, copied
   EXACTLY, and it must add the condition that distinguishes a real
   misconception from a slip. One wrong answer is a slip. A pattern is a
   belief. Follow the shape of the example: "Trigger after <ERROR CODE> when
   <the condition>."

   Never invent an error code. Only the codes listed below exist. If the
   belief you are describing has no error in the list, do not write it.

3. One belief usually causes SEVERAL errors, which is why there are fewer
   misconceptions than errors. Where two errors come from the same belief,
   write one misconception and name both codes in the rule rather than
   writing near-duplicate entries.

4. description is one sentence, about the student's understanding, phrased so
   a tutor could read it and know what to re-teach.

5. descriptor is a SHORT UPPERCASE HYPHENATED name, three or four words at
   most. It becomes the misconception id and must be unique in this list. It
   does not have to match the error's descriptor.

Give between {MIN_MISCONCEPTIONS} and {MAX_MISCONCEPTIONS} misconceptions.
Between them they should account for most of the errors listed.
"""


def build_misconception_prompt(brief, error_types: list[ErrorTypeRow]) -> str:
    """The topic, and the error codes a diagnosis rule is allowed to name."""
    lines = [
        f"Topic {brief.topic_code}: {brief.topic_title}",
        f"Learning goal: {brief.learning_goal}",
        "",
        "Error codes for this topic. A diagnosis_rule may only name codes "
        "from this list, copied exactly:",
    ]
    lines += [
        f"  {row.error_code}  [{row.severity.value}]  {row.error_name}: "
        f"{row.description}"
        for row in error_types
    ]

    if brief.misconceptions_to_prevent:
        lines += [
            "",
            "The brief names these misconceptions to prevent. Your entries "
            "should cover them:",
            *(f"  - {item}" for item in brief.misconceptions_to_prevent),
        ]

    return "\n".join(lines)


@dataclass
class MisconceptionSet:
    """The misconceptions generated for one topic."""

    topic_code: str
    rows: list[MisconceptionRow] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_error]

    @property
    def is_clean(self) -> bool:
        return not self.errors


def referenced_error_codes(diagnosis_rule: str) -> list[str]:
    """The error codes a diagnosis rule names.

    The rule is prose and the schema has no column joining it to Error_Types,
    so this is the only way to find out what a rule depends on. Every one of
    the reference's 16 rules names at least one code.
    """
    return ERROR_CODE_RE.findall(str(diagnosis_rule or ""))


def _check_misconceptions(
    name: str,
    entries: list,
    known_codes: set[str],
) -> tuple[list[ValidationIssue], set[int]]:
    """Everything wrong with the model's misconceptions, and which rows are bad."""
    issues: list[ValidationIssue] = []
    bad: set[int] = set()

    def error(field_name: str, message: str, position: Optional[int] = None) -> None:
        issues.append(ValidationIssue(IssueSeverity.ERROR, name, field_name, message))
        if position is not None:
            bad.add(position)

    def warn(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(IssueSeverity.WARNING, name, field_name, message))

    if not isinstance(entries, list) or not entries:
        error("misconceptions", "model returned no misconceptions")
        return issues, bad

    if len(entries) < MIN_MISCONCEPTIONS:
        error("misconceptions",
              f"only {len(entries)} misconceptions; expected at least "
              f"{MIN_MISCONCEPTIONS}")
    # No error for going over; trim_to_cap handles it before this runs.

    descriptors_seen: set[str] = set()
    cited: set[str] = set()

    for position, entry in enumerate(entries, start=1):
        where = f"misconceptions[{position}]"
        if not isinstance(entry, dict):
            error(where, "not an object", position)
            continue

        for required in ("name", "description", "diagnosis_rule", "descriptor"):
            value = entry.get(required)
            if not isinstance(value, str) or not value.strip():
                error(where, f"{required} is missing or empty", position)

        descriptor = str(entry.get("descriptor") or "").strip()
        if descriptor:
            try:
                slug = slugify(descriptor)
            except IdError:
                slug = ""
            if not slug:
                error(where,
                      f"descriptor {descriptor!r} has nothing usable in it; it "
                      f"becomes the misconception id", position)
            elif slug in descriptors_seen:
                error(where, f"duplicate descriptor {descriptor!r}; "
                             f"misconception ids must be unique", position)
            if slug:
                descriptors_seen.add(slug)

        # The load-bearing check. diagnosis_rule points at Error_Types through
        # prose, so nothing in the schema stops it naming an error that was
        # never defined. The platform reads the rule, so a dangling code is a
        # misconception that can never be diagnosed.
        rule = str(entry.get("diagnosis_rule") or "")
        if rule.strip():
            named = referenced_error_codes(rule)
            if not named:
                error(where,
                      "diagnosis_rule names no error code, so nothing can ever "
                      "trigger it", position)
            unknown = [code for code in named if code not in known_codes]
            if unknown:
                error(where,
                      f"diagnosis_rule names {', '.join(sorted(set(unknown)))}, "
                      f"which {'do' if len(set(unknown)) > 1 else 'does'} not "
                      f"exist in this topic's error types", position)
            cited.update(code for code in named if code in known_codes)

    # -- shape of the set as a whole ------------------------------------
    orphans = known_codes - cited
    if orphans and not bad:
        warn("diagnosis_rule",
             f"{len(orphans)} error type(s) are never explained by any "
             f"misconception ({', '.join(sorted(orphans))}); the tutor can "
             f"detect them but has nothing to re-teach")

    if len(descriptors_seen) > len(known_codes):
        warn("misconceptions",
             f"{len(descriptors_seen)} misconceptions for {len(known_codes)} "
             f"errors; one belief usually causes several errors, so this "
             f"suggests errors were restated rather than explained")

    return issues, bad


def generate_misconceptions(
    brief,
    client: LLMClient,
    *,
    error_types: list[ErrorTypeRow],
    strict: bool = True,
    drop_invalid: bool = False,
    id_service: Optional[IdService] = None,
    version: str = DEFAULT_VERSION,
) -> MisconceptionSet:
    """Generate one topic's Misconceptions rows, after its error types exist."""
    name = brief.source_file_name
    if not error_types:
        raise DiagnosisError(
            f"{name}: cannot write misconceptions with no error types for "
            f"their diagnosis rules to trigger on"
        )

    known_codes = {row.error_code for row in error_types}

    payload = client.complete_json(
        MISCONCEPTION_SYSTEM_PROMPT,
        build_misconception_prompt(brief, error_types),
        purpose=f"CG-015 misconceptions for {name}",
    )

    entries = payload.get("misconceptions")
    trimmed: list[ValidationIssue] = []
    if isinstance(entries, list):
        entries, trimmed = trim_to_cap(
            entries, MAX_MISCONCEPTIONS, name, "misconceptions")

    issues, bad = _check_misconceptions(name, entries, known_codes)
    issues = trimmed + issues

    if bad and drop_invalid:
        kept = [e for i, e in enumerate(entries, start=1) if i not in bad]
        if len(kept) >= MIN_MISCONCEPTIONS:
            recheck, still_bad = _check_misconceptions(name, kept, known_codes)
            if not still_bad and not [i for i in recheck if i.is_error]:
                entries = kept
                issues = _downgrade(
                    issues, recheck, name, "misconceptions", bad, len(kept),
                )

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise DiagnosisError(
            f"{name}: the model's misconceptions cannot be used.\n"
            + "\n".join(f"  {i}" for i in errors)
        )
    if errors:
        return MisconceptionSet(brief.topic_code, [], issues, payload)

    if id_service is None:
        id_service = IdService(brief.topic_code)

    rows: list[MisconceptionRow] = []
    for entry in entries:
        try:
            misconception_id = id_service.misconception_id(
                str(entry["descriptor"]).strip())
        except IdError as exc:
            issues.append(ValidationIssue(
                IssueSeverity.ERROR, name, "misconception_id", str(exc)))
            if strict:
                raise DiagnosisError(f"{name}: {exc}") from exc
            return MisconceptionSet(brief.topic_code, [], issues, payload)

        rows.append(
            MisconceptionRow(
                misconception_id=misconception_id,
                name=str(entry["name"]).strip(),
                description=str(entry["description"]).strip(),
                diagnosis_rule=str(entry["diagnosis_rule"]).strip(),
                active=True,
                version=version,
            )
        )

    return MisconceptionSet(brief.topic_code, rows, issues, payload)


def _downgrade(
    original: list[ValidationIssue],
    recheck: list[ValidationIssue],
    name: str,
    field_name: str,
    dropped: set[int],
    kept: int,
) -> list[ValidationIssue]:
    """Turn a recovered batch's errors into warnings, keeping the detail.

    Same treatment the question generator gives a dropped question: the run
    succeeded, so is_clean should read True, but what was thrown away and why
    has to survive in the report or the row looks authored rather than
    salvaged.

    Two lists go in. `original` holds the reasons rows were dropped, which
    exist nowhere else once the rows are gone. `recheck` holds the warnings
    that describe what was KEPT, which is what a reader of the final table
    cares about; the original warnings are discarded because they described a
    set that no longer exists.
    """
    return [
        ValidationIssue(IssueSeverity.WARNING, i.source_file_name, i.field,
                        f"dropped: {i.message}")
        for i in original if i.is_error
    ] + [
        i for i in recheck if not i.is_error
    ] + [
        ValidationIssue(
            IssueSeverity.WARNING, name, field_name,
            f"dropped {len(dropped)} unusable row(s) at position(s) "
            f"{sorted(dropped)}; kept {kept}",
        )
    ]


if __name__ == "__main__":
    import sys

    from brief_mapper import map_all
    from llm_client import default_client, is_configured
    from micro_skill_generator import generate_micro_skills

    if not is_configured():
        print("No OpenAI API key found. Set OPENAI_API_KEY in your environment.")
        sys.exit(1)

    client = default_client()
    brief = map_all()[0]
    skills = generate_micro_skills(brief, client).rows
    result = generate_error_types(brief, client, micro_skills=skills)

    print(f"{result.topic_code}  {len(result.rows)} error types")
    for row in result.rows:
        print(f"  [{row.severity.value:6}] {row.error_code}")
        print(f"      {row.error_name}  ({row.detection_method.value})")
        print(f"      {row.description}")
        print(f"      shows a gap in {row.related_micro_skill_id}")
    for issue in result.issues:
        print(f"  {issue}")
