"""
CG-003 -- ID generation service
===============================

Every generated record needs an ID that matches the reference workbook's
naming style, is unique across the database, and is reproducible if we
regenerate the same topic (task spec section 11).

WHERE THE PATTERNS COME FROM
    The reference workbook, not the spec's example table. CG-001 extracted
    them into table_schemas.py as `id_pattern` entries and those are what
    this module implements. Where the two disagree the workbook wins,
    because that is the data the platform actually holds. Two known
    disagreements:

      Scope items   spec says SCOPE-T04-IN-001, workbook has SCOPE-T02-I01
      Error codes   spec says ERR-T04-<DESC>, workbook has both forms

    On error codes: the five unprefixed ones (ERR-ADD-AS-MULTIPLY and
    friends) are all Topic 1, which was authored before the convention
    settled. Every Topic 2 and Topic 3 code carries its topic. Checking
    Question_Error_Map, no error code is shared across topics, so there is
    no "generic error" concept to preserve. New topics get the prefix.

TWO FAMILIES OF ID
    Sequential   Q-T04-001, WE-KS3-T04-01, SCOPE-T04-I01 ...
                 A per-topic counter. Deterministic as long as the caller
                 generates records in a stable order, which the generation
                 pipeline does because it works through the source brief
                 top to bottom.

    Descriptor   ERR-T04-ADD-AS-MULTIPLY, MIS-T04-..., SCF-T04-... ...
                 A pure function of the descriptor, so it is stable across
                 runs regardless of ordering. These are the IDs most likely
                 to survive regeneration unchanged, which is what section
                 11.1 asks for.

DERIVED IDS ARE NEVER COUNTED SEPARATELY
    ANS-T04-001 belongs to Q-T04-001. QU-T04-001-P2 belongs to Q-T04-001.
    WE-T04-01-S1 belongs to WE-KS3-T04-01. Each is derived from its parent
    ID rather than from its own counter, because two counters that are
    meant to agree will eventually disagree.

COLLISIONS
    Every issued ID is recorded. Issuing the same ID twice raises
    IdCollisionError rather than silently overwriting, which is what the
    UNIQUE_ID blocking check in section 12.1 is there to catch. Better to
    fail while generating than to ship a workbook with two Q-T04-003 rows.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional


class IdError(Exception):
    """Base class for ID generation failures."""


class IdCollisionError(IdError):
    """An ID was issued twice."""


class IdFormatError(IdError):
    """An input could not produce a valid ID."""


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

_TOPIC_CODE_RE = re.compile(r"^T\d{2}$")
_QUESTION_SUFFIX_RE = re.compile(r"^Q-T\d{2}-(D?\d+)$")
_WE_SUFFIX_RE = re.compile(r"^WE-KS3-T\d{2}-(\d+)$")
_SCAFFOLD_DESC_RE = re.compile(r"^SCF-T\d{2}-(.+)$")


def slugify(text: str) -> str:
    """Turn a human descriptor into the workbook's ID style.

    'adding as multiplying' -> 'ADDING-AS-MULTIPLYING'

    Uppercase, non-alphanumerics collapsed to single hyphens, trimmed. The
    reference IDs are all uppercase hyphenated words, so this reproduces
    that shape from whatever the authoring stage hands us.
    """
    if text is None:
        raise IdFormatError("descriptor is required")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-").upper()
    if not slug:
        raise IdFormatError(f"descriptor {text!r} produced an empty slug")
    return slug


def abbreviate(slug: str, max_len: int = 3) -> str:
    """Derive a short form for scaffold step IDs.

    The reference workbook's short forms were chosen by a human and follow
    no single rule:

        GENERAL-RULE           -> GEN   first three letters
        WRITE-COMPACT          -> WR    first two
        FRACTIONAL-COEFFICIENT -> FC    initials
        CONTEXT-RULE           -> CTX   consonants
        COUNTER-RULE           -> CTR   consonants, disambiguated from CTX

    No function reproduces all five, so this does not try. It returns a
    consistent, readable short form and the caller may override it when
    the exact reference value matters. Collisions inside a topic are
    resolved by the caller via `scaffold_step_id`.

    Rule: first word, vowels dropped after the first letter, padded back
    from the original if that leaves too little.
    """
    first = slug.split("-")[0]
    if not first:
        raise IdFormatError(f"cannot abbreviate {slug!r}")
    head = first[0]
    tail = [c for c in first[1:] if c not in "AEIOU"]
    short = (head + "".join(tail))[:max_len]
    if len(short) < 2:                      # e.g. "AREA" -> "AR"
        short = first[:max_len]
    return short


# ──────────────────────────────────────────────────────────────────────
# The service
# ──────────────────────────────────────────────────────────────────────

class IdService:
    """Issues IDs for one topic.

    One instance per topic. Counters are per-topic because every pattern
    is scoped by topic code, so a fresh instance for T05 starts from 001
    without knowing anything about T04.

    Pre-seeding (`existing_ids`) supports section 11.1: pass the IDs an
    earlier run produced and this instance will refuse to reissue them,
    so a regeneration cannot quietly reuse an ID for a different concept.
    """

    def __init__(self, topic_code: str, existing_ids: Optional[Iterable[str]] = None):
        topic_code = (topic_code or "").strip().upper()
        if not _TOPIC_CODE_RE.match(topic_code):
            raise IdFormatError(
                f"topic_code must look like T01..T99, got {topic_code!r}"
            )
        self.topic_code = topic_code
        self._issued: set[str] = set(existing_ids or ())
        self._counters: dict[str, int] = {}
        # scaffold_id -> short form, so every step of one scaffold agrees
        self._scaffold_shorts: dict[str, str] = {}

    # -- internals ----------------------------------------------------

    def _next(self, counter: str) -> int:
        self._counters[counter] = self._counters.get(counter, 0) + 1
        return self._counters[counter]

    def _issue(self, new_id: str) -> str:
        if new_id in self._issued:
            raise IdCollisionError(f"ID already issued: {new_id}")
        self._issued.add(new_id)
        return new_id

    @property
    def issued(self) -> set[str]:
        """Every ID handed out so far. Feed into a later run to preserve."""
        return set(self._issued)

    # -- level 0: topic scaffolding -----------------------------------

    def scope_item_id(self, scope_type: str) -> str:
        """SCOPE-T04-I01 (included) / SCOPE-T04-E01 (excluded).

        Included and excluded items count separately, matching the
        workbook where SCOPE-T02-I01 and SCOPE-T02-E01 coexist.
        """
        st = str(scope_type).upper()
        if st.startswith("INCLUD"):
            letter = "I"
        elif st.startswith("EXCLUD"):
            letter = "E"
        else:
            raise IdFormatError(
                f"scope_type must be INCLUDED or EXCLUDED, got {scope_type!r}"
            )
        seq = self._next(f"scope_{letter}")
        return self._issue(f"SCOPE-{self.topic_code}-{letter}{seq:02d}")

    def source_provenance_id(self) -> str:
        """SRC-NABLIX-T04-001."""
        seq = self._next("source")
        return self._issue(f"SRC-NABLIX-{self.topic_code}-{seq:03d}")

    def micro_skill_id(self) -> str:
        """T04.M1 -- note the dot, this pattern is unlike all the others."""
        seq = self._next("micro_skill")
        return self._issue(f"{self.topic_code}.M{seq}")

    # -- level 2: worked examples -------------------------------------

    def worked_example_id(self) -> str:
        """WE-KS3-T04-01. KS3 is the key stage, fixed for this product."""
        seq = self._next("worked_example")
        return self._issue(f"WE-KS3-{self.topic_code}-{seq:02d}")

    def worked_example_step_id(self, worked_example_id: str, step_no: int) -> str:
        """WE-T04-01-S1, derived from its parent worked example.

        Note the KS3 segment is dropped in step IDs. That is the workbook's
        convention, not an oversight on our part.
        """
        m = _WE_SUFFIX_RE.match(worked_example_id.strip())
        if not m:
            raise IdFormatError(
                f"expected a worked example ID like WE-KS3-T04-01, "
                f"got {worked_example_id!r}"
            )
        if step_no < 1:
            raise IdFormatError(f"step_no starts at 1, got {step_no}")
        return self._issue(
            f"WE-{self.topic_code}-{m.group(1)}-S{step_no}"
        )

    # -- level 3: questions -------------------------------------------

    def question_id(self, diagnostic: bool = False) -> str:
        """Q-T04-001, or Q-T04-D01 for diagnostics.

        The two forms have different widths in the reference: three digits
        for practice questions, two for diagnostics. They also count
        independently, so Q-T04-001 and Q-T04-D01 can both exist.
        """
        if diagnostic:
            seq = self._next("question_diagnostic")
            return self._issue(f"Q-{self.topic_code}-D{seq:02d}")
        seq = self._next("question")
        return self._issue(f"Q-{self.topic_code}-{seq:03d}")

    def question_usage_id(self, question_id: str, phase: str) -> str:
        """QU-T04-001-P2, derived from the question and its phase.

        Accepts either the Phase enum value (PHASE_2_GUIDED_LEARNING) or a
        bare number, because the generation stage has the enum but the
        workbook stores the digit.
        """
        suffix = self._question_suffix(question_id)
        return self._issue(
            f"QU-{self.topic_code}-{suffix}-P{self._phase_digit(phase)}"
        )

    def item_family_id(self, descriptor: str) -> str:
        """FAM-T04-CONTEXT-ADD.

        Deliberately NOT put through _issue, unlike every other ID here.

        An item family is a grouping, not a row identity: variants of the
        same question are meant to share one, so asking for the same family
        twice has to return the same ID rather than raise a collision. The
        reference workbook happens to have one question per family because
        no variants have been authored yet, which makes this look like a
        unique ID until the first variant arrives.

        So it is a pure function of the descriptor -- same descriptor, same
        family, on this run or any later one.
        """
        return f"FAM-{self.topic_code}-{slugify(descriptor)}"

    def answer_spec_id(self, question_id: str) -> str:
        """ANS-T04-001, sharing its parent question's number.

        Derived rather than counted so the QUESTION_HAS_ANSWER check in
        section 12.1 cannot fail because two counters drifted apart.
        """
        return self._issue(
            f"ANS-{self.topic_code}-{self._question_suffix(question_id)}"
        )

    def _question_suffix(self, question_id: str) -> str:
        m = _QUESTION_SUFFIX_RE.match((question_id or "").strip())
        if not m:
            raise IdFormatError(
                f"expected a question ID like Q-T04-001 or Q-T04-D01, "
                f"got {question_id!r}"
            )
        return m.group(1)

    @staticmethod
    def _phase_digit(phase: str) -> int:
        """PHASE_2_GUIDED_LEARNING -> 2, 'P2' -> 2, 2 -> 2."""
        s = str(phase).upper()
        m = re.search(r"(\d)", s)
        if not m:
            raise IdFormatError(f"cannot read a phase number from {phase!r}")
        digit = int(m.group(1))
        if digit not in (0, 2, 3):
            raise IdFormatError(
                f"phase must be 0, 2 or 3 (this product has no phase 1), "
                f"got {digit}"
            )
        return digit

    # -- level 5: diagnosis and support -------------------------------

    def error_code(self, descriptor: str) -> str:
        """ERR-T04-ADD-AS-MULTIPLY."""
        return self._issue(f"ERR-{self.topic_code}-{slugify(descriptor)}")

    def misconception_id(self, descriptor: str) -> str:
        """MIS-T04-ADD-AS-MULTIPLY."""
        return self._issue(f"MIS-{self.topic_code}-{slugify(descriptor)}")

    def hint_id(self, descriptor: str, level: int) -> str:
        """HINT-T04-GENERAL-L1. Levels are 1..3 (section 9 hint ladder)."""
        if level not in (1, 2, 3):
            raise IdFormatError(f"hint level must be 1, 2 or 3, got {level}")
        return self._issue(
            f"HINT-{self.topic_code}-{slugify(descriptor)}-L{level}"
        )

    def visual_cue_id(self, descriptor: str) -> str:
        """VC-T04-ADD-NOT-MULTIPLY."""
        return self._issue(f"VC-{self.topic_code}-{slugify(descriptor)}")

    def parallel_example_id(self, descriptor: str) -> str:
        """PAR-T04-ADD-01. Sequence counts per descriptor, so one
        descriptor can carry several parallel examples."""
        slug = slugify(descriptor)
        seq = self._next(f"parallel_{slug}")
        return self._issue(
            f"PAR-{self.topic_code}-{slug}-{seq:02d}"
        )

    def scaffold_id(self, descriptor: str) -> str:
        """SCF-T04-GENERAL-RULE."""
        return self._issue(f"SCF-{self.topic_code}-{slugify(descriptor)}")

    def scaffold_step_id(
        self,
        scaffold_id: str,
        stage_no: int,
        short: Optional[str] = None,
    ) -> str:
        """SCF-T04-GEN-S1, using a short form of the scaffold descriptor.

        `short` may be given explicitly when the exact reference value
        matters. Otherwise one is derived and remembered, so every step of
        a scaffold shares it, and a suffix is added if two scaffolds in the
        same topic would otherwise abbreviate identically -- which is what
        happened in the reference between CONTEXT-RULE and COUNTER-RULE.
        """
        m = _SCAFFOLD_DESC_RE.match((scaffold_id or "").strip())
        if not m:
            raise IdFormatError(
                f"expected a scaffold ID like SCF-T04-GENERAL-RULE, "
                f"got {scaffold_id!r}"
            )
        if stage_no < 1:
            raise IdFormatError(f"stage_no starts at 1, got {stage_no}")

        if scaffold_id not in self._scaffold_shorts:
            candidate = slugify(short) if short else abbreviate(m.group(1))
            taken = set(self._scaffold_shorts.values())
            if candidate in taken:
                n = 2
                while f"{candidate}{n}" in taken:
                    n += 1
                candidate = f"{candidate}{n}"
            self._scaffold_shorts[scaffold_id] = candidate

        return self._issue(
            f"SCF-{self.topic_code}-{self._scaffold_shorts[scaffold_id]}-S{stage_no}"
        )
