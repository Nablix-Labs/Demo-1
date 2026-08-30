"""CG-009: generate Topics, Topic_Scope and Source_Provenance rows.

Built the way the roadmap specifies: an LLM prompt does the topic metadata
extraction and scope mapping, rather than the fields being read straight off
the document.

Why the deterministic reader is still here
------------------------------------------

CG-008 established that these particular fields can be read from the documents
exactly -- all 27 reference scope items matched byte-for-byte, as did every
identity field. That result is not thrown away. It is reused as the baseline
the model's output is checked against, which addresses the one real hazard of
generating this data with a model.

The hazard is `scope_item_id`. Ids are positional: SCOPE-T02-I03 means "the
third included item of Topic 2". If a model drops an item, merges two bullets
or reorders them, every later id silently shifts and anything referring to them
points at different content. So model output is compared against the parsed
document before any id is issued, and by default a mismatch stops the run
rather than being written out.

That keeps the roadmap's design -- the model is the generator -- while making
the failure mode loud instead of silent.

Checks applied to model output
------------------------------

    identity      topic_id, title and sequence must agree with the document
    scope         every item must appear in the document, in the same order,
                  with the same count
    prose         learning_goal and core_message must be non-empty

`strict=True` (the default) raises on any of these. `strict=False` records them
on the package as issues and continues, which is useful when reviewing a new
document by hand.

Prose is treated differently on purpose. The reference workbook's learning_goal
is an editorial rewrite of the document -- for Topic 2 it drops "Students
should ", for Topic 3 it condenses a bulleted list -- so the model is asked to
produce that polished form and is not required to match the document verbatim.
It is still checked for emptiness, and CG-008 compares the result against the
reference.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from brief_mapper import to_normalized_brief
from docx_parser import ParsedTopicDocument, parse_all_topic_documents
from id_service import IdService
from llm_client import LLMClient
from models import (
    KSStage,
    NormalizedTopicBrief,
    ScopeType,
    SourceProvenanceRow,
    TopicRow,
    TopicScopeRow,
    TopicStatus,
)
from validation import (
    Severity,
    ValidationIssue,
    build_source_provenance,
    validate_document,
)

DEFAULT_VERSION = "1.0"
DEFAULT_STATUS = TopicStatus.ACTIVE

# Scope fields, and the document heading each is checked against.
SCOPE_FIELDS = (
    ("included_scope", "Included"),
    ("excluded_scope", "Excluded"),
    ("misconceptions_to_prevent", "Misconceptions to Prevent"),
)


class GenerationError(Exception):
    """The model's output could not be trusted for this topic."""


# ──────────────────────────────────────────────────────────────────────
# The prompt
# ──────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You extract structured curriculum data from approved Nablix topic documents.

You are given the Internal Concept Sheet of one topic document. Return a single
JSON object and nothing else. No prose, no explanation, no markdown fences.

Return exactly these keys:

  topic_id                   string, e.g. "ALG-ORI-02". Copy it from the
                             document's "Topic ID:" line.
  topic_title                string, the topic's title without the
                             "Topic N -" prefix.
  ks_stage                   string, "KS3" or "KS4", from the Audience line.
  sequence_no                integer, the N in "Topic N".
  learning_goal              string, one sentence.
  core_message               string, one sentence.
  included_scope             array of strings.
  excluded_scope             array of strings.
  misconceptions_to_prevent  array of strings.

Rules, in order of importance:

1. Use only what the document says. Never add an item, a topic or a
   misconception that is not there. Never fill a gap with your own knowledge of
   algebra.
2. The three scope arrays must reproduce the document's bullet lists exactly:
   the same items, the same wording, the same order, the same number of
   entries. Do not merge two bullets, split one, reorder them, fix spelling or
   change punctuation. These become database identifiers and are checked
   against the document.
3. learning_goal and core_message are the exception, and they are NOT the same
   shape as each other. Match these approved examples exactly in form.

   learning_goal always begins with the word "Understand". It never names the
   student. One sentence.

     Understand that a letter can represent a changing number so one rule can
     describe many cases.

     Understand that algebraic notation is an agreed, shorter way of writing
     familiar mathematical operations.

     Understand that a variable can represent different possible values while
     a constant remains fixed within a rule or situation.

   core_message is a plain statement of the idea itself. It never begins with
   "Understand", never names the student, and never says "understand". One or
   two short sentences.

     A letter can represent a changing quantity in a general rule.

     Algebraic notation makes mathematical ideas shorter without changing
     their meaning.

     A variable can change between cases. A constant stays fixed within the
     rule or situation.

   Do not write "Students understand that", "The student understands that",
   or "Students should understand that" in either field. Keep the document's
   meaning and add nothing it does not say. Where the document gives the goal
   as a lead-in plus bullets, combine them into one sentence.
