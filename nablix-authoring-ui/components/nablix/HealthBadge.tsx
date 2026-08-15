import { Check, AlertTriangle, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ContentHealth, HealthState } from '@/lib/api/v3-contracts';

const MAP: Record<HealthState, { Icon: typeof Check; cls: string; label: string }> = {
  COMPLETE: { Icon: Check, cls: 'text-[#5c6b58] bg-success-sage/18 ring-success-sage/30', label: 'Complete' },
  WARNING: { Icon: AlertTriangle, cls: 'text-action-orange bg-highlight-amber/15 ring-highlight-amber/35', label: 'Needs attention' },
  MISSING: { Icon: X, cls: 'text-danger bg-danger/10 ring-danger/25', label: 'Missing' },
};

/**
 * Green check / amber warning / red X — guide §3. The same indicator is used in
 * the tree, the editor and the coverage grid, so it lives in one place.
 */
export function HealthBadge({
  health,
  count,
  showLabel,
  className,
}: {
  health: ContentHealth;
  count?: number;
  showLabel?: boolean;
  className?: string;
}) {
  const m = MAP[health.state];
  const issues = health.issues?.map((i) => i.message).join(' · ');
  return (
    <span
      title={issues || m.label}
      className={cn(
        'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-2xs font-bold tabular-nums ring-1 ring-inset',
        m.cls,
        className,
      )}
    >
      <m.Icon className="h-3 w-3" strokeWidth={3} />
      {count !== undefined && <span>{count}</span>}
      {showLabel && <span>{m.label}</span>}
    </span>
  );
}

/** The issue list under an editor section, when the node has anything to say. */
export function HealthIssues({ health }: { health: ContentHealth }) {
  if (!health.issues?.length) return null;
  return (
    <ul className="space-y-1.5">
      {health.issues.map((i) => (
        <li
          key={i.code}
          className={cn(
            'flex items-start gap-2 rounded-lg px-3 py-2 text-xs',
            i.severity === 'ERROR' ? 'bg-danger/10 text-danger' : 'bg-highlight-amber/12 text-action-orange',
          )}
        >
          {i.severity === 'ERROR' ? (
            <X className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={3} />
          ) : (
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          )}
          <span className="text-ink/80">{i.message}</span>
        </li>
      ))}
    </ul>
  );
}
