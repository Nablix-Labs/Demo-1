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

    // Reliability gate — see the header.
    next_expected_input: str(msg.next_expected_input),
    requires_written_math_evidence:
      msg.requires_written_math_evidence as boolean | null | undefined,
    write_instruction: str(msg.write_instruction),

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
