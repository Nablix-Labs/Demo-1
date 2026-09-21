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
  const topicTitles = useNumeraStore((s) => s.topicTitles);
  const studentName = useNumeraStore((s) => s.studentName);
  const reset = useNumeraStore((s) => s.reset);
  // "Start over" wipes the LOCAL journey and opens sign-up. That is the mock
  // curriculum's restart; a live student's journey belongs to the backend,
  // and the button sent a signed-in student to "Create your account"
  // (ST030, 21 Sep). Mock mode only.
  const canStartOver = !process.env.NEXT_PUBLIC_API_BASE_URL;

  // Every topic the student has mastered, whatever it is called. Real topics
  // are backend codes (ALG-ORI-03) that the local table does not list, and
  // counting only the table's ids showed a student who had just mastered three
  // topics 'Nothing finished yet' (21 Sep). The table is kept for mock mode;
  // a mastered backend topic is listed by the title the review gave it.
  const masteredIds = Object.keys(masteryByTopic).filter((id) => masteryByTopic[id]);
  const mastered = masteredIds.length;
  const rows = masteredIds.some((id) => !TOPICS.some((t) => t.id === id))
    ? masteredIds.map((id) => ({ id, name: topicTitles[id] ?? id, done: true }))
    : TOPICS.map((t) => ({ id: t.id, name: t.name, done: Boolean(masteryByTopic[t.id]) }));
  const total = rows.length;

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
            : `You’ve mastered ${
                // "1 of 1" reads as a quiz score. When the rows ARE the
                // mastered list (real topics), the count is the whole claim.
                rows.every((r) => r.done) ? `${mastered}` : `${mastered} of ${total}`
              } ${mastered === 1 ? 'topic' : 'topics'}. Every concept checked, practised, and reviewed with the tutor.`}
        </p>

        {/* Mastered-topic recap */}
        <div className="mt-5 rounded-lg border border-muted-gray divide-y divide-muted-gray text-left">
          {rows.map((t) => (
            <div key={t.id} className="flex items-center justify-between px-4 py-3">
              <span className="text-[14px] font-semibold text-ink">{t.name}</span>
              {t.done ? (
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
          {canStartOver && (
            <button
              onClick={startOver}
              className="w-full rounded-md border border-muted-gray bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-blue hover:text-ink hover:border-muted-gray transition-colors"
            >
              Start over
            </button>
          )}
        </div>
      </div>
    </CenteredScreen>
  );
}
