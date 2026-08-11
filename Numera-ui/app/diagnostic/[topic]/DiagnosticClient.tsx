'use client';

/**
 * Topic-entry diagnostic — the SMALL diagnostic. Unlike the one-time placement
 * diagnostic at /diagnostic, this short check opens before every NEW topic to
 * confirm the student is ready and tune where the topic begins.
 *
 * With a backend (NEXT_PUBLIC_API_BASE_URL set) this screen is a renderer only:
 * the Student Model serves the questions, the student's answers are posted once
 * to /session/{id}/diagnostic/complete, and the PHASE THE BACKEND RETURNS
 * decides where the student goes — CONCEPT_ORIENTATION when it finds gaps,
 * INDEPENDENT_PRACTICE when it doesn't. Nothing here grades anything; showing a
 * local verdict would contradict the routing the backend just made.
 *
 * Without a backend it falls back to the original mocked 2-question gate so the
 * demo flow still runs standalone.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { notFound } from 'next/navigation';
import { Compass, ArrowRight, Check, AlertTriangle, RotateCw } from 'lucide-react';
import { getTopic } from '@/lib/curriculum';
import { useFlowNav } from '@/lib/useFlowNav';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useAuthStore } from '@/store/useAuthStore';
import { resumeSession, useDemoTutor, resetSessionStart, sessionStartError } from '@/hooks/useDemoTutor';
import {
  completeDiagnostic,
  diagnosticQuestions,
  studentId,
  type DiagnosticAnswer,
  type SchemaQuestion,
} from '@/lib/api';
import { applyPhaseHandoff } from '@/lib/phaseHandoff';
import { speakTutor, stopTutorSpeech } from '@/lib/tts';
import { cn } from '@/lib/cn';
import { CenteredScreen, ScreenIcon } from '@/components/CenteredScreen';
import { CelebrationMark, PlacementMark, ProblemMark } from '@/components/ScreenMarks';

const apiEnabled = Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

interface Q { prompt: string; options: string[]; answer: number }

// A tiny readiness probe per topic; falls back to a generic pair. Mock mode only.
const PROBES: Record<string, Q[]> = {
  algebra: [
    { prompt: 'What does x mean in 2x?', options: ['Add 2 and x', '2 times x', 'x squared'], answer: 1 },
    { prompt: 'Solve: x + 3 = 7', options: ['x = 4', 'x = 10', 'x = 3'], answer: 0 },
  ],
  number: [
    { prompt: 'Which is larger: 1/2 or 1/3?', options: ['1/3', '1/2', 'Equal'], answer: 1 },
    { prompt: 'Simplify: 4/8', options: ['1/2', '2/4', '4/8'], answer: 0 },
  ],
  geometry: [
    { prompt: 'Angles on a straight line add to…', options: ['90°', '180°', '360°'], answer: 1 },
    { prompt: 'A right angle is…', options: ['45°', '90°', '180°'], answer: 1 },
  ],
  statistics: [
    { prompt: 'The mean is the…', options: ['Middle value', 'Average', 'Most common'], answer: 1 },
    { prompt: 'The mode is the…', options: ['Most common value', 'Average', 'Spread'], answer: 0 },
  ],
};

const GENERIC: Q[] = [
  { prompt: 'Solve: x + 4 = 9', options: ['x = 4', 'x = 5', 'x = 13'], answer: 1 },
  { prompt: 'Simplify: 2x + 3x', options: ['5x', '6x', '23x'], answer: 0 },
];

function diagnosticTransitionFor(
  messages: string[] | undefined,
  fallback: string | null | undefined,
  questionIndex: number
): string | undefined {
  if (messages && messages.length > 0) {
    return messages[questionIndex % messages.length];
  }
  return fallback ?? undefined;
}

export default function DiagnosticClient({ topicId }: { topicId: string }) {
  const topic = getTopic(topicId);
  if (!topic) notFound();
  return apiEnabled ? <BackendDiagnostic topicId={topicId} /> : <MockDiagnostic topicId={topicId} />;
}

// ─── Backend-driven ──────────────────────────────────────────────────────────

type Status = 'loading' | 'ready' | 'submitting' | 'error';

function BackendDiagnostic({ topicId }: { topicId: string }) {
  const topic = getTopic(topicId)!;
  const tutor = useDemoTutor();
  const sessionId = useNumeraStore((s) => s.sessionId);
  const backendSession = useNumeraStore((s) => s.backendSession);
  const setBackendSession = useNumeraStore((s) => s.setBackendSession);
  const activeConceptId = useNumeraStore((s) => s.activeConceptId);

  const [status, setStatus] = useState<Status>('loading');
  const [error, setError] = useState<string | null>(null);
  const [i, setI] = useState(0);
  // question_id -> the option text the student chose.
  const [answers, setAnswers] = useState<Record<string, string>>({});
  // Has a session start been attempted? Ref, not state: it must gate the effect
  // synchronously, or React 18's double-invoke opens two sessions.
  //
  // Deliberately NOT reset on failure. useDemoTutor() returns a fresh object
  // every render, so anything depending on it changes identity every render —
  // an effect that retried on failure re-fired continuously and fired 256
  // session starts in five seconds. Only the retry button clears this.
  const started = useRef(false);
  // True while the chosen option is being shown, just before the next question.
  const advancing = useRef(false);

  const questions = diagnosticQuestions(backendSession);

  const openSession = useCallback(async () => {
    started.current = true;
    setStatus('loading');
    setError(null);
    const rec = await tutor.start(activeConceptId, 'TEXT');
    if (!rec) {
      // Prefer the backend's own reason (e.g. the sign-in mismatch) over the
      // generic network copy, which sends the student off retrying forever.
      setError(sessionStartError() ?? "Couldn't reach the tutor to start your check.");
      setStatus('error');
      return;
    }
    if (diagnosticQuestions(rec).length === 0) {
      setError('The tutor served no questions for this topic yet.');
      setStatus('error');
      return;
    }
    setStatus('ready');
  }, [tutor, activeConceptId]);

  // The auth store persists with skipHydration, so a session started before it
  // rehydrates sends the anonymous bearer instead of the student's real token —
  // student_model rejects that with 401 and the check dies on arrival.
  //
  // This route must rehydrate it ITSELF. `/diagnostic` is in AppFrame's
  // FOCUS_ROUTES, which renders the page WITHOUT AuthGate — and AuthGate is what
  // normally calls rehydrate(). Waiting on hydration here without asking for it
  // waits forever. Same call as /login and /restricted make; it's idempotent.
  //
  // Starts false and is only set from an effect: `useAuthStore.persist` is
  // undefined during the static prerender, so reading it in a useState
  // initializer crashes `next build` on this page.
  const [authReady, setAuthReady] = useState(false);
  useEffect(() => {
    void useAuthStore.persist.rehydrate();
    setAuthReady(true);
  }, []);

  // Speak the tutor's opening line once, when the check is ready. Phase 0 was
  // silent — the messages were shown but never voiced (Sanya, 2026-07-28).
  // The text stays on screen too, so it still works with the sound off.
  const greeted = useRef(false);
  useEffect(() => {
    if (status !== 'ready' || greeted.current) return;
    const opening = backendSession?.message;
    if (!opening) return;
    greeted.current = true;
    speakTutor(opening);
  }, [status, backendSession?.message]);

  // Never let tutor speech follow the student off this screen.
  useEffect(() => () => stopTutorSpeech(), []);

  useEffect(() => {
    if (questions.length > 0) { setStatus('ready'); return; }
    if (!authReady || started.current) return;
    if (sessionId) {
      void resumeSession();
      return;
    }
    void openSession();
    // openSession is intentionally omitted — see the note on `started`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questions.length, sessionId, authReady]);

  /**
   * Record the choice and move on; the last one submits the whole set.
   *
   * `response` must be the OPTION ID, not the option text. The backend grades
   * with `student_response in answer_spec.accepted_answers`, and for
   * EXACT_CHOICE_MATCH questions `accepted_answers` holds ids (`["B"]`).
   * Sending the text scored every answer INCORRECT, so the diagnostic always
   * reported gaps and always routed to orientation no matter what the student
   * picked — the "no gap -> Independent Practice" branch could never fire.
   */
  const choose = (question: SchemaQuestion, response: string) => {
    if (advancing.current) return;       // ignore a double-tap mid-transition
    advancing.current = true;
    const next = { ...answers, [question.question_id]: response };
    setAnswers(next);

    const isLast = i + 1 >= questions.length;
    const transition = isLast ? null : diagnosticTransitionFor(
      backendSession?.diagnostic_transition_messages,
      backendSession?.diagnostic_transition_message,
      i,
    );

    /**
     * Move on once the tutor has finished saying the transition — not on a
     * fixed timer. A flat 420ms flashed the line up and swapped the question
     * before it could be read, which looked broken rather than conversational
     * (Sanya, 2026-07-28).
     *
     * MIN_DWELL keeps a short line on screen long enough to register; the
     * failsafe covers a TTS provider that never calls back, so a silent failure
     * can't strand the student mid-check.
     */
    const MIN_DWELL = 900;
    const FAILSAFE = 8000;
    const shownAt = Date.now();
    let moved = false;
    const go = () => {
      if (moved) return;
      moved = true;
      window.setTimeout(() => {
        advancing.current = false;
        if (!isLast) { setI(i + 1); return; }
        void submit(next);
      }, Math.max(0, MIN_DWELL - (Date.now() - shownAt)));
    };

    if (transition) speakTutor(transition, go);
    else window.setTimeout(go, 420);
    window.setTimeout(go, FAILSAFE);
  };

  /**
   * Post every answer once. The backend derives the micro-skills, so the client
   * sends only what the student picked — never a skill id, never a verdict.
   */
  const submit = async (collected: Record<string, string>) => {
    if (!sessionId) return;
    setStatus('submitting');
    setError(null);
    const payload: DiagnosticAnswer[] = questions.map((q) => ({
      question_id: q.question_id,
      student_response: collected[q.question_id] ?? '',
    }));
    try {
      const rec = await completeDiagnostic(sessionId, studentId(), payload);
      setBackendSession(rec);
      // Drives usePhaseRouting to whichever phase the backend chose. The record
      // carries question_id: null here, which the store now keeps as null.
      //
      applyPhaseHandoff(rec);
    } catch {
      setError("Couldn't send your answers. Please try again.");
      setStatus('ready');
    }
  };

  if (status === 'loading' || status === 'submitting') {
    return (
      <Centered>
        <div className="text-center" aria-busy="true">
          <ScreenIcon mark={PlacementMark} />
          <h1 className="text-[20px] font-semibold text-ink">
            {status === 'submitting' ? 'Working out where to start you' : 'Getting your check ready'}
          </h1>
          <p className="text-[13px] text-slate-blue mt-2">One moment.</p>
        </div>
      </Centered>
    );
  }

  if (status === 'error') {
    return (
      <Centered>
        <div className="text-center">
          <ScreenIcon mark={ProblemMark} />
          <h1 className="text-[20px] font-semibold text-ink">Couldn&apos;t start the check</h1>
          <p className="text-[13px] text-slate-blue mt-2 leading-relaxed">{error}</p>
          <button
            onClick={() => { started.current = false; resetSessionStart(); void openSession(); }}
            className="mt-5 inline-flex items-center gap-1.5 rounded-md border border-focus-navy px-4 py-2.5 text-[12.5px] font-semibold text-ink hover:bg-focus-navy hover:text-white transition-colors"
          >
            <RotateCw size={14} strokeWidth={1.9} /> Try again
          </button>
        </div>
      </Centered>
    );
  }

  const question = questions[i];
  if (!question) return null;
  const picked = answers[question.question_id];

  return (
    <Centered>
      <div>
        {i === 0 && backendSession?.message && (
          <p className="text-[13px] text-slate-blue mb-5 leading-relaxed">
            {backendSession.message}
          </p>
        )}
        <div className="flex items-center gap-1.5 mb-6">
          {questions.map((_, idx) => (
            <span key={idx} className={cn('h-1.5 flex-1 rounded-full', idx <= i ? 'bg-focus-navy' : 'bg-reading-surface')} />
          ))}
        </div>
        <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-2">
          {topic.title} · Question {i + 1} of {questions.length}
        </div>
        <h2 className="text-[20px] font-semibold text-ink font-[Cambria_Math,Georgia,serif] mb-5">
          {question.student_view.question_text}
        </h2>
        {error && <p className="text-[12.5px] text-action-orange mb-3">{error}</p>}
        <div className="flex flex-col gap-3.5">
          {question.student_view.options.map((opt) => (
            <button
              key={opt.option_id}
              onClick={() => choose(question, opt.option_id)}
              className={cn(
                'flex items-center justify-between rounded-xl border-[3px] bg-white px-6 py-5 text-left text-[19px] font-semibold transition-colors font-[Cambria_Math,Georgia,serif]',
                picked === opt.option_id
                  ? 'border-ink bg-reading-surface text-ink'
                  : 'border-ink/85 text-ink hover:border-ink hover:bg-reading-surface'
              )}
            >
              {opt.text}
              {picked === opt.option_id && <Check size={16} strokeWidth={2} />}
            </button>
          ))}
        </div>
        {/* No score, no verdict: the backend decides what this means. */}
        <p className="text-[11.5px] text-slate-blue mt-5">
          Tap an answer to move on — this only tells Numera where to begin.
        </p>
        <p
          className="min-h-5 text-[12.5px] text-slate-blue mt-2"
          aria-live="polite"
        >
          {picked && i + 1 < questions.length
            ? diagnosticTransitionFor(
                backendSession?.diagnostic_transition_messages,
                backendSession?.diagnostic_transition_message,
                i
              )
            : ''}
        </p>
      </div>
    </Centered>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <CenteredScreen label="Topic check">{children}</CenteredScreen>;
}

