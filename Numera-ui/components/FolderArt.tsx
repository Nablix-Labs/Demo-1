'use client';

/**
 * FolderArt — a soft, friendly open-folder illustration (papers peeking out +
 * a little face), used for topic "folders" in the Workbook. Inline SVG so it
 * scales crisply and needs no assets.
 */

export default function FolderArt({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 220 150" className={className} xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true">
      <defs>
        <filter id="folder-shadow" x="-25%" y="-25%" width="150%" height="160%">
          <feDropShadow dx="0" dy="4" stdDeviation="5" floodColor="#1B2A4A" floodOpacity="0.12" />
        </filter>
      </defs>

      {/* Back panel of the folder */}
      <rect x="34" y="36" width="152" height="102" rx="15" fill="#EBEEF1" />

      {/* Papers peeking out the top */}
      <g>
        <rect x="60" y="28" width="48" height="84" rx="7" fill="#FFFFFF" stroke="#EAECEF" strokeWidth="1.2" />
        <rect x="104" y="24" width="52" height="88" rx="7" fill="#FFFFFF" stroke="#EAECEF" strokeWidth="1.2" />
        {[0, 1, 2, 3, 4].map((i) => (
          <rect key={i} x="112" y={40 + i * 11} width={i % 2 ? 28 : 36} height="4.5" rx="2.25" fill="#E7E9EC" />
        ))}
      </g>

      {/* Front flap — high on the left, curving down to reveal the papers */}
      <path
        filter="url(#folder-shadow)"
        d="M22 76
           C22 68 28 62 36 62
           L92 62
           C98 62 103 65 106 70
           L114 84
           C116 88 120 90 125 90
           L184 90
           C192 90 198 96 198 104
           L198 126
           C198 134 192 140 184 140
           L36 140
           C28 140 22 134 22 126
           Z"
        fill="#F4F5F7"
        stroke="#E3E5E8"
        strokeWidth="1.5"
      />

      {/* Face */}
      <circle cx="94" cy="110" r="4.2" fill="#BAC0C8" />
      <circle cx="124" cy="110" r="4.2" fill="#BAC0C8" />
      <rect x="101" y="124" width="16" height="4.2" rx="2.1" fill="#BAC0C8" />
    </svg>
  );
}
