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
import { CenteredScreen, ScreenIcon } from '@/components/CenteredScreen';
import { CelebrationMark, EncourageMark } from '@/components/ScreenMarks';

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
    <CenteredScreen label="Course complete">
      <div>
        <ScreenIcon mark={mastered === 0 ? EncourageMark : CelebrationMark} />
        {/* The heading and copy both depend on whether anything is actually
            mastered. This screen is reachable with a count of zero, and it read
            "You've mastered all 0 topics" — congratulating a student for
            nothing, next to a list showing three dashes (2026-07-29). */}
        <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-1">
          {mastered === 0 ? 'Progress' : 'Course complete'}
        </div>
        <h1 className="text-[24px] font-semibold text-ink leading-tight">
          {mastered === 0
            ? 'Nothing finished yet'
            : studentName
              ? `Well done, ${studentName}`
              : 'Well done'}
        </h1>
        <p className="text-[13px] text-slate-blue mt-2 leading-relaxed">
          {mastered === 0
            ? 'Finish a topic and it will appear here, with everything you covered.'
            : `You’ve mastered ${mastered} of ${TOPICS.length} ${
                TOPICS.length === 1 ? 'topic' : 'topics'
              }. Every concept checked, practised, and reviewed with the tutor.`}
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
    </CenteredScreen>
  );
}
