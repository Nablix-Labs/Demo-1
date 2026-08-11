import { activeScaffold, type InteractionResponse } from '@/lib/api';
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

export function applyInteractionSupport(response: SupportPresentation): string {
  // A GIVE_HINT turn is the only hint the frontend can still get: the backend
  // deleted POST /hint/request in the Schema 3.0 refactor (3 Aug 2026), so the
  // turn message IS the hint. Remembering it is what lets "Need help?" re-open
  // rung 1 of the ladder instead of calling an endpoint that 404s.
  if (response.conversation_action === 'GIVE_HINT' && response.message) {
    useNumeraStore.getState().setLastHintText(response.message);
  }

  const cue = response.visual_cue;
  const showCue = cue?.show ?? response.show_visual_cue;
  // False means no new cue was served on this turn. Keep the cue already
  // authorised for the active question while its scaffold is open;
  // applyBackendPhase clears it when the question or phase changes.
  if (showCue === true) {
    useNumeraStore.getState().setVisualCue({
      show: true,
      cueType: cue?.cue_type ?? null,
      description: cue?.description ?? null,
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
