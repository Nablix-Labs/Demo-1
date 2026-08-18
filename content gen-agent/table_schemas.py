"""
Table Schemas for the Content Generation Agent
=======================================================

This file defines the schema for all 24 in-scope database tables.
For each table, we capture:
  - columns: ordered list matching the reference workbook exactly
  - column_details: per-column type, nullability, constraints, and enum values
  - foreign_keys: which columns reference other tables (for validation later)
  - notes: generation rules from the task spec

WHY A PYTHON FILE (not JSON/markdown)?
  - CG-002 (Pydantic models) can import and iterate over these definitions
  - CG-004 (empty workbook generator) can read column names and order directly
  - CG-020 (deterministic validator) can use foreign_keys for FK checks
  - One source of truth that's both documentation AND code

WHY THIS STRUCTURE?
  - "columns" is an ordered list because Excel column ORDER matters --
    the generated workbook must match the reference exactly
  - "column_details" uses a dict so we can look up constraints by column name
  - Enum values are extracted from actual data in the reference workbook,
    not guessed -- this means our validator will catch any value outside
    the known set
  - "nullable" tells us which fields can be empty (important for validation)
  - "foreign_keys" map column -> (target_table, target_column) so the
    deterministic validator can check referential integrity automatically
"""

# ──────────────────────────────────────────────────────────────────────
# DEPENDENCY ORDER
# This is the order tables must be GENERATED in, because later tables
# reference earlier ones via foreign keys.
#
# Level 0: Topics, Topic_Scope, Source_Provenance  (no dependencies)
# Level 1: Micro_Skills                            (depends on Topics)
# Level 2: Worked_Examples, WE_Steps, WE_Skills    (depends on Topics, Micro_Skills)
# Level 3: Questions, Q_Usage, Q_MicroSkills       (depends on Topics, Micro_Skills)
# Level 4: Answer_Specs                            (depends on Questions)
# Level 5: Error_Types, Misconceptions + mappings  (depends on Micro_Skills, Questions)
# Level 6: Question_Error_Map                      (depends on Questions, Error_Types)
# Level 7: Hints, Visual_Cues, Parallel_Examples   (depends on Misconceptions)
# Level 8: Scaffolds, Scaffold_Steps, Q_Scaffolds  (depends on Questions)
# ──────────────────────────────────────────────────────────────────────

GENERATION_ORDER = [
    # Level 0 -- foundation tables, no FK dependencies
    "Topics",
    "Topic_Scope",
    "Source_Provenance",
    # Level 1
    "Micro_Skills",
    # Level 2 -- worked examples before questions (spec Section 7.1)
    "Worked_Examples",
    "Worked_Example_Steps",
    "Worked_Example_MicroSkills",
    # Level 3
    "Questions",
    "Question_Usage",
    "Question_MicroSkills",
    # Level 4
    "Answer_Specs",
    # Level 5
    "Error_Types",
    "Misconceptions",
    "Misconception_Errors",
    "Misconception_MicroSkills",
    # Level 6
    "Question_Error_Map",
    # Level 7
    "Hints",
    "Misconception_Hints",
    "Visual_Cues",
    "Misconception_VisualCues",
    "Parallel_Examples",
    # Level 8
    "Scaffolds",
    "Scaffold_Steps",
    "Question_Scaffolds",
]


# ──────────────────────────────────────────────────────────────────────
# TABLE SCHEMAS
# ──────────────────────────────────────────────────────────────────────
# Each schema dict has:
#   "columns"        - list of column names IN ORDER (matches reference XLSX)
#   "column_details" - dict of column_name -> {type, nullable, constraints/enums}
#   "foreign_keys"   - dict of column_name -> (target_table, target_column)
#   "notes"          - generation rules from the task spec
#   "reference_row_count" - how many rows Topics 1-3 produced (for scale reference)
# ──────────────────────────────────────────────────────────────────────

