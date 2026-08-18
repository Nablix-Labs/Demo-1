import { cn } from '@/lib/utils';
import type { ActivityStatus, WorkflowStatus } from '@/lib/api/v3-contracts';

/** v3 draws `status` from two vocabularies depending on the entity, and a few
 *  records carry values from neither — so unknowns render rather than crash. */
type Status = WorkflowStatus | ActivityStatus;

const LABELS: Record<Status, string> = {
  DRAFT: 'Draft',
  IN_REVIEW: 'In Review',
  APPROVED: 'Approved',
  PUBLISHED: 'Published',
  ARCHIVED: 'Archived',
  ACTIVE: 'Active',
  INACTIVE: 'Inactive',
};

// Colour carries meaning (Brand Guidelines): green = live, blue = in flight,
// amber = attention, grey = dormant.
const STYLES: Record<Status, string> = {
  DRAFT: 'bg-slate-blue/10 text-slate-blue ring-slate-blue/20',
  IN_REVIEW: 'bg-learning-blue/12 text-learning-blue ring-learning-blue/25',
  APPROVED: 'bg-ai-cyan/12 text-dark-cyan ring-ai-cyan/25',
  PUBLISHED: 'bg-success-sage/18 text-[#5c6b58] ring-success-sage/30',
  ARCHIVED: 'bg-muted-gray/50 text-slate-blue ring-muted-gray',
  ACTIVE: 'bg-success-sage/18 text-[#5c6b58] ring-success-sage/30',
  INACTIVE: 'bg-muted-gray/50 text-slate-blue ring-muted-gray',
};

const UNKNOWN = 'bg-muted-gray/50 text-slate-blue ring-muted-gray';

function titleCase(s: string) {
  return s.toLowerCase().split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

export function StatusPill({ status, className }: { status: Status | string; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-pill px-2.5 py-0.5 text-2xs font-semibold ring-1 ring-inset',
        STYLES[status as Status] ?? UNKNOWN,
        className,
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {LABELS[status as Status] ?? titleCase(status)}
    </span>
  );
}
