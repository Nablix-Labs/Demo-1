import { Check, AlertTriangle, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { CoverageState, ValidationState } from '@/lib/api/contracts';

/** ✓ / ⚠ / ✕ coverage indicator with count — spec §14. */
export function CoverageBadge({
  state,
  count,
  onClick,
  className,
}: {
  state: CoverageState;
  count?: number;
  onClick?: () => void;
  className?: string;
}) {
  const map = {
    ok: { Icon: Check, cls: 'text-[#5c6b58] bg-success-sage/18 ring-success-sage/30' },
    warn: { Icon: AlertTriangle, cls: 'text-action-orange bg-highlight-amber/15 ring-highlight-amber/35' },
    missing: { Icon: X, cls: 'text-danger bg-danger/10 ring-danger/25' },
  }[state];
  const Comp = onClick ? 'button' : 'span';
  return (
    <Comp
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-2xs font-bold tabular-nums ring-1 ring-inset',
        map.cls,
        onClick && 'cursor-pointer transition-transform hover:scale-105',
        className,
      )}
    >
      <map.Icon className="h-3 w-3" strokeWidth={3} />
      {count !== undefined && <span>{count}</span>}
    </Comp>
  );
}

const DOT: Record<ValidationState, string> = {
  green: 'bg-success-sage',
  amber: 'bg-highlight-amber',
  red: 'bg-danger',
};

/** Small round validation dot for tables (green / amber / red). */
export function ValidationDot({ state, className }: { state: ValidationState; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <span className={cn('h-2.5 w-2.5 rounded-full', DOT[state])} />
    </span>
  );
}
