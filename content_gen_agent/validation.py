"""CG-007: source validation and Source_Provenance records.

Two jobs, both about trusting the input before anything is generated from it.

Validation
----------

The mapper (CG-006) raises on the first thing it cannot map. That is right for
a pipeline but unhelpful for a person: fix one heading, rerun, discover the
next. `validate_document` instead checks everything and returns every problem
at once, so one pass tells you the whole story.

Issues are graded. An ERROR means the document cannot produce a usable brief --
no topic ID, no Learning Goal, an empty Included list. A WARNING means it will
map but something looks off, such as a scope list with a single entry. Only
errors stop the pipeline; `require_valid` raises on those and ignores warnings.

Source_Provenance
-----------------

One row per topic, recording where the content came from and what may be done
with it. The reference workbook's rows for Topics 2 and 3 set the pattern, and
this module reproduces it exactly:

    source_provenance_id   SRC-NABLIX-T02-001      (from IdService)
    source_type            NABLIX_AUTHORED
    source_name            the document title, then its first preamble line --
                           "Topic 2 - Algebraic Notation" + "Final Content Pack"
    source_item_id         the topic ID, ALG-ORI-02
    license_name           OWNED_ORIGINAL_CONTENT
    license_url            empty
    adapted                False   -- content is used as authored
    direct_text_copied     True    -- approved wording is reproduced verbatim
    review_status          APPROVED

Topic 1's reference row does not follow this: it is named "Topic 1 Guided
Learning Pilot", carries no source_item_id, and is PENDING_FINAL_REVIEW rather
than APPROVED. Its document is the odd one out in other ways too -- no
preamble, fewer Section B subsections, and a topic_id of ALG-KS3-01 in the
reference against ALG-ORI-01 in the document itself. Topic 1's row looks like
it was written by hand before the convention settled, so the convention is
followed here for all six and the divergence is reported by CG-008 rather than
special-cased.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from brief_mapper import items_of, prose_of
from docx_parser import ParsedTopicDocument
from id_service import IdService
from models import (
    LicenseName,
    NormalizedTopicBrief,
    ReviewStatus,
    SourceProvenanceRow,
    SourceType,
)

# Headings every document must carry, and the field each one feeds.
REQUIRED_PROSE = {
    "Learning Goal": "learning_goal",
    "Core Message": "core_message",
}
REQUIRED_SCOPE = {
    "Included": "included_scope",
    "Excluded": "excluded_scope",
    "Misconceptions to Prevent": "misconceptions_to_prevent",
}

# A scope list shorter than this maps fine but is probably an authoring slip.
MIN_SCOPE_ITEMS = 2

# Provenance defaults, matching the reference rows for Topics 2 and 3.
DEFAULT_ADAPTED = False
DEFAULT_DIRECT_TEXT_COPIED = True
DEFAULT_REVIEW_STATUS = ReviewStatus.APPROVED


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class ValidationIssue:
    """One problem found in a source document."""

    severity: Severity
    source_file_name: str
    field: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.severity is Severity.ERROR

    def __str__(self) -> str:
        return (
            f"[{self.severity.value}] {self.source_file_name} "
            f"({self.field}): {self.message}"
        )


class SourceValidationError(Exception):
    """One or more documents failed validation.

    Carries the issues so a caller can report them, rather than forcing it to
    parse the message string.
    """

    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        errors = [i for i in issues if i.is_error]
        super().__init__(
            f"{len(errors)} validation error(s):\n"
            + "\n".join(f"  {i}" for i in errors)
        )


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────

def validate_document(doc: ParsedTopicDocument) -> list[ValidationIssue]:
    """Every problem with one parsed document, errors and warnings together."""
    name = doc.source_file_name
    issues: list[ValidationIssue] = []

    def error(field: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, name, field, message))

    def warn(field: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.WARNING, name, field, message))

    # -- identity ------------------------------------------------------
    if not doc.topic_id:
        error("topic_id", "no 'Topic ID:' line found")
    if doc.topic_number is None:
        error("sequence_no", "could not determine the topic number from the title")
    if not doc.topic_title:
        error("topic_title", "no title found")

    # -- structure -----------------------------------------------------
    concept = doc.concept_sheet
    if concept is None:
        error("concept_sheet", "no 'A. Internal Concept Sheet' section")
        # Nothing below can be checked without it.
        return issues

    if doc.designer_handoff is None:
        warn("designer_handoff", "no 'B. Designer Handoff' section")

    # -- required content ----------------------------------------------
    for heading, field in REQUIRED_PROSE.items():
        section = concept.subsection(heading)
        if section is None:
            error(field, f"'{heading}' heading is missing")
        elif not prose_of(section).strip():
            error(field, f"'{heading}' is present but empty")

    for heading, field in REQUIRED_SCOPE.items():
        section = concept.subsection(heading)
        if section is None:
            error(field, f"'{heading}' heading is missing")
            continue
        entries = items_of(section)
        if not entries:
            error(field, f"'{heading}' is present but empty")
        elif len(entries) < MIN_SCOPE_ITEMS:
            warn(field, f"'{heading}' has only {len(entries)} entry")

    return issues


def validate_documents(docs: list[ParsedTopicDocument]) -> list[ValidationIssue]:
    """Validate a batch, keeping every document's issues."""
    issues: list[ValidationIssue] = []
    for doc in docs:
        issues.extend(validate_document(doc))
    return issues


