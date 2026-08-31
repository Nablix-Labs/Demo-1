"""CG-014: Worked_Examples, Worked_Example_Steps and Worked_Example_MicroSkills.

The tutor's demonstration: one problem worked through step by step, with what
appears on screen and what is said about it kept separate, so a step can be
narrated without reading the screen aloud.

A defect in the reference, and what this module does instead
-------------------------------------------------------------

The approved workbook stores **three** worked examples as **22 rows**, one step
each:

    reference                        what this module generates
    WE-T01-01-S1   step_no=1         WE-T01-01-S1
    WE-T01-02-S1   step_no=2         WE-T01-01-S2
    WE-T01-03-S1   step_no=3         WE-T01-01-S3
    ...                              ...

All seven Topic 1 rows carry the same title, problem statement and final
answer. Each has exactly one step. `step_no` runs 1 to 7, which only makes
sense as steps of a single example. 19 of the 22 step ids end `-S1` while
their `step_no` says otherwise.

So one seven-step example was flattened into seven one-step examples. The
`step_no` column preserves the real structure; the ids do not.

This is not a Topic 1 quirk like the ALG-KS3-01 topic id. It is consistent
across all three topics, and `IdService.worked_example_step_id` -- written in
CG-003 from the schema, before this data was examined -- produces the
unflattened shape, which is evidence about what the schema intends.

This module generates the correct shape: one worked example per topic with its
steps ordered beneath it. CG-023 will therefore report every worked-example row
as differing from the reference. That is recorded in KNOWN_WE_DIVERGENCE with
the evidence rather than hidden, and the alternative -- reproducing the defect
so the golden test passes -- would make "multi-step breakdowns" meaningless and
leave anything reading the table seeing seven examples that are really one.

Screen and narration are separate on purpose
---------------------------------------------

Each step carries `screen_content`, `narration_text`, `must_show` and
`must_not_show`. The last two are the interesting ones: they are authoring
constraints, not content. `must_not_show` on the first Topic 1 step is
"Different operations across the cases" -- a warning about the specific wrong
thing a designer might otherwise draw. Generating those requires knowing the
topic's misconceptions, so they are supplied to the prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from id_service import IdService
from llm_client import LLMClient
from models import (
    MicroSkillRow,
    NormalizedTopicBrief,
    WorkedExampleMicroSkillRow,
    WorkedExamplePhase,
    WorkedExampleRow,
    WorkedExampleStatus,
    WorkedExampleStepRow,
)
from usage_generator import split_weights
from validation import Severity, ValidationIssue

DEFAULT_VERSION = "1.1"
DEFAULT_STATUS = WorkedExampleStatus.APPROVED
DEFAULT_PHASE = WorkedExamplePhase.PHASE_1_ORIENTATION

# The reference's three examples run 7, 8 and 7 steps.
MIN_STEPS = 4
MAX_STEPS = 12

# Recorded rather than reproduced. See the module docstring.
KNOWN_WE_DIVERGENCE = (
    "The reference stores 3 worked examples as 22 one-step rows with "
    "duplicated titles, problem statements and final answers, and step ids "
    "that all end -S1 while step_no runs 1..7. This module generates one "
    "example per topic with its steps ordered beneath it, which is the shape "
    "the schema and IdService imply."
)


class WorkedExampleError(Exception):
    """The model's worked example could not be trusted for this topic."""


