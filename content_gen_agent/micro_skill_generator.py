"""CG-010: generate the Micro_Skills table for a topic.

The first genuinely generative module. Everything before this reformatted what
the topic document already said; here the model has to invent content -- the
skills a student needs in order to meet the topic's learning goal -- and get
the structure right at the same time.

What the reference workbook actually contains, which shaped this
-----------------------------------------------------------------

Reading the 22 approved rows before writing the prompt changed three things:

  * **Skills form a dependency graph, not a list.** 19 of 22 rows carry a
    prerequisite. A generator emitting seven independent skills would look
    plausible and be wrong.
  * **The graph crosses topics.** T02.M1 depends on T01.M6. So generating a
    topic in isolation cannot reproduce the reference; earlier topics'
    skills have to be available to depend on.
  * **Priority is not uniform.** 16 HIGH to 6 MEDIUM. Emitting all HIGH would
    pass a naive check and lose the distinction the column exists for.

Why the model does not choose ids
---------------------------------

`micro_skill_id` is `T01.M1`, `T01.M2` and so on, minted by IdService in
order. Asking a model to produce them invites duplicates and gaps, and the
same positional-id hazard as scope items: if the model numbers them itself,
one skipped number silently repoints every prerequisite after it.

So the model returns skills **in order** and names prerequisites by
**position** -- "this skill depends on the 2nd skill in this list", or on a
skill id from an earlier topic. Ids are assigned here afterwards, and the
positions are resolved into real ids once they exist. A position that points
outside the list, or forward to a later skill, is rejected rather than
silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from id_service import IdService
from llm_client import LLMClient
from models import (
    AssessmentPriority,
    MicroSkillRow,
    MicroSkillStatus,
    NormalizedTopicBrief,
)
from validation import Severity, ValidationIssue

DEFAULT_VERSION = "1.0"
DEFAULT_STATUS = MicroSkillStatus.ACTIVE

# The reference runs 7 to 8 skills per topic across the three it covers.
MIN_SKILLS = 5
MAX_SKILLS = 10

MICRO_SKILL_ID_RE = re.compile(r"^T\d{2}\.M\d+$")


class MicroSkillError(Exception):
    """The model's micro-skills could not be trusted for this topic."""


SYSTEM_PROMPT = """\
You design the micro-skills a student must acquire to meet a topic's learning
goal. Return a single JSON object and nothing else. No prose, no markdown.

Return exactly this shape:

{
  "micro_skills": [
    {
      "skill_name": "Identify changing quantity",
      "description": "Identify the number or quantity that changes between cases.",
      "prerequisite_position": null,
      "prerequisite_micro_skill_id": null,
      "assessment_priority": "HIGH"
    }
  ]
}

Rules:

1. Produce between 5 and 10 skills, ordered so that a skill always comes after
   anything it depends on. Most topics need 7 or 8.

2. Each skill must be OBSERVABLE and ASSESSABLE: something you could set a
   question about and mark. "Identify the changing quantity" is a skill.
   "Understand algebra" is not, because you cannot see whether it happened.

3. skill_name is a short imperative phrase, five words or fewer, starting with
   a verb. description is one sentence saying what the student does.

4. Dependencies. A skill that requires another skill first must say so:
     - within this topic, set "prerequisite_position" to the 1-based position
       of that earlier skill in this list. It must be smaller than this
       skill's own position.
     - on an earlier topic, set "prerequisite_micro_skill_id" to one of the
       ids listed as available below, COPIED EXACTLY. Never invent an id and
       never write one in your own naming style. If no ids are listed below,
       there are no earlier topics, so this field must be null on every skill.
     - set both to null only for genuinely foundational skills.
   A skill records ONE prerequisite, so exactly one of these two fields may be
   filled in and the other must be null. Never set both, even if the skill
   genuinely builds on two things: choose the nearer one. In practice that is
   almost always the within-topic position -- a skill only depends on an
   earlier topic when it opens a topic and has no earlier skill of its own to
   build on. Most skills have a prerequisite; a list where nothing depends on
   anything is almost certainly wrong.

5. assessment_priority is REQUIRED on every skill and must be exactly "HIGH"
   or "MEDIUM". Do not omit it and do not use any other word. HIGH is a skill
   the topic's learning goal directly requires. MEDIUM supports it but a
   student could meet the goal without demonstrating it separately. Use both;
   they are not all HIGH.

Every skill must carry all five keys: skill_name, description,
prerequisite_position, prerequisite_micro_skill_id, assessment_priority. Use
null where a field does not apply rather than leaving it out.

6. Cover the topic's included scope and nothing outside it. Do not invent
   skills for the excluded scope. The misconceptions listed in the brief tell
   you what students get wrong, which is a good guide to what needs its own
   skill.
"""


