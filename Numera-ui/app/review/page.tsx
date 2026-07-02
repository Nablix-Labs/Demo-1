'use client';

/**
 * Review & Feedback — tutor correction flow.
 *
 * After Independent Practice, each submitted worksheet is reviewed one by one,
 * like a teacher checking a notebook. Two layers:
 *   • Student layer  — the original work, never edited.
 *   • Tutor layer    — an overlay of marks (ticks, a circle on the slip, a
 *                      short label, and the corrected steps in red "ink").
 * The tutor mainly explains by voice; the canvas only marks the key points.
 * A final spoken summary closes the session.
 */

import { useState, useCallback, useEffect } from 'react';
import {
  Check, X, ChevronLeft, ChevronRight, Volume2, Square, Eye, EyeOff,
} from 'lucide-react';
import PageShell, { Chip } from '@/components/PageShell';
import PhaseGate from '@/components/PhaseGate';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useFlowNav } from '@/lib/useFlowNav';
import { demoFor } from '@/lib/demoContent';
import { cn } from '@/lib/cn';

/** Tutor's red pen — the only colour outside the grayscale system, by design. */
const INK = '#b42318';

// ── Speech ────────────────────────────────────────────────────────────────
function speak(text: string, onEnd: () => void) {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) { onEnd(); return; }
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 0.98;
  u.onend = onEnd;
  u.onerror = onEnd;
  window.speechSynthesis.speak(u);
}
function stopSpeaking() {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel();
}