def errors_only(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if i.is_error]


def require_valid(docs: ParsedTopicDocument | list[ParsedTopicDocument]) -> None:
    """Raise SourceValidationError if any document has an error.

    Warnings never stop the pipeline; they are for a person to look at.
    """
    if isinstance(docs, ParsedTopicDocument):
        docs = [docs]
    issues = validate_documents(docs)
    if errors_only(issues):
        raise SourceValidationError(issues)


# ──────────────────────────────────────────────────────────────────────
# Source_Provenance
# ──────────────────────────────────────────────────────────────────────

def source_name_for(doc: ParsedTopicDocument) -> str:
    """The document's own name for itself.

    The reference rows are the title followed by the document's first preamble
    line: "Topic 2 - Algebraic Notation" plus "Final Content Pack". Topic 1 has
    no preamble, so its title is used alone.
    """
    parts = [doc.title.strip()]
    if doc.preamble:
        first = doc.preamble[0].text.strip()
        if first:
            parts.append(first)
    return " ".join(p for p in parts if p)


def build_source_provenance(
    doc: ParsedTopicDocument,
    id_service: Optional[IdService] = None,
    review_status: ReviewStatus = DEFAULT_REVIEW_STATUS,
) -> SourceProvenanceRow:
    """The Source_Provenance row for one topic document.

    Pass an IdService to share a run's id sequence and collision checking;
    without one, a fresh service is created for this topic alone.
    """
    if doc.topic_number is None:
        raise SourceValidationError([
            ValidationIssue(
                Severity.ERROR, doc.source_file_name, "sequence_no",
                "cannot build provenance without a topic number",
            )
        ])

    topic_code = f"T{doc.topic_number:02d}"
    if id_service is None:
        id_service = IdService(topic_code)

    return SourceProvenanceRow(
        source_provenance_id=id_service.source_provenance_id(),
        source_type=SourceType.NABLIX_AUTHORED,
        source_name=source_name_for(doc),
        source_item_id=doc.topic_id,
        license_name=LicenseName.OWNED_ORIGINAL_CONTENT,
        license_url=None,
        adapted=DEFAULT_ADAPTED,
        direct_text_copied=DEFAULT_DIRECT_TEXT_COPIED,
        review_status=review_status,
    )


def build_all_source_provenance(
    docs: list[ParsedTopicDocument],
) -> list[SourceProvenanceRow]:
    """One provenance row per document, each with its own id sequence.

    Ids are scoped per topic (SRC-NABLIX-T02-001), so each document gets a
    fresh IdService rather than sharing one across the batch.
    """
    return [build_source_provenance(d) for d in docs]


if __name__ == "__main__":
    from docx_parser import parse_all_topic_documents

    docs = parse_all_topic_documents()

    issues = validate_documents(docs)
    print(f"validation: {len(errors_only(issues))} error(s), "
          f"{len(issues) - len(errors_only(issues))} warning(s)")
    for issue in issues:
        print(f"  {issue}")

    print("\nSource_Provenance:")
    for row in build_all_source_provenance(docs):
        print(f"  {row.source_provenance_id}  {row.source_item_id}  "
              f"{row.review_status.value:22} {row.source_name}")