TABLE_SCHEMAS = {

    # ──────────────────────────────────────────────────────────────────
    # LEVEL 0: Foundation tables
    # ──────────────────────────────────────────────────────────────────

    "Topics": {
        "columns": [
            "topic_id", "topic_code", "topic_title", "ks_stage",
            "sequence_no", "learning_goal", "core_message",
            "status", "version", "created_at", "updated_at",
        ],
        "column_details": {
            "topic_id":      {"type": "str", "nullable": False, "unique": True,
                              "description": "Curriculum-level ID from the source doc, e.g. ALG-ORI-02"},
            "topic_code":    {"type": "str", "nullable": False, "unique": True,
                              "description": "Short code like T01, T02 -- used in other IDs"},
            "topic_title":   {"type": "str", "nullable": False},
            "ks_stage":      {"type": "str", "nullable": False,
                              "enum": ["KS3"]},
            "sequence_no":   {"type": "int", "nullable": False,
                              "description": "Ordering within the module"},
            "learning_goal": {"type": "str", "nullable": False},
            "core_message":  {"type": "str", "nullable": False},
            "status":        {"type": "str", "nullable": False,
                              "enum": ["DRAFT", "ACTIVE", "ARCHIVED"],
                              "description": "Must be DRAFT on initial generation (spec Section 13)"},
            "version":       {"type": "str", "nullable": False},
            "created_at":    {"type": "str", "nullable": False,
                              "description": "ISO date string YYYY-MM-DD"},
            "updated_at":    {"type": "str", "nullable": False,
                              "description": "ISO date string YYYY-MM-DD"},
        },
        "foreign_keys": {},
        "notes": "One row per topic. Use the topic_id from the source document.",
        "reference_row_count": 3,
    },

    "Topic_Scope": {
        "columns": [
            "scope_item_id", "topic_id", "scope_type", "item_text", "active",
        ],
        "column_details": {
            "scope_item_id": {"type": "str", "nullable": False, "unique": True,
                              "id_pattern": "SCOPE-T{topic_code_num}-{type_letter}{seq:02d}",
                              "description": "e.g. SCOPE-T02-I01 (I=included), SCOPE-T02-E01 (E=excluded)"},
            "topic_id":      {"type": "str", "nullable": False},
            "scope_type":    {"type": "str", "nullable": False,
                              "enum": ["INCLUDED", "EXCLUDED"]},
            "item_text":     {"type": "str", "nullable": False},
            "active":        {"type": "bool", "nullable": False,
                              "description": "false until topic approval (spec Section 5)"},
        },
        "foreign_keys": {
            "topic_id": ("Topics", "topic_id"),
        },
        "notes": "Create separate INCLUDED and EXCLUDED rows from source doc scope sections.",
        "reference_row_count": 27,
    },

    "Source_Provenance": {
        "columns": [
            "source_provenance_id", "source_type", "source_name",
            "source_item_id", "license_name", "license_url",
            "adapted", "direct_text_copied", "review_status",
        ],
        "column_details": {
            "source_provenance_id": {"type": "str", "nullable": False, "unique": True,
                                     "id_pattern": "SRC-NABLIX-T{topic_code_num}-001"},
            "source_type":          {"type": "str", "nullable": False,
                                     "enum": ["NABLIX_AUTHORED"]},
            "source_name":          {"type": "str", "nullable": False},
            "source_item_id":       {"type": "str", "nullable": True},
            "license_name":         {"type": "str", "nullable": False,
                                     "enum": ["OWNED_ORIGINAL_CONTENT"]},
            "license_url":          {"type": "str", "nullable": True,
                                     "description": "Blank for owned content"},
            "adapted":              {"type": "bool", "nullable": False},
            "direct_text_copied":   {"type": "bool", "nullable": False},
            "review_status":        {"type": "str", "nullable": False,
                                     "enum": ["APPROVED", "PENDING_FINAL_REVIEW"]},
        },
        "foreign_keys": {},
        "notes": "One row per topic. Traces generated content back to its source document.",
        "reference_row_count": 3,
    },

    # ──────────────────────────────────────────────────────────────────
    # LEVEL 1: Micro-skills
    # ──────────────────────────────────────────────────────────────────

    "Micro_Skills": {
        "columns": [
            "micro_skill_id", "topic_id", "skill_code", "skill_name",
            "description", "prerequisite_micro_skill_id",
            "assessment_priority", "status", "version",
        ],
        "column_details": {
            "micro_skill_id":             {"type": "str", "nullable": False, "unique": True,
                                           "id_pattern": "T{topic_code_num}.M{seq}",
                                           "description": "e.g. T01.M1, T01.M2"},
            "topic_id":                   {"type": "str", "nullable": False},
            "skill_code":                 {"type": "str", "nullable": False,
                                           "description": "M1, M2, ... within the topic"},
            "skill_name":                 {"type": "str", "nullable": False},
            "description":                {"type": "str", "nullable": False},
            "prerequisite_micro_skill_id": {"type": "str", "nullable": True,
                                           "description": "FK to another micro_skill_id in same topic, or null if no prereq"},
            "assessment_priority":        {"type": "str", "nullable": False,
                                           "enum": ["HIGH", "MEDIUM"]},
            "status":                     {"type": "str", "nullable": False,
                                           "enum": ["DRAFT", "ACTIVE"]},
            "version":                    {"type": "str", "nullable": False},
        },
        "foreign_keys": {
            "topic_id": ("Topics", "topic_id"),
            "prerequisite_micro_skill_id": ("Micro_Skills", "micro_skill_id"),
        },
        "notes": "Observable, assessable skills only. Ordered by prerequisite. Smallest useful set.",
        "reference_row_count": 22,
    },

    # ──────────────────────────────────────────────────────────────────
    # LEVEL 2: Worked examples
    # ──────────────────────────────────────────────────────────────────

    "Worked_Examples": {
        "columns": [
            "worked_example_id", "topic_id", "title", "phase",
            "problem_statement", "final_answer", "status", "version",
        ],
        "column_details": {
            "worked_example_id": {"type": "str", "nullable": False, "unique": True,
                                  "id_pattern": "WE-KS3-T{topic_code_num}-{seq:02d}"},
            "topic_id":          {"type": "str", "nullable": False},
            "title":             {"type": "str", "nullable": False},
            "phase":             {"type": "str", "nullable": False,
                                  "enum": ["PHASE_1_ORIENTATION"]},
            "problem_statement": {"type": "str", "nullable": False},
            "final_answer":      {"type": "str", "nullable": False},
            "status":            {"type": "str", "nullable": False,
                                  "enum": ["DRAFT", "APPROVED"]},
            "version":           {"type": "str", "nullable": False},
        },
        "foreign_keys": {
            "topic_id": ("Topics", "topic_id"),
        },
        "notes": "Must introduce or consolidate the approved concept without exceeding scope.",
        "reference_row_count": 22,
    },

    "Worked_Example_Steps": {
        "columns": [
            "worked_example_step_id", "worked_example_id", "step_no",
            "screen_content", "narration_text", "must_show", "must_not_show",
        ],
        "column_details": {
            "worked_example_step_id": {"type": "str", "nullable": False, "unique": True,
                                       "id_pattern": "WE-T{topic_code_num}-{we_seq:02d}-S{step_no}"},
            "worked_example_id":      {"type": "str", "nullable": False},
            "step_no":                {"type": "int", "nullable": False,
                                       "description": "Sequential within the worked example, starting at 1"},
            "screen_content":         {"type": "str", "nullable": False},
            "narration_text":         {"type": "str", "nullable": False},
            "must_show":              {"type": "str", "nullable": False},
            "must_not_show":          {"type": "str", "nullable": False},
        },
        "foreign_keys": {
            "worked_example_id": ("Worked_Examples", "worked_example_id"),
        },
        "notes": "Ordered, mathematically correct and presentation-ready.",
        "reference_row_count": 22,
    },

    "Worked_Example_MicroSkills": {
        "columns": [
            "worked_example_id", "micro_skill_id", "weight", "is_primary",
        ],
        "column_details": {
            "worked_example_id": {"type": "str", "nullable": False},
            "micro_skill_id":    {"type": "str", "nullable": False},
            "weight":            {"type": "float", "nullable": False,
                                  "constraints": "0.0 < weight <= 1.0"},
            "is_primary":        {"type": "bool", "nullable": False,
                                  "description": "Exactly one primary skill per worked example"},
        },
        "foreign_keys": {
            "worked_example_id": ("Worked_Examples", "worked_example_id"),
            "micro_skill_id": ("Micro_Skills", "micro_skill_id"),
        },
        "notes": "Exactly one primary worked-example skill per worked_example_id.",
        "reference_row_count": 22,
    },

    # ──────────────────────────────────────────────────────────────────
    # LEVEL 3: Questions
    # ──────────────────────────────────────────────────────────────────

    "Questions": {
        "columns": [
            "question_id", "topic_id", "question_text", "question_type",
            "difficulty", "answer_spec_id", "item_family_id",
            "source_provenance_id", "status", "version",
        ],
        "column_details": {
            "question_id":          {"type": "str", "nullable": False, "unique": True,
                                     "id_pattern": "Q-T{topic_code_num}-{seq:03d}"},
            "topic_id":             {"type": "str", "nullable": False},
            "question_text":        {"type": "str", "nullable": False},
            "question_type":        {"type": "str", "nullable": False,
                                     "enum": [
                                         "SINGLE_CHOICE",
                                         "SHORT_RESPONSE",
                                         "MULTI_PART_SHORT_RESPONSE",
                                         "CHOICE_WITH_EXPLANATION",
                                         "TRUE_FALSE_WITH_EXPLANATION",
                                     ]},
            "difficulty":           {"type": "int", "nullable": False,
                                     "enum": [1, 2],
                                     "description": "1-2 scale currently, future 1-5"},
            "answer_spec_id":       {"type": "str", "nullable": False,
                                     "id_pattern": "ANS-T{topic_code_num}-{seq:03d}"},
            "item_family_id":       {"type": "str", "nullable": False,
                                     "description": "Groups questions testing the same task pattern"},
            "source_provenance_id": {"type": "str", "nullable": False},
            "status":               {"type": "str", "nullable": False,
                                     "enum": ["DRAFT", "APPROVED"]},
            "version":              {"type": "str", "nullable": False},
        },
        "foreign_keys": {
            "topic_id": ("Topics", "topic_id"),
            "source_provenance_id": ("Source_Provenance", "source_provenance_id"),
        },
        "notes": "One clear task per question. No unsupported concepts.",
        "reference_row_count": 54,
    },

    "Question_Usage": {
        "columns": [
            "question_usage_id", "question_id", "phase", "question_role",
            "sequence_order", "support_allowed", "max_attempts", "active",
        ],
        "column_details": {
            "question_usage_id": {"type": "str", "nullable": False, "unique": True,
                                  "id_pattern": "QU-T{topic_code_num}-{q_seq:03d}-P{phase_num}"},
            "question_id":       {"type": "str", "nullable": False},
            "phase":             {"type": "str", "nullable": False,
                                  "enum": [
                                      "PHASE_0_DIAGNOSTIC",
                                      "PHASE_2_GUIDED_LEARNING",
                                      "PHASE_3_INDEPENDENT_PRACTICE",
                                  ]},
            "question_role":     {"type": "str", "nullable": False,
                                  "enum": [
                                      "DIAGNOSTIC",
                                      "CLOSE_PRACTICE",
                                      "PARTIAL_APPLICATION",
                                      "NEAR_TRANSFER",
                                      "MISCONCEPTION_PROBE",
                                      "FINAL_GUIDED_CHECK",
                                      "INDEPENDENT_VERIFICATION",
                                  ]},
            "sequence_order":    {"type": "int", "nullable": False,
                                  "description": "Order within the phase for this topic"},
            "support_allowed":   {"type": "str", "nullable": False,
                                  "enum": [
                                      "ADAPTIVE_SUPPORT",
                                      "NO_SUPPORT_DURING_ATTEMPT",
                                  ]},
            "max_attempts":      {"type": "int", "nullable": False,
                                  "description": "Phase 0 and Phase 3 = 1, Phase 2 = 2 or 3"},
            "active":            {"type": "bool", "nullable": False},
        },
        "foreign_keys": {
            "question_id": ("Questions", "question_id"),
        },
        "notes": "Phase-specific policy must be enforced. See phase rules in spec Section 9.",
        "reference_row_count": 54,
    },

    "Question_MicroSkills": {
        "columns": [
            "question_id", "micro_skill_id", "weight", "is_primary",
        ],
        "column_details": {
            "question_id":    {"type": "str", "nullable": False},
            "micro_skill_id": {"type": "str", "nullable": False},
            "weight":         {"type": "float", "nullable": False,
                               "constraints": "0.0 < weight <= 1.0, weights per question sum to ~1.0"},
            "is_primary":     {"type": "bool", "nullable": False,
                               "description": "Exactly ONE True per question_id"},
        },
        "foreign_keys": {
            "question_id": ("Questions", "question_id"),
            "micro_skill_id": ("Micro_Skills", "micro_skill_id"),
        },
        "notes": "Exactly one primary skill per question. Weights sum approximately to 1.0.",
        "reference_row_count": 101,
    },

    # ──────────────────────────────────────────────────────────────────
    # LEVEL 4: Answer specifications
    # ──────────────────────────────────────────────────────────────────

    "Answer_Specs": {
        "columns": [
            "answer_spec_id", "question_id", "answer_type",
            "canonical_answer", "accepted_answers", "common_wrong_answers",
            "verification_method", "required_units",
            "explanation_required", "answer_steps",
        ],
        "column_details": {
            "answer_spec_id":      {"type": "str", "nullable": False, "unique": True,
                                    "id_pattern": "ANS-T{topic_code_num}-{seq:03d}"},
            "question_id":         {"type": "str", "nullable": False},
            "answer_type":         {"type": "str", "nullable": False,
                                    "enum": [
                                        "ALGEBRAIC_EXPRESSION",
                                        "SINGLE_CHOICE",
                                        "MULTI_PART",
                                        "CHOICE_WITH_EXPLANATION",
                                        "TEXT_MEANING",
                                    ]},
            "canonical_answer":    {"type": "str", "nullable": False},
            "accepted_answers":    {"type": "str", "nullable": False,
                                    "description": "Pipe-delimited alternatives: ans1 | ans2 | ans3"},
            "common_wrong_answers": {"type": "str", "nullable": False,
                                     "description": "Pipe-delimited: wrong1 | wrong2"},
            "verification_method": {"type": "str", "nullable": False,
                                    "enum": [
                                        "EXACT_NOTATION_MATCH",
                                        "SYMBOLIC_EQUIVALENCE",
                                        "EXACT_CHOICE_MATCH",
                                        "STRUCTURED_TEXT_MATCH",
                                        "STRUCTURED_TEXT_AND_SYMBOLIC_MATCH",
                                        "CONCEPT_TEXT_MATCH",
                                        "CHOICE_AND_CONCEPT_MATCH",
                                    ]},
            "required_units":      {"type": "str", "nullable": True,
                                    "description": "e.g. 'degrees'. Null for most algebra questions."},
            "explanation_required": {"type": "bool", "nullable": False,
                                     "description": "Phase 3 must be false (spec Section 9)"},
            "answer_steps":        {"type": "str", "nullable": False,
                                    "description": "Newline-separated numbered steps explaining the solution path"},
        },
        "foreign_keys": {
            "question_id": ("Questions", "question_id"),
        },
        "notes": "Every question requires a complete answer spec. Math must be correct.",
        "reference_row_count": 54,
    },

    # ──────────────────────────────────────────────────────────────────
    # LEVEL 5: Errors, misconceptions, and relationship tables
    # ──────────────────────────────────────────────────────────────────

    "Error_Types": {
        "columns": [
            "error_code", "error_name", "description",
            "related_micro_skill_id", "severity", "detection_method", "active",
        ],
        "column_details": {
            "error_code":             {"type": "str", "nullable": False, "unique": True,
                                       "id_pattern": "ERR-{DESCRIPTIVE-NAME}",
                                       "description": "e.g. ERR-ADD-AS-MULTIPLY, ERR-OPERATOR-OMITTED"},
            "error_name":             {"type": "str", "nullable": False},
            "description":            {"type": "str", "nullable": False},
            "related_micro_skill_id": {"type": "str", "nullable": False},
            "severity":               {"type": "str", "nullable": False,
                                       "enum": ["HIGH", "MEDIUM"]},
            "detection_method":       {"type": "str", "nullable": False,
                                       "enum": [
                                           "PATTERN_MATCH",
                                           "SYMBOLIC_PATTERN",
                                           "TOKEN_PATTERN",
                                           "SEMANTIC_CLASSIFICATION",
                                           "SEMANTIC_AND_SYMBOLIC_MATCH",
                                           "STRUCTURED_EXPRESSION_MATCH",
                                           "STRUCTURED_TEXT_MATCH",
                                           "CASE_COMPARISON",
                                       ]},
            "active":                 {"type": "bool", "nullable": False},
        },
        "foreign_keys": {
            "related_micro_skill_id": ("Micro_Skills", "micro_skill_id"),
        },
        "notes": "Observable error, not a general misconception. Names should be concept-general.",
        "reference_row_count": 20,
    },

    "Misconceptions": {
        "columns": [
            "misconception_id", "name", "description",
            "diagnosis_rule", "active", "version",
        ],
        "column_details": {
            "misconception_id": {"type": "str", "nullable": False, "unique": True,
                                 "id_pattern": "MIS-T{topic_code_num}-{DESCRIPTIVE-NAME}"},
            "name":             {"type": "str", "nullable": False},
            "description":      {"type": "str", "nullable": False},
            "diagnosis_rule":   {"type": "str", "nullable": False,
                                 "description": "When to trigger this misconception diagnosis"},
            "active":           {"type": "bool", "nullable": False},
            "version":          {"type": "str", "nullable": False},
        },
        "foreign_keys": {},
        "notes": "Underlying conceptual model explaining one or more errors.",
        "reference_row_count": 25,
    },

    "Misconception_Errors": {
        "columns": [
            "misconception_id", "error_code", "confidence_weight",
        ],
        "column_details": {
            "misconception_id":  {"type": "str", "nullable": False},
            "error_code":        {"type": "str", "nullable": False},
            "confidence_weight": {"type": "float", "nullable": False,
                                  "constraints": "0.0 < confidence_weight <= 1.0"},
        },
        "foreign_keys": {
            "misconception_id": ("Misconceptions", "misconception_id"),
            "error_code": ("Error_Types", "error_code"),
        },
        "notes": "Every relationship must be semantically justified.",
        "reference_row_count": 17,
    },

    "Misconception_MicroSkills": {
        "columns": [
            "misconception_id", "micro_skill_id", "relationship_type",
        ],
        "column_details": {
            "misconception_id": {"type": "str", "nullable": False},
            "micro_skill_id":   {"type": "str", "nullable": False},
            "relationship_type": {"type": "str", "nullable": False,
                                  "enum": [
                                      "DIRECT_FAILURE",
                                      "AFFECTED_SKILL",
                                      "UNDERLYING_GAP",
                                  ]},
        },
        "foreign_keys": {
            "misconception_id": ("Misconceptions", "misconception_id"),
            "micro_skill_id": ("Micro_Skills", "micro_skill_id"),
        },
        "notes": "Use DIRECT_FAILURE, AFFECTED_SKILL or UNDERLYING_GAP.",
        "reference_row_count": 23,
    },

    # ──────────────────────────────────────────────────────────────────
    # LEVEL 6: Question-error mapping
    # ──────────────────────────────────────────────────────────────────

    "Question_Error_Map": {
        "columns": [
            "question_id", "response_pattern", "error_code",
        ],
        "column_details": {
            "question_id":       {"type": "str", "nullable": False},
            "response_pattern":  {"type": "str", "nullable": False,
                                  "description": "The specific wrong answer string a student might type"},
            "error_code":        {"type": "str", "nullable": False},
        },
        "foreign_keys": {
            "question_id": ("Questions", "question_id"),
            "error_code": ("Error_Types", "error_code"),
        },
        "notes": "Question-specific deterministic patterns only. Must not contain correct answers.",
        "reference_row_count": 82,
    },

    # ──────────────────────────────────────────────────────────────────
    # LEVEL 7: Support content
    # ──────────────────────────────────────────────────────────────────

    "Hints": {
        "columns": [
            "hint_id", "hint_level", "hint_type", "content", "active",
        ],
        "column_details": {
            "hint_id":     {"type": "str", "nullable": False, "unique": True,
                            "id_pattern": "HINT-T{topic_code_num}-{DESCRIPTIVE}-L{level}"},
            "hint_level":  {"type": "int", "nullable": False,
                            "enum": [1, 2, 3],
                            "description": "1=attention redirect, 2=concept reminder, 3=partial structure"},
            "hint_type":   {"type": "str", "nullable": False,
                            "enum": ["ATTENTION", "CONCEPT_REMINDER", "PARTIAL_STEP"]},
            "content":     {"type": "str", "nullable": False},
            "active":      {"type": "bool", "nullable": False},
        },
        "foreign_keys": {},
        "notes": "Progressive support. L1->L2->L3. Reusable at misconception level.",
        "reference_row_count": 39,
    },

    "Misconception_Hints": {
        "columns": [
            "misconception_id", "hint_id", "sequence_order",
        ],
        "column_details": {
            "misconception_id": {"type": "str", "nullable": False},
            "hint_id":          {"type": "str", "nullable": False},
            "sequence_order":   {"type": "int", "nullable": False,
                                 "description": "1, 2, 3 matching hint_level"},
        },
        "foreign_keys": {
            "misconception_id": ("Misconceptions", "misconception_id"),
            "hint_id": ("Hints", "hint_id"),
        },
        "notes": "Order must match increasing support (L1 -> L2 -> L3).",
        "reference_row_count": 36,
    },

    "Visual_Cues": {
        "columns": [
            "visual_cue_id", "cue_name", "cue_purpose",
            "image_generation_prompt", "negative_prompt",
            "tutor_explanation_template", "retrieval_text",
            "retrieval_keywords", "asset_url", "embedding_status",
            "review_status", "version",
        ],
        "column_details": {
            "visual_cue_id":              {"type": "str", "nullable": False, "unique": True,
                                           "id_pattern": "VC-T{topic_code_num}-{DESCRIPTIVE-NAME}"},
            "cue_name":                   {"type": "str", "nullable": False},
            "cue_purpose":                {"type": "str", "nullable": False},
            "image_generation_prompt":    {"type": "str", "nullable": False},
            "negative_prompt":            {"type": "str", "nullable": False},
            "tutor_explanation_template": {"type": "str", "nullable": False},
            "retrieval_text":             {"type": "str", "nullable": False},
            "retrieval_keywords":         {"type": "str", "nullable": False,
                                           "description": "Comma-separated keywords for retrieval"},
            "asset_url":                  {"type": "str", "nullable": True,
                                           "description": "Blank until asset pipeline runs"},
            "embedding_status":           {"type": "str", "nullable": False,
                                           "enum": ["PENDING", "COMPLETED"]},
            "review_status":              {"type": "str", "nullable": False,
                                           "enum": ["APPROVED", "PENDING_REVIEW"],
                                           "description": "Must be unapproved on generation"},
            "version":                    {"type": "str", "nullable": False},
        },
        "foreign_keys": {},
        "notes": "Generate cue specification. asset_url blank until asset production.",
        "reference_row_count": 11,
    },

    "Misconception_VisualCues": {
        "columns": [
            "misconception_id", "visual_cue_id", "sequence_order",
        ],
        "column_details": {
            "misconception_id": {"type": "str", "nullable": False},
            "visual_cue_id":    {"type": "str", "nullable": False},
            "sequence_order":   {"type": "int", "nullable": False},
        },
        "foreign_keys": {
            "misconception_id": ("Misconceptions", "misconception_id"),
            "visual_cue_id": ("Visual_Cues", "visual_cue_id"),
        },
        "notes": "Only map cues that directly address the misconception.",
        "reference_row_count": 13,
    },

    "Parallel_Examples": {
        "columns": [
            "parallel_example_id", "topic_id", "misconception_id",
            "problem_statement", "worked_steps", "final_answer", "active",
        ],
        "column_details": {
            "parallel_example_id": {"type": "str", "nullable": False, "unique": True,
                                    "id_pattern": "PAR-T{topic_code_num}-{DESCRIPTIVE}-{seq:02d}"},
            "topic_id":            {"type": "str", "nullable": False},
            "misconception_id":    {"type": "str", "nullable": False},
            "problem_statement":   {"type": "str", "nullable": False},
            "worked_steps":        {"type": "str", "nullable": False,
                                    "description": "Pipe-delimited steps"},
            "final_answer":        {"type": "str", "nullable": False},
            "active":              {"type": "bool", "nullable": False},
        },
        "foreign_keys": {
            "topic_id": ("Topics", "topic_id"),
            "misconception_id": ("Misconceptions", "misconception_id"),
        },
        "notes": "Same conceptual structure as the misconception, different surface form.",
        "reference_row_count": 10,
    },

    # ──────────────────────────────────────────────────────────────────
    # LEVEL 8: Scaffolds
    # ──────────────────────────────────────────────────────────────────

    "Scaffolds": {
        "columns": [
            "scaffold_id", "scaffold_name", "trigger_rule",
            "completion_rule", "active",
        ],
        "column_details": {
            "scaffold_id":     {"type": "str", "nullable": False, "unique": True,
                                "id_pattern": "SCF-T{topic_code_num}-{DESCRIPTIVE-NAME}"},
            "scaffold_name":   {"type": "str", "nullable": False},
            "trigger_rule":    {"type": "str", "nullable": False},
            "completion_rule": {"type": "str", "nullable": False},
            "active":          {"type": "bool", "nullable": False},
        },
        "foreign_keys": {},
        "notes": "Question-specific, not misconception-generic.",
        "reference_row_count": 12,
    },

    "Scaffold_Steps": {
        "columns": [
            "scaffold_step_id", "scaffold_id", "stage_no", "prompt",
            "partial_content", "expected_response",
            "next_on_correct", "next_on_incorrect",
        ],
        "column_details": {
            "scaffold_step_id":  {"type": "str", "nullable": False, "unique": True,
                                  "id_pattern": "SCF-T{topic_code_num}-{SCAFFOLD}-S{stage_no}"},
            "scaffold_id":       {"type": "str", "nullable": False},
            "stage_no":          {"type": "int", "nullable": False,
                                  "description": "1-based sequential, usually 3-4 steps"},
            "prompt":            {"type": "str", "nullable": False},
            "partial_content":   {"type": "str", "nullable": True,
                                  "description": "Partial answer shown to reduce cognitive load"},
            "expected_response": {"type": "str", "nullable": False},
            "next_on_correct":   {"type": "str", "nullable": False,
                                  "enum_like": ["Stage 2", "Stage 3", "Stage 4", "COMPLETE"],
                                  "description": "Next stage or COMPLETE"},
            "next_on_incorrect": {"type": "str", "nullable": False,
                                  "description": "Retry instruction, often referencing a hint or visual cue"},
        },
        "foreign_keys": {
            "scaffold_id": ("Scaffolds", "scaffold_id"),
        },
        "notes": "Usually 3-4 ordered steps, ending in independent completion.",
        "reference_row_count": 48,
    },

    "Question_Scaffolds": {
        "columns": [
            "question_id", "micro_skill_id", "scaffold_id", "priority",
        ],
        "column_details": {
            "question_id":    {"type": "str", "nullable": False},
            "micro_skill_id": {"type": "str", "nullable": False},
            "scaffold_id":    {"type": "str", "nullable": False},
            "priority":       {"type": "int", "nullable": False,
                               "description": "Priority ordering if multiple scaffolds apply"},
        },
        "foreign_keys": {
            "question_id": ("Questions", "question_id"),
            "micro_skill_id": ("Micro_Skills", "micro_skill_id"),
            "scaffold_id": ("Scaffolds", "scaffold_id"),
        },
        "notes": "Phase 2 questions only. Phase 3 must NOT have scaffold rows.",
        "reference_row_count": 14,
    },
}


