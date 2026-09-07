"""CG-011 rewritten: questions generated per micro-skill, not per topic.

The review changed the unit of work. The old generator asked for about 18
questions for a topic and afterwards worked out which skill each one happened
to assess, which produced exactly what the review found:

    17 of 53 micro-skills owned no question at all
    T06.M1 owned 16 of its topic's 20
    7 diagnostics across six topics, three topics with none

None of that is a bug in a check. Coverage was never planned, so there was
nothing to check against. Here the plan comes first, from coverage_plan, and
the model is asked to fill named slots:

    Phase 0 Diagnostic     1    SINGLE_CHOICE, difficulty 2
    Phase 2 Guided         3    difficulty 1, 2, 3
    Phase 3 Independent    3    difficulty 1, 2, 3

One call per micro-skill, 53 calls for six topics, 371 questions. Phase and
difficulty are INPUTS, not something inferred afterwards, so plan_phases and
its heuristic go away entirely.

One skill per question
----------------------

The skill is not something the model chooses. This call is about one skill, so
every question it returns maps to that skill, is_primary=TRUE, weight=1.0. The
review's reasoning: under fractional weights a question gave partial credit to
a prerequisite it merely used along the way, so a student could look competent
at something they were never asked about.

That also removes a whole class of error the old generator could make. There
is no micro_skill_positions field to point at the wrong skill, because there
is nothing to point at.

Phase 3 has a modality rule, and it is hard
--------------------------------------------

Independent questions are answered without support, on a canvas or as a
multiple choice. The review forbids open prose there outright: no "explain in
one sentence", no "in your own words", no "describe why", nothing needing
voice. Those are fine in Phase 2, where the tutor is present to interpret an
answer, and unusable in Phase 3, where nothing is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from answer_generator import question_options
from coverage_plan import Slot, missing_slots, plan_for_skill
from id_service import IdError, IdService, slugify
from llm_client import LLMClient
from models import (
    MicroSkillRow,
    NormalizedTopicBrief,
    Phase,
    QuestionMicroSkillRow,
    QuestionRow,
    QuestionStatus,
    QuestionType,
)
from question_generator import (
    MIN_QUESTION_CHARS,
    _multi_select_phrase,
    multi_part_shape,
)
from table_schemas import PHASE_RULES
from validation import Severity, ValidationIssue

DEFAULT_VERSION = "1.0"

#: Not APPROVED. Nothing generated here has been checked for mathematical
#: correctness; CG-020 and CG-021 are what earn that.
DEFAULT_STATUS = QuestionStatus.GENERATED


class SkillQuestionError(Exception):
    """The model's questions for one micro-skill could not be used."""


#: Types PHASE_RULES permits but we do not ask for.
#:
#: TRUE_FALSE_WITH_EXPLANATION appears in the enum and in PHASE_RULES, and in
#: NONE of the approved reference's 54 rows. Everything about how to answer it
#: was inferred rather than observed, and a six-topic run showed the inference
#: was the wrong shape: the model wrote three-statement questions and answered
#: them "True; False; True", which is a MULTI_PART answer wearing a
#: true/false label. Nine of that run's twenty-five dropped answers were this.
#:
#: So it is not asked for. PHASE_RULES is left alone because it records the
#: spec; this is our decision about what to generate, and reversing it when
#: the shape is confirmed means deleting one line.
SUPPRESSED_QUESTION_TYPES = frozenset({"TRUE_FALSE_WITH_EXPLANATION"})


def allowed_types(phase: Phase) -> list[str]:
    """What a phase permits, minus what we have chosen not to generate."""
    return [
        t for t in PHASE_RULES[phase.value]["allowed_question_types"]
        if t not in SUPPRESSED_QUESTION_TYPES
    ]


#: Wordings the review bans from Phase 3. Each one asks for prose a marker has
#: to interpret, which is not answerable on a canvas and not markable without
#: a model call, and Phase 3 runs with no support at all.
PROSE_RE = re.compile(
    r"(?:"
    r"in your own words"
    r"|explain (?:in|why|how|what|briefly)"
    r"|describe (?:why|how|what|in)"
    r"|say (?:why|how|what) "
    r"|write (?:a|one|two|1|2)(?:\s+or\s+(?:two|three|2|3))?\s+(?:short\s+)?(?:sentence|sentences|phrase|phrases)"
    r"|tell (?:me|us) (?:why|how|what)"
    r"|justify your"
    r"|give a reason"
    r")",
    re.IGNORECASE,
)


