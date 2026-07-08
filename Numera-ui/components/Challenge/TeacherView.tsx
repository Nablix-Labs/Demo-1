'use client';

/**
 * TeacherView — optional full-visibility overview for supervision (PDF §5).
 * Unlike the student view (own private canvas only), a teacher/admin sees
 * every student's scratch pad at once — the grid layout from the concept.
 * Thumbnails are mock placeholders; real ones come from the snapshot stream.
 */

import { useNumeraStore } from '@/store/useNumeraStore';

const STATUSES = ['Working', 'Reviewed', 'Stuck', 'Working', 'Reviewed'];

export default function TeacherView() {
  const participants = useNumeraStore((s) => s.participants);
  const students = [
    { id: 'you', name: 'You', color: '#4169E1' },
    ...participants.map((p) => ({ id: p.id, name: p.name, color: p.color })),
  ];

  return (
    <main className="flex-1 min-w-0 bg-white overflow-y-auto" aria-label="Teacher overview">
      <div className="px-6 py-4 border-b border-muted-gray flex items-center gap-2">
        <span className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue">All student canvases · full visibility</span>
      </div>
      <div className="p-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {students.map((s, idx) => (
          <div key={s.id} className="rounded-lg border border-muted-gray overflow-hidden">
            {/* scratch-pad thumbnail */}
            <div
              className="h-36 relative"
              style={{
                backgroundImage:
                  'linear-gradient(#E0E2E5 1px, transparent 1px), linear-gradient(90deg, #E0E2E5 1px, transparent 1px)',
                backgroundSize: '20px 20px',
              }}
            >
              <span className="absolute top-2 left-2 flex items-center gap-1.5 text-[11px] font-semibold text-white px-2 py-0.5 rounded" style={{ background: s.color }}>
                {s.name}
              </span>
              <span className="absolute bottom-2 right-2 text-[10px] tracking-wide uppercase text-slate-blue bg-white/80 rounded px-1.5 py-0.5">
                {STATUSES[idx % STATUSES.length]}
              </span>
            </div>
            <div className="px-4 py-2.5 text-[11.5px] text-slate-blue border-t border-muted-gray">
              {s.id === 'you' ? 'Your scratch pad' : `${s.name}'s scratch pad`}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