def build_user_prompt(
    brief: NormalizedTopicBrief,
    available_prerequisites: Optional[list[MicroSkillRow]] = None,
) -> str:
    """Render one topic's brief, plus what earlier topics established."""
    lines = [
        f"Topic {brief.sequence_no}: {brief.topic_title}",
        f"Key stage: {brief.ks_stage.value}",
        "",
        f"Learning goal: {brief.learning_goal}",
        f"Core message: {brief.core_message}",
        "",
        "In scope:",
        *(f"  - {item}" for item in brief.included_scope),
        "",
        "Explicitly OUT of scope, do not write skills for these:",
        *(f"  - {item}" for item in brief.excluded_scope),
        "",
        "Misconceptions this topic must prevent:",
        *(f"  - {item}" for item in brief.misconceptions_to_prevent),
    ]

    if available_prerequisites:
        lines += [
            "",
            "Skills already established in earlier topics. A skill here may "
            "depend on one of these by id:",
            *(
                f"  {row.micro_skill_id}  {row.skill_name}"
                for row in available_prerequisites
            ),
        ]

    return "\n".join(lines)


@dataclass
class MicroSkillSet:
    """The micro-skills generated for one topic."""

    topic_code: str
    rows: list[MicroSkillRow] = field(default_factory=list)
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
    skills: list,
    known_ids: set[str],
) -> list[ValidationIssue]:
    """Everything wrong with the model's list, in one pass."""
    issues: list[ValidationIssue] = []

    def error(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, name, field_name, message))

    def warn(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.WARNING, name, field_name, message))

    if not isinstance(skills, list) or not skills:
        error("micro_skills", "model returned no skills")
        return issues

    if len(skills) < MIN_SKILLS:
        error("micro_skills", f"only {len(skills)} skills; expected at least {MIN_SKILLS}")
    if len(skills) > MAX_SKILLS:
        error("micro_skills", f"{len(skills)} skills; expected at most {MAX_SKILLS}")

    names_seen: set[str] = set()

    for position, skill in enumerate(skills, start=1):
        where = f"micro_skills[{position}]"
        if not isinstance(skill, dict):
            error(where, "not an object")
            continue

        for required in ("skill_name", "description"):
            value = skill.get(required)
            if not isinstance(value, str) or not value.strip():
                error(where, f"{required} is missing or empty")

        name_value = str(skill.get("skill_name") or "").strip().lower()
        if name_value:
            if name_value in names_seen:
                error(where, f"duplicate skill_name {skill.get('skill_name')!r}")
            names_seen.add(name_value)

        priority = skill.get("assessment_priority")
        if priority not in {p.value for p in AssessmentPriority}:
            error(where, f"assessment_priority {priority!r} is not HIGH or MEDIUM")

        # Dependencies. Both set is ambiguous; a forward or out-of-range
        # position would repoint silently once ids are assigned.
        pos = skill.get("prerequisite_position")
        ext = skill.get("prerequisite_micro_skill_id")

        if pos is not None and ext is not None:
            error(where, "sets both prerequisite_position and "
                         "prerequisite_micro_skill_id; use one")

        if pos is not None:
            if not isinstance(pos, int) or isinstance(pos, bool):
                error(where, f"prerequisite_position {pos!r} is not a whole number")
            elif pos < 1 or pos > len(skills):
                error(where, f"prerequisite_position {pos} is outside the list")
            elif pos >= position:
                error(where,
                      f"prerequisite_position {pos} points at itself or a later "
                      f"skill; dependencies must come earlier")

        if ext is not None:
            if not isinstance(ext, str) or not MICRO_SKILL_ID_RE.match(ext):
                error(where, f"prerequisite_micro_skill_id {ext!r} is not a valid id")
            elif ext not in known_ids:
                error(where,
                      f"prerequisite_micro_skill_id {ext!r} was not offered as "
                      f"available")

    priorities = {
        s.get("assessment_priority") for s in skills if isinstance(s, dict)
    }
    if len(priorities) == 1:
        warn("assessment_priority",
             f"every skill is {priorities.pop()!r}; the reference uses both")

    linked = sum(
        1 for s in skills
        if isinstance(s, dict)
        and (s.get("prerequisite_position") is not None
             or s.get("prerequisite_micro_skill_id") is not None)
    )
    if linked == 0:
        warn("prerequisite",
             "no skill depends on another; the reference links 19 of 22")

    return issues


