# Phase 2 — what the frontend needs from content, field by field

**For:** Sanya · **From:** Manav (frontend) · 23 Sep 2026
**Against:** the Phase 2 doc "Full Conversation, Adaptive Support, Canvas Behaviour and Critical Thinking" and `main` @ 21 Sep.

Everything in Part A and Part B is **already consumed by the deployed frontend**. Nothing there needs a frontend change; it works the moment the data arrives in this shape. Part C is the one small addition the doc needs. Part D is the worked example for `3 + 5 | 9 + 5 | 14 + 5`.

The rule behind every field: **the backend never sends coordinates or colours.** It names *what* to point at by a stable id and *what* to write; the frontend lays it out.

---

## Part A — Authored once per question

This is the content record. The tutor backend picks from it turn by turn; the frontend never sees it whole.

```jsonc
{
  "question_id": "Q-T01-003",
  "current_question": "3 + 5\n9 + 5\n14 + 5",        // newline-separated cases render as an aligned grid
  "instruction": "Use n for the changing starting number. Write the general rule.",

  // 1. Tokens the tutor may point at. char_start/char_end slice current_question EXACTLY.
  //    One anchor per occurrence. The frontend verifies the slice; a wrong span is dropped.
  "question_anchors": [
    { "token_id": "start_1", "text": "3",  "char_start": 0,  "char_end": 1  },
    { "token_id": "fixed_1", "text": "+ 5", "char_start": 2,  "char_end": 5  },
    { "token_id": "start_2", "text": "9",  "char_start": 6,  "char_end": 7  },
    { "token_id": "fixed_2", "text": "+ 5", "char_start": 8,  "char_end": 11 },
    { "token_id": "start_3", "text": "14", "char_start": 12, "char_end": 14 },
    { "token_id": "fixed_3", "text": "+ 5", "char_start": 15, "char_end": 18 }
  ],

  // 2. Hints, in ladder order. Shown verbatim in the support column.
  "hints": [
    { "hint_id": "H1", "text": "Look only at the first position in each expression. What is different there?" },
    { "hint_id": "H2", "text": "Now compare the part after the first number. Is it different, or exactly the same?" }
  ],

  // 3. Visual cue. description is required; rows and asset_url are optional.
  "visual_cue": {
    "cue_id": "VC-T01-003",
    "cue_type": "COMPARE_CASES",
    "description": "One position can take different values. The other part repeats.",
    "asset_url": null,                                   // optional PNG on nablixmathvideos blob storage
    "actions": [
      { "action": "COMPARE_EXPRESSIONS", "rows": [
        { "expression": "3 + 5",  "annotation": "starting number 3" },
        { "expression": "9 + 5",  "annotation": "starting number 9" },
        { "expression": "14 + 5", "annotation": "starting number 14" }
      ]}
    ]
  },

  // 4. Scaffold. One step is released per turn; the student answers by voice.
  "scaffold": {
    "scaffold_id": "SCF-T01-003",
    "steps": [
      { "step_id": "S1", "text": "The rule has two parts: [ changing part ] + [ fixed part ]. What is our changing part?", "voice": "…" },
      { "step_id": "S2", "text": "The question tells us to call the changing part…?", "voice": "…" },
      { "step_id": "S3", "text": "What is the fixed part? Just 5, or +5?", "voice": "…" },
      { "step_id": "S4", "text": "Put the two parts together.", "voice": "…" }
    ]
  },

  // 5. Parallel solved example. Stays in the panel, never on the student's page.
  "parallel_example": {
    "parallel_example_id": "PX-T01-003",
    "problem": "4 + 2\n8 + 2\n15 + 2",
    "worked_steps": [
      "The starting numbers 4, 8 and 15 change.",
      "+2 stays fixed every time.",
      "Structure: changing starting number + 2.",
      "Using n for the changing starting number: n + 2."
    ],
    "final_answer": "n + 2"
  },

  // 6. Tutor solved. One step per turn on the student's canvas, each with its pause question.
  "tutor_solved": {
    "rescue_id": "TS-T01-003",
    "steps": [
      { "write": "3, 9, 14 → starting number changes",   "voice": "First, I look for what changes… Before I continue, which part do you think I should look at next?" },
      { "write": "+5 → stays fixed",                     "voice": "But +5 stays exactly the same. Why am I keeping the plus sign together with the 5?" },
      { "write": "changing starting number + 5",         "voice": "So the structure is a changing starting number, plus 5. Say that structure in your own words." },
      { "write": "n + 5",                                "voice": "The question tells us to use n. Why did the +5 stay unchanged?", "answer_reveal": true },
      { "write": "n = 3 → 3 + 5,  n = 9 → 9 + 5,  n = 14 → 14 + 5", "voice": "We can check it. Does the rule reproduce each original case?" }
    ],
    "final_answer": "n + 5"
  },

  // 7. NEW — the board script (see Part C). The trail the tutor writes during
  //    normal guided reasoning, one line per doc stage, unlocked by the student.
  "board_script": [
    { "stage": 2, "ct_step": "compare",      "role": "CHANGE",     "action": "HIGHLIGHT",   "targets": ["start_1","start_2","start_3"], "label": null,
      "ask": "Look at the first numbers: 3, 9 and 14. Are those numbers the same?" },
    { "stage": 3, "ct_step": "change",       "role": "CHANGE",     "action": "INSERT_LABEL", "write": "3, 9, 14 → starting number changes",
      "unlock_on": "they are different", "ask": "What is happening to those first numbers?" },
    { "stage": 4, "ct_step": "invariant",    "role": "FIXED",      "action": "HIGHLIGHT",   "targets": ["fixed_1","fixed_2","fixed_3"], "label": null,
      "ask": "What do you see after every starting number?" },
    { "stage": 5, "ct_step": "invariant",    "role": "FIXED",      "action": "INSERT_LABEL", "write": "+5 → stays fixed",
      "unlock_on": "plus 5", "ask": "Look at the sign too. What is the complete part that repeats?" },
    { "stage": 6, "ct_step": "relationship", "role": "CONCLUSION", "action": "INSERT_LABEL", "write": "changing starting number + 5",
      "unlock_on": "add 5", "ask": "We have a changing starting number, and what do we always do to it?" },
    { "stage": 7, "ct_step": "generalise",   "role": "CHANGE",     "action": "INSERT_MATH",  "write": "n",
      "unlock_on": "the changing number", "ask": "The question tells us to use n. What should n replace here?" },
    { "stage": 8, "ct_step": "generalise",   "role": "CONCLUSION", "action": "INSERT_MATH",  "write": "n + 5", "box": true,
      "unlock_on": "plus 5", "ask": "Now read what we have built. n and what?" }
  ]
}
```

