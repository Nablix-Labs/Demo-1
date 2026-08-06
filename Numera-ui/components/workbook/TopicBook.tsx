'use client';

/**
 * A topic, opened as a book.
 *
 * The shelf shows every topic as a closed book; opening one has to open THAT
 * book, or the two screens are unrelated views of the same data rather than one
 * object. So the cover here is built from the same map, in the same colour, with
 * the same cloth band and titled panel — and the book opens itself a beat after
 * it arrives, which is what carries the connection across the navigation.
 *
 * Each subtopic gets a sheet, and its lessons sit on that sheet with their
 * status toggle and action intact. `clickEventForward` is what keeps those
 * controls working inside a draggable page.
 *
 * Like the rest of the book UI this runs on StPageFlip, which animates on
 * requestAnimationFrame: it turns normally in a browser and sits still in the
 * embedded Browser pane.
 */

import { forwardRef, useEffect, useRef } from 'react';
import Link from 'next/link';
import HTMLFlipBook from 'react-pageflip';
import { Check } from 'lucide-react';
import { topicLook } from './topicLook';
import { effectiveStatus, type Subtopic, type Topic, type LessonStatus } from '@/lib/curriculum';

const W = 430;
const H = 580;

const ACTION: Record<LessonStatus, string> = {
  mastered: 'Learn again',
  'in-progress': 'Continue',
  'not-started': 'Start',
};

/** StPageFlip measures each child, so every leaf must forward a real ref. */
const Leaf = forwardRef<HTMLDivElement, { children: React.ReactNode }>(function Leaf(
  { children },
  ref,
) {
  return (
    <div ref={ref} className="overflow-hidden">
      {children}
    </div>
  );
});

export default function TopicBook({
  topic,
  subtopics,
  keyStage,
  progress,
  completed,
  onToggleLesson,
}: {
  topic: Topic;
  subtopics: Subtopic[];
  keyStage: string;
  progress: number;
  completed: string[];
  onToggleLesson: (lessonId: string) => void;
}) {
  const look = topicLook(topic.id);
  const book = useRef<{ pageFlip?: () => { flipNext: () => void } } | null>(null);

  /**
   * Open on arrival.
   *
   * The student clicked a closed book on the shelf and landed here; showing it
   * already open would lose that thread. A beat's delay lets the page settle
   * first, so the turn reads as the book opening rather than as the page
   * finishing loading.
   */
  useEffect(() => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const t = setTimeout(() => book.current?.pageFlip?.().flipNext(), reduced ? 0 : 700);
    return () => clearTimeout(t);
  }, []);

  return (
    <HTMLFlipBook
      ref={book}
      width={W}
      height={H}
      size="fixed"
      minWidth={W}
      maxWidth={W}
      minHeight={H}
      maxHeight={H}
      showCover
      usePortrait={false}
      autoSize={false}
      startPage={0}
      startZIndex={0}
      drawShadow
      maxShadowOpacity={0.35}
      flippingTime={760}
      useMouseEvents
      mobileScrollSupport
      clickEventForward
      disableFlipByClick={false}
      showPageCorners
      swipeDistance={24}
      className="topic-book"
      style={{}}
    >
      <Leaf>
        <Cover
          topic={topic}
          color={look.color}
          Icon={look.Icon}
          keyStage={keyStage}
          progress={progress}
        />
      </Leaf>

      {subtopics.map((sub) => (
        <Leaf key={sub.id}>
          <SubtopicSheet
            sub={sub}
            topicId={topic.id}
            completed={completed}
            onToggleLesson={onToggleLesson}
          />
        </Leaf>
      ))}

      {/*
        A closing sheet, always present.
        Without it a topic with one subtopic opened onto its own back cover — a
        flat slab of colour facing the lessons — because a book needs an even
        number of leaves to pair. It earns its place rather than padding: this is
        where the student sees how far through the topic they actually are.
      */}
      <Leaf>
        <ClosingSheet
          topic={topic}
          subtopics={subtopics}
          completed={completed}
          progress={progress}
        />
      </Leaf>

      <Leaf>
        <BackCover color={look.color} />
      </Leaf>
    </HTMLFlipBook>
  );
}

function Cover({
  topic,
  color,
  Icon,
  keyStage,
  progress,
}: {
  topic: Topic;
  color: string;
  Icon: ReturnType<typeof topicLook>['Icon'];
  keyStage: string;
  progress: number;
}) {
  return (
    <div
      className="relative flex h-full flex-col overflow-hidden rounded-r-md"
      style={{ width: W, height: H }}
    >
      <div
        className="relative flex flex-1 items-center justify-center"
        style={{ background: color }}
      >
        <Icon size={78} strokeWidth={1.2} style={{ color: '#FFFFFF', opacity: 0.9 }} />
        <div
          aria-hidden="true"
          className="absolute inset-y-0 left-0 w-[8.2%] mix-blend-overlay"
          style={{ background: 'var(--ds-book-bind)' }}
        />
      </div>

      <div className="relative flex flex-1 flex-col justify-between bg-book-gradient px-10 py-9 pl-14">
        <div
          aria-hidden="true"
          className="absolute inset-y-0 left-0 w-[8.2%] opacity-20"
          style={{ background: 'var(--ds-book-bind)' }}
        />
        <div>
          <h1 className="text-[30px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink">
            {topic.title}
          </h1>
          <p className="mt-2.5 text-[13px] leading-relaxed text-slate-blue">{topic.blurb}</p>
        </div>
        <p className="text-[11.5px] text-slate-blue">
          {keyStage} · {progress}% complete
        </p>
      </div>

      <div
        aria-hidden="true"
        className="book-texture pointer-events-none absolute inset-0 opacity-[0.35] mix-blend-soft-light"
      />
    </div>
  );
}

