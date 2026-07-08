'use client';

/**
 * Diagnostic — the BIG, one-time placement assessment. Taken once when a
 * student joins; it decides which topic they start on. (The smaller per-topic
 * readiness check lives at /diagnostic/[topic] and runs before each new topic.)
 * Scoring/placement is backend in production; mocked here as a simple wizard.
 */

import { useEffect, useState } from 'react';
import { ClipboardCheck, ArrowRight, Check } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useFlowNav } from '@/lib/useFlowNav';
import { cn } from '@/lib/cn';

interface Q { prompt: string; options: string[]; answer: number }

const QUESTIONS: Q[] = [
  { prompt: 'Solve: x + 4 = 9', options: ['x = 4', 'x = 5', 'x = 13'], answer: 1 },
  { prompt: 'Simplify: 2x + 3x', options: ['5x', '6x', '23x'], answer: 0 },
  { prompt: 'Solve: 2x = 10', options: ['x = 8', 'x = 12', 'x = 5'], answer: 2 },
  { prompt: 'Expand: 3(x + 2)', options: ['3x + 2', '3x + 6', 'x + 6'], answer: 1 },
];

const ORIENTATION: { q: string; options: string[] }[] = [
  { q: 'How are you feeling about maths today?', options: ['Confident', 'Okay', 'A bit nervous'] },
  { q: 'How do you like to learn best?', options: ['Step by step', 'See an example first', 'Just try it'] },
];

export default function DiagnosticPage() {
  const [step, setStep] = useState<'intro' | 'orientation' | 'quiz' | 'result'>('intro');
  const [oi, setOi] = useState(0);
  const [i, setI] = useState(0);
  const [score, setScore] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const completePhase = useNumeraStore((s) => s.completePhase);
  const studentName = useNumeraStore((s) => s.studentName);
  const { placeAtTopic } = useFlowNav();

  // Reaching the result clears the diagnostic phase → unlocks orientation.
  useEffect(() => {
    if (step === 'result') completePhase('diagnostic');
  }, [step, completePhase]);

  const answerOrientation = () => {
    if (oi + 1 < ORIENTATION.length) setOi(oi + 1);
    else setStep('quiz');
  };

  const answer = (idx: number) => {
    setPicked(idx);
    const correct = idx === QUESTIONS[i].answer;
    setTimeout(() => {
      if (correct) setScore((s) => s + 1);
      if (i + 1 < QUESTIONS.length) { setI(i + 1); setPicked(null); }
      else setStep('result');
    }, 450);
  };

  // Placement maps the score onto a starting topic (Topic N). The id must match
  // a flow topic so the loop has content from here on (see lib/topics.ts).
  const placement =
    score <= 1 ? { id: 'algebra', topic: 'Algebra', ks: 'KS3', note: 'We’ll build the basics first.' }
    : score <= 3 ? { id: 'number', topic: 'Number', ks: 'KS4', note: 'You’re ready for GCSE-level work.' }
    : { id: 'geometry', topic: 'Geometry', ks: 'KS5', note: 'Strong start — let’s stretch you.' };

  return (
    <main className="flex-1 min-w-0 flex items-center justify-center bg-white p-8" aria-label="Diagnostic">
      <div className="w-[460px] max-w-full">
        {step === 'intro' && (
          <div className="text-center">
            <div className="w-12 h-12 mx-auto rounded-xl bg-focus-navy text-white flex items-center justify-center mb-4">
              <ClipboardCheck size={22} strokeWidth={1.8} />
            </div>
            <h1 className="text-[22px] font-semibold text-ink">{studentName ? `Nice to meet you, ${studentName}` : 'Quick diagnostic'}</h1>
            <p className="text-[13px] text-slate-blue mt-2 leading-relaxed">
              A one-time check so Numera knows your level and picks the right first topic. You only take this once — no pressure.
            </p>
            <button onClick={() => setStep('orientation')} className="mt-5 w-full rounded-md bg-focus-navy text-white px-4 py-3 text-[13px] font-semibold hover:opacity-80 transition-opacity">
              Begin
            </button>
          </div>
        )}

        {step === 'orientation' && (
          <div>
            <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-2">Getting to know you</div>
            <h2 className="text-[20px] font-semibold text-ink mb-5">{ORIENTATION[oi].q}</h2>
            <div className="flex flex-col gap-2.5">
              {ORIENTATION[oi].options.map((opt) => (
                <button
                  key={opt}
                  onClick={answerOrientation}
                  className="rounded-lg border border-muted-gray hover:border-muted-gray px-4 py-3 text-left text-[14px] transition-colors"
                >
                  {opt}
                </button>
              ))}
            </div>
            <p className="mt-4 text-[11.5px] text-slate-blue">No right answer — this just helps Numera coach you the way you like.</p>
          </div>
        )}

        {step === 'quiz' && (
          <div>
            {/* progress */}
            <div className="flex items-center gap-1.5 mb-6">
              {QUESTIONS.map((_, idx) => (
                <span key={idx} className={cn('h-1.5 flex-1 rounded-full', idx <= i ? 'bg-focus-navy' : 'bg-reading-surface')} />
              ))}
            </div>
            <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-2">Question {i + 1} of {QUESTIONS.length}</div>
            <h2 className="text-[20px] font-semibold text-ink font-[Cambria_Math,Georgia,serif] mb-5">{QUESTIONS[i].prompt}</h2>
            <div className="flex flex-col gap-2.5">
              {QUESTIONS[i].options.map((opt, idx) => (
                <button
                  key={opt}
                  onClick={() => picked === null && answer(idx)}
                  className={cn(
                    'flex items-center justify-between rounded-lg border px-4 py-3 text-left text-[14px] transition-colors font-[Cambria_Math,Georgia,serif]',
                    picked === idx ? 'border-focus-navy bg-reading-surface' : 'border-muted-gray hover:border-muted-gray'
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
            <div className="w-12 h-12 mx-auto rounded-xl bg-focus-navy text-white flex items-center justify-center mb-4">
              <Check size={22} strokeWidth={2} />
            </div>
            <h1 className="text-[22px] font-semibold text-ink">You&apos;re all set</h1>
            <p className="text-[13px] text-slate-blue mt-2">{placement.note}</p>
            <div className="mt-5 rounded-lg border border-focus-navy bg-reading-surface px-5 py-4 text-left">
              <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-1">We&apos;ll start you at</div>
              <div className="text-[16px] font-semibold text-ink">{placement.topic} <span className="text-slate-blue font-normal">· {placement.ks}</span></div>
            </div>
            <button onClick={() => placeAtTopic(placement.id)} className="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-md bg-focus-navy text-white px-4 py-3 text-[13px] font-semibold hover:opacity-80 transition-opacity">
              Begin orientation <ArrowRight size={16} strokeWidth={2} />
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
