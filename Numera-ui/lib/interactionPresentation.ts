import { activeScaffold, type InteractionResponse } from '@/lib/api';
import { useNumeraStore } from '@/store/useNumeraStore';

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
  if (typeof showCue === 'boolean') {
    useNumeraStore.getState().setVisualCue({
      show: showCue,
      cueType: cue?.cue_type ?? null,
      description: cue?.description ?? null,
    });
  }

  if (response.show_scaffold_panel === undefined) {
    return response.message;
  }
  const scaffold = activeScaffold(response as InteractionResponse);
  useNumeraStore.getState().setActiveScaffold(scaffold);
  return scaffold?.stepVoice ?? scaffold?.stepText ?? response.message;
}