# ──────────────────────────────────────────────────────────────────────
# PHASE RULES (from Task Spec Section 9)
# These are used by the validator and by generation prompts to enforce
# phase-specific constraints.
# ──────────────────────────────────────────────────────────────────────

PHASE_RULES = {
    "PHASE_0_DIAGNOSTIC": {
        "allowed_question_types": ["SINGLE_CHOICE"],
        "max_attempts": 1,
        "support_allowed": "NO_SUPPORT_DURING_ATTEMPT",
        "explanation_required": False,
        "allowed_roles": ["DIAGNOSTIC"],
        "scaffold_allowed": False,
    },
    "PHASE_2_GUIDED_LEARNING": {
        "allowed_question_types": [
            "SINGLE_CHOICE", "SHORT_RESPONSE", "MULTI_PART_SHORT_RESPONSE",
            "CHOICE_WITH_EXPLANATION", "TRUE_FALSE_WITH_EXPLANATION",
        ],
        "max_attempts": [2, 3],
        "support_allowed": "ADAPTIVE_SUPPORT",
        "explanation_required": None,  # can be True or False
        "allowed_roles": [
            "CLOSE_PRACTICE", "PARTIAL_APPLICATION", "NEAR_TRANSFER",
            "MISCONCEPTION_PROBE", "FINAL_GUIDED_CHECK",
        ],
        "scaffold_allowed": True,
    },
    "PHASE_3_INDEPENDENT_PRACTICE": {
        "allowed_question_types": [
            "SINGLE_CHOICE", "SHORT_RESPONSE", "MULTI_PART_SHORT_RESPONSE",
        ],
        "max_attempts": 1,
        "support_allowed": "NO_SUPPORT_DURING_ATTEMPT",
        "explanation_required": False,
        "allowed_roles": ["INDEPENDENT_VERIFICATION"],
        "scaffold_allowed": False,
    },
}


