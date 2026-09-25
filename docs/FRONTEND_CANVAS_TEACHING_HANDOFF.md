# Canvas Teaching Plan - Frontend Handoff

## Status

The backend now optionally returns `canvas_teaching_plan` on Guided Practice
interaction and canvas-submit responses. No frontend behavior was changed in
this delivery. Enable it on a test VM only after the frontend consumes it.

The plan is visual-only. Existing `canvas_draw` remains the OCR correction
channel; existing `tutor_canvas_actions` remains the support/control channel.
Neither has been removed or changed.

## Response contract

```json
{
  "canvas_teaching_plan": {
    "plan_id": "Q1:TURN-1:canvas-teaching",
    "question_id": "Q1",
    "source_turn_id": "TURN-1",
    "tutor_turn_id": "TUTOR-1",
    "scene_revision": 3,
    "mode": "append",
    "teaching_mode": "DIRECT_EXPLANATION",
    "beats": [
      {
        "beat_id": "focus-first-values",
        "sequence": 1,
        "speech_anchor": {
          "start_char": 0,
          "end_char": 19,
          "text": "Those first numbers"
        },
        "operations": [
          {
            "operation_id": "circle-first-values",
            "kind": "CIRCLE",
            "target_kind": "QUESTION_ANCHOR",
            "target_ids": ["Q1:QTOKEN:1"],
            "zone": "QUESTION",
            "persistence": "PULSE",
            "evidence_ref": null,
            "text": null,
            "latex": null,
            "color_role": "AMBER"
          }
        ]
      }
    ]
  }
}
```

`speech_anchor` is an exact substring of `message_voice`. Schedule the beat
against audio playback at that phrase; retain already-completed persistent marks
if the student interrupts the tutor and discard unstarted beats.

`teaching_mode` is assigned by the backend from the already-selected teaching
state; the client must not infer or advance support levels. Its values are
`GUIDED`, `DIRECT_EXPLANATION`, `HINT`, `VISUAL_CUE`, `SCAFFOLD`,
`PARALLEL_EXAMPLE`, and `TUTOR_SOLVED`.

## Required rendering rules

1. Process a plan only when `question_id`, `source_turn_id`, and
   `scene_revision` match the visible Guided Practice scene. De-duplicate by
   `plan_id` and `beat_id`.
2. Resolve `QUESTION_ANCHOR` IDs against the existing question-token DOM
   anchors. Resolve `STUDENT_TOKEN` IDs only against locally visible OCR/student
   objects. Resolve `CANVAS_ZONE` values locally; the backend deliberately
   sends no coordinates.
3. Keep the original question and all persistent tutor marks for the active
   question. Apply `mode: replace` only to the tutor layer when it arrives for a
   new question; never clear student ink through this contract.
4. Use amber for changing values, teal for repeated/fixed structure, and navy
   for learner-confirmed conclusions. `PULSE` is temporary; `PERSIST` remains.
5. Never render plan output in the student writing area. Keep it separate from
   the right support pane and from `canvas_draw` correction overlays.
6. Existing `canvas_draw` and `tutor_canvas_actions` must continue to work.
   Do not treat `canvas_teaching_plan` as a replacement for support-panel state.

## Required behaviour by teaching mode

| Mode | Main canvas behaviour | Support-pane behaviour |
| --- | --- | --- |
| `DIRECT_EXPLANATION` | Render only the supplied, voice-synchronised concrete examples in the reasoning zone. The backend rejects a final rule here. | No escalation is implied. |
| `HINT` | Pulse/circle/highlight only. Do not add a completed rule. | Keep existing hint UI. |
| `VISUAL_CUE` | Pulse values/repeated terms only; do not copy the cue onto the tutor layer. | Open and retain the existing visual cue. |
| `SCAFFOLD` | Highlight already-visible learner-confirmed tokens only; do not complete the rule. | Keep the scaffold step in the right pane. |
| `PARALLEL_EXAMPLE` | No `canvas_teaching_plan` is emitted: the original question must remain unchanged. | Render the existing parallel example, then return focus to the original question. |
| `TUTOR_SOLVED` | Render each returned beat cumulatively and in audio order. Pause at the tutor's spoken question; never synthesize later steps. | Keep the current rescue state as the authority for progression. |

The tutor layer is cumulative within one question. On a Tutor Solved sequence,
each server turn supplies only the current authorised step; the UI must wait for
the next server response before drawing another one.

## Operation mapping

| Backend operation | Frontend result |
| --- | --- |
| `FOCUS`, `HIGHLIGHT` | temporary emphasis of the resolved target |
| `CIRCLE`, `BOX` | tutor-layer outline around the resolved target |
| `CONNECT` | arrow/bracket between the listed resolved targets |
| `WRITE_TEXT`, `WRITE_MATH` | left-aligned tutor ink in the requested non-student zone |
| `CHECK` | tutor-layer substitution/check line in the reasoning or Tutor Solved zone |

## VM test checklist

1. Set `canvas_teaching.enabled: true` in the deployed
   `nablix-backend/configs/classifier_rules.yaml`.
2. Set `NABLIX_USE_OPENAI_AI_ENGINE=true` and a valid `NABLIX_OPENAI_API_KEY`.
3. Start a Guided Practice session and inspect the interaction response. A plan
   must contain only valid anchor IDs and narration spans.
4. Ask a direct concept question (for example, “what does n mean?”). Verify
   `DIRECT_EXPLANATION` may return spoken concrete substitutions in the
   reasoning zone, never the complete rule and never an escalation.
5. Verify Hint, Visual Cue, and Scaffold return only attention operations;
   Visual Cue and Scaffold content stays in the existing support pane.
6. Verify Parallel Example returns no plan and changes neither question nor
   tutor layer. Verify each Tutor Solved server turn adds only its current
   speech-synchronised step, and only the approved final step may contain the
   canonical answer.
7. Verify no plan is returned in Independent Practice.

Run the billed planner smoke test directly on the VM with:

```bash
NABLIX_RUN_OPENAI_SMOKE=true .venv/bin/python -m pytest -q tests/test_canvas_teaching_openai_smoke.py
```
