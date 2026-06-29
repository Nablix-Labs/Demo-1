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
        className="fixed bottom-3 right-3 z-50 rounded-full border border-[#c8c8c8] bg-white/95 backdrop-blur px-3 py-1.5 text-[10px] font-semibold tracking-widest uppercase text-[#9a9a9a] hover:text-[#1a1a1a] hover:border-[#9a9a9a] transition-colors"
      >
        Demo
      </button>
    );
  }

  const idx = topicIndex(currentTopicId);
  const topic = topicById(currentTopicId);
  const placed = entryTopicId !== null;

  return (
    <div className="fixed bottom-0 inset-x-0 z-50 border-t border-[#c8c8c8] bg-[#f4f4f4]/95 backdrop-blur">
      <div className="mx-auto max-w-[1500px] px-4 py-2 flex items-center gap-4 flex-wrap text-[12px] text-[#1a1a1a]">
        {/* HUD */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold tracking-widest uppercase text-[#9a9a9a] border border-[#c8c8c8] rounded px-1.5 py-0.5">
            Demo
          </span>
          <span className="font-semibold">
            {placed ? `Topic ${idx + 1}/${TOPICS.length}: ${topic?.name}` : 'Not placed'}
          </span>
          <span className="text-[#7a7a7a]">·</span>
          <span className="text-[#7a7a7a]">{STAGE_LABEL[flowStage]}</span>
          {/* mastery dots */}
          <span className="flex items-center gap-1 ml-1">
            {TOPICS.map((t) => (
              <span
                key={t.id}
                title={t.name}
                className={
                  'w-2.5 h-2.5 rounded-sm border ' +
                  (masteryByTopic[t.id]
                    ? 'bg-[#1a1a1a] border-[#1a1a1a]'
                    : t.id === currentTopicId
                    ? 'bg-white border-[#1a1a1a]'
                    : 'bg-white border-[#c8c8c8]')
                }
              />
            ))}
          </span>
        </div>

        <div className="h-4 w-px bg-[#c8c8c8]" />

        {/* Stage-specific controls */}
        {!placed ? (
          <div className="flex items-center gap-2">
            <span className="text-[#7a7a7a]">Place student (mock diagnostic):</span>
            {TOPICS.map((t) => (
              <Btn key={t.id} onClick={() => place(t.id)}>
                {t.name}
              </Btn>
            ))}
          </div>
        ) : flowStage === 'topic-diagnostic' ? (
          <div className="flex items-center gap-2">
            <span className="text-[#7a7a7a]">Diagnostic result:</span>
            <Btn onClick={() => decideDiagnostic(true)}>Knows concept (skip orientation)</Btn>
            <Btn onClick={() => decideDiagnostic(false)}>Needs orientation</Btn>
          </div>
        ) : flowStage === 'review' ? (
          <div className="flex items-center gap-2">
            <span className="text-[#7a7a7a]">Decision:</span>
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
            className="text-[11px] text-[#9a9a9a] hover:text-[#1a1a1a] underline underline-offset-2"
          >
            Reset demo
          </button>
          <button
            onClick={() => setOpen(false)}
            title="Hide demo controls (Shift+D)"
            className="rounded border border-[#c8c8c8] px-1.5 py-0.5 text-[11px] font-semibold text-[#9a9a9a] hover:text-[#1a1a1a] hover:border-[#9a9a9a] transition-colors"
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
          ? 'bg-[#1a1a1a] text-white hover:opacity-80'
          : 'border border-[#c8c8c8] bg-white text-[#1a1a1a] hover:border-[#9a9a9a]')
      }
    >
      {children}
    </button>
  );
}