# ──────────────────────────────────────────────────────────────────────
# HINT LEVEL RULES (from Task Spec Section 10.3)
# ──────────────────────────────────────────────────────────────────────

HINT_LEVEL_RULES = {
    1: {"purpose": "Attention redirect", "hint_type": "ATTENTION",
        "rule": "Point to the relevant feature without teaching the answer."},
    2: {"purpose": "Concept reminder", "hint_type": "CONCEPT_REMINDER",
        "rule": "State the relevant concept in reusable language."},
    3: {"purpose": "Partial structure", "hint_type": "PARTIAL_STEP",
        "rule": "Reduce the task while withholding the complete answer where possible."},
}


# ──────────────────────────────────────────────────────────────────────
# CONVENIENCE: quick lookups
# ──────────────────────────────────────────────────────────────────────

def get_columns(table_name: str) -> list[str]:
    """Return ordered column list for a table."""
    return TABLE_SCHEMAS[table_name]["columns"]

def get_foreign_keys(table_name: str) -> dict:
    """Return {col: (target_table, target_col)} for a table."""
    return TABLE_SCHEMAS[table_name]["foreign_keys"]

def get_all_table_names() -> list[str]:
    """Return all 24 table names in generation order."""
    return list(GENERATION_ORDER)

def get_enum_values(table_name: str, column_name: str) -> list | None:
    """Return enum values for a column, or None if not an enum."""
    details = TABLE_SCHEMAS[table_name]["column_details"].get(column_name, {})
    return details.get("enum")


