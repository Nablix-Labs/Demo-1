'use client';

/**
 * The portal's three charts, plain SVG.
 *
 * Specs (dataviz skill): 2px lines, ≥8px markers with a 2px surface ring,
 * columns ≤24px with 4px rounded tops on one baseline, hairline solid
 * gridlines, a hover tooltip on every mark, labels in text colours (never the
 * series colour), and a screen-reader table for each. The outcome colours were
 * run through the palette validator (CVD ΔE ≥ 11) and always carry a label.
 */
import { useEffect, useRef, useState } from 'react';
import { dateLabel } from './ui';

/**
 * Charts draw at their real pixel width. A fixed viewBox scaled down into a
 * narrow card shrank the 10px axis text to about 4px.
 */
function useWidth(initial = 560) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(initial);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(160, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

const SURFACE = '#FFFDF2';
const GRID = '#ECE6CF';
const AXIS_TEXT = '#6E6A60';
const SERIES = '#1F9A78';

/* ── Donut: share of answers by outcome ─────────────────────────── */

export interface Slice { label: string; value: number; color: string }

export function Donut({ slices, center, sub }: { slices: Slice[]; center: string; sub: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const total = slices.reduce((s, x) => s + x.value, 0);
  const R = 52, W = 14, C = 2 * Math.PI * R;
  // 2px surface gap between segments, expressed along the circumference.
  const gap = total && slices.filter((s) => s.value > 0).length > 1 ? 2 : 0;
  let offset = 0;
  return (
    <div className="relative h-[136px] w-[136px] flex-shrink-0">
      <svg viewBox="0 0 136 136" className="h-full w-full -rotate-90" role="img" aria-label={`${center} ${sub}`}>
        <circle cx="68" cy="68" r={R} fill="none" stroke={GRID} strokeWidth={W} />
        {total > 0 && slices.map((s, i) => {
          const len = (s.value / total) * C;
          const el = len > 0 && (
            <circle
              key={s.label}
              cx="68" cy="68" r={R} fill="none"
              stroke={s.color}
              strokeWidth={hover === i ? W + 3 : W}
              strokeDasharray={`${Math.max(0, len - gap)} ${C}`}
              strokeDashoffset={-offset}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              className="cursor-default transition-[stroke-width]"
            />
          );
          offset += len;
          return el;
        })}
      </svg>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
        {hover === null ? (
          <>
            <span className="text-[28px] font-black leading-none text-ink">{center}</span>
            <span className="mt-1 text-[11px] font-bold text-ink-soft">{sub}</span>
          </>
        ) : (
          <>
            <span className="text-[22px] font-black leading-none text-ink">{slices[hover].value}</span>
            <span className="mt-1 max-w-[80px] text-[11px] font-bold leading-tight text-ink-soft">{slices[hover].label}</span>
          </>
        )}
      </div>
    </div>
  );
}

/* ── Columns: questions answered per day ────────────────────────── */

export function Columns({ data, height = 120 }: { data: { date: Date; count: number }[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const [ref, W] = useWidth();
  const H = height, PAD_L = 26, PAD_B = 20, PAD_T = 14;
  const max = Math.max(4, ...data.map((d) => d.count));
  const top = Math.ceil(max / 4) * 4;
  const slot = (W - PAD_L) / data.length;
  const bw = Math.min(24, Math.max(3, slot * 0.6));
  const y = (v: number) => PAD_T + (H - PAD_T - PAD_B) * (1 - v / top);
  // Enough room for each date label (~44px), whatever the width.
  const every = Math.max(1, Math.ceil(data.length / Math.floor((W - PAD_L) / 44)));
  const peak = data.reduce((m, d, i) => (d.count > data[m].count ? i : m), 0);
  const fmt = (d: Date) => (data.length <= 7 ? d.toLocaleDateString('en-GB', { weekday: 'short' }) : dateLabel(d));
  const showLabel = (i: number) => (data.length - 1 - i) % every === 0;

  return (
    <div ref={ref} className="relative">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="block" role="img" aria-label="Questions answered per day">
        {[0, top / 2, top].map((v) => (
          <g key={v}>
            <line x1={PAD_L} x2={W} y1={y(v)} y2={y(v)} stroke={GRID} strokeWidth={1} />
            <text x={PAD_L - 6} y={y(v) + 3.5} textAnchor="end" fontSize="10" fill={AXIS_TEXT}>{v}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const cx = PAD_L + slot * i + slot / 2;
          const h = y(0) - y(d.count);
          const r = Math.min(4, bw / 2, h);
          const x0 = cx - bw / 2, yTop = y(d.count), yb = y(0);
          return (
            <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              {/* Hit target: the whole slot, taller than the bar. */}
              <rect x={PAD_L + slot * i} y={PAD_T} width={slot} height={H - PAD_T - PAD_B} fill="transparent" />
              {d.count > 0 && (
                <path
                  d={`M${x0},${yb} V${yTop + r} Q${x0},${yTop} ${x0 + r},${yTop} H${x0 + bw - r} Q${x0 + bw},${yTop} ${x0 + bw},${yTop + r} V${yb} Z`}
                  fill={SERIES}
                  opacity={hover === null || hover === i ? 1 : 0.45}
                />
              )}
              {showLabel(i) && (
                <text x={cx} y={H - 5} textAnchor="middle" fontSize="10" fill={AXIS_TEXT}>{fmt(d.date)}</text>
              )}
              {i === peak && d.count > 0 && hover === null && (
                <text x={cx} y={yTop - 4} textAnchor="middle" fontSize="10.5" fontWeight="800" fill="#1F1D1A">{d.count}</text>
              )}
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <Tip leftPct={((PAD_L + slot * hover + slot / 2) / W) * 100}>
          <b>{data[hover].count}</b> question{data[hover].count === 1 ? '' : 's'} · {dateLabel(data[hover].date, { weekday: 'short', day: 'numeric', month: 'short' })}
        </Tip>
      )}
      <SrTable caption="Questions answered per day" rows={data.map((d) => [dateLabel(d.date), String(d.count)])} />
    </div>
  );
}

/* ── Line: weekly score ─────────────────────────────────────────── */

export function ScoreLine({ data, height = 150 }: { data: { weekEnding: Date; score: number | null }[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const [ref, W] = useWidth();
  const H = height, PAD_L = 34, PAD_R = 22, PAD_B = 22, PAD_T = 18;
  const step = Math.max(1, Math.ceil(data.length / Math.floor((W - PAD_L - PAD_R) / 48)));
  const x = (i: number) => PAD_L + ((W - PAD_L - PAD_R) * i) / Math.max(1, data.length - 1);
  const y = (v: number) => PAD_T + (H - PAD_T - PAD_B) * (1 - v / 100);
  const pts = data.map((d, i) => (d.score === null ? null : { i, x: x(i), y: y(d.score), v: d.score }));
  const real = pts.filter(Boolean) as { i: number; x: number; y: number; v: number }[];
  const path = real.map((p, k) => `${k ? 'L' : 'M'}${p.x},${p.y}`).join(' ');
  const last = real[real.length - 1];

  return (
    <div ref={ref} className="relative">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="block" role="img" aria-label="Weekly score">
        {[0, 50, 100].map((v) => (
          <g key={v}>
            <line x1={PAD_L} x2={W - PAD_R} y1={y(v)} y2={y(v)} stroke={GRID} strokeWidth={1} />
            <text x={PAD_L - 6} y={y(v) + 3.5} textAnchor="end" fontSize="10" fill={AXIS_TEXT}>{v}%</text>
          </g>
        ))}
        {real.length > 1 && (
          <path d={`${path} L${last.x},${y(0)} L${real[0].x},${y(0)} Z`} fill={SERIES} opacity={0.08} />
        )}
        <path d={path} fill="none" stroke={SERIES} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {hover !== null && pts[hover] && (
          <line x1={pts[hover]!.x} x2={pts[hover]!.x} y1={PAD_T} y2={y(0)} stroke="#CFC7A8" strokeWidth={1} />
        )}
        {real.map((p) => (
          <circle key={p.i} cx={p.x} cy={p.y} r={hover === p.i ? 5.5 : 4} fill={SERIES} stroke={SURFACE} strokeWidth={2} />
        ))}
        {last && hover === null && (
          <text x={last.x} y={last.y - 10} textAnchor="middle" fontSize="11" fontWeight="800" fill="#1F1D1A">{last.v}%</text>
        )}
        {data.map((d, i) => (
          <g key={i}>
            <rect
              x={x(i) - (W - PAD_L - PAD_R) / Math.max(1, data.length - 1) / 2}
              y={0}
              width={(W - PAD_L - PAD_R) / Math.max(1, data.length - 1)}
              height={H}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
            {(data.length - 1 - i) % step === 0 && (
              <text x={x(i)} y={H - 6} textAnchor="middle" fontSize="10" fill={AXIS_TEXT}>{dateLabel(d.weekEnding)}</text>
            )}
          </g>
        ))}
      </svg>
      {hover !== null && (
        <Tip leftPct={(x(hover) / W) * 100}>
          Week to {dateLabel(data[hover].weekEnding)}: <b>{data[hover].score === null ? 'no sessions' : `${data[hover].score}%`}</b>
        </Tip>
      )}
      <SrTable caption="Weekly score" rows={data.map((d) => [dateLabel(d.weekEnding), d.score === null ? '—' : `${d.score}%`])} />
    </div>
  );
}

function Tip({ leftPct, children }: { leftPct: number; children: React.ReactNode }) {
  return (
    <div
      className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-lg bg-ink px-3 py-1.5 text-[12px] font-bold text-white shadow-lg"
      style={{ left: `${Math.min(88, Math.max(12, leftPct))}%` }}
    >
      {children}
    </div>
  );
}

function SrTable({ caption, rows }: { caption: string; rows: string[][] }) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
    </table>
  );
}
