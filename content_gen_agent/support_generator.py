"""CG-017: what the tutor offers a student who is stuck.

Five tables, three model calls, because the joins are derived:

    Hints                       generated
    Misconception_Hints         derived
    Visual_Cues                 generated
    Misconception_VisualCues    derived
    Parallel_Examples           generated

The review's minimum, per misconception: two hints (ATTENTION then
CONCEPT_REMINDER, with PARTIAL_STEP optional), one visual cue, one parallel
example.

Two things the template settles rather than leaving to judgement
-----------------------------------------------------------------

**hint_level is hint_type.** Across 40 rows the pairing is exact and without
exception: ATTENTION is always level 1, CONCEPT_REMINDER always 2,
PARTIAL_STEP always 3. So the model is asked for the type, which carries
meaning, and never for the level, which would only be a second chance to
disagree with itself.

**Misconception_Hints.sequence_order is the hint level.** Zero of the
template's 40 join rows differ from it. The order a tutor offers hints in is
the order of escalation, so the join is built rather than asked for.

Escalation is the point
------------------------

The three levels are not three phrasings of the same thing. ATTENTION points
at where to look without saying what is wrong. CONCEPT_REMINDER restates the
idea the student is missing. PARTIAL_STEP does part of the work. A hint set
where all three give away the same amount is one hint written three times, and
the tutor has nothing to escalate through.

Visual cues are prompts, not pictures
--------------------------------------

The template's cues carry an asset_url pointing at produced GIFs in blob
storage. Those are made elsewhere. What is generated here is the
image_generation_prompt and the negative_prompt that would produce one, plus
the retrieval text that decides when to show it. asset_url is left empty and
embedding_status PENDING, so the gap is visible rather than implied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from id_service import IdError, IdService
from llm_client import LLMClient
from models import (
    EmbeddingStatus,
    HintRow,
    HintType,
    MisconceptionHintRow,
    MisconceptionRow,
    MisconceptionVisualCueRow,
    ParallelExampleRow,
    VisualCueReviewStatus,
    VisualCueRow,
)
from validation import Severity, ValidationIssue

DEFAULT_VERSION = "1.0"

#: Exact in all 40 template rows, no exceptions. The model gives the type; the
#: level follows, so the two can never disagree.
LEVEL_FOR_HINT_TYPE = {
    HintType.ATTENTION: 1,
    HintType.CONCEPT_REMINDER: 2,
    HintType.PARTIAL_STEP: 3,
}

#: The review's minimum. PARTIAL_STEP is explicitly optional -- her words,
#: "The Third one is optional" -- and the template only has 4 of them.
REQUIRED_HINT_TYPES = (HintType.ATTENTION, HintType.CONCEPT_REMINDER)

#: Every cue in the template repeats this. It is a house style for the image
#: model, not a judgement, so it is not asked for on every call.
NEGATIVE_PROMPT = (
    "No generated text, letters, numbers, equations, mathematical symbols, "
    "watermarks, logos, clutter, 3D render, photorealism."
)


class SupportError(Exception):
    """Support content could not be built."""


# ──────────────────────────────────────────────────────────────────────
# Hints
# ──────────────────────────────────────────────────────────────────────

HINT_SYSTEM_PROMPT = """\
You write the hints a tutor gives a student who is stuck. Return a single JSON
object and nothing else. No prose, no markdown.

{
  "hints": [
    {"misconception_id": "MIS-T01-ADD-AS-MULTIPLY",
     "hint_type": "ATTENTION",
     "content": "Which part of each example changes, and which part stays the same?"},
    {"misconception_id": "MIS-T01-ADD-AS-MULTIPLY",
     "hint_type": "CONCEPT_REMINDER",
     "content": "Adding the same amount every time is repeated addition, not multiplication by that amount."}
  ]
}

Every misconception below needs at least an ATTENTION hint and a
CONCEPT_REMINDER hint. A PARTIAL_STEP hint is optional; add one only where a
student would still be stuck after the first two.