def prose_phrase(text: str) -> Optional[str]:
    """The phrase making this an open-prose question, if it is one."""
    found = PROSE_RE.search(" ".join(str(text or "").split()))
    return found.group(0) if found else None


# ──────────────────────────────────────────────────────────────────────
# The prompt
# ──────────────────────────────────────────────────────────────────────

DIFFICULTY_GUIDE = """\
     1  Direct recognition or application. Familiar representation, usually
        one obvious step.
     2  Independent application or interpretation that needs a meaningful
        choice, or a distinction a common misconception would get wrong.
     3  Transfer: an unfamiliar representation, multi-step reasoning, or
        telling apart two ideas that look alike."""

SYSTEM_PROMPT = f"""\
You write practice questions for ONE micro-skill of a maths topic. Return a
single JSON object and nothing else. No prose, no markdown.

{{
  "questions": [
    {{
      "slot": 1,
      "question_type": "SINGLE_CHOICE",
      "question_text": "Which rule works for every step? a) n + 3  b) 3n  c) n - 3",
      "item_family": "PATTERN-RULE"
    }}
  ]
}}

Fill EVERY slot listed below, exactly once, and return nothing else. Each slot
fixes the phase and the difficulty; you choose the question type and write the
question.

Rules, in order of importance:

1. THE MATHS MUST BE CORRECT. A question with a wrong premise, an impossible
   answer or an ambiguous one teaches the student something false. If you
   cannot write a sound question for a slot, say so by leaving that slot out
   rather than writing a bad one.

2. EVERY QUESTION MUST ASSESS THE ONE MICRO-SKILL GIVEN BELOW. Not a skill it
   depends on, not the first thing a student does while solving it, not a
   broader idea it belongs to. If a student who has this skill and nothing
   else cannot answer, the question is testing the wrong thing.

   A question may of course USE earlier skills. It must not be ABOUT them.

3. difficulty means COGNITIVE DEMAND, not bigger numbers. Substituting n = 47
   instead of n = 4 is the same question.

{DIFFICULTY_GUIDE}

4. One clear task per question. The student must be able to tell exactly what
   is being asked.

5. For a choice question, write the options into question_text labelled
   a), b), c). EXACTLY ONE option may be correct. Wrong options must be
   plausible and must come from the misconceptions listed below, not from
   absurdities, and no two options may be different spellings of the same
   answer. Never ask for "all correct options": there is no select-all type.

6. item_family is a SHORT UPPERCASE HYPHENATED descriptor of what the question
   tests, three words or fewer: PATTERN-RULE, GENERAL-ADD, READ-COEFFICIENT.
   Questions testing the same thing the same way share one. Do not number them.

7. Stay inside the topic's scope. Nothing may require anything listed as out
   of scope, even in passing.

8. Do not refer to anything the student cannot see. No "using the supporting
   card", "as shown in the example", "look at the diagram", "from the video".
   If a question needs a picture, it cannot be asked here.
"""

#: Extra rules that apply only to some phases, added to the user prompt beside
#: the slots they govern rather than buried in the system prompt.
PHASE_GUIDANCE = {
    Phase.PHASE_0_DIAGNOSTIC: (
        "SINGLE_CHOICE only, and it has to DISCRIMINATE. This one question "
        "decides whether the student already has the skill, so the wrong "
        "options must be ones a student who lacks it would genuinely pick. A "
        "question nearly everyone answers correctly tells you nothing."
    ),
    Phase.PHASE_2_GUIDED_LEARNING: (
        "The tutor is present and can offer hints, so a question here may ask "
        "the student to explain or describe. Any type is allowed."
    ),
    Phase.PHASE_3_INDEPENDENT_PRACTICE: (
        "NO OPEN PROSE. The student works alone with no support, on a canvas "
        "or by picking an option, so the answer must be checkable without "
        "interpreting a sentence. Never write 'explain', 'in your own words', "
        "'describe why', or anything needing speech.\n"
        "        Ask instead for: a calculation, an expression, a completed "
        "equation, a transformed expression, a specific value, or a choice of "
        "option. Use a mix -- do not make all three multiple choice."
    ),
}


