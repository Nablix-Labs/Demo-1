import { cn } from '@/lib/utils';

/** Primary work surface — light liquid glass. */
export function GlassCard({
  children,
  className,
  as: Tag = 'section',
}: {
  children: React.ReactNode;
  className?: string;
  as?: keyof React.JSX.IntrinsicElements;
}) {
  return <Tag className={cn('lg-glass rounded-card', className)}>{children}</Tag>;
}

export function CardHeader({
  icon,
  title,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex items-center justify-between gap-3 px-5 py-3.5 border-b border-muted-gray/70', className)}>
      <div className="flex items-center gap-2.5 min-w-0">
        {icon && <span className="text-learning-blue shrink-0">{icon}</span>}
        <h3 className="truncate font-display text-sm font-bold text-focus-navy">{title}</h3>
      </div>
      {action}
    </div>
  );
}