THE THREE LEVELS GIVE AWAY DIFFERENT AMOUNTS. That is the whole point, because
the tutor escalates through them:

  ATTENTION        Points at WHERE to look. Says nothing about what is wrong
                   and gives no part of the answer. Usually a question.
                   "Look at what changes between the two cases."

  CONCEPT_REMINDER Restates the IDEA the student is missing, in general terms.
                   Still not about this particular question's answer.
                   "A letter stands for a number that can change."

  PARTIAL_STEP     Does part of the work, leaving the rest. Only here may you
                   touch the actual answer, and never all of it.
                   "Start by writing the number that stays the same: + 4."

If your three hints give away the same amount, you have written one hint three
times and the tutor has nothing to escalate through.

Rules:

1. Use only the misconception ids listed below, copied EXACTLY.

2. A hint addresses the BELIEF, not one question. These hints are attached to
   a misconception and will be shown on any question that triggers it, so
   nothing may refer to a specific question's numbers or wording.

3. Never give the whole answer, not even at PARTIAL_STEP. A hint that answers
   the question is not a hint.

4. Write to the student, not about them. "Look at what changes" rather than
   "the student should look at what changes".
"""


def build_hint_prompt(misconceptions: list[MisconceptionRow]) -> str:
    lines = ["Misconceptions needing hints:"]
    for row in misconceptions:
        lines += [
            "",
            f"  {row.misconception_id}  {row.name}",
            f"    {row.description}",
        ]
    return "\n".join(lines)


@dataclass
class SupportSet:
    """Everything CG-017 produces for one topic."""

    topic_code: str
    hints: list[HintRow] = field(default_factory=list)
    hint_links: list[MisconceptionHintRow] = field(default_factory=list)
    visual_cues: list[VisualCueRow] = field(default_factory=list)
    cue_links: list[MisconceptionVisualCueRow] = field(default_factory=list)
    parallel_examples: list[ParallelExampleRow] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_error]

    @property
    def is_clean(self) -> bool:
        return not self.errors


def generate_hints(
    misconceptions: list[MisconceptionRow],
    client: LLMClient,
    topic_code: str,
    *,
    id_service: Optional[IdService] = None,
    strict: bool = True,
) -> tuple[list[HintRow], list[MisconceptionHintRow], list[ValidationIssue]]:
    """Hints, and the join, which is derived from the level."""
    name = f"{topic_code} hints"
    issues: list[ValidationIssue] = []
    known = {row.misconception_id: row for row in misconceptions}
    if id_service is None:
        id_service = IdService(topic_code)

    if not misconceptions:
        raise SupportError(f"{topic_code}: no misconceptions to write hints for")

    payload = client.complete_json(
        HINT_SYSTEM_PROMPT, build_hint_prompt(misconceptions),
        purpose=f"CG-017 hints for {topic_code}",
    )
    entries = payload.get("hints")

    def drop(where: str, message: str) -> None:
        issues.append(ValidationIssue(
            Severity.WARNING, name, where, f"dropped: {message}"))

    hints: list[HintRow] = []
    links: list[MisconceptionHintRow] = []
    seen: set[tuple[str, HintType]] = set()

    for position, entry in enumerate(entries or [], start=1):
        where = f"hints[{position}]"
        if not isinstance(entry, dict):
            drop(where, "not an object")
            continue

        misconception_id = str(entry.get("misconception_id") or "")
        raw_type = str(entry.get("hint_type") or "")
        content = str(entry.get("content") or "").strip()

        if misconception_id not in known:
            drop(where, f"misconception_id {misconception_id!r} does not exist")
            continue
        if raw_type not in {t.value for t in HintType}:
            drop(where, f"hint_type {raw_type!r} is not one of "
                        f"{[t.value for t in HintType]}")
            continue
        if not content:
            drop(where, "content is empty")
            continue

        hint_type = HintType(raw_type)
        if (misconception_id, hint_type) in seen:
            drop(where, f"{misconception_id} already has a {raw_type} hint")
            continue
        seen.add((misconception_id, hint_type))

        # The level is not asked for. It follows from the type without
        # exception in the template, so deriving it removes a way to disagree.
        level = LEVEL_FOR_HINT_TYPE[hint_type]
        try:
            hint_id = id_service.hint_id(known[misconception_id].name, level)
        except IdError as exc:
            drop(where, str(exc))
            continue

        hints.append(HintRow(hint_id=hint_id, hint_level=level,
                             hint_type=hint_type, content=content, active=True))
        # sequence_order IS the level: the order a tutor escalates through.
        # Zero of the template's 40 join rows differ from it.
        links.append(MisconceptionHintRow(
            misconception_id=misconception_id, hint_id=hint_id,
            sequence_order=level,
        ))

    # -- the review's minimum ------------------------------------------
    for misconception_id in known:
        have = {t for m, t in seen if m == misconception_id}
        short = [t for t in REQUIRED_HINT_TYPES if t not in have]
        if short:
            issues.append(ValidationIssue(
                Severity.WARNING, name, misconception_id,
                f"below minimum: no {', '.join(t.value for t in short)} hint; "
                f"the review asks for at least ATTENTION and CONCEPT_REMINDER "
                f"so the tutor has something to escalate through",
            ))

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise SupportError(
            f"{topic_code}: hints cannot be used.\n"
            + "\n".join(f"  {i}" for i in errors)
        )
    return hints, links, issues


# ──────────────────────────────────────────────────────────────────────
# Visual cues
# ──────────────────────────────────────────────────────────────────────

CUE_SYSTEM_PROMPT = f"""\
You write the brief for a picture that fixes a misconception. Return a single
JSON object and nothing else. No prose, no markdown.

