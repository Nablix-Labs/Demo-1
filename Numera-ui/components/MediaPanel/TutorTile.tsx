'use client';

/** AI Tutor video tile with animated avatar */
export default function TutorTile() {
  return (
    <div
      className="relative border border-muted-gray rounded-md overflow-hidden bg-reading-surface"
      style={{ aspectRatio: '4/3' }}
      aria-label="AI tutor"
    >
      {/* Animated avatar centred in tile */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="relative w-20 h-20 flex items-center justify-center">
          {/* Dashed spinning ring */}
          <div className="absolute inset-0 rounded-full border border-dashed border-ai-cyan animate-spin-slow" />
          {/* Pulse ring */}
          <div className="absolute inset-[7px] rounded-full border border-ai-cyan animate-pulse-ring" />
          {/* Avatar circle */}
          <div className="w-[52px] h-[52px] rounded-full bg-white border border-muted-gray flex items-center justify-center">
            {/* Inline robot SVG */}
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#1B2A4A" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="5" y="8" width="14" height="11" rx="2"/>
              <line x1="12" y1="5" x2="12" y2="8"/>
              <circle cx="12" cy="4" r="1"/>
              <circle cx="9.5" cy="13" r="1"/>
              <circle cx="14.5" cy="13" r="1"/>
              <line x1="9" y1="16.5" x2="15" y2="16.5"/>
            </svg>
          </div>
        </div>
      </div>

      {/* Name tag */}
      <div className="absolute left-2 bottom-2 bg-focus-navy/85 text-white text-[9.5px] px-2 py-0.5 rounded flex items-center gap-1">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="5" y="8" width="14" height="11" rx="2"/>
          <line x1="12" y1="5" x2="12" y2="8"/>
          <circle cx="12" cy="4" r="1"/>
          <circle cx="9.5" cy="13" r="1"/>
          <circle cx="14.5" cy="13" r="1"/>
          <line x1="9" y1="16.5" x2="15" y2="16.5"/>
        </svg>
        Numera
      </div>
    </div>
  );
}
