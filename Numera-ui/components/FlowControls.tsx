'use client';

/**
 * FlowControls — the MVP "Demo Director" + skip buttons.
 *
 * A fixed bar that drives the adaptive per-topic loop by hand so the founder
 * can walk the whole journey with no backend: place the student at a topic
 * (mock Main Diagnostic), skip stages, and force each Feedback & Review branch.
 * All rules live in lib/flow.ts; this only calls them, writes the store, and
 * navigates. Monochrome / text-only by house rules (no icons, emoji, gradients).
 *
 * Demo-only scaffolding — remove (or hide behind a flag) before production.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useNumeraStore } from '@/store/useNumeraStore';
import { TOPICS, topicIndex, topicById } from '@/lib/topics';
import { useFlowNav } from '@/lib/useFlowNav';
import type { FlowStage } from '@/lib/flow';

const STAGE_LABEL: Record<FlowStage, string> = {
  'topic-diagnostic': 'Topic diagnostic',
  orientation: 'Orientation',
  guided: 'Guided learning',
  practice: 'Practice',
  review: 'Feedback & review',
};

export default function FlowControls() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(true);
  useEffect(() => setMounted(true), []);

  // Toggle the bar with Shift+D (ignored while typing in a field).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing = el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName);
      if (!typing && e.shiftKey && (e.key === 'D' || e.key === 'd')) {
        setOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const reset = useNumeraStore((s) => s.reset);
  const {
    entryTopicId,
    currentTopicId,
    flowStage,
    masteryByTopic,
    placeAtTopic: place,
    advance: skip,
    decideDiagnostic,
    decideReview,
  } = useFlowNav();

  if (!mounted) return null;

  // Collapsed: a small unobtrusive pill to bring the demo controls back.
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        title="Show demo controls (Shift+D)"
        className="fixed bottom-3 right-3 z-50 rounded-full border border-muted-gray bg-white/95 backdrop-blur px-3 py-1.5 text-[10px] font-semibold tracking-widest uppercase text-slate-blue hover:text-ink hover:border-slate-blue transition-colors"
      >
        Demo
      </button>
    );
  }

  const idx = topicIndex(currentTopicId);
  const topic = topicById(currentTopicId);
  const placed = entryTopicId !== null;

  return (
    <div className="fixed bottom-0 inset-x-0 z-50 border-t border-muted-gray bg-reading-surface/95 backdrop-blur">
      <div className="w-full px-4 py-2 flex items-center gap-4 flex-wrap text-[12px] text-ink">
        {/* HUD */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold tracking-widest uppercase text-slate-blue border border-muted-gray rounded px-1.5 py-0.5">
            Demo
          </span>
          <span className="font-semibold">
            {placed ? `Topic ${idx + 1}/${TOPICS.length}: ${topic?.name}` : 'Not placed'}
          </span>
          <span className="text-slate-blue">·</span>
          <span className="text-slate-blue">{STAGE_LABEL[flowStage]}</span>
          {/* mastery dots */}
          <span className="flex items-center gap-1 ml-1">
            {TOPICS.map((t) => (
              <span
                key={t.id}
                title={t.name}
                className={
                  'w-2.5 h-2.5 rounded-sm border ' +
                  (masteryByTopic[t.id]
                    ? 'bg-success-sage border-success-sage'
                    : t.id === currentTopicId
                    ? 'bg-white border-focus-navy'
                    : 'bg-white border-muted-gray')
                }
              />
            ))}
          </span>
        </div>

        <div className="h-4 w-px bg-muted-gray" />

        {/* Stage-specific controls */}
        {!placed ? (
          <div className="flex items-center gap-2">
            <span className="text-slate-blue">Place student (mock diagnostic):</span>
            {TOPICS.map((t) => (
              <Btn key={t.id} onClick={() => place(t.id)}>
                {t.name}
              </Btn>
            ))}
          </div>
        ) : flowStage === 'topic-diagnostic' ? (
          <div className="flex items-center gap-2">
            <span className="text-slate-blue">Diagnostic result:</span>
            <Btn onClick={() => decideDiagnostic(true)}>Knows concept (skip orientation)</Btn>
            <Btn onClick={() => decideDiagnostic(false)}>Needs orientation</Btn>
          </div>
        ) : flowStage === 'review' ? (
          <div className="flex items-center gap-2">
            <span className="text-slate-blue">Decision:</span>
            <Btn onClick={() => decideReview('cant_solve')}>Can&apos;t solve → guided</Btn>
            <Btn onClick={() => decideReview('foundation_weak')}>Foundation weak → orientation</Btn>
            <Btn solid onClick={() => decideReview('pass')}>Pass → next topic</Btn>
          </div>
        ) : (
          <Btn solid onClick={skip}>
            Skip stage →
          </Btn>
        )}

        <div className="ml-auto flex items-center gap-3">
          <button
            onClick={() => {
              reset();
              router.push('/onboard');
            }}
            className="text-[11px] text-slate-blue hover:text-ink underline underline-offset-2"
          >
            Reset demo
          </button>
          <button
            onClick={() => setOpen(false)}
            title="Hide demo controls (Shift+D)"
            className="rounded border border-muted-gray px-1.5 py-0.5 text-[11px] font-semibold text-slate-blue hover:text-ink hover:border-slate-blue transition-colors"
          >
            Hide
          </button>
        </div>
      </div>
    </div>
  );
}

function Btn({
  children,
  onClick,
  solid,
}: {
  children: React.ReactNode;
  onClick: () => void;
  solid?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={
        'rounded-md px-2.5 py-1 text-[12px] font-semibold transition-colors ' +
        (solid
          ? 'bg-focus-navy text-white hover:opacity-80'
          : 'border border-muted-gray bg-white text-ink hover:border-slate-blue')
      }
    >
      {children}
    </button>
  );
}