SYSTEM_PROMPT = """\
You write the tutor's worked example for a topic: one problem, demonstrated
step by step. Return a single JSON object and nothing else. No prose, no
markdown.

{
  "title": "Many Cases, One General Rule",
  "problem_statement": "Study 2 + 4, 7 + 4 and 12 + 4. Identify the general rule.",
  "final_answer": "n + 4; n represents any starting number; add 4 stays fixed",
  "steps": [
    {
      "screen_content": "2 + 4 | 7 + 4 | 12 + 4",
      "narration_text": "Look across the three cases. They share the same structure.",
      "must_show": "Three cases with the same repeated structure",
      "must_not_show": "Different operations across the cases",
      "micro_skill_positions": [1]
    }
  ]
}

Rules:

1. ONE problem, worked all the way through. Not several problems, and not a
   summary. The student watches this once and it has to stand alone.

2. Between 4 and 12 steps, in the order a student should meet them. Each step
   does ONE thing. A step that both identifies the changing quantity and
   writes the rule is two steps.

3. screen_content is what appears, and nothing else. Keep it short: an
   expression, a few values, a labelled diagram in words. Not a sentence of
   explanation.

4. narration_text is what the tutor SAYS while that is on screen. It must not
   simply read the screen aloud. If the screen shows "2 + 4 | 7 + 4 | 12 + 4",
   the narration says what to notice about them.

5. must_show is the thing a designer has to get right for the step to work.
   must_not_show is the specific wrong thing they might otherwise draw, taken
   from the misconceptions listed below. "Different operations across the
   cases" is useful. "Anything incorrect" is not.

6. micro_skill_positions names which skills the step demonstrates, by their
   1-based position in the list below. At least one per step.

7. final_answer states the result and what its parts mean, so the step-by-step
   reasoning has somewhere to arrive.

8. Stay inside the topic's scope. The example may not require anything listed
   as out of scope.
"""


def build_user_prompt(
    brief: NormalizedTopicBrief,
    micro_skills: Optional[list[MicroSkillRow]] = None,
) -> str:
    lines = [
        f"Topic {brief.sequence_no}: {brief.topic_title}",
        "",
        f"Learning goal: {brief.learning_goal}",
        f"Core message: {brief.core_message}",
        "",
        "In scope:",
        *(f"  - {item}" for item in brief.included_scope),
        "",
        "OUT of scope, the example may not require these:",
        *(f"  - {item}" for item in brief.excluded_scope),
        "",
        "Misconceptions. Use these for must_not_show:",
        *(f"  - {item}" for item in brief.misconceptions_to_prevent),
    ]
    if micro_skills:
        lines += [
            "",
            "Micro-skills for this topic. Reference them by position:",
            *(
                f"  {n}. {row.skill_name} -- {row.description}"
                for n, row in enumerate(micro_skills, start=1)
            ),
        ]
    return "\n".join(lines)


@dataclass
class WorkedExampleSet:
    """All three tables for one topic's worked example."""

    topic_code: str
    example: Optional[WorkedExampleRow] = None
    steps: list[WorkedExampleStepRow] = field(default_factory=list)
    skill_map: list[WorkedExampleMicroSkillRow] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_error]

    @property
    def is_clean(self) -> bool:
        return not self.errors


def _normalise(value: object) -> str:
    return " ".join(str(value).split()).lower()


def _check(name: str, payload: dict, skill_count: int) -> list[ValidationIssue]:
    """Everything wrong with the model's worked example, in one pass."""
    issues: list[ValidationIssue] = []

    def error(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, name, field_name, message))

    def warn(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.WARNING, name, field_name, message))

    for required in ("title", "problem_statement", "final_answer"):
        value = payload.get(required)
        if not isinstance(value, str) or not value.strip():
            error(required, "missing or empty")

    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        error("steps", "the example has no steps")
        return issues

    if len(steps) < MIN_STEPS:
        error("steps", f"only {len(steps)} steps; expected at least {MIN_STEPS}")
    if len(steps) > MAX_STEPS:
        error("steps", f"{len(steps)} steps; expected at most {MAX_STEPS}")

    screens_seen: set[str] = set()

    for position, step in enumerate(steps, start=1):
        where = f"steps[{position}]"
        if not isinstance(step, dict):
            error(where, "not an object")
            continue

        for required in ("screen_content", "narration_text", "must_show",
                         "must_not_show"):
            value = step.get(required)
            if not isinstance(value, str) or not value.strip():
                error(where, f"{required} is missing or empty")

        screen = _normalise(step.get("screen_content"))
        narration = _normalise(step.get("narration_text"))

        if screen:
            if screen in screens_seen:
                warn(where, "repeats an earlier step's screen content")
            screens_seen.add(screen)

        # Narration that merely reads the screen teaches nothing. The prompt
        # says so; this catches it when the model does it anyway.
        if screen and narration and screen == narration:
            error(where,
                  "narration_text only repeats screen_content; it should say "
                  "what to notice, not read the screen aloud")

        positions = step.get("micro_skill_positions")
        if not isinstance(positions, list) or not positions:
            error(where, "micro_skill_positions is missing or empty; a step "
                         "that demonstrates no skill cannot be mapped")
        elif skill_count:
            for value in positions:
                if not isinstance(value, int) or isinstance(value, bool):
                    error(where, f"micro_skill_positions entry {value!r} is not a number")
                elif value < 1 or value > skill_count:
                    error(where,
                          f"micro_skill_positions {value} is outside the "
                          f"{skill_count} skills offered")

    return issues


