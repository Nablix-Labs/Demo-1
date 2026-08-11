'use client';

/**
 * AI Tutor tile — the identity mark for Numera in the tutor panel.
 *
 * The photoreal 3D head (Ready Player Me .glb) was removed on Manjusha's
 * instruction, 2026-07-29. What remains is the orb that was already the tile's
 * fail-soft fallback, so nothing here is newly invented — it is the state the
 * tile already showed whenever WebGL or the model was unavailable.
 *
 * Dropping it also frees a WebGL context. The app runs several at once and
 * browsers evict the oldest, which is what turned the centred screens dark
 * earlier today (see components/ui/waves-shaders-homlu-ui.tsx).
 */

const RobotIcon = ({ size }: { size: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="5" y="8" width="14" height="11" rx="2" />
    <line x1="12" y1="5" x2="12" y2="8" />
    <circle cx="12" cy="4" r="1" />
    <circle cx="9.5" cy="13" r="1" />
    <circle cx="14.5" cy="13" r="1" />
    <line x1="9" y1="16.5" x2="15" y2="16.5" />
  </svg>
);

export default function TutorTile() {
  return (
    <div
      className="relative border border-muted-gray rounded-md overflow-hidden bg-reading-surface"
      style={{ aspectRatio: '4/3' }}
      aria-label="AI tutor"
    >
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="relative w-20 h-20 flex items-center justify-center">
          <div className="absolute inset-0 rounded-full border border-dashed border-ai-cyan animate-spin-slow" />
          <div className="absolute inset-[7px] rounded-full border border-ai-cyan animate-pulse-ring" />
          <div className="w-[52px] h-[52px] rounded-full bg-white border border-muted-gray flex items-center justify-center text-focus-navy">
            <RobotIcon size={24} />
          </div>
        </div>
      </div>

      {/* Name tag */}
      <div className="absolute left-2 bottom-2 z-10 bg-focus-navy/85 text-white text-[9.5px] px-2 py-0.5 rounded flex items-center gap-1">
        <RobotIcon size={12} />
        Numera
      </div>
    </div>
  );
}