#: What a skill falls back to when the model omits the priority entirely.
#: HIGH rather than MEDIUM because the failure modes are not symmetric: a skill
#: wrongly marked HIGH gets assessed when it need not be, which wastes a
#: question. Wrongly marked MEDIUM, it can be skipped, and a skill the learning
#: goal actually requires goes unassessed. The reference is 16 HIGH to 6 MEDIUM,
#: so HIGH is also the likelier answer.
FALLBACK_PRIORITY = AssessmentPriority.HIGH

#: Marks a warning that describes something _repair changed, so the pipeline can
#: surface repairs without matching on the wording of each message.
REPAIR_PREFIX = "repaired: "


def _repair(
    name: str,
    skills: list,
    known_ids: set[str],
) -> tuple[list, list[ValidationIssue]]:
    """Fix the field-level mistakes that are safe to fix, and say what was fixed.

    Micro-skills cannot use the drop-one-and-continue approach the questions
    take, because the skills form a dependency graph addressed by position:
    remove the third skill and every prerequisite_position above two now points
    at the wrong skill. So the recovery here is narrower, and repairs a field
    rather than removing a row.

    Only two repairs, both of which fall back to something safe rather than
    inventing content:

      * a missing or unrecognised assessment_priority becomes HIGH
      * a prerequisite_micro_skill_id that was never offered becomes null,
        which costs the graph one edge and keeps the skill itself

    Both are reported as warnings. A repair nobody is told about is worse than
    the failure, because the row looks authored rather than guessed.

    Everything else -- too few skills, a duplicate name, an empty description,
    a prerequisite_position pointing forwards -- is left for _check to reject.
    Those are not field-level slips; they mean the model misread the task.
    """
    notes: list[ValidationIssue] = []

    def note(field_name: str, message: str) -> None:
        # The prefix is how a caller tells a repair apart from the ordinary
        # warnings _check produces, without matching on the wording.
        notes.append(
            ValidationIssue(Severity.WARNING, name, field_name,
                            f"{REPAIR_PREFIX}{message}")
        )

    repaired: list = []
    for position, skill in enumerate(skills, start=1):
        if not isinstance(skill, dict):
            repaired.append(skill)
            continue

        skill = dict(skill)
        where = f"micro_skills[{position}]"

        priority = skill.get("assessment_priority")
        if priority not in {p.value for p in AssessmentPriority}:
            skill["assessment_priority"] = FALLBACK_PRIORITY.value
            note(where, f"assessment_priority was {priority!r}; defaulted to "
                        f"{FALLBACK_PRIORITY.value}")

        pos = skill.get("prerequisite_position")
        ext = skill.get("prerequisite_micro_skill_id")

        # A row holds one prerequisite, so only one of these can survive.
        # "Valid" is checked here rather than trusted, because dropping the
        # good one and keeping a broken one would turn an ambiguity into a
        # wrong dependency, which is worse than the failure being repaired.
        pos_ok = (
            isinstance(pos, int) and not isinstance(pos, bool)
            and 1 <= pos < position
        )
        ext_ok = (
            isinstance(ext, str) and bool(MICRO_SKILL_ID_RE.match(ext))
            and ext in known_ids
        )

        if pos is not None and ext is not None:
            # Both set. The reference resolves this: 16 of its 22 skills depend
            # on one in the same topic, only 3 on an earlier topic, and those 3
            # are all a topic's opening skills, where no within-topic skill
            # exists to point at yet. So the position is the more likely
            # intent -- but only when the position itself is usable.
            if pos_ok:
                skill["prerequisite_micro_skill_id"] = None
                note(where, f"set both prerequisites; kept "
                            f"prerequisite_position {pos} (the same topic is "
                            f"the nearer dependency) and cleared "
                            f"prerequisite_micro_skill_id {ext!r}")
            elif ext_ok:
                skill["prerequisite_position"] = None
                note(where, f"set both prerequisites, and prerequisite_position "
                            f"{pos!r} is not usable; kept "
                            f"prerequisite_micro_skill_id {ext!r}")
            # Neither usable: not a slip. _check reports both problems.

        elif ext is not None and not ext_ok:
            skill["prerequisite_micro_skill_id"] = None
            if not known_ids:
                note(where, f"prerequisite_micro_skill_id {ext!r} was invented "
                            f"-- no earlier topics exist to depend on; cleared")
            else:
                note(where, f"prerequisite_micro_skill_id {ext!r} was not "
                            f"offered as available; cleared")

        repaired.append(skill)

    return repaired, notes


