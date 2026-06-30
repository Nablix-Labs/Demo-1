'use client';

import Link from 'next/link';
import { Folder, ClipboardCheck } from 'lucide-react';
import PageShell, { ProgressBar, Chip, EmptyState } from '@/components/PageShell';
import PhaseGate from '@/components/PhaseGate';
import { useNumeraStore } from '@/store/useNumeraStore';
import {
  CURRICULUM, KEY_STAGES, subtopicsForStage, topicProgressForStage,
  keyStageForAge,
} from '@/lib/curriculum';

export default function WorkbookPage() {
  const completed = useNumeraStore((s) => s.completedLessons);
  const age = useNumeraStore((s) => s.studentAge);
  const setAge = useNumeraStore((s) => s.setStudentAge);

  // Age decides the Key Stage — the student only sees content for their stage.
  const ks = keyStageForAge(age);
  const stage = KEY_STAGES.find((k) => k.id === ks)!;

  // Only topics that have subtopics at the student's stage.
  const topics = CURRICULUM
    .map((t) => ({ topic: t, subs: subtopicsForStage(t, ks) }))
    .filter((x) => x.subs.length > 0);

  return (
    <PhaseGate phase="workbook">
    <PageShell
      title="Workbook"
      subtitle="Your topics and subtopics — matched to your school year."
      action={
        <Link href="/diagnostic" className="inline-flex items-center gap-1.5 rounded-md border border-muted-gray bg-white px-3.5 py-2 text-[12px] font-semibold text-ink hover:bg-reading-surface transition-colors">
          <ClipboardCheck size={15} strokeWidth={1.8} /> Take diagnostic
        </Link>
      }
    >
      {/* Age → Key Stage. Content is shown by age, not free choice. */}
      <div className="flex items-center justify-between gap-4 mb-5 rounded-lg border border-muted-gray bg-reading-surface px-5 py-3.5">
        <div className="flex items-center gap-2.5">
          <label htmlFor="student-age" className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue">
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
            <Link href="/diagnostic" className="inline-flex items-center gap-1.5 rounded-md bg-focus-navy text-white px-4 py-2.5 text-[12.5px] font-semibold hover:opacity-80 transition-opacity">
              <ClipboardCheck size={15} strokeWidth={1.8} /> Retake diagnostic
            </Link>
          }
        />
      ) : (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {topics.map(({ topic: t, subs }) => {
          const lessons = subs.flatMap((s) => s.lessons);
          const pct = topicProgressForStage(t, ks, completed);
          return (
            <Link
              key={t.id}
              href={`/workbook/${t.id}`}
              className="flex flex-col rounded-lg border border-muted-gray bg-white p-5 hover:border-muted-gray transition-colors"
            >
              <div className="flex items-start gap-3">
                <span className="flex-shrink-0 w-10 h-10 rounded-lg border border-muted-gray bg-reading-surface flex items-center justify-center">
                  <Folder size={18} strokeWidth={1.6} />
                </span>
                <div className="min-w-0">
                  <h2 className="text-[15px] font-semibold text-ink">{t.title}</h2>
                  <p className="text-[11.5px] text-slate-blue mt-0.5">{t.blurb}</p>
                </div>
              </div>

              <div className="flex flex-wrap gap-1.5 mt-3">
                <Chip>{ks}</Chip>
              </div>

              <div className="mt-4">
                <div className="flex items-center justify-between text-[11px] text-slate-blue mb-1.5">
                  <span>{subs.length} subtopics · {lessons.length} lessons</span>
                  <span>{pct}%</span>
                </div>
                <ProgressBar value={pct} />
              </div>
            </Link>
          );
        })}
      </div>
      )}
    </PageShell>
    </PhaseGate>
  );
}
