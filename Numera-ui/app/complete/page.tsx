'use client';

/**
 * Course complete — the end state once every topic has been mastered. Recaps
 * the mastered topics and offers a way to start over or browse topics. Reached
 * from the final Feedback & Review "Mastered" decision (see lib/useFlowNav.ts).
 */

import { useRouter } from 'next/navigation';
import { Check } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { TOPICS } from '@/lib/topics';

export default function CompletePage() {
  const router = useRouter();
  const masteryByTopic = useNumeraStore((s) => s.masteryByTopic);
  const studentName = useNumeraStore((s) => s.studentName);
  const reset = useNumeraStore((s) => s.reset);

  const mastered = TOPICS.filter((t) => masteryByTopic[t.id]).length;

  const startOver = () => {
    reset();
    router.push('/onboard');
  };

  return (
    <main className="flex-1 min-w-0 flex items-center justify-center bg-white p-8" aria-label="Course complete">
      <div className="w-[460px] max-w-full text-center">
        <div className="w-12 h-12 mx-auto rounded-xl bg-focus-navy text-white flex items-center justify-center mb-4">
          <Check size={24} strokeWidth={2.2} />
        </div>
        <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-1">Course complete</div>
        <h1 className="text-[24px] font-semibold text-ink leading-tight">
          {studentName ? `Well done, ${studentName}` : 'Well done'}
        </h1>
        <p className="text-[13px] text-slate-blue mt-2 leading-relaxed">
          You&apos;ve mastered all {mastered} {mastered === 1 ? 'topic' : 'topics'}. Every concept checked,
          practised, and reviewed with the tutor.
        </p>

        {/* Mastered-topic recap */}
        <div className="mt-5 rounded-lg border border-muted-gray divide-y divide-muted-gray text-left">
          {TOPICS.map((t) => (
            <div key={t.id} className="flex items-center justify-between px-4 py-3">
              <span className="text-[14px] font-semibold text-ink">{t.name}</span>
              {masteryByTopic[t.id] ? (
                <span className="flex items-center gap-1.5 text-[12px] font-semibold text-ink">
                  <span className="w-5 h-5 rounded-full bg-focus-navy text-white flex items-center justify-center">
                    <Check size={12} strokeWidth={2.4} />
                  </span>
                  Mastered
                </span>
              ) : (
                <span className="text-[12px] text-slate-blue">—</span>
              )}
            </div>
          ))}
        </div>

        <div className="mt-5 flex flex-col gap-2.5">
          <button
            onClick={() => router.push('/workbook')}
            className="w-full rounded-md bg-focus-navy text-white px-4 py-3 text-[13px] font-semibold hover:opacity-80 transition-opacity"
          >
            Browse topics
          </button>
          <button
            onClick={startOver}
            className="w-full rounded-md border border-muted-gray bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-blue hover:text-ink hover:border-muted-gray transition-colors"
          >
            Start over
          </button>
        </div>
      </div>
    </main>
  );
}
