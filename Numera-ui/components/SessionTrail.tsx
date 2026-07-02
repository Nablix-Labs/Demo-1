'use client';

/**
 * SessionTrail — renders the current session's interaction trail from the store.
 *
 * The backend keeps no transcript and resets on reload, so this is the frontend's
 * own record of the run (question / answer / canvas / tutor / hint). Renders
 * nothing until there's at least one entry, so it stays out of the way on a cold
 * History page.
 */
import { useNumeraStore } from '@/store/useNumeraStore';
import type { TrailKind } from '@/store/useNumeraStore';

const LABELS: Record<TrailKind, string> = {
  question: 'Question',
  answer: 'Your answer',
  canvas: 'Canvas / OCR',
  tutor: 'Tutor',
  hint: 'Hint',
};

const ACCENT: Record<TrailKind, string> = {
  question: '#1B2A4A', // focus-navy
  answer: '#4169E1', // learning-blue (student)
  canvas: '#008B8B', // dark-cyan (OCR / working)
  tutor: '#00B4D8', // ai-cyan (AI)
  hint: '#FF9F1C', // highlight-amber
};

export default function SessionTrail() {
  const trail = useNumeraStore((s) => s.interactionTrail);
  if (trail.length === 0) return null;

  return (
    <section className="mb-8">
      <h2 className="text-[13px] font-semibold tracking-wide uppercase text-slate-blue mb-3">
        Current session
      </h2>
      <ol className="rounded-lg border border-muted-gray divide-y divide-muted-gray overflow-hidden">
        {trail.map((e) => (
          <li key={e.id} className="flex items-start gap-4 px-5 py-3">
            <span
              className="flex-shrink-0 mt-1 inline-block w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: ACCENT[e.kind] }}
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-blue">
                  {LABELS[e.kind]}
                </span>
                {e.meta && (
                  <span className="text-[11px] text-slate-blue/70">{e.meta}</span>
                )}
              </div>
              <p className="text-[13.5px] text-ink leading-snug mt-0.5 break-words">
                {e.text}
              </p>
            </div>
            <time className="flex-shrink-0 text-[11px] text-slate-blue/70 tabular-nums">
              {new Date(e.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </time>
          </li>
        ))}
      </ol>
    </section>
  );
}
