import PageShell, { Chip } from '@/components/PageShell';
import { FileText, Image as ImageIcon, NotebookPen } from 'lucide-react';

interface FileItem {
  name: string;
  kind: 'worksheet' | 'canvas' | 'notes';
  meta: string;
}

const FILES: FileItem[] = [
  { name: 'Linear equations — worksheet', kind: 'worksheet', meta: 'PDF · 240 KB · 12 Jun' },
  { name: 'Session 3 — my working', kind: 'canvas', meta: 'PNG · 88 KB · 13 Jun' },
  { name: 'Fractions practice', kind: 'worksheet', meta: 'PDF · 196 KB · 10 Jun' },
  { name: 'Solving for x — notes', kind: 'notes', meta: 'Note · 9 Jun' },
  { name: 'Session 2 — my working', kind: 'canvas', meta: 'PNG · 102 KB · 9 Jun' },
  { name: 'Angles cheat sheet', kind: 'notes', meta: 'Note · 6 Jun' },
];

const ICON = {
  worksheet: FileText,
  canvas: ImageIcon,
  notes: NotebookPen,
} as const;

const KIND_LABEL = {
  worksheet: 'Worksheet',
  canvas: 'Canvas',
  notes: 'Notes',
} as const;

export default function FilesPage() {
  return (
    <PageShell
      title="Files"
      subtitle="Worksheets, saved canvas working and notes from your sessions."
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {FILES.map((f) => {
          const Icon = ICON[f.kind];
          return (
            <div
              key={f.name}
              className="flex flex-col rounded-lg border border-muted-gray bg-white overflow-hidden hover:border-muted-gray transition-colors cursor-pointer"
            >
              {/* Striped thumbnail (wireframe placeholder language) */}
              <div
                className="h-28 flex items-center justify-center border-b border-muted-gray"
                style={{
                  backgroundImage:
                    'repeating-linear-gradient(45deg,#ededed,#ededed 9px,#f7f7f7 9px,#f7f7f7 18px)',
                }}
              >
                <Icon size={26} strokeWidth={1.4} className="text-slate-blue" />
              </div>
              <div className="flex items-start justify-between gap-2 p-4">
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold text-ink truncate">{f.name}</div>
                  <div className="text-[11px] text-slate-blue mt-0.5">{f.meta}</div>
                </div>
                <Chip>{KIND_LABEL[f.kind]}</Chip>
              </div>
            </div>
          );
        })}
      </div>
    </PageShell>
  );
}
