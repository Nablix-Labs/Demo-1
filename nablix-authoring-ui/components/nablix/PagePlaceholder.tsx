import { Compass } from 'lucide-react';
import { Topbar } from './Topbar';

/** Full-page placeholder for global nav destinations not yet built. */
export function PagePlaceholder({
  crumb,
  title,
  blurb,
}: {
  crumb: string;
  title: string;
  blurb: string;
}) {
  return (
    <>
      <Topbar title="Content Authoring Portal" crumb={crumb} />
      <main className="relative z-10 flex flex-1 items-center justify-center px-6 pb-10">
        <div className="lg-glass lg-anim-rise max-w-md rounded-card p-8 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-card bg-learning-blue/12 text-learning-blue">
            <Compass className="h-6 w-6" />
          </div>
          <h1 className="mt-4 text-lg font-black text-focus-navy">{title}</h1>
          <p className="mt-1 text-sm text-slate-blue">{blurb}</p>
          <p className="mt-4 text-2xs font-semibold uppercase tracking-wide text-slate-blue/70">
            Open a topic from the Dashboard to author its content
          </p>
        </div>
      </main>
    </>
  );
}