{{
  "cues": [
    {{
      "misconception_id": "MIS-T01-ADD-AS-MULTIPLY",
      "cue_name": "Repeated Adding Is Not Multiplying",
      "cue_purpose": "Show that adding the same amount each step builds a total by steps, not by multiplying the start.",
      "image_generation_prompt": "Premium 2D educational infographic, 16:9 landscape. Two side-by-side panels...",
      "tutor_explanation_template": "Look at the two panels. Each step adds the same amount; nothing is being multiplied.",
      "retrieval_text": "Use when a student turns a fixed change into multiplication by that number.",
      "retrieval_keywords": "repeated addition, fixed change, not multiplication"
    }}
  ]
}}

One cue per misconception.

Rules:

1. Use only the misconception ids listed below, copied EXACTLY.

2. image_generation_prompt describes a PICTURE, and the picture must carry the
   idea on its own. Say what is on screen, how it is arranged, and what the
   contrast is. Begin "Premium 2D educational infographic, 16:9 landscape."

3. NO TEXT, LETTERS, NUMBERS OR SYMBOLS IN THE IMAGE. The image model renders
   them badly and they cannot be translated. Ask for shapes, panels, colour
   contrast, arrows and placeholders instead. If your idea cannot be shown
   without writing an equation, it is not a picture idea.

4. tutor_explanation_template is what the tutor SAYS while the picture is on
   screen. One or two sentences, addressed to the student.

5. retrieval_text says WHEN to show this cue, starting "Use when a student".
   It is how the cue is found, so describe the student's mistake, not the
   picture.

6. retrieval_keywords is a short comma-separated list of the words someone
   would search to find this cue.