Notes on Part A:

- **Anchors are the whole trick.** "Circle 3, 9 and 14" is three `HIGHLIGHT` actions on `start_1..3`. No geometry, no colour. If the anchors are wrong the tutor points at the wrong symbol, so please generate `char_start`/`char_end` programmatically from the question string, never by hand.
- **The direct concept explanation (doc §1.2)** needs no field of its own. It is an ordinary tutor turn whose `tutor_canvas_actions` carry three `INSERT_MATH` lines (`n = 3 → 3 + 5`, …). Only the decision "explain first, don't escalate" is backend logic.
- **Scaffold placement.** Today the scaffold renders under the question, not in the right pane. Say if you want it moved; it is a frontend change, not a content one.

---

## Part B — What each turn's `/interaction` response must carry

All of these exist today. One turn = one spoken line + whatever the tutor writes for it.

| Field | Type | When |
|---|---|---|
| `message` / `message_voice` | string | every turn; `message_voice` is what is spoken |
| `expects_student_response` | bool | `true` on every turn that ends in a question (all of them, per the doc) |
| `conversation_action` | `"GIVE_HINT"` | on Hint 1 / Hint 2 turns; the hint text rides in `message` (or `support_message`) |
| `support_served_this_turn` | `HINT` \| `VISUAL_CUE` \| `SCAFFOLD` \| `PARALLEL_EXAMPLE` \| `TUTOR_SOLVED` \| null | the rung served on **this** turn; the column shows whatever came last |
| `active_support_level`, `highest_support_used` | same enum | persisted |
| `show_visual_cue` + `visual_cue` | bool + object from Part A §3 | on the Visual Cue turn |
| `show_scaffold_panel`, `scaffold_id`, `current_scaffold_step_id`, `scaffold_step_number`, `scaffold_step_text`, `scaffold_step_voice`, `total_scaffold_steps` | | one authorised step per turn |
| `tutor_canvas_actions[]` | see below | anything the tutor draws or writes |
| `guided_student_state` | `CORRECT` \| `PARTIAL` \| `WRONG` \| `STUCK` \| `UNCLEAR` | drives the "tick / question / tick" partial-credit marks |
| `question_anchors[]` | from Part A §1 | on the first turn of the question, and any turn that adds a label |
| `tutor_turn_id`, `accepted_turn_id`, `interaction_state_version` | | turn sync, unchanged |

