/**
 * Turning a voice `tutor_response` frame into the support payload the
 * presentation layer reads.
 *
 * This exists because the mapping used to be an object literal inline in
 * useWebSocket, and an allow-list written inline is invisible: a field missing
 * from it looks exactly like a field the backend never sent.
 *
 * That is not hypothetical. `next_expected_input: "WRITE"` — the reliability
 * gate asking the student to write the rule down — began arriving on voice
 * turns (Sanya, 18 Aug 2026: "a voice-only final algebra rule"). The literal
 * did not list it, `requiresWriting` reads an absent field as "not a WRITE
 * turn", and the prompt was dropped on the one transport where the student has
 * written nothing at all. It worked over REST, which forwards the whole
 * response object, so no test failed and nothing looked broken.
 *
 * Same failure as `strokes` on /canvas/submit: the field a caller MAY omit is
 * the field that silently stops being sent. Here it is a named function with a
 * test that fails when a field stops being carried.
 */

import type { SupportPresentation } from '@/lib/interactionPresentation';

/** The raw WS frame. Values are unknown because the socket is untyped. */
export type VoiceTutorFrame = Record<string, unknown>;

const str = (v: unknown) => v as string | null | undefined;

export function voiceSupportFrame(msg: VoiceTutorFrame): SupportPresentation {
  return {
    message: msg.text as string,
    support_message: str(msg.support_message),
    conversation_action: str(msg.conversation_action),

    // Pointing at the question text (Chirudeva §1). Defaulted to an empty
    // array rather than left undefined, so a voice turn that points at nothing
    // clears the previous turn's highlight instead of leaving it standing.
    // Array.isArray, not a bare cast. A non-array here is stored raw and then
    // throws inside usableAnchors during React render — a genuine blank
    // screen. voiceSessionSync already doubts this exact field's shape.
    question_anchors: Array.isArray(msg.question_anchors)
      ? (msg.question_anchors as SupportPresentation['question_anchors'])
      : [],

    // Reliability gate — see the header.
    next_expected_input: str(msg.next_expected_input),
    requires_written_math_evidence:
      msg.requires_written_math_evidence as boolean | null | undefined,
    write_instruction: str(msg.write_instruction),

    // The bottom two rungs (parallel example / tutor-solved). The streaming
    // server spreads the whole tutor_response onto the frame, so a rescue
    // served on a voice turn is already on the wire — it was simply never
    // read here, and a voice-led student got no rescue at all.
    guided_rescue: msg.guided_rescue as SupportPresentation['guided_rescue'],

    // Persisted scaffold state. Without it the voice path always fell through
    // to the pre-contract per-turn booleans, so a scaffold still open closed
    // itself on the next reply that served no new support — the exact
    // regression `active_scaffold` was introduced to end.
    active_scaffold: msg.active_scaffold as SupportPresentation['active_scaffold'],

    // Semantic tutor canvas actions (Sanya, 19 Aug). Guided Practice is voice-led
    // more often than not, so this is the transport that needs them most.
    // Same guard, sharper consequence: applyTutorCanvasActions spreads this
    // into an array, so a non-array throws before the reply renders at all.
    tutor_canvas_actions: Array.isArray(msg.tutor_canvas_actions)
      ? (msg.tutor_canvas_actions as SupportPresentation['tutor_canvas_actions'])
      : undefined,

    show_visual_cue: msg.show_visual_cue as boolean | undefined,
    visual_cue: msg.visual_cue as SupportPresentation['visual_cue'],

    show_scaffold_panel: msg.show_scaffold_panel as boolean | undefined,
    scaffold_id: str(msg.scaffold_id),
    current_scaffold_step_id: str(msg.current_scaffold_step_id),
    scaffold_step_number: msg.scaffold_step_number as number | null | undefined,
    scaffold_step_text: str(msg.scaffold_step_text),
    scaffold_step_voice: str(msg.scaffold_step_voice),
    total_scaffold_steps: msg.total_scaffold_steps as number | null | undefined,
  };
}
