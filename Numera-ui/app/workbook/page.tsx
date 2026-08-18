'use client';

/**
 * Workbook — the student's topics for their key stage.
 *
 * Topics were cards carrying the same grey folder illustration, so four of them
 * differed only by their titles. They are books now, at the size of a real
 * textbook: colour and thickness of subject distinguish them on sight, which is
 * what a shelf is for. Colour is per topic and fixed, so Algebra is the same
 * blue book every time a student opens this page — the point is that it becomes
 * recognisable, not decorative.
 *
 * Progress stays OUTSIDE the book, on the shelf edge beneath it. A cover that
 * changed as you worked through it would stop being a stable object to
 * recognise, and progress is about the reading, not the book.
 *
 * The route leaves PageShell for the reason Files did: covers picked up the
 * blue wash through the shared glass panel, and objects need a surface.
 */

import { useState } from 'react';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import { ClipboardCheck, Folder, X } from 'lucide-react';
import { ProgressBar, EmptyState } from '@/components/PageShell';
import PhaseGate from '@/components/PhaseGate';
import { Book } from '@/components/ui/book';
import { topicLook } from '@/components/workbook/topicLook';
import { useNumeraStore } from '@/store/useNumeraStore';
import {
  CURRICULUM, KEY_STAGES, subtopicsForStage, topicProgressForStage,
  keyStageForAge, type Topic,
} from '@/lib/curriculum';

/** StPageFlip touches the DOM on mount, so the book is browser-only. */
const TopicBook = dynamic(() => import('@/components/workbook/TopicBook'), { ssr: false });