4. Copy topic_id exactly as written, including its prefix.
"""


def build_user_prompt(doc: ParsedTopicDocument) -> str:
    """Render one document's Internal Concept Sheet for the model.

    Only Section A is sent. Section B is video production material -- scenes,
    narration, colour guides -- which none of these fields come from, and
    including it would be a large distraction in the prompt.
    """
    concept = doc.concept_sheet
    if concept is None:
        raise GenerationError(
            f"{doc.source_file_name}: no Internal Concept Sheet to send"
        )

    lines = [f"Document title: {doc.title}", ""]

    if concept.paragraphs:
        lines.append("Document metadata:")
        lines.extend(f"  {p.text}" for p in concept.paragraphs)
        lines.append("")

    lines.append("A. Internal Concept Sheet")
    for heading, section in concept.subsections.items():
        lines.append("")
        lines.append(f"## {heading}")
        for para in section.paragraphs:
            lines.append(f"- {para.text}" if para.is_list_item else para.text)

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Checking the model
# ──────────────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def _check_scope(
    name: str,
    field_name: str,
    expected: list[str],
    produced: list[str],
) -> list[ValidationIssue]:
    """Compare one scope list against the document's own bullets."""
    issues: list[ValidationIssue] = []

    def error(message: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, name, field_name, message))

    if len(produced) != len(expected):
        error(
            f"model returned {len(produced)} items, the document has "
            f"{len(expected)}. Scope ids are positional, so this would shift them."
        )

    wanted = [_normalise(e) for e in expected]
    got = [_normalise(p) for p in produced]

    for item in got:
        if item not in wanted:
            error(f"model produced an item that is not in the document: {item[:70]!r}")

    for index, (want, have) in enumerate(zip(wanted, got), start=1):
        if want != have:
            error(
                f"item {index} does not match the document. "
                f"document: {want[:50]!r}, model: {have[:50]!r}"
            )

    return issues


def check_against_document(
    doc: ParsedTopicDocument,
    payload: dict,
    brief: Optional[NormalizedTopicBrief] = None,
) -> list[ValidationIssue]:
    """Every disagreement between the model's output and the document."""
    name = doc.source_file_name
    brief = brief or to_normalized_brief(doc)
    issues: list[ValidationIssue] = []

    def error(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, name, field_name, message))

    # -- identity ------------------------------------------------------
    if _normalise(payload.get("topic_id", "")) != _normalise(brief.topic_id):
        error("topic_id",
              f"model said {payload.get('topic_id')!r}, "
              f"the document says {brief.topic_id!r}")

    if _normalise(payload.get("topic_title", "")) != _normalise(brief.topic_title):
        error("topic_title",
              f"model said {payload.get('topic_title')!r}, "
              f"the document says {brief.topic_title!r}")

    try:
        if int(payload.get("sequence_no")) != brief.sequence_no:
            error("sequence_no",
                  f"model said {payload.get('sequence_no')!r}, "
                  f"the document says {brief.sequence_no}")
    except (TypeError, ValueError):
        error("sequence_no", f"model returned {payload.get('sequence_no')!r}, "
                             "which is not a whole number")

    if _normalise(payload.get("ks_stage", "")) != _normalise(brief.ks_stage.value):
        error("ks_stage",
              f"model said {payload.get('ks_stage')!r}, "
              f"the document says {brief.ks_stage.value!r}")

    # -- scope, where ids are at stake ---------------------------------
    for field_name, _heading in SCOPE_FIELDS:
        produced = payload.get(field_name)
        if not isinstance(produced, list):
            error(field_name,
                  f"model returned {type(produced).__name__}, expected a list")
            continue
        issues.extend(
            _check_scope(name, field_name, getattr(brief, field_name),
                         [str(p) for p in produced])
        )

    # -- prose, allowed to be rewritten but not to be empty -------------
    for field_name in ("learning_goal", "core_message"):
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            error(field_name, "model returned nothing usable")

    issues.extend(_check_house_style(name, payload))

    return issues


# The approved wording never names the student. On the first live run the
# model produced "Students understand that ..." for five of six topics,
# because the prompt said to drop "Students should" and it dropped only the
# "should". The prompt now carries worked examples; this catches drift back.
_NAMES_THE_STUDENT = re.compile(
    r"^\s*(the\s+)?students?\s+(should\s+)?understands?\b", re.IGNORECASE
)


def _check_house_style(name: str, payload: dict) -> list[ValidationIssue]:
    """Warn when the prose drifts from the approved form.

    Warnings, not errors. The reference workbook is consistent across the three
    topics it covers, but it is three topics; a future one may legitimately
    read differently and that is an editorial call, not a fault the pipeline
    should refuse to proceed on.
    """
    issues: list[ValidationIssue] = []

    def warn(field_name: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.WARNING, name, field_name, message))

    goal = str(payload.get("learning_goal") or "")
    message = str(payload.get("core_message") or "")

    if goal.strip() and not goal.strip().lower().startswith("understand"):
        warn("learning_goal",
             f"does not begin with 'Understand': {goal[:60]!r}")

    for field_name, value in (("learning_goal", goal), ("core_message", message)):
        if _NAMES_THE_STUDENT.match(value):
            warn(field_name,
                 f"names the student; the approved form does not: {value[:60]!r}")

    if message.strip().lower().startswith("understand"):
        warn("core_message",
             "reads like a learning goal; it should state the idea itself")

    return issues