def generate_micro_skills(
    brief: NormalizedTopicBrief,
    client: LLMClient,
    *,
    available_prerequisites: Optional[list[MicroSkillRow]] = None,
    strict: bool = True,
    repair: bool = False,
    id_service: Optional[IdService] = None,
    version: str = DEFAULT_VERSION,
) -> MicroSkillSet:
    """Generate one topic's micro-skills, ids assigned here rather than by the model."""
    name = brief.source_file_name
    available = available_prerequisites or []
    known_ids = {row.micro_skill_id for row in available}

    payload = client.complete_json(
        SYSTEM_PROMPT,
        build_user_prompt(brief, available),
        purpose=f"CG-010 micro-skills for {name}",
    )

    skills = payload.get("micro_skills")

    # Repair before checking, so a repaired field does not also get reported as
    # an error. The raw payload is kept on the result either way, so what the
    # model actually said is never lost.
    notes: list[ValidationIssue] = []
    if repair and isinstance(skills, list) and skills:
        skills, notes = _repair(name, skills, known_ids)

    issues = notes + _check(name, skills, known_ids)

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise MicroSkillError(
            f"{name}: the model's micro-skills cannot be used.\n"
            + "\n".join(f"  {i}" for i in errors)
        )
    if errors:
        return MicroSkillSet(brief.topic_code, [], issues, payload)

    if id_service is None:
        id_service = IdService(brief.topic_code)

    # Ids first, so a within-topic prerequisite can be resolved to a real id
    # once every skill has one.
    minted = [id_service.micro_skill_id() for _ in skills]

    rows: list[MicroSkillRow] = []
    for index, (skill, micro_skill_id) in enumerate(zip(skills, minted)):
        pos = skill.get("prerequisite_position")
        ext = skill.get("prerequisite_micro_skill_id")
        prerequisite = minted[pos - 1] if isinstance(pos, int) else ext

        rows.append(
            MicroSkillRow(
                micro_skill_id=micro_skill_id,
                topic_id=brief.topic_id,
                skill_code=micro_skill_id.split(".", 1)[1],
                skill_name=str(skill["skill_name"]).strip(),
                description=str(skill["description"]).strip(),
                prerequisite_micro_skill_id=prerequisite,
                assessment_priority=AssessmentPriority(skill["assessment_priority"]),
                status=DEFAULT_STATUS,
                version=version,
            )
        )

    return MicroSkillSet(brief.topic_code, rows, issues, payload)


def generate_all_micro_skills(
    briefs: list[NormalizedTopicBrief],
    client: LLMClient,
    *,
    strict: bool = True,
    **kwargs,
) -> list[MicroSkillSet]:
    """Every topic in order, each able to depend on the ones before it.

    Order matters and is not incidental: the reference has T02.M1 depending on
    T01.M6, so a topic can only be generated once its predecessors exist.
    """
    established: list[MicroSkillRow] = []
    out: list[MicroSkillSet] = []
    for brief in briefs:
        result = generate_micro_skills(
            brief, client,
            available_prerequisites=list(established),
            strict=strict,
            **kwargs,
        )
        out.append(result)
        established.extend(result.rows)
    return out


if __name__ == "__main__":
    import sys

    from brief_mapper import map_all
    from llm_client import default_client, is_configured

    if not is_configured():
        print("No OpenAI API key found. Set OPENAI_API_KEY in your environment.")
        sys.exit(1)

    for result in generate_all_micro_skills(map_all(), default_client()):
        print(f"\n{result.topic_code}  {len(result.rows)} skills")
        for row in result.rows:
            depends = f"  <- {row.prerequisite_micro_skill_id}" if row.prerequisite_micro_skill_id else ""
            print(f"  {row.micro_skill_id:8} {row.assessment_priority.value:7} "
                  f"{row.skill_name}{depends}")
        for issue in result.issues:
            print(f"    {issue}")