def build_user_prompt(
    brief: NormalizedTopicBrief,
    skill: MicroSkillRow,
    plan: list[Slot],
    only: Optional[set[int]] = None,
) -> str:
    """One skill, its topic context, and the slots to fill.

    `only` narrows it to particular slot numbers for a retry. The numbers stay
    as they were in the full plan, so a reply about slot 4 is still about slot
    4 and the two passes can be merged without translating anything.
    """
    lines = [
        f"Topic {brief.topic_code}: {brief.topic_title}",
        f"Topic learning goal: {brief.learning_goal}",
        "",
        "THE MICRO-SKILL THESE QUESTIONS MUST ASSESS:",
        f"  {skill.skill_name}",
        f"  {skill.description}",
    ]
    if skill.prerequisite_micro_skill_id:
        lines.append(
            f"  (it builds on {skill.prerequisite_micro_skill_id}, which a "
            f"question may use but must not be about)"
        )

    if only:
        lines += [
            "",
            "An earlier attempt covered the other slots. These are the ones "
            "still needed, and they keep their original numbers:",
        ]
    lines += ["", "SLOTS TO FILL:"]
    for number, slot in enumerate(plan, start=1):
        if only is not None and number not in only:
            continue
        allowed = allowed_types(slot.phase)
        lines.append(
            f"  slot {number}: {slot.phase.value}, difficulty "
            f"{slot.difficulty}"
        )
        lines.append(f"        question_type one of: {', '.join(allowed)}")
        guidance = PHASE_GUIDANCE.get(slot.phase)
        if guidance and number == next(
            i for i, s in enumerate(plan, start=1) if s.phase is slot.phase
        ):
            lines.append(f"        {guidance}")

    if brief.misconceptions_to_prevent:
        lines += [
            "",
            "Misconceptions to draw wrong options from:",
            *(f"  - {item}" for item in brief.misconceptions_to_prevent),
        ]

    if brief.excluded_scope:
        lines += [
            "",
            "Out of scope, must not be required:",
            *(f"  - {item}" for item in brief.excluded_scope),
        ]

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Result
# ──────────────────────────────────────────────────────────────────────

@dataclass
class SkillQuestionSet:
    """The questions generated for one micro-skill."""

    micro_skill_id: str
    rows: list[QuestionRow] = field(default_factory=list)

    #: The slot each question fills, by question id. Carries the phase, the
    #: difficulty and the role together, because they were decided together
    #: and splitting them is how they drift apart.
    slots: dict[str, Slot] = field(default_factory=dict)

    #: One mapping per question, always primary, always weight 1.0.
    skill_map: list[QuestionMicroSkillRow] = field(default_factory=list)

    issues: list[ValidationIssue] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)

    #: Slots still unfilled after the retry. Empty means the plan is met.
    missing: list[Slot] = field(default_factory=list)

    @property
    def phases(self) -> dict[str, Phase]:
        """Phase per question id, derived rather than stored separately."""
        return {qid: slot.phase for qid, slot in self.slots.items()}

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_error]

    @property
    def is_clean(self) -> bool:
        """Nothing wrong with the questions that ARE here."""
        return not self.errors

    @property
    def is_complete(self) -> bool:
        """The coverage plan is filled.

        Deliberately separate from is_clean. A skill can produce six sound
        questions and still be short of its plan, and calling that "clean"
        would hide the gap while calling it "dirty" would imply the six are
        suspect. They are different facts and the run reports both.
        """
        return not self.missing


# ──────────────────────────────────────────────────────────────────────
# Checking what came back
# ──────────────────────────────────────────────────────────────────────

