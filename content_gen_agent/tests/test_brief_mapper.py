"""CG-006 tests.

The exit condition is "output matches Pydantic schema for all 6 topics", which
`map_all()` proves by construction -- NormalizedTopicBrief validates on
instantiation, so a bad mapping raises rather than returning something wrong.
That makes the interesting tests the ones either side of it: the flattening
helpers on their own, and the failure cases where a document is missing
something the brief requires.

Failure cases use hand-built Section objects rather than damaged .docx files,
so they describe the rule being tested instead of hiding it inside a fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brief_mapper import (                      # noqa: E402
    BriefMappingError,
    items_of,
    map_all,
    metadata_of,
    prose_of,
    storyboard_notes_of,
    to_normalized_brief,
)
from docx_parser import Para, ParsedTopicDocument, Section  # noqa: E402
from models import KSStage, NormalizedTopicBrief            # noqa: E402
from sources import find_topic_documents                    # noqa: E402

TOPIC_DOCS = find_topic_documents()
needs_docs = pytest.mark.skipif(not TOPIC_DOCS, reason="topic documents not available")


@pytest.fixture(scope="module")
def briefs():
    if not TOPIC_DOCS:
        pytest.skip("topic documents not available")
    return map_all()


# ──────────────────────────────────────────────────────────────────────
# Flattening helpers
# ──────────────────────────────────────────────────────────────────────

def test_prose_of_a_single_paragraph_is_that_paragraph():
    sec = Section("Core Message", 2, paragraphs=[Para("One clear sentence.")])
    assert prose_of(sec) == "One clear sentence."


def test_prose_of_joins_multiple_plain_paragraphs():
    sec = Section("Mindset Shift", 2, paragraphs=[
        Para("Before: confusing."), Para("After: clear."),
    ])
    assert prose_of(sec) == "Before: confusing. After: clear."


def test_prose_of_reads_a_lead_in_plus_bullets_as_one_sentence():
    """Topics 3, 4, 5 and 6 write the learning goal this way."""
    sec = Section("Learning Goal", 2, paragraphs=[
        Para("Students should understand that:"),
        Para("a variable can change.", is_list_item=True),
        Para("a constant stays fixed.", is_list_item=True),
    ])
    assert prose_of(sec) == (
        "Students should understand that: a variable can change; a constant stays fixed"
    )


def test_prose_of_bullets_with_no_lead_in():
    sec = Section("Learning Goal", 2, paragraphs=[
        Para("first thing.", is_list_item=True), Para("second thing.", is_list_item=True),
    ])
    assert prose_of(sec) == "first thing; second thing"


def test_prose_of_a_missing_section_is_empty():
    assert prose_of(None) == ""


def test_items_of_keeps_unmarked_lines():
    """Topic 6 has Golden Rules written as plain paragraphs; keep them."""
    sec = Section("Part 2 — Golden Rules", 2, paragraphs=[
        Para("marked rule", is_list_item=True),
        Para("unmarked rule", is_list_item=False),
    ])
    assert items_of(sec) == ["marked rule", "unmarked rule"]


def test_items_of_a_missing_section_is_empty():
    assert items_of(None) == []


def test_metadata_of_reads_key_value_lines():
    sec = Section("A. Internal Concept Sheet", 1, paragraphs=[
        Para("Topic ID: ALG-ORI-01"),
        Para("Audience: KS3 students, ages 11-14"),
        Para("This line is not metadata and should be ignored"),
    ])
    meta = metadata_of(sec)
    assert meta["topic id"] == "ALG-ORI-01"
    assert meta["audience"] == "KS3 students, ages 11-14"
    assert len(meta) == 2


def test_storyboard_notes_of_a_missing_section_is_empty():
    assert storyboard_notes_of(None) == ""
    assert storyboard_notes_of(Section("B. Designer Handoff", 1)) == ""


def test_storyboard_notes_include_scene_headings_and_table_narration():
    scene = Section("Scene 1 — Why letters?", 3,
                    paragraphs=[Para("Duration: 8 seconds")],
                    tables=[[["Visual action", "Narration"],
                             ["Show cards", "Narration: \"Why letters?\""]]])
    part3 = Section("Part 3 — Storyboard and Script", 2,
                    subsections={scene.heading: scene})
    handoff = Section("B. Designer Handoff", 1, subsections={part3.heading: part3})

    notes = storyboard_notes_of(handoff)
    assert "Scene 1 — Why letters?" in notes
    assert "Duration: 8 seconds" in notes
    assert "Show cards | Narration:" in notes


# ──────────────────────────────────────────────────────────────────────
# Failure cases
# ──────────────────────────────────────────────────────────────────────

def _concept_sheet(**overrides) -> Section:
    """A minimally complete Section A, so tests can remove one piece at a time."""
    subs = {
        "Learning Goal": Section("Learning Goal", 2, paragraphs=[Para("A goal.")]),
        "Core Message": Section("Core Message", 2, paragraphs=[Para("A message.")]),
        "Included": Section("Included", 2, paragraphs=[Para("in", is_list_item=True)]),
        "Excluded": Section("Excluded", 2, paragraphs=[Para("out", is_list_item=True)]),
        "Misconceptions to Prevent": Section(
            "Misconceptions to Prevent", 2, paragraphs=[Para("wrong", is_list_item=True)]
        ),
    }
    subs.update(overrides)
    subs = {k: v for k, v in subs.items() if v is not None}
    return Section("A. Internal Concept Sheet", 1,
                   paragraphs=[Para("Topic ID: ALG-ORI-09"),
                               Para("Audience: KS3 students, ages 11-14")],
                   subsections=subs)


def _doc(concept: Section | None, title="Topic 9 — A Test Topic",
         topic_id="ALG-ORI-09") -> ParsedTopicDocument:
    sections = {concept.heading: concept} if concept is not None else {}
    return ParsedTopicDocument(Path("Topic_9_Formatted.docx"), title, topic_id,
                               sections=sections)


def test_a_complete_minimal_document_maps():
    brief = to_normalized_brief(_doc(_concept_sheet()))
    assert isinstance(brief, NormalizedTopicBrief)
    assert brief.topic_code == "T09"
    assert brief.golden_rules == []
    assert brief.storyboard_notes == ""


def test_missing_concept_sheet_is_reported():
    with pytest.raises(BriefMappingError, match="Internal Concept Sheet"):
        to_normalized_brief(_doc(None))


@pytest.mark.parametrize("heading", ["Learning Goal", "Core Message"])
def test_missing_prose_section_is_reported(heading):
    with pytest.raises(BriefMappingError, match=heading):
        to_normalized_brief(_doc(_concept_sheet(**{heading: None})))


@pytest.mark.parametrize("heading", ["Included", "Excluded", "Misconceptions to Prevent"])
def test_missing_scope_section_is_reported(heading):
    with pytest.raises(BriefMappingError, match=heading):
        to_normalized_brief(_doc(_concept_sheet(**{heading: None})))


def test_an_empty_section_is_reported_like_a_missing_one():
    empty = Section("Core Message", 2, paragraphs=[])
    with pytest.raises(BriefMappingError, match="Core Message"):
        to_normalized_brief(_doc(_concept_sheet(**{"Core Message": empty})))


def test_missing_topic_number_is_reported():
    doc = _doc(_concept_sheet(), title="An Untitled Topic", topic_id=None)
    doc.sections["A. Internal Concept Sheet"].paragraphs = []
    with pytest.raises(BriefMappingError, match="topic ID"):
        to_normalized_brief(doc)


def test_the_error_names_the_document():
    """With six documents, an error that does not say which one is unhelpful."""
    with pytest.raises(BriefMappingError, match="Topic_9_Formatted.docx"):
        to_normalized_brief(_doc(_concept_sheet(**{"Included": None})))


def test_topic_id_falls_back_to_the_metadata_line():
    doc = _doc(_concept_sheet(), topic_id=None)
    assert to_normalized_brief(doc).topic_id == "ALG-ORI-09"


# ──────────────────────────────────────────────────────────────────────
# The exit condition: all six real documents
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_all_six_map_to_a_valid_brief(briefs):
    """CG-006 exit condition. NormalizedTopicBrief validates on construction."""
    assert len(briefs) == 6
    assert all(isinstance(b, NormalizedTopicBrief) for b in briefs)


@needs_docs
def test_identity_fields_are_right_for_every_topic(briefs):
    for i, brief in enumerate(briefs, start=1):
        assert brief.sequence_no == i
        assert brief.topic_code == f"T{i:02d}"
        assert brief.topic_id == f"ALG-ORI-{i:02d}"
        assert brief.source_file_name == f"Topic_{i}_Formatted.docx"
        assert brief.ks_stage is KSStage.KS3


@needs_docs
def test_titles_are_clean(briefs):
    expected = [
        "What Is Algebra?",
        "Algebraic Notation",
        "Variables and Constants",
        "Expressions",
        "Terms, Coefficients and Factors",
        "Substitution",
    ]
    assert [b.topic_title for b in briefs] == expected


@needs_docs
def test_no_mandatory_field_is_empty(briefs):
    for brief in briefs:
        assert brief.learning_goal.strip(), brief.source_file_name
        assert brief.core_message.strip(), brief.source_file_name
        for field in ("included_scope", "excluded_scope", "misconceptions_to_prevent"):
            entries = getattr(brief, field)
            assert entries, f"{brief.source_file_name}: {field} empty"
            assert all(e.strip() for e in entries), f"{brief.source_file_name}: {field}"


@needs_docs
def test_optional_designer_handoff_fields_are_populated(briefs):
    """Optional in the model, but present in all six documents in practice."""
    for brief in briefs:
        assert len(brief.golden_rules) >= 5, brief.source_file_name
        assert len(brief.storyboard_notes) > 1000, brief.source_file_name
        assert "Scene 1" in brief.storyboard_notes, brief.source_file_name


@needs_docs
def test_scope_lists_do_not_leak_headings_or_duplicates(briefs):
    for brief in briefs:
        for field in ("included_scope", "excluded_scope", "misconceptions_to_prevent"):
            entries = getattr(brief, field)
            assert len(entries) == len(set(entries)), f"{brief.source_file_name}: {field}"
            assert not any(e.endswith(":") for e in entries), brief.source_file_name


@needs_docs
def test_briefs_round_trip_through_json(briefs):
    """The brief is a handoff to the next module, so it has to serialise."""
    for brief in briefs:
        restored = NormalizedTopicBrief.model_validate_json(brief.model_dump_json())
        assert restored == brief
