"""CG-018: the guided walk-through for a student stuck on a Phase 2 question.

    Scaffolds            generated
    Scaffold_Steps       generated, with the forward routing derived
    Question_Scaffolds   derived

One scaffold per micro-skill, not per question
-----------------------------------------------

The review says "1 scaffold per Phase-2 question". Read literally that is 27
scaffolds a topic under the new plan, each with four steps: 108 step rows per
topic, and three near-identical scaffolds for the three guided questions on
one skill, which differ only in their numbers.

The template does not do that. It has 14 scaffolds serving 16 questions, so a
scaffold is written for a PATTERN and reused. Here that pattern is the
micro-skill: one scaffold per skill, linked to all three of that skill's
guided questions. Every Phase 2 question still has a scaffold, which is what
the rule asks for, and the walk-through is written once for the thing the
student is actually stuck on.

That is also why the steps say "What changes?" rather than naming a number.
A scaffold that quoted one question's values could not serve the other two.

Routing forward is derived
---------------------------

next_on_correct is "Stage 2", "Stage 3" and so on in every template row: a
step that is answered correctly moves to the next one. So it is built, not
asked for. next_on_incorrect is the interesting half -- it names a hint or a
visual cue to fall back to -- and that is asked for, and checked, because a
scaffold routing to a hint that does not exist strands the student at the
exact moment they needed help.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from id_service import IdError, IdService
from llm_client import LLMClient
from models import (
    HintRow,
    MicroSkillRow,
    Phase,
    QuestionRow,
    QuestionScaffoldRow,
    ScaffoldRow,
    ScaffoldStepRow,
    VisualCueRow,
)
from validation import Severity, ValidationIssue

#: The review asks for "about 3-5 ordered steps". Every template scaffold has
#: exactly 4.
MIN_STEPS, MAX_STEPS = 3, 5

#: Only one scaffold per question in the template, so there is nothing to
#: rank. Kept explicit because the column exists and would otherwise be blank.
DEFAULT_PRIORITY = 1

#: A step may fall back to a hint or a visual cue. Both come from CG-017, so
#: both can be checked.
SUPPORT_ID_RE = re.compile(r"(?:HINT|VC)-[A-Z0-9.-]+")


class ScaffoldError(Exception):
    """Scaffolds could not be built."""


SYSTEM_PROMPT = f"""\
You write the step-by-step walk-through a tutor uses when a student is stuck
on a guided question. Return a single JSON object and nothing else. No prose,
no markdown.

{{
  "scaffolds": [
    {{
      "micro_skill_id": "T01.M4",
      "scaffold_name": "Cases to General Rule",
      "trigger_rule": "Activate after repeated difficulty writing a rule that works for every case, normally after hint and visual support.",
      "completion_rule": "Write the full rule independently after the scaffold.",
      "steps": [
        {{"prompt": "What changes between the cases?",
          "partial_content": "3+5 | 9+5 | 14+5",
          "expected_response": "The starting number",
          "next_on_incorrect": "Use HINT-T01-GENERAL-L1"}},
        {{"prompt": "What stays the same?",
          "partial_content": "+5",
          "expected_response": "Add 5",
          "next_on_incorrect": "Use VC-T01-ADD-NOT-MULTIPLY"}}
      ]
    }}
  ]
}}

One scaffold per micro-skill listed below. Between {MIN_STEPS} and {MAX_STEPS}
steps each.

Rules:

1. A SCAFFOLD BREAKS THE THINKING INTO STEPS. It does not solve the question
   and then show the answer. Each step asks the student for one small thing
   they can get right, and the steps together arrive at the method.

2. THE SCAFFOLD SERVES EVERY GUIDED QUESTION ON THIS SKILL, not one of them.
   So the prompts must work whatever the numbers are: "What changes between
   the cases?" works everywhere, "What is 3 + 5?" works once. Put example
   values in partial_content, never in prompt.

3. prompt is what the tutor ASKS. Short, one thing, answerable in a few words.

4. partial_content is what the student SEES at that step: the working so far,
   or the part of the problem being looked at. It may be empty for a step that
   is purely a question.

5. expected_response is what a correct answer looks like, in a few words. It
   is what the tutor compares against, so keep it short and general.

