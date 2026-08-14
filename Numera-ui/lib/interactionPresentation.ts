import { activeScaffold, type InteractionResponse } from '@/lib/api';
import { cueAssetUrl } from '@/lib/cueAsset';
import { useNumeraStore } from '@/store/useNumeraStore';
import {
  shouldApply,
  noteApplied,
  scaffoldVisible,
  type VersionedResponse,
} from '@/lib/responseGate';

export type SupportPresentation = Pick<
  InteractionResponse,
  | 'message'
  | 'support_message'
  | 'show_visual_cue'
  | 'visual_cue'
  | 'show_scaffold_panel'
  | 'scaffold_id'
  | 'current_scaffold_step_id'
  | 'scaffold_step_number'
  | 'scaffold_step_text'
  | 'scaffold_step_voice'
  | 'total_scaffold_steps'
> & { conversation_action?: string | null };

/**
 * Should this response be rendered at all?
 *
 * Wraps the version gate with the client's applied-state bookkeeping, so every
 * caller gets the same ordering rule. Returns false for a response that is
 * older than what is already on screen, or an equal-version replay that has
 * already been applied for its accepted turn.
 */
export function acceptResponse(response: VersionedResponse): boolean {
  const store = useNumeraStore.getState();
  if (!shouldApply(response, store.appliedResponse)) return false;
  store.setAppliedResponse(noteApplied(response, store.appliedResponse));
  return true;
}

/**
 * A hint the backend has already authorised on this turn.
 *
 * Sanya, 12 Aug 2026: on WRONG_1 and WRONG_2 the Student Model returns real
 * hints with `conversation_action: GIVE_HINT` and the text in
 * `support_message`. The client stored them for the "Need help?" replay and
 * showed nothing — so a student who had already earned a hint had to know to
 * ask for it. "The student should not have to press Need help? to receive a
 * hint that the backend has already authorised."
 *
 * Null when there is nothing extra to present: no hint was served, or the
 * support text IS the tutor's line, in which case showing both would say the
 * same thing twice.
 */
export function authorisedHint(response: SupportPresentation): string | null {
  if (response.conversation_action !== 'GIVE_HINT') return null;
  const hint = response.support_message?.trim();
  if (!hint) return null;
  return hint === response.message?.trim() ? null : hint;
}

export function applyInteractionSupport(response: SupportPresentation): string {
  // Support is separate from the tutor's actual response. Keeping it apart
  // prevents a generic content hint from replacing a question-aware correction
  // in the chat, while preserving it for the existing Need help? control.
  const supportMessage = response.support_message ?? response.message;
  if (response.conversation_action === 'GIVE_HINT' && supportMessage) {
    useNumeraStore.getState().setLastHintText(supportMessage);
  }

  // Put the hint on screen as its own card, not only in the transcript.
  //
  // It was reaching the student as a plain tutor bubble — indistinguishable
  // from the tutor talking, and invisible altogether once the transcript panel
  // was collapsed, which is a persisted preference. So a hint the backend had
  // authorised could be delivered, logged, counted in `hint_count`, and still
  // never seen (Sanya, 13 Aug 2026).
  //
  // `authorisedHint` rather than `supportMessage`: it drops a support message
  // that only repeats the tutor's own line, which would otherwise put the same
  // sentence on the screen twice.
  const hint = authorisedHint(response);
  if (hint) useNumeraStore.getState().setVisibleHint(hint);

  const cue = response.visual_cue;
  const showCue = cue?.show ?? response.show_visual_cue;
  // False means no new cue was served on this turn. Keep the cue already
  // authorised for the active question while its scaffold is open;
  // applyBackendPhase clears it when the question or phase changes.
  if (showCue === true) {
    useNumeraStore.getState().setVisualCue({
      show: true,
      // Stored whole, as sent. `cue_id` is the cue's identity AND the evidence
      // that this is an authored cue at all — `cue_type` is null on the real
      // Topic 1 cues, so it can serve as neither (Sanya, 13 Aug 2026).
      cueId: cue?.cue_id?.trim() || null,
      cueType: cue?.cue_type ?? null,
      description: cue?.description ?? null,
      // Additive: null whenever the backend sent no usable URL, and the card
      // renders text-only exactly as before (see lib/cueAsset).
      assetUrl: cueAssetUrl(cue?.asset_url),
      actions: cue?.actions ?? null,
    });
  }

  // Scaffold visibility follows PERSISTED state (`active_scaffold`), not the
  // per-turn event — handoff item 3. Rendering from the event made the panel
  // vanish on the next reply, because that reply served no new support even
  // though the scaffold was still open.
  const persisted = (response as InteractionResponse).active_scaffold;
  if (persisted !== undefined) {
    const store = useNumeraStore.getState();
    if (!scaffoldVisible(response as InteractionResponse)) {
      store.setActiveScaffold(null);
      return response.message;
    }
    store.setActiveScaffold({
      scaffoldId: persisted!.scaffold_id,
      currentStepId: persisted!.current_step_id,
      stepNumber: persisted!.step_number,
      stepText: persisted!.step_text,
      stepVoice: persisted!.step_voice ?? null,
      totalSteps: persisted!.total_steps,
    });
    return persisted!.step_voice ?? persisted!.step_text ?? response.message;
  }

  // Pre-contract backend: the per-turn booleans are all we have.
  if (response.show_scaffold_panel === undefined) {
    return response.message;
  }
  const scaffold = activeScaffold(response as InteractionResponse);
  useNumeraStore.getState().setActiveScaffold(scaffold);
  return scaffold?.stepVoice ?? scaffold?.stepText ?? response.message;
}
