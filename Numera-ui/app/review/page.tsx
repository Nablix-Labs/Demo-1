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

import { useState, useCallback, useEffect, useRef } from 'react';
import {
  Check, X, ChevronLeft, ChevronRight, Volume2, Square, Eye, EyeOff,
} from 'lucide-react';
import PageShell, { Chip } from '@/components/PageShell';
import PhaseGate from '@/components/PhaseGate';
import { planReviewCompletion, runReviewFinish } from '@/lib/reviewCompletion';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useDemoTutor, resetSessionStart } from '@/hooks/useDemoTutor';
import { useFlowNav } from '@/lib/useFlowNav';
import { demoFor, type DemoWorksheet } from '@/lib/demoContent';
import { cn } from '@/lib/cn';
import {
  sessionTopicTitle, completeReview, studentId, getSession,
  type FiveCategorySummary, type QuestionOutcome, type NextTopicHandoff,
} from '@/lib/api';
import { reviewIsReady, isReviewUnavailable } from '@/lib/reviewReady';
import { phase4FromSession, type SessionForPhase4 } from '@/lib/phase4FromSession';
import { handoffDestination } from '@/lib/usePhaseRouting';
import { reviewSource } from '@/lib/reviewContent';
import { speakTutor, stopTutorSpeech } from '@/lib/tts';
import Phase4Review from '@/components/Phase4/Phase4Review';

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
  const [endFailed, setEndFailed] = useState<'empty' | 'failed' | null>(null);

  const completePhase = useNumeraStore((s) => s.completePhase);
  const currentTopicId = useNumeraStore((s) => s.currentTopicId);
  const sessionSummary = useNumeraStore((s) => s.sessionSummary);
  const backendSession = useNumeraStore((s) => s.backendSession);
  const sessionReview = useNumeraStore((s) => s.sessionReview);
  const { decideReview, goStage } = useFlowNav();
  const tutor = useDemoTutor();

  const { apiEnabled, sessionId, end } = tutor;
  // Hold the id so it survives end() clearing it on the way OUT. The completion
  // event belongs to the moment the student finishes the review.
  const reviewSessionId = useRef<string | null>(null);
  if (sessionId && !reviewSessionId.current) reviewSessionId.current = sessionId;

  // Arriving here is NOT the session end.
  //
  // This used to call end() on mount, on the reasoning that reaching Review
  // meant the session was over. It is the opposite way round: Review is a phase
  // the student works through, and /session/end neither emits REVIEW_COMPLETED
  // nor transitions anything -- it just marks the record ended. Ending on
  // arrival therefore closed the session before the student had done the one
  // thing this screen exists for, and REVIEW_COMPLETED (the event that actually
  // advances the Student Model past Review) went out against a session already
  // marked ended. The session is now ended on the way out, after completion.

  // A review the backend could not prepare. Distinct from "no review" and from
  // "nothing graded": generation failed and asking again may well work, so the
  // student is offered a retry rather than an apology.
  const [reviewBlocked, setReviewBlocked] = useState(false);
  const [retrying, setRetrying] = useState(false);
  /**
   * Has the first read of the session finished, either way?
   *
   * On first paint `phase4` is null and `reviewBlocked` is false, so neither
   * gate below catches — and the page fell through to the legacy worksheet UI,
   * which flashed "You worked through 0 questions" before the mount read
   * resolved. The mount read does rescue it; the defect is the gap before that,
   * and the missing state is "in flight, not yet known".
   */
  const [resolved, setResolved] = useState(false);
  const retryReview = useCallback(async () => {
    const id = reviewSessionId.current;
    if (!id) return;
    setRetrying(true);
    try {
      const fresh = await getSession(id);
      useNumeraStore.getState().setBackendSession(fresh);
      // Only clear the blocked state when the review is genuinely there;
      // otherwise the screen would fall through to a Phase 4 it cannot render.
      setReviewBlocked(!reviewIsReady(fresh));
    } catch (err) {
      setReviewBlocked(isReviewUnavailable(err));
    } finally {
      setRetrying(false);
      setResolved(true);
    }
  }, []);

  // Ask once on arrival: a student routed here by the backend has not been
  // through the practice screen's readiness check.
  useEffect(() => {
    if (apiEnabled && reviewSessionId.current && !reviewIsReady(backendSession)) {
      void retryReview();
    } else {
      // Nothing to wait for: no session to read, or the review is already here.
      setResolved(true);
    }
    // Deliberately mount-only — this is the initial read, and retryReview is
    // the button for every read after it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The same rescue as the mount read above, for a refresh AFTER the session
  // has been ended.
  //
  // `backendSession` is not persisted, so a reload always arrives with the
  // record gone and has to fetch it back. Which id to fetch depends on where in
  // the review the student was:
  //
  //   • still working through it — the session is open, `sessionId` persisted,
  //     and retryReview() above uses it. That is the ordinary refresh.
  //   • already finished it — ending happens on the way out and clears
  //     `sessionId`, so retryReview has no id to use and the screen would show
  //     "nothing to review yet" for work the student had just completed.
  //
  // The second case is this effect, keyed on the ended id kept for exactly this
  // (see NumeraState.endedSessionId). GET /session serves an ended session and
  // does not strip `phase4_review`, so the review comes back from the backend
  // and only an ID was ever stored on the device.
  //
  // Guarded on `!sessionId` so the two never both fire: a live session belongs
  // to retryReview, which also knows how to report a failed generation.
  const endedSessionId = useNumeraStore((s) => s.endedSessionId);
  const setBackendSession = useNumeraStore((s) => s.setBackendSession);
  const restoring = useRef(false);
  useEffect(() => {
    if (!apiEnabled || sessionId || backendSession || !endedSessionId) return;
    if (restoring.current) return;
    restoring.current = true;
    getSession(endedSessionId, studentId())
      .then((rec) => setBackendSession(rec))
      // Degrade to the empty state, which is what this screen already shows
      // when there is nothing to review. A session the backend has forgotten
      // (its store is in memory) is not an error the student can act on.
      .catch(() => { restoring.current = false; });
  }, [apiEnabled, sessionId, backendSession, endedSessionId, setBackendSession]);



  // Escape hatch for a session the backend refuses to end: drop it locally so
  // a fresh one can start, and go back to the lesson to produce reviewable work.
  /**
   * Report the review as finished, on the way out. Awaited, in order.
   *
   * `REVIEW_COMPLETED` is what advances the Student Model past Review;
   * `/session/end` does not emit it, so without this a student who works all the
   * way through Phase 4 is never recorded as having done so.
   *
   * This was fire-and-forget, on the reasoning that a slow call should not hold
   * the student on a screen they had asked to leave. The cost was silent: a
   * REVIEW_COMPLETED that failed left the Student Model still in Review, so the
   * next session reopened into a topic the student had finished, and nobody
   * learned why. It is also ordered -- completion before end -- because ending
   * first marks the session done while the event that closes the phase has not
   * landed.
   *
   * Returns false when the student should stay put.
   */
  const reportReviewFinished = useCallback(async (): Promise<NextTopicHandoff | null> => {
    if (!apiEnabled) return null;
    const plan = planReviewCompletion(reviewSessionId.current, () => `REVIEW-COMPLETE-${Date.now()}`);
    if (!plan.send) return null;
    const res = await completeReview(reviewSessionId.current!, studentId(), plan.turnId);
    // `completeReview` answers null on failure by design, so a bookkeeping
    // problem cannot trap the student on this screen. That is deliberate and
    // stays — but the caller must still know, or the retry it offers is a
    // button for a failure it never sees.
    if (res === null) throw new Error('review/complete did not land');
    return res.next_topic_handoff ?? null;
  }, [apiEnabled]);

  const [leaving, setLeaving] = useState(false);
  const [leaveError, setLeaveError] = useState<string | null>(null);
  /** The outcome to retry with, set only when a step actually failed. */
  const [retryOutcome, setRetryOutcome] = useState<Parameters<typeof decideReview>[0] | null>(null);

  const finishReview = useCallback(async (outcome: Parameters<typeof decideReview>[0]) => {
    setLeaveError(null);
    setRetryOutcome(null);
    setLeaving(true);
    // Neither step may fail silently — see runReviewFinish. Retrying is safe:
    // planReviewCompletion refuses a second REVIEW_COMPLETED for this session,
    // so a retry re-attempts only what did not land.
    let handoff: NextTopicHandoff | null = null;
    const outcomeOf = await runReviewFinish({
      reportCompletion: async () => { handoff = await reportReviewFinished(); },
      endSession: async () => { if (apiEnabled && sessionId) await end(); },
    });
    setLeaving(false);
    if (outcomeOf.ok) {
      // The backend decides what comes next. `decideReview` walks a hardcoded
      // TOPICS table, which handed the student a topic the Student Model had
      // already completed — so it reopened in REVIEW and they came straight
      // back here, every time. It is kept only for mock mode and for a genuinely
      // absent handoff, which means the curriculum has ended.
      const next = handoffDestination(handoff);
      if (next) {
        resetSessionStart();
        const store = useNumeraStore.getState();
        store.clearSessionId();
        store.setEndedSessionId(null);
        store.completePhase('review');
        // Unlock the gate for the phase the backend is sending them to, or
        // PhaseGate bounces them straight back out of it.
        store.setCurrentTopic(next.topicId);
        store.setPendingTopicCode(next.topicId);
        goStage(next.unlock, next.topicId);
        return;
      }
      decideReview(outcome);
      return;
    }
    setRetryOutcome(outcome);
    setLeaveError(
      outcomeOf.stage === 'complete'
        ? "We couldn't record that you finished this review. Your work is saved — try again."
        : "Your review is recorded, but we couldn't close the session. Try again.",
    );
  }, [reportReviewFinished, decideReview, apiEnabled, sessionId, end]);

  const backToLesson = useCallback(async () => {
    await reportReviewFinished().catch(() => undefined);
    resetSessionStart();
    useNumeraStore.getState().clearSessionId();
    goStage('guided', currentTopicId);
  }, [reportReviewFinished, goStage, currentTopicId]);

  // Real session outcomes when the backend sent them; demo worksheets otherwise.
  const demo = demoFor(currentTopicId);
  const outcomes = sessionSummary?.outcomes ?? [];
  // Which of the three sources this screen may draw on — see lib/reviewContent
  // for why this is a mode question and not an outcome-count question.
  const source = reviewSource(apiEnabled, outcomes.length);
  const live = source !== 'demo';
  const WORKSHEETS = live ? outcomeWorksheets(outcomes) : demo.worksheets;

  // Row 42: the header read "Linear equations · today" for every student,
  // because it used the mock worksheet's label even on a real session — so a
  // student who had spent the lesson on "What Is Algebra?" was told otherwise.
  // The demo label is correct for demo worksheets and wrong for anything else;
  // when the session is real and unnamed, say only when it happened.
  const topicLabel = live ? sessionTopicTitle(backendSession) : demo.label;
  const subtitle = [topicLabel, 'today'].filter(Boolean).join(' · ');

  /**
   * Phase 4 replaces this screen the moment the backend produces one.
   *
   * There is no endpoint: Chiru's orchestration (PR #156) generates the review
   * on entering Review and attaches it to the session record, so /session/end
   * already carries it and no second request is needed. `phase4FromSession`
   * owns reading it and says what is still missing from that payload.
   *
   * Additive rather than a rewrite — a session that produced no review (an
   * older backend, a generation that failed, a topic that never reached
   * Review) falls through to the screen below exactly as before.
   */
  const phase4 = phase4FromSession(
    backendSession as SessionForPhase4 | null,
    topicLabel || 'This topic',
  );

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

  // Phase 4 (§8). Takes precedence over everything below: when the backend has
  // produced a real review, no fallback is relevant.
  // In flight. Returns EARLY rather than falling through: below this point the
  // legacy worksheet screen renders, and on a live session it renders demo
  // content — which is what flashed "You worked through 0 questions" at a
  // student whose review was still being read.
  if (apiEnabled && !phase4 && !resolved) {
    return (
      <PhaseGate phase="review">
        <PageShell title="Review &amp; feedback" subtitle={subtitle}>
          <div
            role="status"
            aria-busy="true"
            className="rounded-lg border border-muted-gray bg-white px-6 py-8 flex flex-col gap-3"
          >
            <div className="flex items-center gap-2 text-[13px] font-semibold text-ink">
              <span className="w-3.5 h-3.5 rounded-full border-2 border-muted-gray border-t-focus-navy animate-spin" />
              Preparing your review…
            </div>
            <div className="flex flex-col gap-2" aria-hidden="true">
              <div className="h-3 w-2/3 rounded bg-reading-surface" />
              <div className="h-3 w-1/2 rounded bg-reading-surface" />
              <div className="h-3 w-3/5 rounded bg-reading-surface" />
            </div>
          </div>
        </PageShell>
      </PhaseGate>
    );
  }

  if (phase4) {
    return (
      <PhaseGate phase="review">
        <PageShell title="Review &amp; feedback" subtitle={phase4.topic_title} wide>
          <Phase4Review
            review={phase4}
            onEnd={() => {
              completePhase('review');
              // §6.9 makes routing the backend's decision, and
              // `recommended_next_action` carries it — but the specification
              // never enumerates its values (START_NEXT_TOPIC is the only one
              // shown, in an example). Until Chiru confirms the vocabulary,
              // this takes the existing pass route rather than branching on a
              // string we would be guessing at.
              void finishReview('pass');
            }}
          />
          {leaveError && (
            <div role="alert" className="mt-4 flex flex-wrap items-center gap-3">
              <p className="text-[13px] text-action-orange">{leaveError}</p>
              {retryOutcome && (
                <button
                  onClick={() => void finishReview(retryOutcome)}
                  disabled={leaving}
                  aria-busy={leaving}
                  className="rounded-full border border-focus-navy bg-white px-4 py-1.5 text-[12px] font-semibold text-ink hover:bg-focus-navy hover:text-white transition-colors disabled:opacity-60"
                >
                  {leaving ? 'Trying again…' : 'Try again'}
                </button>
              )}
            </div>
          )}
        </PageShell>
      </PhaseGate>
    );
  }

  // The backend is in Review but could not prepare one. Retryable, and
  // deliberately ABOVE the empty state: "nothing to review yet" is the wrong
  // thing to tell a student who has work waiting behind a failed generation.
  // The session id is kept, because it is the argument to the retry.
  if (apiEnabled && reviewBlocked) {
    return (
      <PhaseGate phase="review">
        <PageShell title="Review &amp; feedback" subtitle={subtitle}>
          <div className="rounded-lg border border-muted-gray bg-white px-6 py-8 flex flex-col items-start gap-3">
            <div className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue">
              Review could not be prepared
            </div>
            <p className="text-[14px] text-ink leading-relaxed max-w-prose">
              Your work is saved. We could not put your review together just now —
              try again in a moment.
            </p>
            <button
              onClick={() => void retryReview()}
              disabled={retrying}
              aria-busy={retrying}
              className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-focus-navy text-white px-5 py-2.5 text-[13px] font-semibold hover:opacity-80 transition-opacity disabled:opacity-60"
            >
              {retrying ? 'Trying again…' : <>Try again <ChevronRight size={15} strokeWidth={1.8} /></>}
            </button>
          </div>
        </PageShell>
      </PhaseGate>
    );
  }

  // Nothing to look back over — showing demo worksheets here would present
  // fabricated results as the student's own.
  //
  // Two ways to arrive: the end failed outright, or it succeeded and graded
  // nothing. The second was falling through to the demo, because it has a
  // sessionSummary and no endFailed — it just has an empty outcome list.
  // Phase 4 has already returned above, so this cannot hide a real review.
  const nothingGraded = source === 'none';
  if (apiEnabled && ((endFailed && !sessionSummary) || nothingGraded)) {
    return (
      <PhaseGate phase="review">
        <PageShell title="Review & feedback" subtitle={subtitle}>
          <div className="rounded-lg border border-muted-gray bg-white px-6 py-8 flex flex-col items-start gap-3">
            <div className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue">
              {endFailed === 'empty' || nothingGraded ? 'Nothing to review yet' : 'Review unavailable'}
            </div>
            <p className="text-[14px] text-ink leading-relaxed max-w-prose">
              {endFailed === 'empty' || nothingGraded
                ? 'This session ended before any questions were completed, so there is no work to look back over. Head back to the lesson and solve a question or two — the review will be waiting.'
                : 'Your session review could not be loaded. Head back to the lesson and try again in a moment.'}
            </p>
            <button
              onClick={() => void backToLesson()}
              className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-focus-navy text-white px-5 py-2.5 text-[13px] font-semibold hover:opacity-80 transition-opacity"
            >
              Back to the lesson <ChevronRight size={15} strokeWidth={1.8} />
            </button>
          </div>
        </PageShell>
      </PhaseGate>
    );
  }

  return (
    <PhaseGate phase="review">
    <PageShell
      title="Review & feedback"
      subtitle={subtitle}
      action={<Chip tone="solid">{score} / {total}</Chip>}
    >
      <div className="flex flex-col gap-6">
        {/* Ended-session summary from /session/end (attempts, hints used). */}
        {sessionSummary && (
          <div className="rounded-lg border border-muted-gray bg-white px-5 py-4">
            <div className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue mb-3">
              Session summary
            </div>
            {/* Totals come from the backend's own counters and are shown only
                when it sent them — see SessionPerformance. The screen saying
                nothing is recoverable; the screen stating a number the session
                did not produce is not. */}
            <div className="flex flex-wrap gap-x-10 gap-y-3">
              {sessionSummary.performance ? (
                <>
                  <div>
                    <div className="text-[22px] font-semibold text-ink leading-none tabular-nums">
                      {sessionSummary.performance.total_attempts}
                    </div>
                    <div className="text-[11px] text-slate-blue mt-1">Attempts</div>
                  </div>
                  <div>
                    <div className="text-[22px] font-semibold text-ink leading-none tabular-nums">
                      {sessionSummary.performance.correct_attempts}
                      <span className="text-[13px] font-normal text-slate-blue">
                        {' '}/ {sessionSummary.performance.incorrect_attempts} wrong
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-blue mt-1">Correct</div>
                  </div>
                  <div>
                    <div className="text-[22px] font-semibold text-ink leading-none tabular-nums">
                      {sessionSummary.performance.independent_attempts}
                    </div>
                    <div className="text-[11px] text-slate-blue mt-1">Independent attempts</div>
                  </div>
                  <div>
                    <div className="text-[22px] font-semibold text-ink leading-none tabular-nums">
                      {sessionSummary.performance.hints_used}
                    </div>
                    <div className="text-[11px] text-slate-blue mt-1">Hints used</div>
                  </div>
                  <div>
                    <div className="text-[22px] font-semibold text-ink leading-none tabular-nums">
                      {sessionSummary.performance.canvas_submissions}
                    </div>
                    <div className="text-[11px] text-slate-blue mt-1">Canvas submissions</div>
                  </div>
                </>
              ) : (
                <div className="text-[12.5px] text-slate-blue">
                  Your totals for this session aren&apos;t available yet.
                </div>
              )}
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
                      onClick={() => void finishReview('pass')}
                  disabled={leaving}
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
                  onClick={() => void finishReview('foundation_weak')}
                  disabled={leaving}
                  className="rounded-md border border-muted-gray bg-white px-3 py-3 text-left hover:border-focus-navy transition-colors"
                >
                  <div className="text-[13px] font-semibold text-ink">Foundation weak</div>
                  <div className="text-[11.5px] text-slate-blue mt-0.5">Recap the concept — back to orientation.</div>
                </button>
                <button
                  onClick={() => void finishReview('cant_solve')}
                  disabled={leaving}
                  className="rounded-md border border-muted-gray bg-white px-3 py-3 text-left hover:border-focus-navy transition-colors"
                >
                  <div className="text-[13px] font-semibold text-ink">Can&apos;t solve yet</div>
                  <div className="text-[11.5px] text-slate-blue mt-0.5">Knows it, needs help applying — back to guided.</div>
                </button>
                <button
                  onClick={() => void finishReview('pass')}
                  disabled={leaving}
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
