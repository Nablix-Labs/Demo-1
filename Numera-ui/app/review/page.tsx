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
import { demoFor, type DemoWorksheet } from '@/lib/demoContent';
import { cn } from '@/lib/cn';
import type { FiveCategorySummary, QuestionOutcome } from '@/lib/api';
import { speakTutor, stopTutorSpeech } from '@/lib/tts';

/** Real session outcomes rendered through the same worksheet layout. */
function outcomeWorksheets(outcomes: QuestionOutcome[]): DemoWorksheet[] {
  return outcomes.map((o) => ({
    question: o.question,
    correct: o.correct,
    student: [],
    voice: o.correct
      ? `You solved this correctly in ${o.attempts} attempt${o.attempts === 1 ? '' : 's'}${o.hint_level > 0 ? `, using a level ${o.hint_level} hint` : ''}. Well done.`
      : `This one isn't solved yet after ${o.attempts} attempt${o.attempts === 1 ? '' : 's'}. We will come back to it together.`,
  }));
}

/** Tutor's red pen — the only colour outside the grayscale system, by design. */
const INK = '#b42318';

// ── Speech ────────────────────────────────────────────────────────────────
// OpenAI audio via /voice/tts with browser speechSynthesis as the fallback.
function speak(text: string, onEnd: () => void) {
  speakTutor(text, onEnd);
}
function stopSpeaking() {
  stopTutorSpeech();
}

/** Human labels for the engine's five review categories, in delivery order. */
const REVIEW_CATEGORY_LABELS: [keyof FiveCategorySummary, string][] = [
  ['category_1_strength', 'Strength'],
  ['category_2_first_error', 'First error'],
  ['category_3_pattern', 'Pattern'],
  ['category_4_next_practice', 'Next practice'],
  ['category_5_mastery', 'Mastery'],
];

export default function ReviewPage() {
  const [i, setI] = useState(0);
  const [showMarks, setShowMarks] = useState(false);
  const [speakingId, setSpeakingId] = useState<string | null>(null);

  const completePhase = useNumeraStore((s) => s.completePhase);
  const currentTopicId = useNumeraStore((s) => s.currentTopicId);
  const sessionSummary = useNumeraStore((s) => s.sessionSummary);
  const sessionReview = useNumeraStore((s) => s.sessionReview);
  const { decideReview, goStage } = useFlowNav();

  // Real session outcomes when the backend sent them; demo worksheets otherwise.
  const demo = demoFor(currentTopicId);
  const outcomes = sessionSummary?.outcomes ?? [];
  const live = outcomes.length > 0;
  const WORKSHEETS = live ? outcomeWorksheets(outcomes) : demo.worksheets;

  const total = WORKSHEETS.length;
  const done = i >= total;                 // past the last sheet → final summary
  const ws = WORKSHEETS[Math.min(i, total - 1)];
  const score = WORKSHEETS.filter((w) => w.correct).length;
  // The engine's natural-language review is shown verbatim; the sentence built
  // from outcome counts is only the fallback when no review was returned.
  const SUMMARY = sessionReview
    ? sessionReview.student_facing_summary
    : live
      ? `You worked through ${total} question${total === 1 ? '' : 's'} this session and solved ${score} of them. ${score === total ? 'Excellent work — you are ready to move on.' : 'Let us keep practising the ones that got away.'}`
      : demo.reviewSummary;
  const reviewCategories = sessionReview
    ? REVIEW_CATEGORY_LABELS.filter(([key]) => sessionReview.five_category_summary[key] !== null)
    : [];

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
        {/* Ended-session summary from /session/end (attempts, hints used). */}
        {sessionSummary && (
          <div className="rounded-lg border border-muted-gray bg-white px-5 py-4">
            <div className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue mb-3">
              Session summary
            </div>
            <div className="flex flex-wrap gap-x-10 gap-y-3">
              <div>
                <div className="text-[22px] font-semibold text-ink leading-none">{sessionSummary.attempts}</div>
                <div className="text-[11px] text-slate-blue mt-1">Attempts</div>
              </div>
              <div>
                <div className="text-[22px] font-semibold text-ink leading-none">{sessionSummary.hints_used}</div>
                <div className="text-[11px] text-slate-blue mt-1">Hints used</div>
              </div>
              {sessionSummary.question && (
                <div className="min-w-0">
                  <div className="text-[15px] font-semibold text-ink leading-tight font-[Cambria_Math,Georgia,serif] truncate">
                    {sessionSummary.question}
                  </div>
                  <div className="text-[11px] text-slate-blue mt-1">Question</div>
                </div>
              )}
            </div>
          </div>
        )}

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

            {/* Engine review — the five categories, shown verbatim (nulls omitted). */}
            {reviewCategories.length > 0 && sessionReview && (
              <div className="rounded-lg border border-muted-gray divide-y divide-muted-gray overflow-hidden">
                {reviewCategories.map(([key, label]) => (
                  <div key={key} className="px-5 py-3.5">
                    <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-1">{label}</div>
                    <p className="text-[13.5px] text-ink leading-relaxed">
                      {sessionReview.five_category_summary[key]}
                    </p>
                  </div>
                ))}
                {sessionReview.b6_hook && (
                  <div className="px-5 py-3.5 bg-reading-surface">
                    <p className="text-[13.5px] text-ink leading-relaxed italic">{sessionReview.b6_hook}</p>
                  </div>
                )}
              </div>
            )}

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

            {/* Decision point. With a live engine review the backend's
                call_to_action decides the (single) next step; the manual
                three-way choice remains the mock-mode flow. */}
            {sessionReview ? (
              sessionReview.call_to_action !== 'NONE' && (
                <div className="mt-6 rounded-lg border border-muted-gray bg-reading-surface p-4">
                  <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-3">What happens next</div>
                  {sessionReview.call_to_action === 'CONTINUE_PRACTICE' ? (
                    <button
                      onClick={() => goStage('practice', currentTopicId)}
                      className="rounded-md border border-focus-navy bg-focus-navy px-4 py-3 text-left text-white hover:opacity-80 transition-opacity"
                    >
                      <div className="text-[13px] font-semibold">Continue practising</div>
                      <div className="text-[11.5px] text-white/70 mt-0.5">More practice on this topic.</div>
                    </button>
                  ) : (
                    <button
                      onClick={() => decideReview('pass')}
                      className="rounded-md border border-focus-navy bg-focus-navy px-4 py-3 text-left text-white hover:opacity-80 transition-opacity"
                    >
                      <div className="text-[13px] font-semibold">Next topic</div>
                      <div className="text-[11.5px] text-white/70 mt-0.5">On to the next topic.</div>
                    </button>
                  )}
                </div>
              )
            ) : (
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
            )}
          </div>
        )}
      </div>
    </PageShell>
    </PhaseGate>
  );
}