# ──────────────────────────────────────────────────────────────────────
# The generated package
# ──────────────────────────────────────────────────────────────────────

@dataclass
class TopicPackage:
    """Everything CG-009 produces for one topic."""

    topic: TopicRow
    scope_items: list[TopicScopeRow]
    source_provenance: SourceProvenanceRow
    brief: NormalizedTopicBrief
    issues: list[ValidationIssue] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_error]

    @property
    def is_clean(self) -> bool:
        return not self.errors

    def to_rows(self) -> dict[str, list[dict]]:
        """The package as sheet-name -> list of row dicts, ready for the workbook."""
        return {
            "Topics": [json.loads(self.topic.model_dump_json())],
            "Topic_Scope": [json.loads(r.model_dump_json()) for r in self.scope_items],
            "Source_Provenance": [
                json.loads(self.source_provenance.model_dump_json())
            ],
        }


def generate_topic_package(
    doc: ParsedTopicDocument,
    client: LLMClient,
    *,
    strict: bool = True,
    version: str = DEFAULT_VERSION,
    today: Optional[str] = None,
    id_service: Optional[IdService] = None,
) -> TopicPackage:
    """Generate one topic's rows, checking the model against the document."""
    name = doc.source_file_name
    today = today or date.today().isoformat()

    document_issues = validate_document(doc)
    if [i for i in document_issues if i.is_error]:
        raise GenerationError(
            f"{name}: the document itself failed validation; fix that before "
            "generating.\n" + "\n".join(f"  {i}" for i in document_issues if i.is_error)
        )

    brief = to_normalized_brief(doc)

    payload = client.complete_json(
        SYSTEM_PROMPT,
        build_user_prompt(doc),
        purpose=f"CG-009 topic metadata for {name}",
    )

    issues = list(document_issues)
    issues.extend(check_against_document(doc, payload, brief))

    errors = [i for i in issues if i.is_error]
    if errors and strict:
        raise GenerationError(
            f"{name}: the model's output disagrees with the document.\n"
            + "\n".join(f"  {i}" for i in errors)
        )

    # Identity comes from the document even when strict is off. If the model
    # got these wrong the errors above already say so, and writing a wrong
    # topic_id would corrupt every table that references it.
    topic_code = brief.topic_code
    if id_service is None:
        id_service = IdService(topic_code)

    topic = TopicRow(
        topic_id=brief.topic_id,
        topic_code=topic_code,
        topic_title=brief.topic_title,
        ks_stage=KSStage(brief.ks_stage.value),
        sequence_no=brief.sequence_no,
        learning_goal=str(payload.get("learning_goal") or brief.learning_goal).strip(),
        core_message=str(payload.get("core_message") or brief.core_message).strip(),
        status=DEFAULT_STATUS,
        version=version,
        created_at=today,
        updated_at=today,
    )

    scope_items: list[TopicScopeRow] = []
    for scope_type, field_name in (
        (ScopeType.INCLUDED, "included_scope"),
        (ScopeType.EXCLUDED, "excluded_scope"),
    ):
        produced = payload.get(field_name)
        # Fall back to the document when the model's list was rejected, so a
        # non-strict run still produces usable, correctly ordered ids.
        if not isinstance(produced, list) or len(produced) != len(
            getattr(brief, field_name)
        ):
            produced = getattr(brief, field_name)
        for text in produced:
            scope_items.append(
                TopicScopeRow(
                    scope_item_id=id_service.scope_item_id(scope_type.value),
                    topic_id=brief.topic_id,
                    scope_type=scope_type,
                    item_text=str(text).strip(),
                    active=True,
                )
            )

    return TopicPackage(
        topic=topic,
        scope_items=scope_items,
        source_provenance=build_source_provenance(doc, id_service=id_service),
        brief=brief,
        issues=issues,
        raw_response=payload,
    )


def generate_all(
    client: LLMClient,
    docs: Optional[list[ParsedTopicDocument]] = None,
    *,
    strict: bool = True,
    **kwargs,
) -> list[TopicPackage]:
    """One package per topic document, each with its own id sequence."""
    docs = docs if docs is not None else parse_all_topic_documents()
    return [generate_topic_package(d, client, strict=strict, **kwargs) for d in docs]


if __name__ == "__main__":
    import sys

    from llm_client import default_client, is_configured

    if not is_configured():
        print("No OpenAI API key found. Set OPENAI_API_KEY in your .env file.")
        sys.exit(1)

    for package in generate_all(default_client()):
        topic = package.topic
        print(f"\n{topic.topic_code}  {topic.topic_id}  {topic.topic_title}")
        print(f"  learning_goal : {topic.learning_goal[:88]}")
        print(f"  core_message  : {topic.core_message[:88]}")
        print(f"  scope items   : {len(package.scope_items)}")
        print(f"  provenance    : {package.source_provenance.source_provenance_id}")
        print(f"  issues        : {len(package.issues)}")
        for issue in package.issues:
            print(f"    {issue}")
