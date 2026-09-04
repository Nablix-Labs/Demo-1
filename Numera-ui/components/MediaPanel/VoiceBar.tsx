'use client';

import { useNumeraStore } from '@/store/useNumeraStore';
import { rescueBlocksSubmission, RESCUE_INPUT_NOTICE } from '@/lib/rescueMode';
import { useMicLevel, MIC_BARS } from '@/store/useMicLevel';
import { useAuthStore, isConsentActive } from '@/store/useAuthStore';
import { cn } from '@/lib/cn';

export default function VoiceBar() {
  // Selector subscriptions — the whole-store form re-rendered this bar (and
  // re-ran its parents' effects) on every store write, several times a second
  // while the student speaks.
  const micMuted = useNumeraStore((s) => s.micMuted);
  const voiceStatus = useNumeraStore((s) => s.voiceStatus);
  const levels = useMicLevel((s) => s.levels);
  const active = useMicLevel((s) => s.active);
  const caption = useMicLevel((s) => s.caption);
  const micError = useMicLevel((s) => s.micError);
  const consents = useAuthStore((s) => s.consents);
  /**
   * A rescue is running, so a spoken answer is not being submitted.
   *
   * Said out loud here because the mic is otherwise indistinguishable from
   * broken: it still listens, still shows levels, and the turn simply goes
   * nowhere. That silence is exactly what got reported as "the tutor is
   * ignoring me" for the capture-failure case above, and it would read the same
   * way here.
   */
  const rescueOn = useNumeraStore(rescueBlocksSubmission);

  // Voice is a consented feature (§10): only available with voice_processing consent.
  const voiceAllowed = isConsentActive(consents, 'voice_processing');

  // The bar is "live" (reacting to real input) only while capturing + unmuted.
  const live = active && !micMuted;

  return (
    <div className="px-3.5 pb-3.5 flex flex-col gap-2.5">
      {/* Status */}
      <p className="text-[11.5px] text-slate-blue text-center">
        Status:{' '}
        <strong className="text-ink">
          {!voiceAllowed ? 'Unavailable' : micError ? 'Microphone unavailable' : micMuted ? 'Muted' : voiceStatus === 'listening' ? 'Listening…' : voiceStatus === 'speaking' ? 'Speaking…' : voiceStatus === 'processing' ? 'Processing…' : 'Idle'}
        </strong>
      </p>

      {rescueOn && (
        <div className="rounded-md bg-reading-surface border border-muted-gray px-3 py-2.5 text-center">
          <p className="text-[11.5px] text-ink font-medium">{RESCUE_INPUT_NOTICE}</p>
        </div>
      )}

      {/* Capture failed: saying "Listening…" here while sending nothing is
          exactly what got reported as "the tutor is ignoring me". */}
      {voiceAllowed && micError && (
        <div className="rounded-md bg-reading-surface border border-muted-gray px-3 py-2.5 text-center">
          <p className="text-[11.5px] text-ink font-medium">
            {micError === 'denied' ? 'Microphone is blocked' : 'Microphone isn’t working'}
          </p>
          <p className="text-[11px] text-slate-blue mt-0.5 leading-snug">
            {micError === 'denied'
              ? 'Allow the microphone in your browser’s address bar, then tap the mic button.'
              : 'Check that a microphone is connected, then tap the mic button to retry.'}
          </p>
        </div>
      )}

      {!voiceAllowed ? (
        /* §14: voice consent missing */
        <div className="rounded-md bg-reading-surface border border-muted-gray px-3 py-2.5 text-center">
          <p className="text-[11.5px] text-ink font-medium">Voice mode is not available</p>
          <p className="text-[11px] text-slate-blue mt-0.5 leading-snug">
            Voice consent is required. You can continue with text below.
          </p>
        </div>
      ) : (
      <>

      {/* Live input level — reflects how much mic signal is being detected */}
      <div className="flex items-center justify-center gap-[3px] h-[26px]" aria-hidden="true">
        {Array.from({ length: MIC_BARS }).map((_, i) => {
          const lvl = live ? levels[i] ?? 0 : 0;
          const height = 3 + lvl * 23; // 3px (silent) … 26px (loud)
          return (
            <span
              key={i}
              className={cn(
                'w-[3px] rounded-sm transition-[height,background-color] duration-75 ease-out',
                live ? 'bg-ai-cyan' : 'bg-muted-gray'
              )}
              style={{ height: `${height}px` }}
            />
          );
        })}
      </div>

      {/* Live caption — what Numera is hearing (helps confirm the mic is working) */}
      {live && (
        <div
          className="min-h-[34px] rounded-md bg-reading-surface border border-muted-gray px-2.5 py-1.5 flex items-center justify-center text-center"
          aria-live="polite"
        >
          {caption ? (
            <p className="text-[11.5px] text-ink leading-snug">
              <span className="text-ai-cyan font-semibold">“</span>{caption}<span className="text-ai-cyan font-semibold">”</span>
            </p>
          ) : (
            <p className="text-[11px] text-slate-blue italic">Listening — start speaking…</p>
          )}
        </div>
      )}

      {/* Mute toggle lives in FloatingMicButton (bottom-center, always visible
          regardless of panel side/collapse) — see components/FloatingMicButton.tsx */}
      <p className="text-[10.5px] text-slate-blue text-center italic">
        {micMuted ? 'Muted — tap the mic button below to unmute' : 'Tap the mic button below to mute'}
      </p>
      </>
      )}
    </div>
  );
}