"""


def build_cue_prompt(misconceptions: list[MisconceptionRow]) -> str:
    lines = ["Misconceptions needing a visual cue:"]
    for row in misconceptions:
        lines += ["", f"  {row.misconception_id}  {row.name}",
                  f"    {row.description}"]
    return "\n".join(lines)


def generate_visual_cues(
    misconceptions: list[MisconceptionRow],
    client: LLMClient,
    topic_code: str,
    *,
    id_service: Optional[IdService] = None,
    strict: bool = True,
) -> tuple[list[VisualCueRow], list[MisconceptionVisualCueRow], list[ValidationIssue]]:
    """One cue per misconception, and the join, which is 1:1 by construction."""
    name = f"{topic_code} visual cues"
    issues: list[ValidationIssue] = []
    known = {row.misconception_id for row in misconceptions}
    if id_service is None:
        id_service = IdService(topic_code)

    if not misconceptions:
        raise SupportError(f"{topic_code}: no misconceptions to illustrate")

    payload = client.complete_json(
        CUE_SYSTEM_PROMPT, build_cue_prompt(misconceptions),
        purpose=f"CG-017 visual cues for {topic_code}",
    )
    entries = payload.get("cues")

    def drop(where: str, message: str) -> None:
        issues.append(ValidationIssue(
            Severity.WARNING, name, where, f"dropped: {message}"))

    cues: list[VisualCueRow] = []
    links: list[MisconceptionVisualCueRow] = []
    served: set[str] = set()

    required = ("cue_name", "cue_purpose", "image_generation_prompt",
                "tutor_explanation_template", "retrieval_text",
                "retrieval_keywords")

    for position, entry in enumerate(entries or [], start=1):
        where = f"cues[{position}]"
        if not isinstance(entry, dict):
            drop(where, "not an object")
            continue

        misconception_id = str(entry.get("misconception_id") or "")
        if misconception_id not in known:
            drop(where, f"misconception_id {misconception_id!r} does not exist")
            continue
        if misconception_id in served:
            drop(where, f"{misconception_id} already has a cue")
            continue

        missing = [f for f in required if not str(entry.get(f) or "").strip()]
        if missing:
            drop(where, f"missing {', '.join(missing)}")
            continue

        try:
            cue_id = id_service.visual_cue_id(str(entry["cue_name"]))
        except IdError as exc:
            drop(where, str(exc))
            continue

        served.add(misconception_id)
        cues.append(VisualCueRow(
            visual_cue_id=cue_id,
            cue_name=str(entry["cue_name"]).strip(),
            cue_purpose=str(entry["cue_purpose"]).strip(),
            image_generation_prompt=str(entry["image_generation_prompt"]).strip(),
            # Not asked for. Every template cue repeats the same wording, so it
            # is house style for the image model rather than a judgement.
            negative_prompt=NEGATIVE_PROMPT,
            tutor_explanation_template=str(entry["tutor_explanation_template"]).strip(),
            retrieval_text=str(entry["retrieval_text"]).strip(),
            retrieval_keywords=str(entry["retrieval_keywords"]).strip(),
            # The picture does not exist yet. Left empty rather than invented,
            # so the gap is visible in the file.
            asset_url=None,
            embedding_status=EmbeddingStatus.PENDING,
            review_status=VisualCueReviewStatus.PENDING_REVIEW,
            version=DEFAULT_VERSION,
        ))
        # Derived: we make one cue per misconception, so the join is 1:1 and
        # the order is always first. A cue shared across misconceptions is
        # possible in the template but is an optimisation, not a requirement.
        links.append(MisconceptionVisualCueRow(
            misconception_id=misconception_id, visual_cue_id=cue_id,
            sequence_order=1,
        ))

    for misconception_id in known - served:
        issues.append(ValidationIssue(
            Severity.WARNING, name, misconception_id,
            "below minimum: no visual cue; the review asks for one per "
            "misconception",
        ))

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise SupportError(f"{topic_code}: visual cues cannot be used.\n"
                           + "\n".join(f"  {i}" for i in errors))
    return cues, links, issues


# ──────────────────────────────────────────────────────────────────────
# Parallel examples
# ──────────────────────────────────────────────────────────────────────

PARALLEL_SYSTEM_PROMPT = """\
You write a fresh worked example for a student who has just got something
wrong. Return a single JSON object and nothing else. No prose, no markdown.

{
  "examples": [
    {"misconception_id": "MIS-T01-ADD-AS-MULTIPLY",
     "problem_statement": "A robot starts at any position r and moves forward 2 spaces.",
     "worked_steps": ["changing value r", "fixed action +2", "rule r + 2"],
     "final_answer": "r + 2"}
  ]
}

One example per misconception.

A parallel example is the SAME IDEA IN A DIFFERENT SITUATION. The student has
just failed a question and been shown why. Repeating that question teaches
nothing, and jumping to a harder one teaches less. This is the same step, in a
setting they have not seen, so they can succeed at it.

Rules:

1. Use only the misconception ids listed below, copied EXACTLY.

2. Change the CONTEXT, not the difficulty. A different object, a different
   story, the same mathematical move.

3. Use a different letter from the obvious one where you can. A student who
   has just been confused by n benefits from seeing the same idea with r.