### `tutor_canvas_actions[]` — the shape the frontend reads

```jsonc
{
  "action_id": "Q-T01-003:t04:hl:fixed_1",   // unique per action; duplicates are ignored
  "type": "HIGHLIGHT",                         // HIGHLIGHT | GROUP | ARROW | INSERT_LABEL | INSERT_MATH | SHOW_PARALLEL | TUTOR_SOLVED_STEP
  "target_kind": "QUESTION_ANCHOR",            // QUESTION_ANCHOR | TUTOR_ANCHOR | STUDENT_ATTEMPT | CANVAS_OBJECT | WRITE_AREA
  "target_object_id": "fixed_1",
  "text": "stays fixed",                       // HIGHLIGHT: label under the token, or null. INSERT_*: what to write.
  "confirmed_component_id": null,
  "source_id": null,
  "answer_reveal_allowed": false
}
```

Target ids the frontend resolves:

| `target_kind` | `target_object_id` | Meaning |
|---|---|---|
| `QUESTION_ANCHOR` | a `token_id` from `question_anchors` | mark a token in the question strip |
| `TUTOR_ANCHOR` | `TUTOR_ANCHOR:WRITE_RULE:{n}` (n = 1, 2, 3…) | the n-th line of the trail under the question; use for `INSERT_LABEL` / `INSERT_MATH` |
| `TUTOR_ANCHOR` | `TUTOR_ANCHOR:CONFIRMED:{question_id}:{n}` | a line in the "confirmed so far" column (partial credit) |
| `TUTOR_ANCHOR` | `TUTOR_ANCHOR:RESCUE:{rescue_id}:STEP:{i}` | a Tutor Solved / parallel step row |
| `TUTOR_ANCHOR` | an earlier action's element id | point at something the tutor already wrote |
| `STUDENT_ATTEMPT` | an ink object id from `/canvas/submit` | mark the student's own writing |

Rescue steps add: `rescue_id`, `step_index` (1-based), `total_steps`, `presentation_mode` (`"PARALLEL"` \| `"TUTOR_SOLVED"`), `return_target_object_id`. `SHOW_PARALLEL` renders in the panel only; `TUTOR_SOLVED_STEP` is written on the canvas.

---

## Part C — The one addition: `role` on an action

The doc's whole visual language is three colours with meanings: amber = changing, teal = fixed, navy = statements and the rule. Today every highlight is one colour and every written line is navy.

Add one optional field to `tutor_canvas_actions[]`:

```jsonc
"role": "CHANGE"        // CHANGE | FIXED | CONCLUSION   (null → navy, as today)
```

and one optional flag for the boxed rule:

```jsonc
"box": true             // draws the outline around an INSERT_MATH line (stage 8 and Tutor Solved reveal)
```

That is the entire contract change. The frontend maps role → colour; content never types a hex value. Everything else in the doc (rings, connections, arrows, the trail, the boxed rule, step-by-step Tutor Solved, the parallel example) is expressible with fields that already exist.

