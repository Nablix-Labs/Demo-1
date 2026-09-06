'use client';

/**
 * InterventionInputModal — "What are you finding difficult?"
 *
 * Spec: "Phase 3 Repeated Failure & Prerequisite Remediation", 5 Sep 2026, §11.
 * Shown whenever the backend raises `intervention_required`, which happens when
 * automated remediation has run out: two guided repairs and a prerequisite
 * route have not fixed the same checkpoint question, or there was no
 * prerequisite route to take (TC-33, TC-34, TC-35).
 *
 * Its purpose is evidence, not teaching. By the time this opens the student has
 * failed the same question four times and been sent back through two topics;
 * the case going to a human should carry what the student says is hard, not
 * only what the system observed.
 *
 * Three rules from §11 that are easy to get wrong:
 *
 *   - At least one selection is required. Voice is encouraged and never
 *     required — a student who will not speak must still be able to submit.
 *   - Voice explains; it does not answer. Phase 3 forbids voice submitting an
 *     independent answer, and the same caution holds here: speaking fills the
 *     transcript box and nothing else. The student presses Send.
 *   - Submitting does NOT resume learning or clear INTERVENTION_REQUIRED. It
 *     records the input. So this closes onto the paused state, never back onto
 *     the question.
 *
 * The options are the backend's when it sends them and the spec's six when it
 * does not (see interventionOptions) — an empty popup could never satisfy the
 * required selection, leaving the student with a dead submit button on the
 * screen that was supposed to be their way to be heard.
 */

import { useEffect, useRef, useState } from 'react';
import { Mic, Square, X } from 'lucide-react';
import { useVoiceTurn } from '@/hooks/useVoiceTurn';
import {
  interventionOptions,
  DEFAULT_INTERVENTION_PROMPT,
  type InterventionInputRequest,
} from '@/lib/phase3Routing';
import { cn } from '@/lib/cn';

export interface InterventionInputSubmission {
  selected_reason_codes: string[];
  voice_input: {
    provided: boolean;
    /**
     * Always null. There is no audio upload anywhere in this app, so no
     * reference can honestly be produced; the transcript is the evidence. If
     * audio itself is ever wanted for the intervention case, that is an upload
     * endpoint and a separate piece of work — not a field quietly filled in
     * with something that is not an audio reference.
     */
    audio_ref: null;
    transcript: string | null;
  };
}

interface Props {
  request: InterventionInputRequest | null;
  onSubmit: (input: InterventionInputSubmission) => Promise<void> | void;
  /** Only offered once the input is in — §11 requires it before moving on. */
  onDismiss?: () => void;
}