function ClosingSheet({
  topic,
  subtopics,
  completed,
  progress,
}: {
  topic: Topic;
  subtopics: Subtopic[];
  completed: string[];
  progress: number;
}) {
  const lessons = subtopics.flatMap((s) => s.lessons);
  const done = lessons.filter((l) => effectiveStatus(l, completed) === 'mastered').length;
  const started = lessons.filter((l) => effectiveStatus(l, completed) === 'in-progress').length;

  return (
    <div
      className="relative flex h-full flex-col bg-[#FDFBF7] px-9 pb-8 pt-9"
      style={{ width: W, height: H }}
    >
      <p className="text-[10px] font-semibold uppercase tracking-[1.2px] text-slate-blue">
        Where you are
      </p>
      <h2 className="mt-1 text-[19px] font-semibold leading-tight tracking-[-0.01em] text-ink">
        {topic.title}
      </h2>
      <div className="mt-4 h-px bg-[#1B2A4A]/12" />

      <div className="mt-6">
        <div className="flex items-baseline justify-between">
          <span className="text-[12px] text-slate-blue">Progress</span>
          <span className="text-[26px] font-semibold tabular-nums text-ink">{progress}%</span>
        </div>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted-gray">
          <div
            className="h-full rounded-full bg-learning-blue transition-[width] duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <dl className="mt-8 flex flex-col gap-3.5">
        {[
          ['Lessons finished', `${done} of ${lessons.length}`],
          ['In progress', started === 0 ? 'None' : String(started)],
          ['Subtopics', String(subtopics.length)],
        ].map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-3">
            <dt className="text-[12.5px] text-slate-blue">{label}</dt>
            <dd className="text-[13px] font-semibold tabular-nums text-ink">{value}</dd>
          </div>
        ))}
      </dl>

      <Link
        href={`/diagnostic/${topic.id}`}
        className="mt-auto inline-flex items-center justify-center rounded-md border border-focus-navy px-4 py-2.5 text-[12px] font-semibold text-ink transition-colors hover:bg-focus-navy hover:text-white"
      >
        Check my level on {topic.title}
      </Link>
    </div>
  );
}

function BackCover({ color }: { color: string }) {
  return (
    <div
      className="relative h-full overflow-hidden rounded-l-md"
      style={{ width: W, height: H, background: color }}
    >
      <div
        aria-hidden="true"
        className="absolute inset-y-0 right-0 w-[8.2%] mix-blend-overlay"
        style={{ background: 'var(--ds-book-bind)' }}
      />
      <div
        aria-hidden="true"
        className="book-texture pointer-events-none absolute inset-0 opacity-[0.35] mix-blend-soft-light"
      />
    </div>
  );
}

function SubtopicSheet({
  sub,
  topicId,
  completed,
  onToggleLesson,
}: {
  sub: Subtopic;
  topicId: string;
  completed: string[];
  onToggleLesson: (lessonId: string) => void;
}) {
  // A new lesson starts via the topic-entry diagnostic; resuming or re-learning
  // goes straight to the guided lesson.
  const linkFor = (status: LessonStatus, lessonId: string) =>
    status === 'not-started' ? `/diagnostic/${topicId}?lesson=${lessonId}` : '/';

  return (
    <div
      className="relative flex h-full flex-col bg-[#FDFBF7] px-9 pb-8 pt-9"
      style={{ width: W, height: H }}
    >
      <p className="text-[10px] font-semibold uppercase tracking-[1.2px] text-slate-blue">
        {sub.keyStage}
      </p>
      <h2 className="mt-1 text-[19px] font-semibold leading-tight tracking-[-0.01em] text-ink">
        {sub.title}
      </h2>
      <div className="mt-4 mb-1 h-px bg-[#1B2A4A]/12" />

      <ul className="flex flex-col">
        {sub.lessons.map((l) => {
          const status = effectiveStatus(l, completed);
          const done = status === 'mastered';
          return (
            <li key={l.id} className="flex items-center gap-3 border-b border-[#1B2A4A]/8 py-3.5">
              <button
                onClick={() => onToggleLesson(l.id)}
                title={done ? 'Mark as not learned' : 'Mark as learned'}
                aria-label={done ? `Mark ${l.title} as not learned` : `Mark ${l.title} as learned`}
                aria-pressed={done}
                className={
                  'flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border transition-colors ' +
                  (done
                    ? 'border-focus-navy bg-focus-navy text-white'
                    : 'border-muted-gray text-transparent hover:border-focus-navy')
                }
              >
                <Check size={13} strokeWidth={2.4} />
              </button>

              <span className="min-w-0 flex-1">
                <span
                  className={
                    'block text-[13.5px] leading-snug ' +
                    (done ? 'text-slate-blue' : 'font-medium text-ink')
                  }
                >
                  {l.title}
                </span>
                {status === 'in-progress' && (
                  <span className="mt-0.5 block text-[10.5px] font-semibold uppercase tracking-[0.4px] text-highlight-amber">
                    In progress
                  </span>
                )}
              </span>

              <Link
                href={linkFor(status, l.id)}
                className="inline-flex flex-shrink-0 items-center justify-center rounded-md border border-focus-navy px-3 py-1.5 text-[11.5px] font-semibold text-ink transition-colors hover:bg-focus-navy hover:text-white"
              >
                {ACTION[status]}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
