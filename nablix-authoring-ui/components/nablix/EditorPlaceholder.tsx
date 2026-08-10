import { Hammer, ArrowRight } from 'lucide-react';

/** Center-pane placeholder for workspace sections not yet built (roadmap §18). */
export function EditorPlaceholder({
  title,
  specRef,
  blurb,
  increment,
}: {
  title: string;
  specRef: string;
  blurb: string;
  increment: string;
}) {
  return (
    <div className="lg-anim-rise flex h-full flex-col items-center justify-center p-8 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-card bg-learning-blue/12 text-learning-blue">
        <Hammer className="h-6 w-6" />
      </div>
      <h1 className="mt-4 text-lg font-black text-focus-navy">{title}</h1>
      <p className="mt-1 max-w-md text-sm text-slate-blue">{blurb}</p>
      <div className="mt-4 flex items-center gap-2 text-2xs font-semibold">
        <span className="rounded-pill bg-reading-surface px-2.5 py-1 text-slate-blue ring-1 ring-inset ring-muted-gray/70">
          Spec {specRef}
        </span>
        <ArrowRight className="h-3.5 w-3.5 text-slate-blue/60" />
        <span className="rounded-pill bg-learning-blue/12 px-2.5 py-1 text-learning-blue">{increment}</span>
      </div>
    </div>
  );
}
