'use client';

/**
 * PrivateCanvas — the student's own working surface in Group Challenge Mode.
 * Only this student and the AI see it. Auto-reviews on a ~3s pause (no Submit
 * button), reflecting the "auto canvas review" rule.
 */

import { useCallback, useEffect, useRef } from 'react';
import dynamic from 'next/dynamic';
import { Lock } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import Toolbar from '@/components/Canvas/Toolbar';

const DrawingCanvas = dynamic(() => import('@/components/Canvas/DrawingCanvas'), { ssr: false });

export default function PrivateCanvas() {
  const items = useNumeraStore((s) => s.items);
  const reviewStatus = useNumeraStore((s) => s.reviewStatus);
  const setReviewStatus = useNumeraStore((s) => s.setReviewStatus);
  const setCanvasExporter = useNumeraStore((s) => s.setCanvasExporter);
  const exportRef = useRef<(() => string | null) | null>(null);

  const handleExportReady = useCallback((fn: () => string | null) => {
    exportRef.current = fn;
    setCanvasExporter(fn);
  }, [setCanvasExporter]);

  // Auto-review: after a stroke, mark "reviewing", then "reviewed" on a 3s pause
  useEffect(() => {
    if (items.length === 0) return;
    setReviewStatus('reviewing');
    const t = setTimeout(() => setReviewStatus('reviewed'), 3000);
    return () => clearTimeout(t);
  }, [items.length, setReviewStatus]);

  const reviewLabel =
    reviewStatus === 'reviewing' ? 'Reviewing…' : reviewStatus === 'reviewed' ? 'Reviewed' : 'Auto-review on';

  return (
    <main
      className="flex-1 relative min-w-0 bg-white overflow-hidden"
      aria-label="Your private canvas"
      style={{
        backgroundImage:
          'linear-gradient(#E0E2E5 1px, transparent 1px), linear-gradient(90deg, #E0E2E5 1px, transparent 1px)',
        backgroundSize: '28px 28px',
      }}
    >
      {/* Private label + auto-review status */}
      <div className="absolute top-[22px] left-[34px] z-10 flex items-center gap-3">
        <span className="flex items-center gap-1.5 text-[11px] tracking-[1px] uppercase text-slate-blue">
          <Lock size={13} strokeWidth={1.8} /> Your canvas
        </span>
        <span
          className={
            'flex items-center gap-1.5 text-[11px] rounded-full border px-2.5 py-1 ' +
            (reviewStatus === 'reviewed'
              ? 'border-focus-navy text-ink'
              : 'border-muted-gray text-slate-blue')
          }
        >
          <span className={'w-1.5 h-1.5 rounded-full ' + (reviewStatus === 'reviewing' ? 'bg-ai-cyan animate-pulse' : 'bg-focus-navy')} />
          {reviewLabel}
        </span>
      </div>

      <div className="absolute inset-0 z-[1]">
        <DrawingCanvas onExportReady={handleExportReady} />
      </div>

      {/* Manual review still available via Check (auto-review is primary) */}
      <Toolbar onCheckWork={() => setReviewStatus('reviewed')} />
    </main>
  );
}
