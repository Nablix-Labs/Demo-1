import { Search, Bell, ChevronDown } from 'lucide-react';

export function Topbar({
  title,
  crumb,
}: {
  title: string;
  crumb?: string;
}) {
  return (
    <header className="relative z-10 flex h-16 shrink-0 items-center gap-4 px-6">
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <h1 className="truncate font-display text-lg font-bold tracking-tight text-focus-navy">{title}</h1>
          {crumb && (
            <>
              <span className="text-slate-blue/40">/</span>
              <span className="truncate text-sm font-medium text-slate-blue">{crumb}</span>
            </>
          )}
        </div>
      </div>

      <div className="ml-auto flex items-center gap-3">
        <div className="lg-glass hidden items-center gap-2 rounded-pill px-3.5 py-2 md:flex">
          <Search className="h-4 w-4 text-slate-blue" />
          <input
            className="w-52 bg-transparent text-sm text-ink placeholder:text-slate-blue/60 focus:outline-none"
            placeholder="Search topics, skills, questions…"
          />
          <kbd className="rounded bg-reading-surface px-1.5 py-0.5 font-mono text-2xs font-semibold text-slate-blue ring-1 ring-inset ring-muted-gray/70">⌘K</kbd>
        </div>

        <button className="relative flex h-9 w-9 items-center justify-center rounded-full border border-muted-gray bg-white text-slate-blue transition-colors hover:bg-reading-surface">
          <Bell className="h-4 w-4" />
          <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-action-orange ring-2 ring-white" />
        </button>

        <button className="flex items-center gap-2 rounded-pill border border-muted-gray bg-white py-1 pl-1 pr-2.5 transition-colors hover:bg-reading-surface">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-focus-navy text-2xs font-bold text-white">
            AK
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-slate-blue" />
        </button>
      </div>
    </header>
  );
}