export default function ReviewPage() {
  const [i, setI] = useState(0);
  const [showMarks, setShowMarks] = useState(false);
  const [speakingId, setSpeakingId] = useState<string | null>(null);

  const completePhase = useNumeraStore((s) => s.completePhase);
  const currentTopicId = useNumeraStore((s) => s.currentTopicId);
  const { decideReview } = useFlowNav();

  // Worksheets + summary for the placed topic.
  const demo = demoFor(currentTopicId);
  const WORKSHEETS = demo.worksheets;
  const SUMMARY = demo.reviewSummary;

  const total = WORKSHEETS.length;
  const done = i >= total;                 // past the last sheet → final summary
  const ws = WORKSHEETS[Math.min(i, total - 1)];
  const score = WORKSHEETS.filter((w) => w.correct).length;

  // Reaching the final summary clears the review phase.
  useEffect(() => {
    if (done) completePhase('review');
  }, [done, completePhase]);

  const stop = useCallback(() => { stopSpeaking(); setSpeakingId(null); }, []);

  const play = useCallback((id: string, text: string) => {
    if (speakingId === id) { stop(); return; }
    if (id !== 'summary') setShowMarks(true);
    setSpeakingId(id);
    speak(text, () => setSpeakingId(null));
  }, [speakingId, stop]);

  const goto = (next: number) => { stop(); setShowMarks(false); setI(next); };

  return (
    <PhaseGate phase="review">
    <PageShell
      title="Review & feedback"
      subtitle={`${demo.label} · today`}
      action={<Chip tone="solid">{score} / {total}</Chip>}
    >
      <div className="flex flex-col gap-6 max-w-3xl">
        {/* Worksheet progress */}
        <div className="flex items-center gap-1.5">
          {WORKSHEETS.map((w, idx) => (
            <button
              key={idx}
              onClick={() => goto(idx)}
              title={`Worksheet ${idx + 1}`}
              className={cn(
                'h-1.5 flex-1 rounded-full transition-colors',
                idx === i ? 'bg-focus-navy' : idx < i ? 'bg-slate-blue' : 'bg-reading-surface'
              )}
            />
          ))}
          <button
            onClick={() => goto(total)}
            title="Summary"
            className={cn('h-1.5 w-1.5 rounded-full transition-colors', done ? 'bg-focus-navy' : 'bg-reading-surface')}
          />
        </div>

        {!done ? (
          <>
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue">
                Worksheet {i + 1} of {total}
              </div>
              <button
                onClick={() => setShowMarks((v) => !v)}
                className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-slate-blue hover:text-ink transition-colors"
              >
                {showMarks ? <><EyeOff size={14} strokeWidth={1.8} /> Hide tutor marks</> : <><Eye size={14} strokeWidth={1.8} /> Show tutor marks</>}
              </button>
            </div>

            {/* Paper — student layer with tutor overlay */}
            <div
              className="relative rounded-lg border border-muted-gray bg-white px-6 py-6 overflow-hidden"
              style={{
                backgroundImage:
                  'linear-gradient(#eef0f2 1px, transparent 1px), linear-gradient(90deg, #eef0f2 1px, transparent 1px)',
                backgroundSize: '26px 26px',
              }}
            >
              <div className="mb-4 inline-flex items-center gap-2">
                <Chip tone="outline">Question {i + 1}</Chip>
                <span className="text-[17px] text-ink font-[Cambria_Math,Georgia,serif]">{ws.question}</span>
              </div>

              {/* Student working */}
              <div className="flex flex-col gap-2">
                {ws.student.map((ln, idx) => (
                  <div key={idx} className="flex items-center gap-3 min-h-[30px]">
                    {/* tutor tick / cross gutter */}
                    <span className="w-5 flex-shrink-0 flex items-center justify-center">
                      {showMarks && ln.mark === 'tick' && <Check size={16} strokeWidth={2.6} style={{ color: INK }} />}
                      {showMarks && ln.mark === 'cross' && <X size={16} strokeWidth={2.6} style={{ color: INK }} />}
                    </span>
                    {/* student ink (unchanged) — optionally circled by tutor */}
                    <span
                      className="text-[17px] text-ink font-[Cambria_Math,Georgia,serif] px-1.5 py-0.5 transition-all"
                      style={showMarks && ln.circle ? { boxShadow: `0 0 0 2px ${INK}`, borderRadius: '45% 48% 46% 50%' } : undefined}
                    >
                      {ln.text}
                    </span>
                    {/* tutor label in red */}
                    {showMarks && ln.label && (
                      <span className="text-[12px] font-semibold italic" style={{ color: INK }}>
                        ← {ln.label}
                      </span>
                    )}
                  </div>
                ))}

                {/* tutor corrected steps, written in red below the slip */}
                {showMarks && ws.corrections && (
                  <div className="mt-1 ml-8 pl-3 flex flex-col gap-1" style={{ borderLeft: `2px solid ${INK}` }}>
                    {ws.corrections.map((c, idx) => (
                      <span key={idx} className="text-[16px] font-[Cambria_Math,Georgia,serif]" style={{ color: INK }}>
                        {c}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Tutor voice */}
            <div className="rounded-lg border border-muted-gray bg-reading-surface px-5 py-4">
              <div className="flex items-center justify-between gap-3 mb-2">
                <span className="text-[10px] tracking-widest uppercase text-slate-blue">Tutor</span>
                <button
                  onClick={() => play(`ws-${i}`, ws.voice)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-focus-navy px-3 py-1.5 text-[12px] font-semibold text-ink hover:bg-focus-navy hover:text-white transition-colors"
                >
                  {speakingId === `ws-${i}` ? <><Square size={13} strokeWidth={2.2} /> Stop</> : <><Volume2 size={14} strokeWidth={1.9} /> Read out loud</>}
                </button>
              </div>
              <p className="text-[13.5px] text-ink leading-relaxed">{ws.voice}</p>
            </div>

            {/* Navigation */}
            <div className="flex items-center justify-between">
              <button
                onClick={() => goto(Math.max(0, i - 1))}
                disabled={i === 0}
                className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-slate-blue hover:text-ink disabled:opacity-30 disabled:hover:text-slate-blue transition-colors"
              >
                <ChevronLeft size={15} strokeWidth={1.8} /> Previous
              </button>
              <button
                onClick={() => goto(i + 1)}
                className="inline-flex items-center gap-1.5 rounded-md bg-focus-navy text-white px-5 py-2.5 text-[13px] font-semibold hover:opacity-80 transition-opacity"
              >
                {i + 1 < total ? <>Next worksheet <ChevronRight size={15} strokeWidth={1.8} /></> : <>Finish & summary <ChevronRight size={15} strokeWidth={1.8} /></>}
              </button>
            </div>
          </>
        ) : (
          /* Final spoken summary */
          <div className="flex flex-col gap-6">
            <div className="rounded-lg border border-focus-navy bg-reading-surface px-6 py-5">
              <div className="flex items-center justify-between gap-3 mb-2">
                <div className="text-[10px] tracking-widest uppercase text-slate-blue">Final feedback · {score} of {total} correct</div>
                <button
                  onClick={() => play('summary', SUMMARY)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-focus-navy px-3 py-1.5 text-[12px] font-semibold text-ink hover:bg-focus-navy hover:text-white transition-colors"
                >
                  {speakingId === 'summary' ? <><Square size={13} strokeWidth={2.2} /> Stop</> : <><Volume2 size={14} strokeWidth={1.9} /> Read out loud</>}
                </button>
              </div>
              <p className="text-[14px] text-ink leading-relaxed">{SUMMARY}</p>
            </div>

            {/* Per-worksheet recap */}
            <div className="rounded-lg border border-muted-gray divide-y divide-muted-gray overflow-hidden">
              {WORKSHEETS.map((w, idx) => (
                <button
                  key={idx}
                  onClick={() => goto(idx)}
                  className="w-full flex items-center gap-4 px-5 py-3.5 text-left hover:bg-reading-surface transition-colors"
                >
                  <span className={cn('flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center', w.correct ? 'bg-focus-navy text-white' : 'border border-muted-gray text-slate-blue')}>
                    {w.correct ? <Check size={13} strokeWidth={2.4} /> : <X size={13} strokeWidth={2.4} />}
                  </span>
                  <span className="text-[15px] text-ink font-[Cambria_Math,Georgia,serif] flex-1">{w.question}</span>
                  <ChevronRight size={15} strokeWidth={1.8} className="text-slate-blue" />
                </button>
              ))}
            </div>

            <button
              onClick={() => goto(total - 1)}
              className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-slate-blue hover:text-ink transition-colors"
            >
              <ChevronLeft size={15} strokeWidth={1.8} /> Back to worksheets
            </button>

            {/* Decision point — where the tutor routes the student next. */}
            <div className="mt-6 rounded-lg border border-muted-gray bg-reading-surface p-4">
              <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-3">What happens next</div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                <button
                  onClick={() => decideReview('foundation_weak')}
                  className="rounded-md border border-muted-gray bg-white px-3 py-3 text-left hover:border-focus-navy transition-colors"
                >
                  <div className="text-[13px] font-semibold text-ink">Foundation weak</div>
                  <div className="text-[11.5px] text-slate-blue mt-0.5">Recap the concept — back to orientation.</div>
                </button>
                <button
                  onClick={() => decideReview('cant_solve')}
                  className="rounded-md border border-muted-gray bg-white px-3 py-3 text-left hover:border-focus-navy transition-colors"
                >
                  <div className="text-[13px] font-semibold text-ink">Can&apos;t solve yet</div>
                  <div className="text-[11.5px] text-slate-blue mt-0.5">Knows it, needs help applying — back to guided.</div>
                </button>
                <button
                  onClick={() => decideReview('pass')}
                  className="rounded-md border border-focus-navy bg-focus-navy px-3 py-3 text-left text-white hover:opacity-80 transition-opacity"
                >
                  <div className="text-[13px] font-semibold">Mastered</div>
                  <div className="text-[11.5px] text-white/70 mt-0.5">On to the next topic.</div>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </PageShell>
    </PhaseGate>
  );
}
