'use client';

/**
 * VoicePicker — a Demo Director control to switch the tutor's voice variant, so
 * different TTS providers/voices can be compared (Manjusha's ask, 2026-07-26).
 *
 * The selection is sent on POST /voice/tts and on the /voice/stream WS, and the
 * backend honours both since PR #39 — falling back to the VOICE_TTS_PROVIDER /
 * VOICE_TTS_VOICE env vars when nothing is picked. See lib/voiceOptions.ts.
 */

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Volume2, X } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { VOICE_PROVIDERS, providerById, VOICE_SAMPLE_TEXT } from '@/lib/voiceOptions';
import { speakTutor } from '@/lib/tts';

export default function VoicePicker() {
  const ttsProvider = useNumeraStore((s) => s.ttsProvider);
  const ttsVoice = useNumeraStore((s) => s.ttsVoice);
  const setTtsVoice = useNumeraStore((s) => s.setTtsVoice);

  const [open, setOpen] = useState(false);
  const [customVoice, setCustomVoice] = useState('');
  const [mounted, setMounted] = useState(false); // portals need a client DOM
  const ref = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    // The dialog is portalled out of this subtree, so an outside-click test has
    // to check the dialog AND the trigger explicitly — the trigger would
    // otherwise close on mousedown and immediately reopen on click.
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (ref.current?.contains(t) || triggerRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey); };
  }, [open]);

  const selected = ttsProvider ? providerById(ttsProvider) : undefined;
  const triggerLabel = selected ? `${selected.label} · ${ttsVoice ?? 'default'}` : 'Backend default';

  const applyCustom = () => {
    const v = customVoice.trim();
    if (!v || !ttsProvider) return;
    setTtsVoice(ttsProvider, v);
  };

  return (
    <div className="relative">
      {/* Icon-only trigger: the tutor panel is 234px wide, so the current
          selection is shown inside the popover rather than on the button. */}
      <button
        ref={triggerRef}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label="Tutor voice (testing)"
        title={`Tutor voice (testing) — ${triggerLabel}`}
        className="w-6 h-6 rounded-md flex items-center justify-center text-slate-blue hover:bg-reading-surface hover:text-ink transition-colors"
      >
        <Volume2 size={15} strokeWidth={1.8} />
      </button>

      {open && mounted && createPortal(
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          {/* Backdrop. The panel used to be anchored under the trigger, which put
              it off-screen once the picker moved to the corner of a full-bleed
              screen — present in the DOM but unreadable. A centred dialog is
              position-independent, so it works wherever the trigger sits. */}
          <div className="absolute inset-0 bg-ink/40" aria-hidden="true" onClick={() => setOpen(false)} />
          <div
            ref={ref}
            className="relative w-full max-w-sm max-h-[80vh] overflow-y-auto rounded-xl border border-muted-gray bg-white"
            style={{ boxShadow: '0 18px 48px rgba(0,0,0,0.28)' }}
            role="dialog"
            aria-modal="true"
            aria-label="Tutor voice"
          >
            <div className="sticky top-0 flex items-center justify-between gap-3 px-3 py-2.5 border-b border-muted-gray bg-white">
              <span className="text-[13px] font-semibold text-ink">Tutor voice</span>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="w-7 h-7 rounded-md flex items-center justify-center text-slate-blue hover:bg-reading-surface hover:text-ink transition-colors"
              >
                <X size={16} strokeWidth={2} />
              </button>
            </div>
          <div className="px-3 pt-2 text-[11px] text-slate-blue">
            Current: <span className="font-semibold text-ink">{triggerLabel}</span>
          </div>
          <div className="px-3 py-2 border-b border-muted-gray text-[10px] font-semibold tracking-widest uppercase text-slate-blue">
            Tutor voice
          </div>

          <button
            onClick={() => { setTtsVoice(null, null); setOpen(false); }}
            className={
              'w-full text-left px-3 py-1.5 text-[12.5px] transition-colors ' +
              (!ttsProvider ? 'bg-reading-surface font-semibold text-ink' : 'hover:bg-reading-surface text-ink')
            }
          >
            Backend default
            <span className="block text-[10.5px] text-slate-blue">Whatever env is set to</span>
          </button>

          {VOICE_PROVIDERS.map((p) => (
            <div key={p.id} className="border-t border-muted-gray">
              <div className="px-3 pt-2 pb-1 text-[10px] font-semibold tracking-wide uppercase text-slate-blue">
                {p.label}
              </div>
              {p.voices.map((v) => {
                const isActive = ttsProvider === p.id && ttsVoice === v.id;
                return (
                  <button
                    key={v.id}
                    onClick={() => { setTtsVoice(p.id, v.id); setOpen(false); }}
                    className={
                      'w-full flex items-center justify-between gap-2 px-3 py-1.5 text-left transition-colors ' +
                      (isActive ? 'bg-reading-surface' : 'hover:bg-reading-surface')
                    }
                  >
                    <span className="text-[12.5px] text-ink">{v.label}</span>
                    {isActive && <span className="text-[10px] font-semibold text-ai-cyan">active</span>}
                  </button>
                );
              })}
              {p.browseAt && (
                <div className="px-3 pb-2 text-[10px] text-slate-blue/80">
                  More IDs at {p.browseAt} — paste below
                </div>
              )}
            </div>
          ))}

          {/* The lists above mirror each adapter's curated presets; this covers
              anything else a tester wants to try from the provider's playground. */}
          <div className="border-t border-muted-gray p-3 space-y-2">
            <div className="text-[10px] font-semibold tracking-wide uppercase text-slate-blue">
              Custom voice ID
            </div>
            <input
              value={customVoice}
              onChange={(e) => setCustomVoice(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && applyCustom()}
              placeholder={ttsProvider ? 'voice id / uuid' : 'pick a provider first'}
              disabled={!ttsProvider}
              className="w-full rounded border border-muted-gray px-2 py-1 text-[11.5px] text-ink placeholder:text-slate-blue/60 focus:outline-none focus:border-ai-cyan disabled:bg-reading-surface disabled:cursor-not-allowed"
            />
            <button
              onClick={applyCustom}
              disabled={!customVoice.trim() || !ttsProvider}
              className="w-full rounded bg-focus-navy text-white py-1.5 text-[11.5px] font-semibold hover:opacity-90 disabled:opacity-30 transition-opacity"
            >
              Use this voice
            </button>
            <button
              onClick={() => speakTutor(VOICE_SAMPLE_TEXT)}
              className="w-full flex items-center justify-center gap-1.5 rounded border border-muted-gray py-1.5 text-[11.5px] font-semibold text-ink hover:border-slate-blue transition-colors"
            >
              <Volume2 size={13} strokeWidth={1.9} /> Test voice
            </button>
          </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