export default function WorkbookPage() {
  const [open, setOpen] = useState<Topic | null>(null);
  const completed = useNumeraStore((s) => s.completedLessons);
  const age = useNumeraStore((s) => s.studentAge);
  const setAge = useNumeraStore((s) => s.setStudentAge);
  const toggleLessonLearned = useNumeraStore((s) => s.toggleLessonLearned);

  // Age decides the Key Stage — the student only sees content for their stage.
  const ks = keyStageForAge(age);
  const stage = KEY_STAGES.find((k) => k.id === ks)!;

  // Only topics that have subtopics at the student's stage.
  const topics = CURRICULUM
    .map((t) => ({ topic: t, subs: subtopicsForStage(t, ks) }))
    .filter((x) => x.subs.length > 0);

  return (
    <PhaseGate phase="workbook">
      <main className="flex-1 min-w-0 overflow-y-auto bg-white" aria-label="Workbook">
        <div className="mx-auto w-full max-w-[1180px] px-10 py-10">
          <header className="mb-8 flex items-end justify-between gap-4">
            <div>
              <h1 className="text-[30px] font-semibold leading-[1.15] tracking-[-0.02em] text-ink">
                Workbook
              </h1>
              <p className="mt-1.5 text-[14px] text-slate-blue">
                Your topics and subtopics — matched to your school year.
              </p>
            </div>
            <Link
              href="/diagnostic"
              className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-md border border-muted-gray bg-white px-3.5 py-2 text-[12px] font-semibold text-ink transition-colors hover:bg-reading-surface"
            >
              <ClipboardCheck size={15} strokeWidth={1.8} /> Take diagnostic
            </Link>
          </header>

          {/* Age → Key Stage. Content is shown by age, not free choice. */}
          <div className="mb-10 flex items-center justify-between gap-4 rounded-lg border border-muted-gray bg-reading-surface px-5 py-3.5">
            <div className="flex items-center gap-2.5">
              <label
                htmlFor="student-age"
                className="text-[11px] font-semibold uppercase tracking-widest text-slate-blue"
              >
                Age
              </label>
              <select
                id="student-age"
                value={age}
                onChange={(e) => setAge(Number(e.target.value))}
                className="rounded-md border border-muted-gray bg-white px-3 py-1.5 text-[13px] font-semibold text-ink"
              >
                {Array.from({ length: 8 }, (_, i) => 11 + i).map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>
            <div className="text-right">
              <div className="text-[13px] font-semibold text-ink">{stage.label}</div>
              <div className="text-[11px] text-slate-blue">{stage.ages}</div>
            </div>
          </div>

          {topics.length === 0 ? (
            <EmptyState
              icon={<Folder size={20} strokeWidth={1.6} />}
              title={`No topics for ${stage.label} yet`}
              body="We haven't added content for your school year here yet. Try another age, or retake the diagnostic to re-check your level."
              action={
                <Link
                  href="/diagnostic"
                  className="inline-flex items-center gap-1.5 rounded-md bg-focus-navy px-4 py-2.5 text-[12.5px] font-semibold text-white transition-opacity hover:opacity-80"
                >
                  <ClipboardCheck size={15} strokeWidth={1.8} /> Retake diagnostic
                </Link>
              }
            />
          ) : (
            <div className="flex flex-wrap gap-x-12 gap-y-14">
              {topics.map(({ topic: t, subs }) => {
                const lessons = subs.flatMap((s) => s.lessons);
                const pct = topicProgressForStage(t, ks, completed);
                const look = topicLook(t.id);
                const Icon = look.Icon;

                return (
                  <button
                    key={t.id}
                    onClick={() => setOpen(t)}
                    className="group/book flex w-[236px] flex-col items-start text-left"
                    aria-label={`Open ${t.title} — ${subs.length} subtopics, ${lessons.length} lessons, ${pct}% complete`}
                  >
                    <Book
                      variant="stripe"
                      title={t.title}
                      width={236}
                      color={look.color}
                      textColor="#2B2D42"
                      textured
                      illustration={
                        <Icon size={62} strokeWidth={1.25} style={{ color: '#FFFFFF', opacity: 0.9 }} />
                      }
                    />

                    <span
                      aria-hidden="true"
                      className="mt-3 h-px w-full bg-gradient-to-r from-muted-gray to-transparent"
                    />

                    <span className="mt-2.5 block text-[13.5px] font-semibold leading-snug text-ink">
                      {t.title}
                    </span>
                    <span className="mt-0.5 block text-[11.5px] leading-snug text-slate-blue">
                      {t.blurb}
                    </span>

                    <span className="mt-3 flex w-full items-center justify-between text-[11px] text-slate-blue">
                      <span>
                        {stage.label} · {subs.length} subtopic{subs.length === 1 ? '' : 's'} ·{' '}
                        {lessons.length} lesson{lessons.length === 1 ? '' : 's'}
                      </span>
                      <span className="tabular-nums">{pct}%</span>
                    </span>
                    <span className="mt-1.5 w-full">
                      <ProgressBar value={pct} />
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/*
          The topic opens ON the shelf rather than on its own route. Navigating
          away replaced the shelf with an unrelated page and broke the thread
          between the book you clicked and the book that opened; here the shelf
          stays visible behind it, so it is plainly the same object lifted off
          the shelf and opened.
        */}
        {open && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-[#1B2A4A]/55 p-6 backdrop-blur-sm"
            role="dialog"
            aria-modal="true"
            aria-label={`${open.title}, open`}
            onClick={() => setOpen(null)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setOpen(null);
            }}
          >
            {/* The backdrop closes; the book itself must not. */}
            <div className="relative" onClick={(e) => e.stopPropagation()}>
              <button
                onClick={() => setOpen(null)}
                aria-label="Close topic"
                className="absolute -top-12 right-0 inline-flex items-center gap-1.5 rounded-full bg-white/95 px-3.5 py-2 text-[12px] font-semibold text-ink shadow-lg transition-colors hover:bg-white"
              >
                <X size={14} strokeWidth={2.4} />
                Close
              </button>

              <TopicBook
                topic={open}
                subtopics={subtopicsForStage(open, ks)}
                keyStage={ks}
                progress={topicProgressForStage(open, ks, completed)}
                completed={completed}
                onToggleLesson={toggleLessonLearned}
              />
            </div>
          </div>
        )}
      </main>
    </PhaseGate>
  );
}