4. worked_steps is a short list, two to four entries, each naming one thing:
   what changes, what stays fixed, what the rule is. They are labels a tutor
   reads out, not sentences.

5. final_answer is the expression or value alone.
"""


def build_parallel_prompt(misconceptions: list[MisconceptionRow]) -> str:
    lines = ["Misconceptions needing a parallel example:"]
    for row in misconceptions:
        lines += ["", f"  {row.misconception_id}  {row.name}",
                  f"    {row.description}"]
    return "\n".join(lines)


def generate_parallel_examples(
    misconceptions: list[MisconceptionRow],
    client: LLMClient,
    topic_code: str,
    topic_id: str,
    *,
    id_service: Optional[IdService] = None,
    strict: bool = True,
) -> tuple[list[ParallelExampleRow], list[ValidationIssue]]:
    """One fresh example per misconception. No join table: it carries the id."""
    name = f"{topic_code} parallel examples"
    issues: list[ValidationIssue] = []
    known = {row.misconception_id for row in misconceptions}
    if id_service is None:
        id_service = IdService(topic_code)

    if not misconceptions:
        raise SupportError(f"{topic_code}: no misconceptions to illustrate")

    payload = client.complete_json(
        PARALLEL_SYSTEM_PROMPT, build_parallel_prompt(misconceptions),
        purpose=f"CG-017 parallel examples for {topic_code}",
    )
    entries = payload.get("examples")

    def drop(where: str, message: str) -> None:
        issues.append(ValidationIssue(
            Severity.WARNING, name, where, f"dropped: {message}"))

    rows: list[ParallelExampleRow] = []
    served: set[str] = set()

    for position, entry in enumerate(entries or [], start=1):
        where = f"examples[{position}]"
        if not isinstance(entry, dict):
            drop(where, "not an object")
            continue

        misconception_id = str(entry.get("misconception_id") or "")
        statement = str(entry.get("problem_statement") or "").strip()
        answer = str(entry.get("final_answer") or "").strip()
        steps = entry.get("worked_steps")

        if misconception_id not in known:
            drop(where, f"misconception_id {misconception_id!r} does not exist")
            continue
        if misconception_id in served:
            drop(where, f"{misconception_id} already has a parallel example")
            continue
        if not statement or not answer:
            drop(where, "problem_statement or final_answer is empty")
            continue
        if not isinstance(steps, list) or len(steps) < 2:
            drop(where, "worked_steps needs at least two entries; an example "
                        "with one step shows no working")
            continue

        try:
            example_id = id_service.parallel_example_id(misconception_id)
        except IdError as exc:
            drop(where, str(exc))
            continue

        served.add(misconception_id)
        rows.append(ParallelExampleRow(
            parallel_example_id=example_id,
            topic_id=topic_id,
            misconception_id=misconception_id,
            problem_statement=statement,
            worked_steps=" | ".join(str(s).strip() for s in steps),
            final_answer=answer,
            active=True,
        ))

    for misconception_id in known - served:
        issues.append(ValidationIssue(
            Severity.WARNING, name, misconception_id,
            "below minimum: no parallel example; the review asks for one per "
            "misconception",
        ))

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise SupportError(f"{topic_code}: parallel examples cannot be used.\n"
                           + "\n".join(f"  {i}" for i in errors))
    return rows, issues


def generate_support(
    misconceptions: list[MisconceptionRow],
    client: LLMClient,
    topic_code: str,
    topic_id: str,
    *,
    id_service: Optional[IdService] = None,
    strict: bool = True,
) -> SupportSet:
    """All five tables for one topic, in three calls."""
    hints, hint_links, hint_issues = generate_hints(
        misconceptions, client, topic_code,
        id_service=id_service, strict=strict)
    cues, cue_links, cue_issues = generate_visual_cues(
        misconceptions, client, topic_code,
        id_service=id_service, strict=strict)
    examples, example_issues = generate_parallel_examples(
        misconceptions, client, topic_code, topic_id,
        id_service=id_service, strict=strict)

    return SupportSet(
        topic_code, hints, hint_links, cues, cue_links, examples,
        hint_issues + cue_issues + example_issues,
    )