def _check(
    name: str,
    entries: list,
    plan: list[Slot],
) -> tuple[list[ValidationIssue], set[int], list[Slot]]:
    """Row-level problems, the slots they spoil, and the slots left unfilled.

    Coverage is returned rather than reported, because how a gap should be
    treated depends on where the caller is. On a first pass it is something to
    retry; after a retry it is something to live with and declare. Deciding
    that in here would force one answer on both.
    """
    issues: list[ValidationIssue] = []
    bad: set[int] = set()

    def error(field_name: str, message: str, slot: Optional[int] = None) -> None:
        issues.append(ValidationIssue(Severity.ERROR, name, field_name, message))
        if slot is not None:
            bad.add(slot)

    def warn(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.WARNING, name, field_name, message))

    if not isinstance(entries, list) or not entries:
        error("questions", "model returned no questions")
        return issues, bad, list(plan)

    by_slot: dict[int, dict] = {}
    families: list[str] = []

    for entry in entries:
        if not isinstance(entry, dict):
            error("questions", "entry is not an object")
            continue

        slot_no = entry.get("slot")
        where = f"slot {slot_no}"
        if not isinstance(slot_no, int) or not 1 <= slot_no <= len(plan):
            error("questions",
                  f"slot {slot_no!r} is not one of the {len(plan)} offered")
            continue
        if slot_no in by_slot:
            error(where, "two questions returned for the same slot", slot_no)
            continue
        by_slot[slot_no] = entry

        slot = plan[slot_no - 1]
        permitted = allowed_types(slot.phase)
        text = str(entry.get("question_text") or "")

        if len(text.strip()) < MIN_QUESTION_CHARS:
            error(where, f"question_text is too short to be a task: "
                         f"{text.strip()!r}", slot_no)

        qtype = entry.get("question_type")
        if qtype not in permitted:
            error(where,
                  f"question_type {qtype!r} is not allowed in "
                  f"{slot.phase.value}; allowed {permitted}", slot_no)
        elif slot.required_type and qtype != slot.required_type.value:
            error(where,
                  f"this slot requires {slot.required_type.value}, not "
                  f"{qtype!r}", slot_no)

        # -- choice questions ------------------------------------------
        if qtype in ("SINGLE_CHOICE", "CHOICE_WITH_EXPLANATION"):
            if len(question_options(text)) < 2:
                error(where,
                      f"{qtype} but question_text carries fewer than two "
                      f"labelled options; it cannot be answered", slot_no)
            phrase = _multi_select_phrase(text)
            if phrase:
                error(where,
                      f"asks for more than one option ({phrase!r}); exactly "
                      f"one option must be correct, and there is no "
                      f"select-all question type", slot_no)

        # -- Phase 3 modality, the review's hard rule -------------------
        if slot.phase is Phase.PHASE_3_INDEPENDENT_PRACTICE:
            phrase = prose_phrase(text)
            if phrase:
                error(where,
                      f"Phase 3 forbids open prose ({phrase!r}). The student "
                      f"works with no support, so the answer must be a "
                      f"calculation, an expression or a chosen option",
                      slot_no)

        # -- a question may not point at something that does not exist --
        missing_asset = _absent_reference(text)
        if missing_asset:
            error(where,
                  f"refers to something the student cannot see "
                  f"({missing_asset!r}); the content package has no such "
                  f"item", slot_no)

        # -- multi-part mislabelled, same check the old generator gained -
        if qtype == "SHORT_RESPONSE" and multi_part_shape(text):
            error(where,
                  "asks for several separate answers but is typed "
                  "SHORT_RESPONSE; use MULTI_PART_SHORT_RESPONSE", slot_no)

        family = entry.get("item_family")
        if not isinstance(family, str) or not family.strip():
            error(where, "item_family is missing or empty", slot_no)
        else:
            try:
                slugify(family)
            except IdError as exc:
                error(where, f"item_family {family!r} is unusable: {exc}", slot_no)
            families.append(family.strip().lower())

    # -- coverage, returned rather than judged -----------------------
    produced = [
        (plan[n - 1].phase, plan[n - 1].difficulty)
        for n in by_slot if n not in bad
    ]
    missing = missing_slots(produced, plan)

    # -- shape of the set --------------------------------------------
    if len(set(families)) == 1 and len(families) > 2:
        warn("item_family",
             f"every question is family {families[0]!r}; seven questions on "
             f"one skill should still vary what they ask")

    p3 = [
        e for n, e in by_slot.items()
        if plan[n - 1].phase is Phase.PHASE_3_INDEPENDENT_PRACTICE
    ]
    if len(p3) > 1 and {e.get("question_type") for e in p3} == {"SINGLE_CHOICE"}:
        warn("question_type",
             "every Phase 3 question is SINGLE_CHOICE; the review asks for a "
             "mix of recognition and canvas work")

    return issues, bad, missing