def generate_worked_example(
    brief: NormalizedTopicBrief,
    client: LLMClient,
    *,
    micro_skills: Optional[list[MicroSkillRow]] = None,
    phase: WorkedExamplePhase = DEFAULT_PHASE,
    strict: bool = True,
    id_service: Optional[IdService] = None,
    version: str = DEFAULT_VERSION,
) -> WorkedExampleSet:
    """Generate one topic's worked example and its ordered steps."""
    name = brief.source_file_name
    skills = micro_skills or []

    payload = client.complete_json(
        SYSTEM_PROMPT,
        build_user_prompt(brief, skills),
        purpose=f"CG-014 worked example for {name}",
    )

    issues = _check(name, payload, len(skills))
    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise WorkedExampleError(
            f"{name}: the model's worked example cannot be used.\n"
            + "\n".join(f"  {i}" for i in errors)
        )
    if errors:
        return WorkedExampleSet(brief.topic_code, None, [], [], issues, payload)

    if id_service is None:
        id_service = IdService(brief.topic_code)

    # One example, steps beneath it. See the module docstring on why this
    # differs from the reference.
    example_id = id_service.worked_example_id()
    example = WorkedExampleRow(
        worked_example_id=example_id,
        topic_id=brief.topic_id,
        title=str(payload["title"]).strip(),
        phase=phase,
        problem_statement=str(payload["problem_statement"]).strip(),
        final_answer=str(payload["final_answer"]).strip(),
        status=DEFAULT_STATUS,
        version=version,
    )

    steps: list[WorkedExampleStepRow] = []
    demonstrated: list[str] = []

    for step_no, step in enumerate(payload["steps"], start=1):
        steps.append(
            WorkedExampleStepRow(
                worked_example_step_id=id_service.worked_example_step_id(
                    example_id, step_no
                ),
                worked_example_id=example_id,
                step_no=step_no,
                screen_content=str(step["screen_content"]).strip(),
                narration_text=str(step["narration_text"]).strip(),
                must_show=str(step["must_show"]).strip(),
                must_not_show=str(step["must_not_show"]).strip(),
            )
        )
        for p in step["micro_skill_positions"]:
            skill_id = skills[p - 1].micro_skill_id
            if skill_id not in demonstrated:
                demonstrated.append(skill_id)

    # The example as a whole demonstrates whatever its steps did, weighted
    # evenly, with the first one primary. Same invariants as CG-012.
    skill_map: list[WorkedExampleMicroSkillRow] = []
    if demonstrated:
        for skill_id, weight in zip(demonstrated, split_weights(len(demonstrated))):
            skill_map.append(
                WorkedExampleMicroSkillRow(
                    worked_example_id=example_id,
                    micro_skill_id=skill_id,
                    weight=weight,
                    is_primary=(skill_id == demonstrated[0]),
                )
            )

    return WorkedExampleSet(
        brief.topic_code, example, steps, skill_map, issues, payload,
    )
