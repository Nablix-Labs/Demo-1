import { ChevronUp, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

/** Up/down reorder control for ordered lists (scenes, steps, stages). */
export function MoveControls({ onUp, onDown, canUp, canDown }: { onUp: () => void; onDown: () => void; canUp: boolean; canDown: boolean }) {
  return (
    <div className="flex flex-col">
      <button onClick={onUp} disabled={!canUp} className="flex h-4 w-5 items-center justify-center rounded text-slate-blue/70 hover:bg-reading-surface hover:text-ink disabled:opacity-30" aria-label="Move up">
        <ChevronUp className="h-3.5 w-3.5" />
      </button>
      <button onClick={onDown} disabled={!canDown} className="flex h-4 w-5 items-center justify-center rounded text-slate-blue/70 hover:bg-reading-surface hover:text-ink disabled:opacity-30" aria-label="Move down">
        <ChevronDown className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

/** Consistent editor-section masthead: eyebrow · display title · description · action. */
export function SectionHeader({
  eyebrow,
  icon,
  title,
  description,
  action,
  className,
}: {
  eyebrow: string;
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-wrap items-start justify-between gap-3', className)}>
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 text-2xs font-bold uppercase tracking-widest text-learning-blue">
          {icon}
          {eyebrow}
        </div>
        <h1 className="mt-1 font-display text-xl font-bold text-focus-navy">{title}</h1>
        {description && <p className="mt-0.5 max-w-2xl text-sm text-slate-blue">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/** Placeholder shown while section content is loading. */
export function SectionLoading() {
  return (
    <div className="space-y-4 p-5">
      <div className="h-7 w-64 animate-pulse rounded bg-white/70" />
      <div className="h-40 w-full animate-pulse rounded-card bg-white/60" />
      <div className="h-40 w-full animate-pulse rounded-card bg-white/60" />
    </div>
  );
}

/** Small labelled value used inside section sheets. */
export function Meta({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    // Wraps rather than using a fixed two-column grid. The old
    // `grid-cols-[128px_minmax(0,1fr)]` demanded 128px for the label whatever
    // the container was, and the workspace detail sheets get genuinely narrow:
    // the shell is [240px_1fr_320px] inside a 240px app rail, so at a 1440px
    // viewport the Hints detail panel is ~180px, and a two-column split inside
    // that leaves each Meta ~57px. The label then overflowed its own container
    // and the value column collapsed to zero, rendering text one character per
    // line down the page.
    //
    // flex-wrap reacts to the container instead of the viewport: while the label
    // and a readable value both fit they share a row, otherwise the value drops
    // below. `basis-40` is what decides that — it asks for 160px before
    // agreeing to share. Tailwind's sm:/lg: cannot express this, because they
    // measure the window, and here the window is wide while the box is not.
    <div className="flex flex-wrap items-start gap-x-3 gap-y-0.5 py-1.5">
      {/* max-w-full so a label never pushes past a container narrower than itself. */}
      <span className="w-32 max-w-full shrink-0 text-xs font-semibold text-slate-blue">{label}</span>
      <span className="min-w-0 flex-1 basis-40 break-words text-sm text-ink">{value}</span>
    </div>
  );
}

/** Active / inactive toggle shown as a read state (backend owns writes). */
export function Toggle({ on, labels = ['Active', 'Inactive'] }: { on: boolean; labels?: [string, string] }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-pill px-2 py-0.5 text-2xs font-semibold ring-1 ring-inset',
        on ? 'bg-success-sage/18 text-[#5c6b58] ring-success-sage/30' : 'bg-muted-gray/50 text-slate-blue ring-muted-gray',
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', on ? 'bg-success-sage' : 'bg-slate-blue/50')} />
      {on ? labels[0] : labels[1]}
    </span>
  );
}

/** Coverage weight chip (0.25–1.00) with primary marker — spec §9.3/§10.8. */
export function WeightChip({ weight, primary }: { weight: number; primary?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="rounded-md bg-reading-surface px-1.5 py-0.5 font-mono text-2xs font-bold text-slate-blue ring-1 ring-inset ring-muted-gray/70">
        {weight.toFixed(2)}
      </span>
      {primary && (
        <span className="rounded-md bg-learning-blue/12 px-1.5 py-0.5 text-2xs font-bold text-learning-blue">primary</span>
      )}
    </span>
  );
}