#: Phrasings that point at an asset. The review found a question citing a
#: support card the package did not contain.
ABSENT_REFERENCE_RE = re.compile(
    r"(?:using|from|as shown in|look at|see|refer to|watch)\s+the\s+"
    r"(?:supporting\s+card|support\s+card|card|example|diagram|image|picture|"
    r"video|animation|scene|worked\s+example)",
    re.IGNORECASE,
)


def _absent_reference(text: str) -> Optional[str]:
    """The phrase citing an asset, if the question cites one.

    Every such reference is treated as absent, because this generator writes
    no assets and cannot create one. If orientation content is ever generated
    alongside, this becomes a lookup rather than a refusal.
    """
    found = ABSENT_REFERENCE_RE.search(" ".join(str(text or "").split()))
    return found.group(0) if found else None


# ──────────────────────────────────────────────────────────────────────
# Generating
# ──────────────────────────────────────────────────────────────────────

def _usable(entries, bad: set[int], slots: int) -> dict[int, dict]:
    """The entries that survived checking, keyed by slot.

    The slot number is range-checked here as well as in _check. A model that
    answers "slot 99" is reported there, but this is what stops the number
    reaching plan[98] and raising an IndexError instead.
    """
    return {
        e["slot"]: e for e in entries
        if isinstance(e, dict) and isinstance(e.get("slot"), int)
        and 1 <= e["slot"] <= slots and e["slot"] not in bad
    }


def generate_for_skill(
    brief: NormalizedTopicBrief,
    skill: MicroSkillRow,
    client: LLMClient,
    *,
    source_provenance_id: str,
    plan: Optional[list[Slot]] = None,
    retry: bool = True,
    strict: bool = True,
    id_service: Optional[IdService] = None,
    version: str = DEFAULT_VERSION,
) -> SkillQuestionSet:
    """The questions one micro-skill needs, phase and difficulty fixed.

    Recovery here cannot be the drop-and-continue the other generators use: a
    dropped question leaves a hole in the very coverage this rewrite exists to
    guarantee. But refusing outright is worse, because one bad question would
    cost all seven and leave the skill with nothing, which is the failure the
    review flagged in the first place.

    So a gap is RETRIED once, asking only for the slots still missing. If the
    retry also comes up short, the sound questions are kept and the skill is
    recorded as below its minimum. The review asks for exactly that: "if any
    required micro-skill/phase/difficulty combination is below the minimum,
    generation should be marked incomplete". A gap that is declared is a
    different thing from a gap that is hidden.

    Only one retry. A second attempt is the same roll of the same dice: if the
    model cannot write a sound difficulty 3 question for this skill, asking
    again mostly buys another call to find that out.
    """
    plan = plan if plan is not None else plan_for_skill()
    name = f"{skill.micro_skill_id} questions"
    wanted = set(range(1, len(plan) + 1))

    payload = client.complete_json(
        SYSTEM_PROMPT,
        build_user_prompt(brief, skill, plan),
        purpose=f"CG-011 questions for {skill.micro_skill_id}",
    )
    entries = payload.get("questions")
    issues, bad, missing = _check(name, entries, plan)
    good = _usable(entries if isinstance(entries, list) else [], bad, len(plan))

    outstanding = wanted - set(good)
    if outstanding and retry:
        issues.append(ValidationIssue(
            Severity.WARNING, name, "questions",
            f"retrying {len(outstanding)} slot(s) the first attempt did not "
            f"fill: {sorted(outstanding)}",
        ))
        second = client.complete_json(
            SYSTEM_PROMPT,
            build_user_prompt(brief, skill, plan, only=outstanding),
            purpose=f"CG-011 retry for {skill.micro_skill_id}",
        )
        extra = second.get("questions")
        retry_issues, retry_bad, _ = _check(name, extra, plan)
        recovered = {
            n: e for n, e in _usable(
                extra if isinstance(extra, list) else [], retry_bad,
                len(plan)).items()
            if n in outstanding
        }
        good.update(recovered)
        issues += retry_issues
        if recovered:
            issues.append(ValidationIssue(
                Severity.WARNING, name, "questions",
                f"retry filled {sorted(recovered)}",
            ))

    produced = [(plan[n - 1].phase, plan[n - 1].difficulty) for n in good]
    missing = missing_slots(produced, plan)

    # Every row-level complaint describes a question that is no longer in the
    # output, so none of them is a reason to refuse what is. They are kept as
    # warnings, with their wording intact, because "slot 4 is missing" is far
    # less useful than "slot 4 is missing because it asked for open prose in
    # Phase 3". The one thing that IS fatal is having nothing at all.
    issues = [
        i if not i.is_error else ValidationIssue(
            Severity.WARNING, i.source_file_name, i.field,
            f"dropped: {i.message}")
        for i in issues
    ]

    # A gap is reported, never silent, but it does not make the questions we
    # do have unusable. is_complete carries it; is_clean stays about quality.
    for slot in missing:
        issues.append(ValidationIssue(
            Severity.WARNING, name, "questions",
            f"below minimum: nothing usable for {slot}",
        ))

    if not good:
        issues.append(ValidationIssue(
            Severity.ERROR, name, "questions",
            "no usable question for any slot",
        ))

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise SkillQuestionError(
            f"{skill.micro_skill_id}: the model's questions cannot be used.\n"
            + "\n".join(f"  {i}" for i in errors)
        )
    if errors:
        return SkillQuestionSet(skill.micro_skill_id, issues=issues,
                                raw_response=payload, missing=missing)

    if id_service is None:
        id_service = IdService(brief.topic_code)

    rows: list[QuestionRow] = []
    slots: dict[str, Slot] = {}
    skill_map: list[QuestionMicroSkillRow] = []

    # Slot order, not the order the model happened to reply in, so ids run
    # diagnostic first and a skill's questions read as a student meets them.
    for number, slot in enumerate(plan, start=1):
        entry = good.get(number)
        if entry is None:
            continue
        question_id = id_service.question_id(
            diagnostic=slot.phase is Phase.PHASE_0_DIAGNOSTIC)

        rows.append(
            QuestionRow(
                question_id=question_id,
                topic_id=brief.topic_id,
                question_text=str(entry["question_text"]).strip(),
                question_type=QuestionType(entry["question_type"]),
                difficulty=slot.difficulty,
                answer_spec_id=id_service.answer_spec_id(question_id),
                item_family_id=id_service.item_family_id(
                    str(entry["item_family"]).strip()),
                source_provenance_id=source_provenance_id,
                status=DEFAULT_STATUS,
                version=version,
            )
        )
        slots[question_id] = slot
        skill_map.append(
            QuestionMicroSkillRow(
                question_id=question_id,
                micro_skill_id=skill.micro_skill_id,
                weight=1.0,
                is_primary=True,
            )
        )

    return SkillQuestionSet(skill.micro_skill_id, rows, slots, skill_map,
                            issues, payload, missing)


