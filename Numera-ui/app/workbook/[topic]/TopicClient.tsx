'use client';

import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ChevronLeft, Check, BookOpen } from 'lucide-react';
import PageShell, { Chip, EmptyState } from '@/components/PageShell';
import { useNumeraStore } from '@/store/useNumeraStore';
import {
  getTopic, effectiveStatus, subtopicsForStage, keyStageForAge,
  type LessonStatus,
} from '@/lib/curriculum';

const ACTION: Record<LessonStatus, string> = {
  mastered: 'Learn again',
  'in-progress': 'Continue',
  'not-started': 'Start',
};

export default function TopicClient({ topicId }: { topicId: string }) {
  const topic = getTopic(topicId);
  const completed = useNumeraStore((s) => s.completedLessons);
  const age = useNumeraStore((s) => s.studentAge);
  const toggleLessonLearned = useNumeraStore((s) => s.toggleLessonLearned);

  if (!topic) notFound();

  // Only show subtopics for the student's Key Stage (age-gated).
  const ks = keyStageForAge(age);
  const subtopics = subtopicsForStage(topic, ks);

  // A new lesson starts via the topic-entry (small) diagnostic; resuming or
  // re-learning goes straight to the guided lesson.
  const linkFor = (status: LessonStatus, lessonId: string) =>
    status === 'not-started'
      ? `/diagnostic/${topic.id}?lesson=${lessonId}`
      : '/';

  return (
    <PageShell
      title={topic.title}
      subtitle={topic.blurb}
      action={
        <Link
          href="/workbook"
          className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-[#7a7a7a] hover:text-[#1a1a1a] transition-colors"
        >
          <ChevronLeft size={15} strokeWidth={1.8} /> Workbook
        </Link>
      }
    >
      <div className="flex flex-col gap-7 max-w-3xl">
        {subtopics.length === 0 && (
          <EmptyState
            icon={<BookOpen size={20} strokeWidth={1.6} />}
            title="Nothing at your level here yet"
            body={`${topic.title} has no subtopics for your school year right now. Pick another topic from your workbook.`}
            action={
              <Link href="/workbook" className="inline-flex items-center gap-1.5 rounded-md bg-[#1a1a1a] text-white px-4 py-2.5 text-[12.5px] font-semibold hover:opacity-80 transition-opacity">
                <ChevronLeft size={15} strokeWidth={1.8} /> Back to workbook
              </Link>
            }
          />
        )}
        {subtopics.map((sub) => (
          <section key={sub.id}>
            <div className="flex items-center gap-2 mb-2.5">
              <span className="text-[11px] font-semibold tracking-widest uppercase text-[#9a9a9a]">
                {sub.title}
              </span>
              <Chip>{sub.keyStage}</Chip>
            </div>
            <div className="rounded-lg border border-[#c8c8c8] divide-y divide-[#eaeaea] overflow-hidden">
              {sub.lessons.map((l) => {
                const status = effectiveStatus(l, completed);
                const done = status === 'mastered';
                return (
                  <div key={l.id} className="flex items-center gap-4 px-5 py-3.5 hover:bg-[#f9f9f9] transition-colors">
                    {/* status toggle — mark learned / unlearned */}
                    <button
                      onClick={() => toggleLessonLearned(l.id)}
                      title={done ? 'Mark as not learned' : 'Mark as learned'}
                      aria-label={done ? `Mark ${l.title} as not learned` : `Mark ${l.title} as learned`}
                      aria-pressed={done}
                      className={
                        'flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center border transition-colors ' +
                        (done
                          ? 'bg-[#1a1a1a] border-[#1a1a1a] text-white'
                          : 'border-[#9a9a9a] text-transparent hover:border-[#1a1a1a]')
                      }
                    >
                      <Check size={13} strokeWidth={2.4} />
                    </button>
                    <div className="min-w-0 flex-1">
                      <div className={'text-[13.5px] ' + (done ? 'text-[#7a7a7a]' : 'text-[#1a1a1a] font-medium')}>
                        {l.title}
                      </div>
                    </div>
                    {status === 'in-progress' && <Chip>In progress</Chip>}
                    <Link
                      href={linkFor(status, l.id)}
                      className="flex-shrink-0 inline-flex items-center justify-center rounded-md border border-[#1a1a1a] text-[#1a1a1a] text-[12px] font-semibold px-3.5 py-1.5 hover:bg-[#1a1a1a] hover:text-white transition-colors"
                    >
                      {ACTION[status]}
                    </Link>
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </PageShell>
  );
}
