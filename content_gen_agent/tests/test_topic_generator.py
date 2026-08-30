"""CG-009 tests.

The generator's job is to call a model and then refuse to trust it blindly, so
most of these script a model that misbehaves in one specific way and check the
run stops. The scope cases matter most: `scope_item_id` is positional, so a
dropped, reordered or reworded item silently repoints every id after it.

Every test uses FakeLLMClient. Nothing here touches the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brief_mapper import to_normalized_brief      # noqa: E402
from docx_parser import parse_all_topic_documents  # noqa: E402
from llm_client import FakeLLMClient, LLMError    # noqa: E402
from models import ScopeType, TopicStatus         # noqa: E402
from sources import find_topic_documents          # noqa: E402
from topic_generator import (                     # noqa: E402
    SYSTEM_PROMPT,
    GenerationError,
    _check_house_style,
    build_user_prompt,
    check_against_document,
    generate_all,
    generate_topic_package,
)

TOPIC_DOCS = find_topic_documents()
needs_docs = pytest.mark.skipif(not TOPIC_DOCS, reason="topic documents not available")


@pytest.fixture(scope="module")
def docs():
    if not TOPIC_DOCS:
        pytest.skip("topic documents not available")
    return parse_all_topic_documents()


@pytest.fixture
def doc(docs):
    """Topic 2: the reference covers it and it is not the odd one out."""
    return docs[1]


def faithful(document, **overrides) -> dict:
    """What a well-behaved model returns: the document, echoed back."""
    brief = to_normalized_brief(document)
    payload = {
        "topic_id": brief.topic_id,
        "topic_title": brief.topic_title,
        "ks_stage": brief.ks_stage.value,
        "sequence_no": brief.sequence_no,
        # Deliberately not the document's wording: prose may be rewritten.
        "learning_goal": "Understand that algebraic notation is a shorter way to write maths.",
        "core_message": brief.core_message,
        "included_scope": list(brief.included_scope),
        "excluded_scope": list(brief.excluded_scope),
        "misconceptions_to_prevent": list(brief.misconceptions_to_prevent),
    }
    payload.update(overrides)
    return payload


def generate(document, payload, **kwargs):
    return generate_topic_package(document, FakeLLMClient([payload]), **kwargs)


# ──────────────────────────────────────────────────────────────────────
# The prompt
# ──────────────────────────────────────────────────────────────────────

def test_the_system_prompt_forbids_inventing_content():
    assert "Never add an item" in SYSTEM_PROMPT
    assert "same order" in SYSTEM_PROMPT


# ──────────────────────────────────────────────────────────────────────
# House style for the two prose fields
#
# The first live run produced "Students understand that ..." for five of six
# topics. The prompt had said to drop the "Students should" opening and the
# model dropped only the "should", which is a fair reading of what it was
# told. Describing the style did not work; the prompt now shows it.
# ──────────────────────────────────────────────────────────────────────

def _style(goal="Understand that x.", message="X is true."):
    return _check_house_style("T.docx", {
        "learning_goal": goal, "core_message": message,
    })


def test_the_prompt_carries_worked_examples_not_a_description():
    """Three of each, taken verbatim from the approved reference."""
    assert SYSTEM_PROMPT.count("Understand that") >= 3
    assert "A letter can represent a changing quantity in a general rule." in SYSTEM_PROMPT
    assert "Do not write \"Students understand that\"" in SYSTEM_PROMPT


def test_the_approved_form_produces_no_warnings():
    assert _style(
        "Understand that a letter can represent a changing number.",
        "A letter can represent a changing quantity in a general rule.",
    ) == []


@pytest.mark.parametrize("goal", [
    "Students understand that algebraic notation is shorter.",
    "The student understands that algebra is a language.",
    "Students should understand that a variable can change.",
])
def test_naming_the_student_in_the_goal_is_flagged(goal):
    fields = [i.field for i in _style(goal=goal)]
    assert "learning_goal" in fields


def test_a_goal_that_does_not_begin_with_understand_is_flagged():
    issues = _style(goal="Know that a letter can represent a number.")
    assert any("does not begin with 'Understand'" in i.message for i in issues)


def test_naming_the_student_in_the_core_message_is_flagged():
    issues = _style(message="Students understand that notation is shorter.")
    assert any(i.field == "core_message" for i in issues)


def test_a_core_message_written_as_a_goal_is_flagged():
    issues = _style(message="Understand that notation makes ideas shorter.")
    assert any("reads like a learning goal" in i.message for i in issues)


def test_style_problems_are_warnings_not_errors():
    """A future topic may legitimately read differently. Flag, do not block."""
    issues = _style(goal="Students understand that x.", message="Students understand y.")
    assert issues
    assert not any(i.is_error for i in issues)


def test_style_warnings_do_not_stop_a_strict_run(docs):
    """Errors stop generation; editorial drift should not."""
    doc = docs[1]
    payload = faithful(doc, learning_goal="Students understand that notation is shorter.")
    package = generate(doc, payload)
    assert package.topic.learning_goal.startswith("Students understand")
    assert not package.errors
    assert any(i.field == "learning_goal" for i in package.issues)


@needs_docs
def test_the_prompt_carries_the_concept_sheet(doc):
    prompt = build_user_prompt(doc)
    for heading in ("Learning Goal", "Core Message", "Included", "Excluded",
                    "Misconceptions to Prevent"):
        assert f"## {heading}" in prompt


@needs_docs
def test_the_prompt_includes_the_topic_id_line(doc):
    assert "Topic ID: ALG-ORI-02" in build_user_prompt(doc)


@needs_docs
def test_the_prompt_leaves_out_the_designer_handoff(doc):
    """Section B is video production material and none of these fields use it."""
    prompt = build_user_prompt(doc)
    assert "Golden Rules" not in prompt
    assert "Storyboard" not in prompt
    assert "Scene 1" not in prompt


@needs_docs
def test_bullets_are_marked_in_the_prompt(doc):
    assert "- collecting like terms" in build_user_prompt(doc)


# ──────────────────────────────────────────────────────────────────────
# A well-behaved model
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_a_faithful_response_produces_a_clean_package(doc):
    package = generate(doc, faithful(doc), today="2026-08-21")
    assert package.is_clean
    assert package.topic.topic_id == "ALG-ORI-02"
    assert package.topic.topic_code == "T02"
    assert package.topic.status is TopicStatus.ACTIVE
    assert package.topic.version == "1.0"
    assert package.topic.created_at == package.topic.updated_at == "2026-08-21"


@needs_docs
def test_the_models_prose_is_used_not_the_documents(doc):
    """The one place the model is allowed to rewrite."""
    package = generate(doc, faithful(doc))
    assert package.topic.learning_goal.startswith("Understand that algebraic notation")
    assert package.topic.learning_goal != package.brief.learning_goal


@needs_docs
def test_scope_ids_are_positional_and_included_come_first(doc):
    package = generate(doc, faithful(doc))
    included = [r for r in package.scope_items if r.scope_type is ScopeType.INCLUDED]
    excluded = [r for r in package.scope_items if r.scope_type is ScopeType.EXCLUDED]

    assert [r.scope_item_id for r in included] == [
        f"SCOPE-T02-I{i:02d}" for i in range(1, len(included) + 1)
    ]
    assert [r.scope_item_id for r in excluded] == [
        f"SCOPE-T02-E{i:02d}" for i in range(1, len(excluded) + 1)
    ]
    assert package.scope_items[: len(included)] == included


@needs_docs
def test_the_package_carries_its_provenance_row(doc):
    package = generate(doc, faithful(doc))
    assert package.source_provenance.source_provenance_id == "SRC-NABLIX-T02-001"
    assert package.source_provenance.source_item_id == "ALG-ORI-02"


@needs_docs
def test_to_rows_produces_the_three_sheets(doc):
    rows = generate(doc, faithful(doc)).to_rows()
    assert set(rows) == {"Topics", "Topic_Scope", "Source_Provenance"}
    assert len(rows["Topics"]) == 1
    assert len(rows["Source_Provenance"]) == 1
    assert rows["Topic_Scope"][0]["scope_item_id"] == "SCOPE-T02-I01"


@needs_docs
def test_one_model_call_per_document(doc):
    client = FakeLLMClient([faithful(doc)])
    generate_topic_package(doc, client)
    assert client.call_count == 1
    assert "CG-009" in client.calls[0]["purpose"]


@needs_docs
def test_all_six_topics_generate(docs):
    client = FakeLLMClient([faithful(d) for d in docs])
    packages = generate_all(client, docs)
    assert len(packages) == 6
    assert all(p.is_clean for p in packages)
    assert [p.topic.topic_code for p in packages] == [f"T{i:02d}" for i in range(1, 7)]


# ──────────────────────────────────────────────────────────────────────
# A model that gets the scope wrong -- the id-shifting hazard
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_a_dropped_scope_item_stops_the_run(doc):
    brief = to_normalized_brief(doc)
    payload = faithful(doc, included_scope=brief.included_scope[:-1])
    with pytest.raises(GenerationError, match="positional"):
        generate(doc, payload)


@needs_docs
def test_an_extra_scope_item_stops_the_run(doc):
    brief = to_normalized_brief(doc)
    payload = faithful(doc, included_scope=brief.included_scope + ["invented item"])
    with pytest.raises(GenerationError, match="not in the document"):
        generate(doc, payload)


@needs_docs
def test_reordered_scope_items_stop_the_run(doc):
    """Same items, same count -- but every id after the swap would move."""
    brief = to_normalized_brief(doc)
    swapped = list(brief.included_scope)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    with pytest.raises(GenerationError, match="does not match the document"):
        generate(doc, faithful(doc, included_scope=swapped))


@needs_docs
def test_a_reworded_scope_item_stops_the_run(doc):
    brief = to_normalized_brief(doc)
    reworded = list(brief.included_scope)
    reworded[2] = reworded[2] + " and a little extra"
    with pytest.raises(GenerationError, match="not in the document"):
        generate(doc, faithful(doc, included_scope=reworded))


@needs_docs
def test_scope_returned_as_a_string_stops_the_run(doc):
    with pytest.raises(GenerationError, match="expected a list"):
        generate(doc, faithful(doc, excluded_scope="collecting like terms"))


@needs_docs
def test_misconceptions_are_checked_too(doc):
    with pytest.raises(GenerationError, match="misconceptions"):
        generate(doc, faithful(doc, misconceptions_to_prevent=["made up"]))


# ──────────────────────────────────────────────────────────────────────
# A model that gets the identity wrong
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_a_wrong_topic_id_stops_the_run(doc):
    with pytest.raises(GenerationError, match="topic_id"):
        generate(doc, faithful(doc, topic_id="ALG-ORI-99"))


@needs_docs
def test_a_wrong_title_stops_the_run(doc):
    with pytest.raises(GenerationError, match="topic_title"):
        generate(doc, faithful(doc, topic_title="Something Else"))


@needs_docs
def test_a_wrong_sequence_number_stops_the_run(doc):
    with pytest.raises(GenerationError, match="sequence_no"):
        generate(doc, faithful(doc, sequence_no=7))


@needs_docs
def test_a_non_numeric_sequence_stops_the_run(doc):
    with pytest.raises(GenerationError, match="not a whole number"):
        generate(doc, faithful(doc, sequence_no="second"))


@needs_docs
def test_a_wrong_key_stage_stops_the_run(doc):
    with pytest.raises(GenerationError, match="ks_stage"):
        generate(doc, faithful(doc, ks_stage="KS4"))


@needs_docs
@pytest.mark.parametrize("field_name", ["learning_goal", "core_message"])
def test_empty_prose_stops_the_run(doc, field_name):
    with pytest.raises(GenerationError, match=field_name):
        generate(doc, faithful(doc, **{field_name: "   "}))


# ──────────────────────────────────────────────────────────────────────
# Non-strict mode
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_non_strict_records_the_problem_instead_of_raising(doc):
    package = generate(doc, faithful(doc, topic_id="ALG-ORI-99"), strict=False)
    assert not package.is_clean
    assert any(i.field == "topic_id" for i in package.errors)


@needs_docs
def test_non_strict_still_writes_the_documents_identity(doc):
    """A wrong topic_id would corrupt every table that references it."""
    package = generate(doc, faithful(doc, topic_id="ALG-ORI-99"), strict=False)
    assert package.topic.topic_id == "ALG-ORI-02"


@needs_docs
def test_non_strict_falls_back_to_the_document_for_a_bad_scope_list(doc):
    brief = to_normalized_brief(doc)
    package = generate(doc, faithful(doc, included_scope=["only one"]), strict=False)
    included = [r for r in package.scope_items if r.scope_type is ScopeType.INCLUDED]
    assert [r.item_text for r in included] == brief.included_scope


# ──────────────────────────────────────────────────────────────────────
# Model and document failures
# ──────────────────────────────────────────────────────────────────────

@needs_docs
def test_an_api_failure_propagates(doc):
    client = FakeLLMClient([LLMError("the api fell over")])
    with pytest.raises(LLMError, match="fell over"):
        generate_topic_package(doc, client)


@needs_docs
def test_malformed_json_propagates(doc):
    client = FakeLLMClient(["{not json at all"])
    with pytest.raises(LLMError, match="did not return valid JSON"):
        generate_topic_package(doc, client)


@needs_docs
def test_a_broken_document_is_refused_before_the_model_is_called(doc):
    """No point spending a call on a document that cannot be used."""
    broken = parse_all_topic_documents()[1]
    del broken.concept_sheet.subsections["Included"]
    client = FakeLLMClient([faithful(doc)])
    with pytest.raises(GenerationError, match="failed validation"):
        generate_topic_package(broken, client)
    assert client.call_count == 0


@needs_docs
def test_check_against_document_finds_nothing_wrong_with_a_faithful_response(doc):
    assert check_against_document(doc, faithful(doc)) == []