def generate_for_topic(
    brief: NormalizedTopicBrief,
    skills: list[MicroSkillRow],
    client: LLMClient,
    *,
    source_provenance_id: str,
    plan: Optional[list[Slot]] = None,
    retry: bool = True,
    strict: bool = True,
    id_service: Optional[IdService] = None,
    progress=None,
) -> list[SkillQuestionSet]:
    """Every skill in a topic, one call each.

    A skill that fails does not take the topic with it. That is a change of
    blast radius, not of standards: under the old generator one bad question
    lost all eighteen, and here it loses seven and names which skill is short.
    """
    if id_service is None:
        id_service = IdService(brief.topic_code)

    out: list[SkillQuestionSet] = []
    for number, skill in enumerate(skills, start=1):
        # Said BEFORE the call, not after. This loop makes one API call per
        # skill and used to print nothing until every one had returned, so a
        # run that was working looked exactly like a run that had hung. It
        # did hang once, for fifteen minutes, and there was no way to tell.
        if progress:
            progress(f"    skill {number}/{len(skills)}  "
                     f"{skill.micro_skill_id} {skill.skill_name}")
        try:
            out.append(generate_for_skill(
                brief, skill, client,
                source_provenance_id=source_provenance_id,
                plan=plan, retry=retry, strict=strict, id_service=id_service,
            ))
        except SkillQuestionError as exc:
            if strict:
                raise
            out.append(SkillQuestionSet(
                skill.micro_skill_id,
                issues=[ValidationIssue(
                    Severity.ERROR, f"{skill.micro_skill_id} questions",
                    "questions", str(exc))],
            ))
    return out
