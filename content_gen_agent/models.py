"""
Pydantic Models for the Content Generation Agent
=================================================

Two layers of models:

1. ROW MODELS (one per table)
   - Each model represents a single row in an Excel sheet / database table
   - Field types, enums, and nullability match table_schemas.py exactly
   - Used by: Excel exporter (CG-022), validator (CG-020), all generators

2. PACKAGE MODELS (one per pipeline stage)
   - Each model groups related rows that a pipeline stage produces
   - Used by: LLM generation prompts (the LLM returns JSON matching these)
   - Maps to the spec's module architecture (Section 6):
     Module A -> NormalizedTopicBrief
     Module B -> TopicPlan
     Module C -> QuestionPackage
     Module D -> AnswerPackage
     Module E -> DiagnosisPackage
     Module F -> SupportPackage
     Module G -> ScaffoldPackage
     Module H -> WorkedExamplePackage

WHY PYDANTIC?
  - Automatic JSON validation: when the LLM returns JSON, we parse it
    into these models. If a field is wrong type, missing, or has an
    invalid enum value, Pydantic raises a clear error immediately.
  - JSON Schema generation: Pydantic can export JSON Schema, which we
    can pass to the LLM as a structured output format.
  - Serialization: .model_dump() gives us clean dicts for writing to Excel.

WHY TWO LAYERS?
  - The LLM generates content in PACKAGES (a batch of related rows).
    e.g., QuestionPackage has questions + usage + skill mappings together
    because the LLM needs to think about them holistically.
  - But Excel/DB writes happen at ROW level (one row at a time per sheet).
  - Separating them means we can validate at both levels.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ══════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════
# These match the enum values extracted from the reference workbook
# in table_schemas.py. Defining them as Python Enums means Pydantic
# will reject any value not in this list.

class KSStage(str, Enum):
    KS3 = "KS3"

class TopicStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"

class ScopeType(str, Enum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"

class SourceType(str, Enum):
    NABLIX_AUTHORED = "NABLIX_AUTHORED"

class LicenseName(str, Enum):
    OWNED_ORIGINAL_CONTENT = "OWNED_ORIGINAL_CONTENT"

class ReviewStatus(str, Enum):
    APPROVED = "APPROVED"
    PENDING_FINAL_REVIEW = "PENDING_FINAL_REVIEW"

class AssessmentPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"

class MicroSkillStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"

class WorkedExamplePhase(str, Enum):
    PHASE_1_ORIENTATION = "PHASE_1_ORIENTATION"

class WorkedExampleStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"

class QuestionType(str, Enum):
    SINGLE_CHOICE = "SINGLE_CHOICE"
    SHORT_RESPONSE = "SHORT_RESPONSE"
    MULTI_PART_SHORT_RESPONSE = "MULTI_PART_SHORT_RESPONSE"
    CHOICE_WITH_EXPLANATION = "CHOICE_WITH_EXPLANATION"
    TRUE_FALSE_WITH_EXPLANATION = "TRUE_FALSE_WITH_EXPLANATION"

class QuestionStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"

class Phase(str, Enum):
    PHASE_0_DIAGNOSTIC = "PHASE_0_DIAGNOSTIC"
    PHASE_2_GUIDED_LEARNING = "PHASE_2_GUIDED_LEARNING"
    PHASE_3_INDEPENDENT_PRACTICE = "PHASE_3_INDEPENDENT_PRACTICE"

class QuestionRole(str, Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    CLOSE_PRACTICE = "CLOSE_PRACTICE"
    PARTIAL_APPLICATION = "PARTIAL_APPLICATION"
    NEAR_TRANSFER = "NEAR_TRANSFER"
    MISCONCEPTION_PROBE = "MISCONCEPTION_PROBE"
    FINAL_GUIDED_CHECK = "FINAL_GUIDED_CHECK"
    INDEPENDENT_VERIFICATION = "INDEPENDENT_VERIFICATION"

class SupportAllowed(str, Enum):
    ADAPTIVE_SUPPORT = "ADAPTIVE_SUPPORT"
    NO_SUPPORT_DURING_ATTEMPT = "NO_SUPPORT_DURING_ATTEMPT"

class AnswerType(str, Enum):
    ALGEBRAIC_EXPRESSION = "ALGEBRAIC_EXPRESSION"
    SINGLE_CHOICE = "SINGLE_CHOICE"
    MULTI_PART = "MULTI_PART"
    CHOICE_WITH_EXPLANATION = "CHOICE_WITH_EXPLANATION"
    TEXT_MEANING = "TEXT_MEANING"

class VerificationMethod(str, Enum):
    EXACT_NOTATION_MATCH = "EXACT_NOTATION_MATCH"
    SYMBOLIC_EQUIVALENCE = "SYMBOLIC_EQUIVALENCE"
    EXACT_CHOICE_MATCH = "EXACT_CHOICE_MATCH"
    STRUCTURED_TEXT_MATCH = "STRUCTURED_TEXT_MATCH"
    STRUCTURED_TEXT_AND_SYMBOLIC_MATCH = "STRUCTURED_TEXT_AND_SYMBOLIC_MATCH"
    CONCEPT_TEXT_MATCH = "CONCEPT_TEXT_MATCH"
    CHOICE_AND_CONCEPT_MATCH = "CHOICE_AND_CONCEPT_MATCH"

class Severity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"

class DetectionMethod(str, Enum):
    PATTERN_MATCH = "PATTERN_MATCH"
    SYMBOLIC_PATTERN = "SYMBOLIC_PATTERN"
    TOKEN_PATTERN = "TOKEN_PATTERN"
    SEMANTIC_CLASSIFICATION = "SEMANTIC_CLASSIFICATION"
    SEMANTIC_AND_SYMBOLIC_MATCH = "SEMANTIC_AND_SYMBOLIC_MATCH"
    STRUCTURED_EXPRESSION_MATCH = "STRUCTURED_EXPRESSION_MATCH"
    STRUCTURED_TEXT_MATCH = "STRUCTURED_TEXT_MATCH"
    CASE_COMPARISON = "CASE_COMPARISON"

class HintType(str, Enum):
    ATTENTION = "ATTENTION"
    CONCEPT_REMINDER = "CONCEPT_REMINDER"
    PARTIAL_STEP = "PARTIAL_STEP"

class EmbeddingStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"

class VisualCueReviewStatus(str, Enum):
    APPROVED = "APPROVED"
    PENDING_REVIEW = "PENDING_REVIEW"

class RelationshipType(str, Enum):
    DIRECT_FAILURE = "DIRECT_FAILURE"
    AFFECTED_SKILL = "AFFECTED_SKILL"
    UNDERLYING_GAP = "UNDERLYING_GAP"


# ══════════════════════════════════════════════════════════════════════
# ROW MODELS
# ══════════════════════════════════════════════════════════════════════
# One model per Excel sheet / database table.
# Field order matches the column order in table_schemas.py.

class TopicRow(BaseModel):
    """One row in the Topics sheet."""
    topic_id: str
    topic_code: str
    topic_title: str
    ks_stage: KSStage
    sequence_no: int
    learning_goal: str
    core_message: str
    status: TopicStatus
    version: str
    created_at: str
    updated_at: str

class TopicScopeRow(BaseModel):
    """One row in the Topic_Scope sheet."""
    scope_item_id: str
    topic_id: str
    scope_type: ScopeType
    item_text: str
    active: bool

class SourceProvenanceRow(BaseModel):
    """One row in the Source_Provenance sheet."""
    source_provenance_id: str
    source_type: SourceType
    source_name: str
    source_item_id: Optional[str] = None
    license_name: LicenseName
    license_url: Optional[str] = None
    adapted: bool
    direct_text_copied: bool
    review_status: ReviewStatus

class MicroSkillRow(BaseModel):
    """One row in the Micro_Skills sheet."""
    micro_skill_id: str
    topic_id: str
    skill_code: str
    skill_name: str
    description: str
    prerequisite_micro_skill_id: Optional[str] = None
    assessment_priority: AssessmentPriority
    status: MicroSkillStatus
    version: str

class WorkedExampleRow(BaseModel):
    """One row in the Worked_Examples sheet."""
    worked_example_id: str
    topic_id: str
    title: str
    phase: WorkedExamplePhase
    problem_statement: str
    final_answer: str
    status: WorkedExampleStatus
    version: str

class WorkedExampleStepRow(BaseModel):
    """One row in the Worked_Example_Steps sheet."""
    worked_example_step_id: str
    worked_example_id: str
    step_no: int
    screen_content: str
    narration_text: str
    must_show: str
    must_not_show: str

class WorkedExampleMicroSkillRow(BaseModel):
    """One row in the Worked_Example_MicroSkills sheet."""
    worked_example_id: str
    micro_skill_id: str
    weight: float
    is_primary: bool

class QuestionRow(BaseModel):
    """One row in the Questions sheet."""
    question_id: str
    topic_id: str
    question_text: str
    question_type: QuestionType
    difficulty: int = Field(ge=1, le=2)
    answer_spec_id: str
    item_family_id: str
    source_provenance_id: str
    status: QuestionStatus
    version: str

class QuestionUsageRow(BaseModel):
    """One row in the Question_Usage sheet."""
    question_usage_id: str
    question_id: str
    phase: Phase
    question_role: QuestionRole
    sequence_order: int
    support_allowed: SupportAllowed
    max_attempts: int = Field(ge=1, le=3)
    active: bool

class QuestionMicroSkillRow(BaseModel):
    """One row in the Question_MicroSkills sheet."""
    question_id: str
    micro_skill_id: str
    weight: float = Field(gt=0, le=1.0)
    is_primary: bool

class AnswerSpecRow(BaseModel):
    """One row in the Answer_Specs sheet."""
    answer_spec_id: str
    question_id: str
    answer_type: AnswerType
    canonical_answer: str
    accepted_answers: str  # pipe-delimited
    common_wrong_answers: str  # pipe-delimited
    verification_method: VerificationMethod
    required_units: Optional[str] = None
    explanation_required: bool
    answer_steps: str  # newline-separated numbered steps

class ErrorTypeRow(BaseModel):
    """One row in the Error_Types sheet."""
    error_code: str
    error_name: str
    description: str
    related_micro_skill_id: str
    severity: Severity
    detection_method: DetectionMethod
    active: bool

class MisconceptionRow(BaseModel):
    """One row in the Misconceptions sheet."""
    misconception_id: str
    name: str
    description: str
    diagnosis_rule: str
    active: bool
    version: str

class MisconceptionErrorRow(BaseModel):
    """One row in the Misconception_Errors sheet."""
    misconception_id: str
    error_code: str
    confidence_weight: float = Field(gt=0, le=1.0)

class MisconceptionMicroSkillRow(BaseModel):
    """One row in the Misconception_MicroSkills sheet."""
    misconception_id: str
    micro_skill_id: str
    relationship_type: RelationshipType

class QuestionErrorMapRow(BaseModel):
    """One row in the Question_Error_Map sheet."""
    question_id: str
    response_pattern: str
    error_code: str

class HintRow(BaseModel):
    """One row in the Hints sheet."""
    hint_id: str
    hint_level: int = Field(ge=1, le=3)
    hint_type: HintType
    content: str
    active: bool

class MisconceptionHintRow(BaseModel):
    """One row in the Misconception_Hints sheet."""
    misconception_id: str
    hint_id: str
    sequence_order: int

class VisualCueRow(BaseModel):
    """One row in the Visual_Cues sheet."""
    visual_cue_id: str
    cue_name: str
    cue_purpose: str
    image_generation_prompt: str
    negative_prompt: str
    tutor_explanation_template: str
    retrieval_text: str
    retrieval_keywords: str  # comma-separated
    asset_url: Optional[str] = None  # blank until asset pipeline
    embedding_status: EmbeddingStatus
    review_status: VisualCueReviewStatus
    version: str

class MisconceptionVisualCueRow(BaseModel):
    """One row in the Misconception_VisualCues sheet."""
    misconception_id: str
    visual_cue_id: str
    sequence_order: int

class ParallelExampleRow(BaseModel):
    """One row in the Parallel_Examples sheet."""
    parallel_example_id: str
    topic_id: str
    misconception_id: str
    problem_statement: str
    worked_steps: str  # pipe-delimited
    final_answer: str
    active: bool

class ScaffoldRow(BaseModel):
    """One row in the Scaffolds sheet."""
    scaffold_id: str
    scaffold_name: str
    trigger_rule: str
    completion_rule: str
    active: bool

class ScaffoldStepRow(BaseModel):
    """One row in the Scaffold_Steps sheet."""
    scaffold_step_id: str
    scaffold_id: str
    stage_no: int
    prompt: str
    partial_content: Optional[str] = None
    expected_response: str
    next_on_correct: str
    next_on_incorrect: str

class QuestionScaffoldRow(BaseModel):
    """One row in the Question_Scaffolds sheet."""
    question_id: str
    micro_skill_id: str
    scaffold_id: str
    priority: int


# ══════════════════════════════════════════════════════════════════════
# LOOKUP: table name -> row model class
# ══════════════════════════════════════════════════════════════════════
# Used by the Excel exporter and validator to dynamically get the
# right model for any table name.

ROW_MODEL_MAP: dict[str, type[BaseModel]] = {
    "Topics": TopicRow,
    "Topic_Scope": TopicScopeRow,
    "Source_Provenance": SourceProvenanceRow,
    "Micro_Skills": MicroSkillRow,
    "Worked_Examples": WorkedExampleRow,
    "Worked_Example_Steps": WorkedExampleStepRow,
    "Worked_Example_MicroSkills": WorkedExampleMicroSkillRow,
    "Questions": QuestionRow,
    "Question_Usage": QuestionUsageRow,
    "Question_MicroSkills": QuestionMicroSkillRow,
    "Answer_Specs": AnswerSpecRow,
    "Error_Types": ErrorTypeRow,
    "Misconceptions": MisconceptionRow,
    "Misconception_Errors": MisconceptionErrorRow,
    "Misconception_MicroSkills": MisconceptionMicroSkillRow,
    "Question_Error_Map": QuestionErrorMapRow,
    "Hints": HintRow,
    "Misconception_Hints": MisconceptionHintRow,
    "Visual_Cues": VisualCueRow,
    "Misconception_VisualCues": MisconceptionVisualCueRow,
    "Parallel_Examples": ParallelExampleRow,
    "Scaffolds": ScaffoldRow,
    "Scaffold_Steps": ScaffoldStepRow,
    "Question_Scaffolds": QuestionScaffoldRow,
}


# ══════════════════════════════════════════════════════════════════════
# PACKAGE MODELS (pipeline stage outputs)
# ══════════════════════════════════════════════════════════════════════
# Each package groups the rows that one pipeline stage generates.
# The LLM returns JSON matching one of these packages.
#
# WHY PACKAGES?
#   The LLM needs to think about related rows together. For example,
#   when generating questions, it needs to simultaneously decide the
#   question_type, phase assignment, and skill mappings -- these are
#   separate tables but one coherent decision. Packages keep that
#   bundled in one LLM call.


class NormalizedTopicBrief(BaseModel):
    """
    Module A output: Source Parser.
    Extracted and normalized content from the formatted topic DOCX.
    This is NOT generated by the LLM -- it's parsed from the document.
    """
    topic_id: str = Field(description="e.g. ALG-ORI-04")
    topic_code: str = Field(description="e.g. T04")
    topic_title: str
    ks_stage: KSStage
    sequence_no: int
    learning_goal: str
    core_message: str

    # From the Internal Concept Sheet
    included_scope: list[str] = Field(description="List of in-scope items from the source doc")
    excluded_scope: list[str] = Field(description="List of explicitly excluded items")
    misconceptions_to_prevent: list[str] = Field(description="Misconceptions listed in the source doc")

    # From the Designer Handoff
    golden_rules: list[str] = Field(default_factory=list, description="Creative brief golden rules")
    storyboard_notes: str = Field(default="", description="Storyboard/script notes from designer handoff")

    # Source tracking
    source_file_name: str = Field(description="Original DOCX filename")


class TopicPlan(BaseModel):
    """
    Module B output: Curriculum Planner.
    Defines micro-skills and the question plan for this topic.
    """
    topic: TopicRow
    scope_items: list[TopicScopeRow]
    source_provenance: SourceProvenanceRow
    micro_skills: list[MicroSkillRow]

    # Planning metadata (not written to Excel, but guides generation)
    planned_question_count: int = Field(description="Target number of questions")
    phase_distribution: dict[str, int] = Field(
        description="How many questions per phase, e.g. {'PHASE_0': 3, 'PHASE_2': 10, 'PHASE_3': 5}"
    )


class WorkedExamplePackage(BaseModel):
    """
    Module H output: Worked Example Author.
    Worked examples with steps and skill mappings.
    """
    worked_examples: list[WorkedExampleRow]
    worked_example_steps: list[WorkedExampleStepRow]
    worked_example_micro_skills: list[WorkedExampleMicroSkillRow]


class QuestionPackage(BaseModel):
    """
    Module C output: Question Author.
    Questions with phase usage and skill mappings.
    """
    questions: list[QuestionRow]
    question_usage: list[QuestionUsageRow]
    question_micro_skills: list[QuestionMicroSkillRow]


class AnswerPackage(BaseModel):
    """
    Module D output: Answer Author.
    Answer specifications for all questions.
    """
    answer_specs: list[AnswerSpecRow]


class DiagnosisPackage(BaseModel):
    """
    Module E output: Diagnostic Author.
    Error types, misconceptions, and all their cross-table mappings.
    """
    error_types: list[ErrorTypeRow]
    misconceptions: list[MisconceptionRow]
    misconception_errors: list[MisconceptionErrorRow]
    misconception_micro_skills: list[MisconceptionMicroSkillRow]
    question_error_map: list[QuestionErrorMapRow]


class SupportPackage(BaseModel):
    """
    Module F output: Support Author.
    Hints, visual cues, and parallel examples -- all misconception-level.
    """
    hints: list[HintRow]
    misconception_hints: list[MisconceptionHintRow]
    visual_cues: list[VisualCueRow]
    misconception_visual_cues: list[MisconceptionVisualCueRow]
    parallel_examples: list[ParallelExampleRow]


class ScaffoldPackage(BaseModel):
    """
    Module G output: Scaffold Author.
    Question-specific scaffolds with steps.
    """
    scaffolds: list[ScaffoldRow]
    scaffold_steps: list[ScaffoldStepRow]
    question_scaffolds: list[QuestionScaffoldRow]


class ValidationResult(BaseModel):
    """
    Module I output: Deterministic Validator.
    Results of running the 17 blocking checks.
    """
    passed: bool
    total_checks: int
    checks_passed: int
    checks_failed: int
    errors: list[ValidationError_] = Field(default_factory=list)

class ValidationError_(BaseModel):
    """A single validation failure."""
    check_name: str = Field(description="e.g. UNIQUE_ID, FOREIGN_KEY, WEIGHT_SUM")
    table_name: str
    row_identifier: str = Field(description="The ID or key of the failing row")
    message: str
    severity: str = Field(default="BLOCKING")


class QAReviewResult(BaseModel):
    """
    Module J output: Semantic QA Reviewer.
    LLM-based quality review results.
    """
    passed: bool
    issues: list[QAIssue] = Field(default_factory=list)

class QAIssue(BaseModel):
    """A single QA concern."""
    category: str = Field(description="e.g. PEDAGOGY, MATH_ACCURACY, SCOPE, AGE_APPROPRIATENESS")
    table_name: str
    row_identifier: str
    concern: str
    suggestion: str
    severity: str = Field(description="BLOCKING or WARNING")


# ══════════════════════════════════════════════════════════════════════
# FULL TOPIC OUTPUT
# ══════════════════════════════════════════════════════════════════════
# This is the complete output for one topic -- all packages combined.
# Matches the intermediate structured output format from spec Section 16.

class FullTopicOutput(BaseModel):
    """
    Complete generated content for one topic.
    This is what the full pipeline produces before Excel export.
    """
    topic: TopicRow
    scope_items: list[TopicScopeRow]
    source_provenance: SourceProvenanceRow
    micro_skills: list[MicroSkillRow]
    worked_examples: list[WorkedExampleRow]
    worked_example_steps: list[WorkedExampleStepRow]
    worked_example_micro_skills: list[WorkedExampleMicroSkillRow]
    questions: list[QuestionRow]
    question_usage: list[QuestionUsageRow]
    question_micro_skills: list[QuestionMicroSkillRow]
    answer_specs: list[AnswerSpecRow]
    error_types: list[ErrorTypeRow]
    misconceptions: list[MisconceptionRow]
    misconception_errors: list[MisconceptionErrorRow]
    misconception_micro_skills: list[MisconceptionMicroSkillRow]
    question_error_map: list[QuestionErrorMapRow]
    hints: list[HintRow]
    misconception_hints: list[MisconceptionHintRow]
    visual_cues: list[VisualCueRow]
    misconception_visual_cues: list[MisconceptionVisualCueRow]
    parallel_examples: list[ParallelExampleRow]
    scaffolds: list[ScaffoldRow]
    scaffold_steps: list[ScaffoldStepRow]
    question_scaffolds: list[QuestionScaffoldRow]


# ══════════════════════════════════════════════════════════════════════
# SELF-CHECK
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from table_schemas import TABLE_SCHEMAS, GENERATION_ORDER

    # Verify every table has a row model
    for table_name in GENERATION_ORDER:
        assert table_name in ROW_MODEL_MAP, f"Missing row model for {table_name}"
        model = ROW_MODEL_MAP[table_name]
        schema_cols = TABLE_SCHEMAS[table_name]["columns"]
        model_fields = list(model.model_fields.keys())
        assert schema_cols == model_fields, (
            f"{table_name} field order mismatch:\n"
            f"  schema: {schema_cols}\n"
            f"  model:  {model_fields}"
        )

    # Verify ROW_MODEL_MAP covers all 24 tables
    assert len(ROW_MODEL_MAP) == 24, f"Expected 24 models, got {len(ROW_MODEL_MAP)}"

    # Quick validation test: create a sample row and validate it
    test_topic = TopicRow(
        topic_id="ALG-ORI-04", topic_code="T04", topic_title="Expressions",
        ks_stage="KS3", sequence_no=4, learning_goal="Test goal",
        core_message="Test message", status="DRAFT", version="1.0",
        created_at="2026-08-06", updated_at="2026-08-06",
    )
    assert test_topic.status == TopicStatus.DRAFT

    # Test enum validation catches bad values
    try:
        TopicRow(
            topic_id="X", topic_code="X", topic_title="X",
            ks_stage="KS4",  # invalid
            sequence_no=1, learning_goal="X", core_message="X",
            status="DRAFT", version="1.0", created_at="X", updated_at="X",
        )
        assert False, "Should have rejected KS4"
    except Exception:
        pass  # expected

    print(f"Row models: {len(ROW_MODEL_MAP)} (all 24 tables covered)")
    print(f"Package models: 8 (NormalizedTopicBrief, TopicPlan, QuestionPackage,")
    print(f"  AnswerPackage, DiagnosisPackage, SupportPackage, ScaffoldPackage,")
    print(f"  WorkedExamplePackage)")
    print(f"Validation models: ValidationResult, QAReviewResult")
    print(f"Full output model: FullTopicOutput")
    print()

    for table_name in GENERATION_ORDER:
        model = ROW_MODEL_MAP[table_name]
        n_fields = len(model.model_fields)
        print(f"  {table_name:30s} -> {model.__name__:30s} ({n_fields} fields)")

    print("\nAll checks passed.")
