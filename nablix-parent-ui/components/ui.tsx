/**
 * Building blocks, ported from ResQMe/ios/ResQMe/UI/Components.swift so the
 * portal reads as the same system: cream canvas, notched cards, pastel stat
 * tiles, coloured hero blocks, numbered step rows, ranked capsule rows, round
 * icon tiles and dark pill buttons. Build every screen from these.
 */
import Link from 'next/link';
import type { ReactNode } from 'react';
import clsx from 'clsx';
import { ArrowDownRight, ArrowUpRight, Minus, Check } from 'lucide-react';
import { BASE_PATH } from '@/lib/api';

export const art = (name: string) => `${BASE_PATH}/art/${name}.webp`;

/** A picture per topic where we have one, else the subject's cover. */
const TOPIC_ART: Record<string, string> = {
  'ALG-KS3-01': 'linear-equations',
  'ALG-ORI-02': 'expressions',
  'ALG-ORI-03': 'algebra',
  'NUM-KS3-01': 'fractions',
};
export const topicArt = (t: { topic_id: string; strand: string }) => art(TOPIC_ART[t.topic_id] ?? t.strand);

export const dateLabel = (d: Date | string, opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' }) =>
  new Date(d).toLocaleDateString('en-GB', opts);

/* ── Surfaces ──────────────────────────────────────────────────── */

/** Cream card, 28px radius. `notch` adds the small tab bump on the top edge. */
export function Card({
  title, subtitle, icon, iconTint = 'teal', action, notch, fill = 'bg-card', className, children,
}: {
  title?: string;
  subtitle?: string;
  icon?: ReactNode;
  iconTint?: Tint;
  action?: ReactNode;
  notch?: boolean;
  fill?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={clsx('relative rounded-card p-5 sm:p-6', fill, className)}>
      {notch && <span aria-hidden className={clsx('absolute -top-[7px] left-1/2 h-[15px] w-[34px] -translate-x-1/2 rounded-[9px]', fill)} />}
      {(title || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            {icon && <IconTile tint={iconTint}>{icon}</IconTile>}
            <div>
              {title && <h2 className="text-[19px] font-extrabold leading-tight tracking-[-0.01em] text-ink">{title}</h2>}
              {subtitle && <p className="mt-0.5 text-[13px] font-semibold text-ink-soft">{subtitle}</p>}
            </div>
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

/** Bold coloured block (the teal "Leaderboard" / pink "Hi, Elizabeth" panels). */
export function Hero({ color = 'bg-teal', className, children }: { color?: string; className?: string; children: ReactNode }) {
  return <section className={clsx('relative overflow-hidden rounded-card p-6 text-white sm:p-7', color, className)}>{children}</section>;
}

/** The wave that splits coloured bands (bottom of the SOS card). */
export function Wave({ className, color = '#F4B63F' }: { className?: string; color?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 400 80" preserveAspectRatio="none" className={clsx('pointer-events-none absolute left-0 w-full', className)}>
      <path d="M0 26 C120 -14 260 70 400 26 L400 80 L0 80 Z" fill={color} />
    </svg>
  );
}

/* ── Tiles ─────────────────────────────────────────────────────── */

export type Tint = 'teal' | 'mustard' | 'coral' | 'mint' | 'info' | 'cream';

const TINT_BG: Record<Tint, string> = {
  teal: 'bg-teal-soft', mustard: 'bg-mustard-soft', coral: 'bg-coral-soft', mint: 'bg-mint', info: 'bg-info-soft', cream: 'bg-cream-deep',
};

/** Round tinted icon at the start of rows and cards. */
export function IconTile({ tint = 'teal', size = 40, children }: { tint?: Tint; size?: number; children: ReactNode }) {
  return (
    <span className={clsx('flex flex-shrink-0 items-center justify-center rounded-full text-ink', TINT_BG[tint])} style={{ width: size, height: size }}>
      {children}
    </span>
  );
}

/** Pastel stat tile: icon circle, big number, small label. `dashed` is the outlined variant. */
export function StatTile({ value, label, icon, tint = 'mint', dashed, className }: {
  value: ReactNode;
  label: string;
  icon?: ReactNode;
  tint?: Tint;
  dashed?: boolean;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        'flex flex-col items-center justify-center gap-1.5 rounded-tile px-2 py-4 text-center',
        dashed ? 'border-[1.5px] border-dashed border-ink/35' : TINT_BG[tint],
        className,
      )}
    >
      {icon && (
        <span className={clsx('flex h-8 w-8 items-center justify-center rounded-full text-ink', dashed ? 'border-[1.5px] border-ink/50' : 'bg-white/70')}>
          {icon}
        </span>
      )}
      <span className="tabular text-[30px] font-black leading-none tracking-[-0.02em] text-ink">{value}</span>
      <span className="text-[12px] font-bold text-ink-soft">{label}</span>
    </div>
  );
}

/* ── Rows ──────────────────────────────────────────────────────── */

/** Numbered progress row (the "1 Alert sent ✓" rows). */
export function StepRow({ n, title, body, state, tint = 'teal', trailing }: {
  n: number;
  title: string;
  body?: string;
  state: 'done' | 'now' | 'todo';
  tint?: Tint;
  trailing?: ReactNode;
}) {
  return (
    <div
      className={clsx(
        'flex items-center gap-3.5 rounded-[22px] px-4 py-3',
        state === 'done' ? 'bg-teal-soft' : state === 'now' ? TINT_BG[tint] : 'border-[1.5px] border-dashed border-ink/25',
      )}
    >
      <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-white/80 text-[15px] font-black text-ink">{n}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] font-extrabold leading-tight text-ink">{title}</span>
        {body && <span className="mt-0.5 block text-[12.5px] font-semibold leading-snug text-ink-soft">{body}</span>}
      </span>
      {trailing ?? (state === 'done' ? (
        <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-teal text-white"><Check size={16} strokeWidth={3.2} aria-label="Done" /></span>
      ) : state === 'todo' ? (
        <span className="h-5 w-5 flex-shrink-0 rounded-full border-[1.5px] border-ink/35" aria-label="To come" />
      ) : null)}
    </div>
  );
}

/** Ranked capsule row (the "#1 Priya · Alert  47s" rows). */
export function RankRow({ rank, title, body, fill = 'bg-mustard', trailing }: {
  rank: string;
  title: string;
  body?: string;
  fill?: string;
  trailing?: ReactNode;
}) {
  return (
    <div className={clsx('flex min-h-[60px] items-center gap-3 rounded-full py-2 pl-5 pr-2', fill)}>
      <span className="text-[20px] font-black text-ink">{rank}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[15px] font-extrabold text-ink">{title}</span>
        {body && <span className="block truncate text-[12px] font-semibold text-ink/70">{body}</span>}
      </span>
      {trailing}
    </div>
  );
}

/** White bubble at the end of a rank row. */
export function Bubble({ children, dark }: { children: ReactNode; dark?: boolean }) {
  return (
    <span className={clsx('flex h-11 min-w-11 flex-shrink-0 flex-col items-center justify-center rounded-full px-2 text-center leading-none', dark ? 'bg-ink text-white' : 'bg-white text-ink')}>
      {children}
    </span>
  );
}

/* ── Labels and buttons ───────────────────────────────────────── */

export type Tone = 'good' | 'warn' | 'bad' | 'neutral' | 'info';
const TONE_DOT: Record<Tone, string> = { good: 'bg-teal', warn: 'bg-mustard', bad: 'bg-coral', neutral: 'bg-ink-soft', info: 'bg-info' };
const TONE_BG: Record<Tone, string> = {
  good: 'bg-teal-soft', warn: 'bg-mustard-soft', bad: 'bg-coral-soft', neutral: 'bg-cream-deep', info: 'bg-info-soft',
};

/** Status chip: tinted capsule with a dot. */
export function Pill({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={clsx('inline-flex flex-shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[12px] font-extrabold text-ink', TONE_BG[tone])}>
      <span className={clsx('h-[7px] w-[7px] rounded-full', TONE_DOT[tone])} aria-hidden />
      {children}
    </span>
  );
}

/** Dark capsule button or link. */
export function PillButton({ href, onClick, icon, children, tone = 'dark', className, disabled }: {
  href?: string;
  onClick?: () => void;
  icon?: ReactNode;
  children: ReactNode;
  tone?: 'dark' | 'light' | 'coral' | 'teal';
  className?: string;
  disabled?: boolean;
}) {
  const cls = clsx(
    'inline-flex items-center justify-center gap-2.5 rounded-full px-5 py-3 text-[14px] font-extrabold transition-transform active:scale-[0.97] disabled:opacity-60',
    tone === 'dark' && 'bg-ink text-white',
    tone === 'light' && 'bg-white text-ink',
    tone === 'coral' && 'bg-coral text-white',
    tone === 'teal' && 'bg-teal text-white',
    className,
  );
  const inner = (
    <>
      {icon && <span className={clsx('flex h-[26px] w-[26px] items-center justify-center rounded-full', tone === 'light' ? 'bg-ink/10' : 'bg-white/20')}>{icon}</span>}
      {children}
    </>
  );
  return href ? <Link href={href} className={cls}>{inner}</Link> : <button onClick={onClick} disabled={disabled} className={cls}>{inner}</button>;
}

/** Segmented capsule switch: selected is a white capsule. */
export function Segments<T extends string | number>({ options, value, onChange, onDark, label }: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  onDark?: boolean;
  label: string;
}) {
  return (
    <div className="flex gap-1.5" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={clsx(
            'min-h-[40px] flex-1 whitespace-nowrap rounded-full px-4 text-[13.5px] font-extrabold transition-colors',
            value === o.value ? 'bg-white text-ink shadow-[0_1px_0_rgba(31,29,26,0.06)]' : onDark ? 'bg-white/15 text-white' : 'bg-cream-deep text-ink-soft hover:text-ink',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Section heading outside a card ("Quick dial"  ·  "UAE"). */
export function SectionTitle({ children, trailing }: { children: ReactNode; trailing?: ReactNode }) {
  return (
    <div className="mb-3 mt-8 flex items-end justify-between px-1">
      <h2 className="text-[21px] font-black tracking-[-0.01em] text-ink">{children}</h2>
      {trailing && <span className="text-[12.5px] font-bold text-ink-soft">{trailing}</span>}
    </div>
  );
}

/**
 * Change against the previous period. `goodWhenUp` says which way is good —
 * fewer seconds per question is an improvement, so time passes `false`.
 */
export function Delta({ value, unit = '', goodWhenUp = true, label = 'vs before', onDark }: {
  value: number;
  unit?: string;
  goodWhenUp?: boolean;
  label?: string;
  onDark?: boolean;
}) {
  const good = value === 0 ? null : (value > 0) === goodWhenUp;
  const Icon = value > 0 ? ArrowUpRight : value < 0 ? ArrowDownRight : Minus;
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[12px] font-extrabold',
        onDark ? 'bg-white/20 text-white' : good === null ? 'bg-cream-deep text-ink' : good ? 'bg-teal-soft text-ink' : 'bg-coral-soft text-ink',
      )}
    >
      <Icon size={14} strokeWidth={2.6} aria-hidden />
      {value > 0 ? '+' : ''}{value}{unit} <span className="font-bold opacity-70">{label}</span>
    </span>
  );
}

export function ProgressBar({ value, tone = 'teal' }: { value: number; tone?: 'teal' | 'mustard' }) {
  return (
    <div className="h-2.5 w-full overflow-hidden rounded-full bg-cream-deep" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <div className={clsx('h-full rounded-full', tone === 'teal' ? 'bg-teal' : 'bg-mustard')} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[32px] font-black leading-[1.05] tracking-[-0.025em] text-ink">{title}</h1>
        {subtitle && <p className="mt-1.5 text-[14.5px] font-semibold text-ink-soft">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

/** Empty / placeholder state with art. */
export function Empty({ title, body, image = 'axo-sleep' }: { title: string; body: string; image?: string }) {
  return (
    <div className="flex flex-col items-center px-6 py-8 text-center">
      {/* eslint-disable-next-line @next/next/no-img-element -- static export */}
      <img src={art(image)} alt="" aria-hidden className="mb-3 h-24 w-auto object-contain" />
      <p className="text-[17px] font-extrabold text-ink">{title}</p>
      <p className="mt-1 max-w-sm text-[13px] font-semibold leading-relaxed text-ink-soft">{body}</p>
    </div>
  );
}
