'use client';

/**
 * Topic-entry diagnostic — the SMALL diagnostic. Unlike the one-time placement
 * diagnostic at /diagnostic, this short check opens before every NEW topic to
 * confirm the student is ready and tune where the topic begins. On finish it
 * leads into the concept Orientation screen for that topic.
 *
 * (Scoring is backend in production; mocked here as a 2-question gate.)
 */

import { useState } from 'react';
import { notFound } from 'next/navigation';
import { Compass, ArrowRight, Check } from 'lucide-react';
import { getTopic } from '@/lib/curriculum';
import { useFlowNav } from '@/lib/useFlowNav';
import { cn } from '@/lib/cn';

interface Q { prompt: string; options: string[]; answer: number }

// A tiny readiness probe per topic; falls back to a generic pair.
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

export default function DiagnosticClient({ topicId }: { topicId: string }) {
  const { decideDiagnostic } = useFlowNav();
  const topic = getTopic(topicId);
  const questions = PROBES[topicId] ?? GENERIC;

  const [step, setStep] = useState<'intro' | 'quiz' | 'result'>('intro');
  const [i, setI] = useState(0);
  const [score, setScore] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);

  if (!topic) notFound();

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
    <main className="flex-1 min-w-0 flex items-center justify-center bg-white p-8" aria-label="Topic check">
      <div className="w-[460px] max-w-full">
        {step === 'intro' && (
          <div className="text-center">
            <div className="w-12 h-12 mx-auto rounded-xl bg-[#1a1a1a] text-white flex items-center justify-center mb-4">
              <Compass size={22} strokeWidth={1.8} />
            </div>
            <div className="text-[10px] tracking-widest uppercase text-[#9a9a9a] mb-1">New topic · {topic.title}</div>
            <h1 className="text-[22px] font-semibold text-[#1a1a1a]">Quick check before we start</h1>
            <p className="text-[13px] text-[#7a7a7a] mt-2 leading-relaxed">
              Two short questions so Numera knows where to begin <b>{topic.title}</b>. This runs once before each new topic.
            </p>
            <button onClick={() => setStep('quiz')} className="mt-5 w-full rounded-md bg-[#1a1a1a] text-white px-4 py-3 text-[13px] font-semibold hover:opacity-80 transition-opacity">
              Begin check
            </button>
          </div>
        )}

        {step === 'quiz' && (
          <div>
            <div className="flex items-center gap-1.5 mb-6">
              {questions.map((_, idx) => (
                <span key={idx} className={cn('h-1.5 flex-1 rounded-full', idx <= i ? 'bg-[#1a1a1a]' : 'bg-[#eaeaea]')} />
              ))}
            </div>
            <div className="text-[10px] tracking-widest uppercase text-[#9a9a9a] mb-2">Question {i + 1} of {questions.length}</div>
            <h2 className="text-[20px] font-semibold text-[#1a1a1a] font-[Cambria_Math,Georgia,serif] mb-5">{questions[i].prompt}</h2>
            <div className="flex flex-col gap-2.5">
              {questions[i].options.map((opt, idx) => (
                <button
                  key={opt}
                  onClick={() => picked === null && answer(idx)}
                  className={cn(
                    'flex items-center justify-between rounded-lg border px-4 py-3 text-left text-[14px] transition-colors font-[Cambria_Math,Georgia,serif]',
                    picked === idx ? 'border-[#1a1a1a] bg-[#f4f4f4]' : 'border-[#c8c8c8] hover:border-[#9a9a9a]'
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
            <div className="w-12 h-12 mx-auto rounded-xl bg-[#1a1a1a] text-white flex items-center justify-center mb-4">
              <Check size={22} strokeWidth={2} />
            </div>
            <h1 className="text-[22px] font-semibold text-[#1a1a1a]">Ready to begin</h1>
            <p className="text-[13px] text-[#7a7a7a] mt-2">
              {ready
                ? `You already know the concept — we'll skip ahead to guided ${topic.title}.`
                : `We'll ease into ${topic.title} with the concept orientation first.`}
            </p>
            <button
              onClick={() => decideDiagnostic(ready, topic.id)}
              className="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-md bg-[#1a1a1a] text-white px-4 py-3 text-[13px] font-semibold hover:opacity-80 transition-opacity"
            >
              {ready ? 'Start guided learning' : 'Begin orientation'} <ArrowRight size={16} strokeWidth={2} />
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