6. next_on_incorrect says where to go when the student gets that step wrong.
   Name one of the hints or visual cues listed below, copied EXACTLY, as
   "Use HINT-..." or "Repeat this stage with VC-...". Never invent an id. If
   nothing listed fits, describe the fallback in words instead.

7. trigger_rule says WHEN the tutor should start the scaffold. It is a last
   resort, after hints and cues have not worked, so say so.

8. completion_rule says what the student must do unaided afterwards to count
   as having recovered. Finishing the scaffold is not the same as having
   learned the skill.

Do not write next_on_correct. A correct answer always moves to the next step,
and the last step ends the scaffold.
"""


def build_user_prompt(
    skills: list[MicroSkillRow],
    hints: list[HintRow],
    cues: list[VisualCueRow],
) -> str:
    """The skills needing a scaffold, and the support a step may fall back to."""
    lines = ["Micro-skills needing a scaffold:"]
    for row in skills:
        lines += ["", f"  {row.micro_skill_id}  {row.skill_name}",
                  f"    {row.description}"]

    if hints or cues:
        lines += ["", "Support a step may fall back to. Copy an id exactly:"]
        lines += [f"  {h.hint_id}  ({h.hint_type.value}) {h.content[:70]}"
                  for h in hints]
        lines += [f"  {c.visual_cue_id}  {c.cue_name}" for c in cues]
    return "\n".join(lines)


@dataclass
class ScaffoldSet:
    """Scaffolds, their steps, and the questions they serve."""

    topic_code: str
    scaffolds: list[ScaffoldRow] = field(default_factory=list)
    steps: list[ScaffoldStepRow] = field(default_factory=list)
    links: list[QuestionScaffoldRow] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_error]

    @property
    def is_clean(self) -> bool:
        return not self.errors


def generate_scaffolds(
    skills: list[MicroSkillRow],
    guided_questions: dict[str, list[QuestionRow]],
    hints: list[HintRow],
    cues: list[VisualCueRow],
    client: LLMClient,
    topic_code: str,
    *,
    id_service: Optional[IdService] = None,
    strict: bool = True,
) -> ScaffoldSet:
    """One scaffold per skill, linked to that skill's guided questions.

    `guided_questions` maps micro_skill_id to the Phase 2 questions it owns.
    Only skills that have one are scaffolded: a scaffold with nothing to
    attach to would never be shown.
    """
    name = f"{topic_code} scaffolds"
    issues: list[ValidationIssue] = []
    if id_service is None:
        id_service = IdService(topic_code)

    wanted = [s for s in skills if guided_questions.get(s.micro_skill_id)]
    if not wanted:
        raise ScaffoldError(
            f"{topic_code}: no micro-skill has a Phase 2 question, so there is "
            f"nothing to scaffold"
        )

    known_support = {h.hint_id for h in hints} | {c.visual_cue_id for c in cues}
    known_skills = {s.micro_skill_id for s in wanted}

    payload = client.complete_json(
        SYSTEM_PROMPT, build_user_prompt(wanted, hints, cues),
        purpose=f"CG-018 scaffolds for {topic_code}",
    )
    entries = payload.get("scaffolds")

    def drop(where: str, message: str) -> None:
        issues.append(ValidationIssue(
            Severity.WARNING, name, where, f"dropped: {message}"))

    scaffolds: list[ScaffoldRow] = []
    steps: list[ScaffoldStepRow] = []
    links: list[QuestionScaffoldRow] = []
    served: set[str] = set()

    for position, entry in enumerate(entries or [], start=1):
        where = f"scaffolds[{position}]"
        if not isinstance(entry, dict):
            drop(where, "not an object")
            continue

        skill_id = str(entry.get("micro_skill_id") or "")
        scaffold_name = str(entry.get("scaffold_name") or "").strip()
        trigger = str(entry.get("trigger_rule") or "").strip()
        completion = str(entry.get("completion_rule") or "").strip()
        raw_steps = entry.get("steps")

        if skill_id not in known_skills:
            drop(where, f"micro_skill_id {skill_id!r} has no Phase 2 question "
                        f"to attach a scaffold to")
            continue
        if skill_id in served:
            drop(where, f"{skill_id} already has a scaffold")
            continue
        if not scaffold_name or not trigger or not completion:
            drop(where, "scaffold_name, trigger_rule or completion_rule is empty")
            continue
        if not isinstance(raw_steps, list) or not MIN_STEPS <= len(raw_steps) <= MAX_STEPS:
            drop(where,
                 f"{len(raw_steps) if isinstance(raw_steps, list) else 0} steps; "
                 f"the review asks for {MIN_STEPS} to {MAX_STEPS}")
            continue

        try:
            scaffold_id = id_service.scaffold_id(scaffold_name)
        except IdError as exc:
            drop(where, str(exc))
            continue

        built: list[ScaffoldStepRow] = []
        broken = False
        for stage_no, raw in enumerate(raw_steps, start=1):
            step_where = f"{where} stage {stage_no}"
            if not isinstance(raw, dict):
                drop(step_where, "not an object")
                broken = True
                break

            prompt = str(raw.get("prompt") or "").strip()
            expected = str(raw.get("expected_response") or "").strip()
            on_incorrect = str(raw.get("next_on_incorrect") or "").strip()

            if not prompt or not expected:
                drop(step_where, "prompt or expected_response is empty")
                broken = True
                break

            # A step routing to a hint that does not exist strands the student
            # at the moment they needed help most.
            unknown = [s for s in SUPPORT_ID_RE.findall(on_incorrect)
                       if s not in known_support]
            if unknown:
                issues.append(ValidationIssue(
                    Severity.WARNING, name, step_where,
                    f"next_on_incorrect names {', '.join(unknown)}, which does "
                    f"not exist; replaced with a plain retry so the student is "
                    f"not routed nowhere",
                ))
                on_incorrect = "Repeat this stage"

            try:
                step_id = id_service.scaffold_step_id(scaffold_id, stage_no)
            except IdError as exc:
                drop(step_where, str(exc))
                broken = True
                break

            built.append(ScaffoldStepRow(
                scaffold_step_id=step_id,
                scaffold_id=scaffold_id,
                stage_no=stage_no,
                prompt=prompt,
                partial_content=str(raw.get("partial_content") or "").strip() or None,
                expected_response=expected,
                # Derived. A correct answer always advances, and the last step
                # ends the scaffold. Every template row agrees.
                next_on_correct=(f"Stage {stage_no + 1}"
                                 if stage_no < len(raw_steps) else "Complete"),
                next_on_incorrect=on_incorrect,
            ))

        if broken:
            continue

        served.add(skill_id)
        scaffolds.append(ScaffoldRow(
            scaffold_id=scaffold_id, scaffold_name=scaffold_name,
            trigger_rule=trigger, completion_rule=completion, active=True,
        ))
        steps.extend(built)
        # Derived: every guided question on this skill gets the scaffold, and
        # the skill is the question's one skill, so nothing is asked for.
        links.extend(
            QuestionScaffoldRow(
                question_id=question.question_id,
                micro_skill_id=skill_id,
                scaffold_id=scaffold_id,
                priority=DEFAULT_PRIORITY,
            )
            for question in guided_questions[skill_id]
        )

    for skill_id in known_skills - served:
        issues.append(ValidationIssue(
            Severity.WARNING, name, skill_id,
            f"below minimum: no scaffold, so its "
            f"{len(guided_questions[skill_id])} guided question(s) have no "
            f"walk-through when a student is stuck",
        ))

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise ScaffoldError(f"{topic_code}: scaffolds cannot be used.\n"
                            + "\n".join(f"  {i}" for i in errors))
    return ScaffoldSet(topic_code, scaffolds, steps, links, issues)


def guided_by_skill(
    questions: list[QuestionRow],
    slots: dict,
    skill_of_question: dict[str, str],
) -> dict[str, list[QuestionRow]]:
    """Phase 2 questions grouped by the skill they assess.

    Scaffolds only apply to guided practice: PHASE_RULES sets
    scaffold_allowed False for the diagnostic and independent phases, where
    the student is meant to work without support.
    """
    out: dict[str, list[QuestionRow]] = {}
    for question in questions:
        slot = slots.get(question.question_id)
        if slot is None or slot.phase is not Phase.PHASE_2_GUIDED_LEARNING:
            continue
        skill_id = skill_of_question.get(question.question_id)
        if skill_id:
            out.setdefault(skill_id, []).append(question)
    return out
