'use client';

/**
 * ConceptArt — self-contained inline-SVG concept illustrations, keyed by name.
 *
 * Used as the "picture" for guided-practice visual cues and orientation
 * micro-content. Inline SVG (no asset files) so it's crisp at any size and needs
 * no backend media. When the backend serves real images later, callers can swap
 * to an <img>; the surrounding UI (VisualCue / orientation) stays the same.
 */

export type ConceptArtName = 'balance' | 'fractionBar' | 'anglePair' | 'barChart';

const NAVY = '#1B2A4A';
const CYAN = '#00B4D8';
const AMBER = '#FF9F1C';
const SURFACE = '#F4F6F9';
const MUTED = '#C7CCD3';

export default function ConceptArt({ name, className }: { name: ConceptArtName; className?: string }) {
  return (
    <svg viewBox="0 0 240 150" className={className} role="img" xmlns="http://www.w3.org/2000/svg">
      {name === 'balance' && <Balance />}
      {name === 'fractionBar' && <FractionBar />}
      {name === 'anglePair' && <AnglePair />}
      {name === 'barChart' && <BarChart />}
    </svg>
  );
}

/** Balance scale — "keep both sides equal" (algebra). */
function Balance() {
  return (
    <g fill="none" stroke={NAVY} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      {/* stand */}
      <line x1="120" y1="34" x2="120" y2="104" />
      <line x1="98" y1="120" x2="142" y2="120" />
      <path d="M108 120 L120 104 L132 120 Z" fill={SURFACE} />
      {/* beam */}
      <line x1="58" y1="46" x2="182" y2="46" stroke={CYAN} strokeWidth="3" />
      <circle cx="120" cy="46" r="4" fill={NAVY} stroke="none" />
      {/* left pan */}
      <line x1="58" y1="46" x2="58" y2="78" />
      <path d="M40 78 Q58 96 76 78" fill={SURFACE} />
      <text x="58" y="70" textAnchor="middle" fontSize="15" fontWeight="700" fill={NAVY} stroke="none" fontFamily="Georgia, serif">2x+5</text>
      {/* right pan */}
      <line x1="182" y1="46" x2="182" y2="78" />
      <path d="M164 78 Q182 96 200 78" fill={SURFACE} />
      <text x="182" y="70" textAnchor="middle" fontSize="15" fontWeight="700" fill={NAVY} stroke="none" fontFamily="Georgia, serif">13</text>
      {/* equals accent */}
      <line x1="112" y1="132" x2="128" y2="132" stroke={AMBER} strokeWidth="3" />
      <line x1="112" y1="138" x2="128" y2="138" stroke={AMBER} strokeWidth="3" />
    </g>
  );
}

/** Fraction bar — 3 of 4 parts shaded (number / fractions). */
function FractionBar() {
  const x0 = 24, x1 = 216, y = 52, h = 46, n = 4;
  const w = (x1 - x0) / n;
  return (
    <g>
      {Array.from({ length: n }).map((_, i) => (
        <rect
          key={i}
          x={x0 + i * w}
          y={y}
          width={w}
          height={h}
          fill={i < 3 ? CYAN : SURFACE}
          stroke={NAVY}
          strokeWidth="2"
        />
      ))}
      <text x="120" y="124" textAnchor="middle" fontSize="20" fontWeight="700" fill={NAVY} fontFamily="Georgia, serif">
        3&frasl;4
      </text>
    </g>
  );
}

/** Bar chart — the tallest bar (the mode) highlighted (statistics). */
function BarChart() {
  const bars = [40, 66, 96, 58, 30]; // heights; index 2 is the mode
  const baseY = 122, x0 = 34, bw = 26, gap = 12;
  const modeIdx = bars.indexOf(Math.max(...bars));
  return (
    <g>
      {/* axes */}
      <line x1={x0 - 8} y1={baseY} x2="214" y2={baseY} stroke={NAVY} strokeWidth="2.4" strokeLinecap="round" />
      <line x1={x0 - 8} y1={baseY} x2={x0 - 8} y2="28" stroke={NAVY} strokeWidth="2.4" strokeLinecap="round" />
      {bars.map((h, i) => {
        const x = x0 + i * (bw + gap);
        const isMode = i === modeIdx;
        return (
          <rect
            key={i}
            x={x}
            y={baseY - h}
            width={bw}
            height={h}
            rx="2"
            fill={isMode ? AMBER : CYAN}
            stroke={NAVY}
            strokeWidth="1.6"
          />
        );
      })}
      <text x={x0 + modeIdx * (bw + gap) + bw / 2} y="20" textAnchor="middle" fontSize="11" fontWeight="700" fill={AMBER}>
        mode
      </text>
    </g>
  );
}

/** Two angles on a straight line — one known, one is x (geometry). */
function AnglePair() {
  return (
    <g fill="none" stroke={NAVY} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <line x1="26" y1="112" x2="214" y2="112" />
      <line x1="120" y1="112" x2="176" y2="44" stroke={CYAN} strokeWidth="2.8" />
      <circle cx="120" cy="112" r="3.5" fill={NAVY} stroke="none" />
      {/* known-angle arc (right side) */}
      <path d="M150 112 A30 30 0 0 0 141 90" stroke={MUTED} />
      <text x="150" y="104" textAnchor="middle" fontSize="12" fontWeight="600" fill={NAVY} stroke="none">50°</text>
      {/* unknown-angle arc (left side) */}
      <path d="M92 112 A28 28 0 0 1 103 92" stroke={AMBER} strokeWidth="2.8" />
      <text x="86" y="98" textAnchor="middle" fontSize="15" fontWeight="700" fill={AMBER} stroke="none" fontStyle="italic" fontFamily="Georgia, serif">x</text>
    </g>
  );
}