**Not asking for:** pulse or transient marks (the doc's "briefly pulse"). Marks stay on the board; the persistent trail is what the student reasons over. Say if you disagree and I'll scope a fading highlight separately.

---

## Part D — Three real turns for `3 + 5 | 9 + 5 | 14 + 5`

### Turn at doc stage 2 — "Reduce the thinking load"

```jsonc
{
  "message_voice": "That's okay. Let's look at just one part. Look at the first numbers: 3, 9 and 14. Are those numbers the same?",
  "expects_student_response": true,
  "support_served_this_turn": null,
  "tutor_canvas_actions": [
    { "action_id": "Q3:s2:hl:1", "type": "HIGHLIGHT", "target_kind": "QUESTION_ANCHOR", "target_object_id": "start_1", "text": null, "role": "CHANGE", "answer_reveal_allowed": false },
    { "action_id": "Q3:s2:hl:2", "type": "HIGHLIGHT", "target_kind": "QUESTION_ANCHOR", "target_object_id": "start_2", "text": null, "role": "CHANGE", "answer_reveal_allowed": false },
    { "action_id": "Q3:s2:hl:3", "type": "HIGHLIGHT", "target_kind": "QUESTION_ANCHOR", "target_object_id": "start_3", "text": null, "role": "CHANGE", "answer_reveal_allowed": false }
  ]
}
```

### Turn at doc stage 5 — student said "plus 5"

```jsonc
{
  "message_voice": "Yes. So forget the actual numbers for a moment. We have a changing starting number, and what do we always do to it?",
  "expects_student_response": true,
  "guided_student_state": "PARTIAL",
  "tutor_canvas_actions": [
    { "action_id": "Q3:s5:hl:1", "type": "HIGHLIGHT", "target_kind": "QUESTION_ANCHOR", "target_object_id": "fixed_1", "text": "stays fixed", "role": "FIXED", "answer_reveal_allowed": false },
    { "action_id": "Q3:s5:hl:2", "type": "HIGHLIGHT", "target_kind": "QUESTION_ANCHOR", "target_object_id": "fixed_2", "text": null, "role": "FIXED", "answer_reveal_allowed": false },
    { "action_id": "Q3:s5:hl:3", "type": "HIGHLIGHT", "target_kind": "QUESTION_ANCHOR", "target_object_id": "fixed_3", "text": null, "role": "FIXED", "answer_reveal_allowed": false },
    { "action_id": "Q3:s5:line", "type": "INSERT_LABEL", "target_kind": "TUTOR_ANCHOR", "target_object_id": "TUTOR_ANCHOR:WRITE_RULE:2", "text": "+5 → stays fixed", "role": "FIXED", "answer_reveal_allowed": false }
  ]
}
```

### Turn at doc stage 8 — student said "plus 5" after n

```jsonc
{
  "message_voice": "Exactly. Tell me what n + 5 means in your own words.",
  "expects_student_response": true,
  "tutor_canvas_actions": [
    { "action_id": "Q3:s8:rule", "type": "INSERT_MATH", "target_kind": "TUTOR_ANCHOR", "target_object_id": "TUTOR_ANCHOR:WRITE_RULE:5", "text": "n + 5", "role": "CONCLUSION", "box": true, "answer_reveal_allowed": false }
  ]
}
```

### Turn in Tutor Solved — step 2 of 5

```jsonc
{
  "message_voice": "But +5 stays exactly the same in every case. Why am I keeping the plus sign together with the 5?",
  "expects_student_response": true,
  "support_served_this_turn": "TUTOR_SOLVED",
  "tutor_canvas_actions": [
    { "action_id": "TS-T01-003:2", "type": "TUTOR_SOLVED_STEP", "target_kind": "TUTOR_ANCHOR",
      "target_object_id": "TUTOR_ANCHOR:RESCUE:TS-T01-003:STEP:2",
      "text": "+5 → stays fixed", "role": "FIXED",
      "rescue_id": "TS-T01-003", "step_index": 2, "total_steps": 5, "presentation_mode": "TUTOR_SOLVED",
      "return_target_object_id": "start_1", "answer_reveal_allowed": false }
  ]
}
```

---

## The one product decision this contract cannot make

Every path in the doc ends with the student *saying* "n + 5". The deployed rule (`requires_written_symbolic_rule_evidence`) advances an algebra-rule question only on a written rule submitted with **Check**. Either that rule is relaxed for these questions, or the last board-script line asks the student to write the rule and press Check, which is also the doc's own "Test" step. I'd take the second. Needs a yes from you and Chiru.