// ─── Mock (no backend) ───────────────────────────────────────────────────────

function MockDiagnostic({ topicId }: { topicId: string }) {
  const { decideDiagnostic } = useFlowNav();
  const topic = getTopic(topicId)!;
  const questions = PROBES[topicId] ?? GENERIC;

  const [step, setStep] = useState<'intro' | 'quiz' | 'result'>('intro');
  const [i, setI] = useState(0);
  const [score, setScore] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);

  const answer = (idx: number) => {
    setPicked(idx);
    const correct = idx === questions[i].answer;
    setTimeout(() => {
      if (correct) setScore((s) => s + 1);
      if (i + 1 < questions.length) { setI(i + 1); setPicked(null); }
      else setStep('result');
    }, 420);
  };

  const ready = score >= Math.ceil(questions.length / 2);

  return (
    <Centered>
      {step === 'intro' && (
        <div className="text-center">
          <ScreenIcon mark={PlacementMark} />
          <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-1">New topic · {topic.title}</div>
          <h1 className="text-[22px] font-semibold text-ink">Quick check before we start</h1>
          <p className="text-[13px] text-slate-blue mt-2 leading-relaxed">
            Two short questions so Numera knows where to begin <b>{topic.title}</b>. This runs once before each new topic.
          </p>
          <button onClick={() => setStep('quiz')} className="mt-5 w-full rounded-md bg-focus-navy text-white px-4 py-3 text-[13px] font-semibold hover:opacity-80 transition-opacity">
            Begin check
          </button>
        </div>
      )}

      {step === 'quiz' && (
        <div>
          <div className="flex items-center gap-1.5 mb-6">
            {questions.map((_, idx) => (
              <span key={idx} className={cn('h-1.5 flex-1 rounded-full', idx <= i ? 'bg-focus-navy' : 'bg-reading-surface')} />
            ))}
          </div>
          <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-2">Question {i + 1} of {questions.length}</div>
          <h2 className="text-[20px] font-semibold text-ink font-[Cambria_Math,Georgia,serif] mb-5">{questions[i].prompt}</h2>
          <div className="flex flex-col gap-3.5">
            {questions[i].options.map((opt, idx) => (
              <button
                key={opt}
                onClick={() => picked === null && answer(idx)}
                className={cn(
                  'flex items-center justify-between rounded-xl border-[3px] bg-white px-6 py-5 text-left text-[19px] font-semibold transition-colors font-[Cambria_Math,Georgia,serif]',
                  picked === idx
                    ? 'border-ink bg-reading-surface text-ink'
                    : 'border-ink/85 text-ink hover:border-ink hover:bg-reading-surface'
                )}
              >
                {opt}
                {picked === idx && <Check size={16} strokeWidth={2} />}
              </button>
            ))}
          </div>
        </div>
      )}

      {step === 'result' && (
        <div className="text-center">
          <ScreenIcon mark={CelebrationMark} />
          <h1 className="text-[22px] font-semibold text-ink">Ready to begin</h1>
          <p className="text-[13px] text-slate-blue mt-2">
            {ready
              ? `You already know the concept — we'll skip ahead to guided ${topic.title}.`
              : `We'll ease into ${topic.title} with the concept orientation first.`}
          </p>
          <button
            onClick={() => decideDiagnostic(ready, topic.id)}
            className="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-md bg-focus-navy text-white px-4 py-3 text-[13px] font-semibold hover:opacity-80 transition-opacity"
          >
            {ready ? 'Start guided learning' : 'Begin orientation'} <ArrowRight size={16} strokeWidth={2} />
          </button>
        </div>
      )}
    </Centered>
  );
}