# ──────────────────────────────────────────────────────────────────────
# SELF-CHECK: verify schema completeness
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Total tables defined: {len(TABLE_SCHEMAS)}")
    print(f"Generation order has: {len(GENERATION_ORDER)} tables")
    print()

    # Check every table in GENERATION_ORDER exists in TABLE_SCHEMAS
    for t in GENERATION_ORDER:
        assert t in TABLE_SCHEMAS, f"Missing schema for {t}"

    # Check every table in TABLE_SCHEMAS is in GENERATION_ORDER
    for t in TABLE_SCHEMAS:
        assert t in GENERATION_ORDER, f"{t} not in GENERATION_ORDER"

    # Check all FK targets exist
    for table_name, schema in TABLE_SCHEMAS.items():
        for col, (target_table, target_col) in schema["foreign_keys"].items():
            assert target_table in TABLE_SCHEMAS, \
                f"{table_name}.{col} -> {target_table} (table not found)"
            assert target_col in TABLE_SCHEMAS[target_table]["columns"], \
                f"{table_name}.{col} -> {target_table}.{target_col} (column not found)"

    # Print summary
    total_cols = 0
    total_fks = 0
    total_ref_rows = 0
    for name in GENERATION_ORDER:
        s = TABLE_SCHEMAS[name]
        nc = len(s["columns"])
        nf = len(s["foreign_keys"])
        nr = s["reference_row_count"]
        total_cols += nc
        total_fks += nf
        total_ref_rows += nr
        print(f"  {name:30s}  cols={nc:2d}  FKs={nf}  ref_rows={nr}")

    print(f"\nTotals: {total_cols} columns, {total_fks} foreign keys, {total_ref_rows} reference rows")
    print("\nAll checks passed.")