export default function InterventionInputModal({ request, onSubmit, onDismiss }: Props) {
  const options = interventionOptions(request);
  const prompt = request?.prompt?.trim() || DEFAULT_INTERVENTION_PROMPT;
  const voiceEnabled = request?.voice_input_enabled !== false;

  const [selected, setSelected] = useState<string[]>([]);
  const [transcript, setTranscript] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Speech fills the box; it never submits. Held in a ref so the hook keeps one
  // stable callback while the text it appends to keeps changing.
  const appendRef = useRef<(t: string) => void>(() => {});
  appendRef.current = (text: string) => {
    const said = text.trim();
    if (said) setTranscript((prev) => (prev ? `${prev} ${said}` : said));
  };
  const voice = useVoiceTurn({ onTurnEnd: (t) => appendRef.current(t) });
  const { stop: stopVoice } = voice;
  useEffect(() => () => stopVoice(), [stopVoice]);

  const toggle = (code: string) =>
    setSelected((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]));

  // §11: "At least one selection is required." Nothing else gates the send —
  // in particular not the voice, which is explicitly optional.
  const canSend = selected.length > 0 && !sending;

  const send = async () => {
    if (!canSend) return;
    setSending(true);
    setError(null);
    stopVoice();
    const said = transcript.trim();
    try {
      await onSubmit({
        selected_reason_codes: selected,
        voice_input: {
          provided: said.length > 0,
          audio_ref: null,
          transcript: said || null,
        },
      });
    } catch {
      // The student's words are still in the box, so the button is the retry.
      setError("We couldn't send that just now. Your answer is still here — try again.");
      setSending(false);
    }
  };

  return (
    <div
      className="lg-scrim lg-anim-fade fixed inset-0 z-[95] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Tell us what you are finding difficult"
    >
      <div className="lg-sheet lg-anim-pop w-[460px] max-w-full rounded-[24px] overflow-hidden">
        <div className="flex items-start justify-between gap-4 px-5 pt-5">
          <div>
            <div className="text-[10px] tracking-widest uppercase text-slate-blue">
              Let&apos;s get you some help
            </div>
            <h2 className="text-[16px] font-semibold text-ink mt-1 leading-snug">{prompt}</h2>
          </div>
          {/* Only after the input is recorded. Before that there is nothing to
              close onto — §11 wants the popup shown before the student is left
              on the intervention state. */}
          {onDismiss && (
            <button
              onClick={onDismiss}
              aria-label="Close"
              className="w-7 h-7 rounded-md flex items-center justify-center text-slate-blue hover:bg-reading-surface flex-shrink-0"
            >
              <X size={16} strokeWidth={1.8} />
            </button>
          )}
        </div>

        <p className="px-5 mt-2 text-[12.5px] text-slate-blue leading-snug">
          Pick everything that fits — you can choose more than one.
        </p>

        <div className="px-5 mt-3 flex flex-col gap-2 max-h-[38vh] overflow-y-auto">
          {options.map((opt) => {
            const on = selected.includes(opt.code);
            return (
              <button
                key={opt.code}
                type="button"
                role="checkbox"
                aria-checked={on}
                onClick={() => toggle(opt.code)}
                className={cn(
                  'rounded-lg border px-4 py-2.5 text-left text-[13.5px] leading-snug transition-colors',
                  on
                    ? 'border-learning-blue bg-learning-blue/8 text-ink font-semibold'
                    : 'border-muted-gray text-ink hover:border-slate-blue',
                )}
              >
                {opt.label}
              </button>
            );
          })}
        </div>

        {voiceEnabled && (
          <div className="px-5 mt-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[12.5px] text-slate-blue">
                Want to say more? This part is optional.
              </span>
              {voice.supported && (
                <button
                  type="button"
                  onClick={() => (voice.active ? voice.stop() : voice.start())}
                  aria-label={voice.active ? 'Stop recording' : 'Explain by voice'}
                  className={cn(
                    'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-semibold transition-colors',
                    voice.active
                      ? 'bg-learning-blue text-white'
                      : 'lg-chip text-ink/80 hover:text-ink',
                  )}
                >
                  {voice.active ? <Square size={12} strokeWidth={2.4} /> : <Mic size={13} strokeWidth={1.9} />}
                  {voice.active ? 'Stop' : 'Speak'}
                </button>
              )}
            </div>
            {/* Editable: the transcript is what gets saved, so the student has
                to be able to correct anything the recogniser misheard. */}
            <textarea
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              rows={3}
              placeholder="You can type here too."
              aria-label="Explain what you are finding difficult"
              className="mt-2 w-full rounded-lg border border-muted-gray px-3 py-2 text-[13px] text-ink
                         placeholder:text-slate-blue/60 resize-none
                         focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-learning-blue/40"
            />
          </div>
        )}

        {error && <p className="px-5 mt-3 text-[12.5px] text-slate-blue">{error}</p>}

        <div className="px-5 py-4 mt-1">
          <button
            onClick={() => void send()}
            disabled={!canSend}
            className="btn btn-primary w-full !py-2.5 !rounded-full text-[13px] disabled:opacity-45 disabled:cursor-not-allowed"
          >
            {sending ? 'Sending…' : 'Send'}
          </button>
          {selected.length === 0 && (
            <p className="mt-2 text-center text-[11.5px] text-slate-blue">
              Choose at least one so we know where to start.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
