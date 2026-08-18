'use client';

/**
 * A topic from the workbook, opened.
 *
 * This was a list of lesson rows on the shared glass shell, which had no
 * relationship to the book the student had just clicked on the shelf. It is now
 * that book, opening: same colour, same cover, lessons on the sheets inside.
 *
 * The route leaves PageShell for the same reason the shelf did — paper and
 * cloth seen through a translucent panel over the ambient gradient stop reading
 * as objects.
 */

import Link from 'next/link';
import dynamic from 'next/dynamic';
import { notFound } from 'next/navigation';
import { ChevronLeft, BookOpen } from 'lucide-react';
import { EmptyState } from '@/components/PageShell';
import { useNumeraStore } from '@/store/useNumeraStore';
import {
  getTopic, subtopicsForStage, keyStageForAge, topicProgressForStage,
} from '@/lib/curriculum';

/** StPageFlip touches the DOM on mount, so the book is browser-only. */
const TopicBook = dynamic(() => import('@/components/workbook/TopicBook'), {
  ssr: false,
  loading: () => (
    <div
      className="rounded-md bg-[#F1EDE4]"
      style={{ width: 860, height: 580 }}
      aria-hidden="true"
    />
  ),
});

export default function TopicClient({ topicId }: { topicId: string }) {
  const topic = getTopic(topicId);
  const completed = useNumeraStore((s) => s.completedLessons);
  const age = useNumeraStore((s) => s.studentAge);
  const toggleLessonLearned = useNumeraStore((s) => s.toggleLessonLearned);

  if (!topic) notFound();

  // Only show subtopics for the student's Key Stage (age-gated).
  const ks = keyStageForAge(age);
  const subtopics = subtopicsForStage(topic, ks);
  const pct = topicProgressForStage(topic, ks, completed);

  return (
    <main className="flex-1 min-w-0 overflow-y-auto bg-white" aria-label={topic.title}>
      <div className="mx-auto w-full max-w-[1180px] px-10 py-8">
        <Link
          href="/workbook"
          className="mb-6 inline-flex items-center gap-1.5 text-[12px] font-semibold text-slate-blue transition-colors hover:text-ink"
        >
          <ChevronLeft size={15} strokeWidth={1.8} /> Workbook
        </Link>

        {subtopics.length === 0 ? (
          <EmptyState
            icon={<BookOpen size={20} strokeWidth={1.6} />}
            title="Nothing at your level here yet"
            body={`${topic.title} has no subtopics for your school year right now. Pick another topic from your workbook.`}
            action={
              <Link
                href="/workbook"
                className="inline-flex items-center gap-1.5 rounded-md bg-focus-navy px-4 py-2.5 text-[12.5px] font-semibold text-white transition-opacity hover:opacity-80"
              >
                <ChevronLeft size={15} strokeWidth={1.8} /> Back to workbook
              </Link>
            }
          />
        ) : (
          <div className="flex justify-center">
            <TopicBook
              topic={topic}
              subtopics={subtopics}
              keyStage={ks}
              progress={pct}
              completed={completed}
              onToggleLesson={toggleLessonLearned}
            />
          </div>
        )}
      </div>
    </main>
  );
}
