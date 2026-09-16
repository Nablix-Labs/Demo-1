/**
 * Outbound rescue events: step advance, and renderer acknowledgement.
 *
 * The handoff (§4) requires the renderer to send both, and specifies their
 * shape exactly — but not where they go. So the shapes are built and validated
 * here and the delivery is left to a registered transport, which is what let
 * the button, the step ordering and the supersession all be built and tested
 * before any endpoint existed.
 *
 * Both endpoints now exist — `POST /session/{id}/rescue/advance` and
 * `/rescue/render-ack`, each returning a `RescueStepResponse` — and
 * useWebSocket registers a transport that calls them through lib/api in both
 * text and voice modes. This header used to say neither existed, which by now
 * reads as "rescue advance goes nowhere" — worth correcting, because that is
 * the first thing anyone debugging a stuck walkthrough would find.
 *
 * With no transport registered, an emit warns and reports false. It never
 * throws and never blocks a render: a rescue that cannot report itself is still
 * a rescue the student can read.
 */

export interface RescueAdvanceEvent {
  event_type: 'RESCUE_STEP_ADVANCE';
  session_id: string;
  question_id: string;
  rescue_id: string;
  current_step_index: number;
  trigger: 'UI_NEXT_STEP' | 'VOICE_NEXT';
}

export interface RescueRenderAck {
  action_id: string;
  status: 'RENDERED';
  target_object_id: string;
}

export type RescueTransport = (
  event: RescueAdvanceEvent | RescueRenderAck,
) => boolean | void;

let transport: RescueTransport | null = null;

/**
 * Point rescue events at a transport (the voice socket, or a REST client).
 *
 * Pass null on teardown. Kept module-level rather than in the store because it
 * is plumbing: a socket send function is not state any component renders from,
 * and putting it in the store would re-render every subscriber on reconnect.
 */
export function registerRescueTransport(next: RescueTransport | null): void {
  transport = next;
}

function emit(event: RescueAdvanceEvent | RescueRenderAck, label: string): boolean {
  if (!transport) {
    // Warn rather than fail quietly. A dropped ack is exactly the kind of thing
    // that gets diagnosed as "the renderer never rendered it".
    console.warn(`[rescue] ${label} not sent — no transport registered`, event);
    return false;
  }
  try {
    // A transport that reports false delivered nothing — a closed socket warns
    // rather than throwing, so the try/catch alone would report success for a
    // frame that went nowhere, and the caller would latch its UI on that.
    return transport(event) !== false;
  } catch (error) {
    console.warn(`[rescue] ${label} failed to send`, error);
    return false;
  }
}

/**
 * Ask Chirudeva to advance one step.
 *
 * `current_step_index` is the step the student is looking at NOW, not the one
 * being asked for. Chirudeva rejects the request unless it equals the persisted
 * index, which is what makes a double-click or a replayed frame a no-op instead
 * of a skipped step — so this must never be pre-incremented here.
 */
export function emitRescueAdvance(event: RescueAdvanceEvent): boolean {
  if (!event.session_id || !event.question_id || !event.rescue_id) {
    console.warn('[rescue] advance not sent — incomplete context', event);
    return false;
  }
  return emit(event, 'RESCUE_STEP_ADVANCE');
}

/** Tell the backend a rescue action actually reached the screen. */
export function emitRenderAck(ack: RescueRenderAck): boolean {
  return emit(ack, 'render ack');
}
