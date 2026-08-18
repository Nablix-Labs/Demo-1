'use client';

/**
 * Files — the student's worksheets, saved canvas working and notes.
 *
 * These were a grid of identical cards with a striped placeholder thumbnail,
 * which told a student nothing: six rectangles differing only by the words on
 * them. As books they differ by colour and by spine, so the shelf is scannable
 * before a single label is read — which is how you actually find something you
 * saved three weeks ago. Colour carries the file's KIND, per the brand rule
 * that colour always means something.
 *
 * The route leaves PageShell for the same reason Key Notes did: the shared
 * shell puts a translucent panel over the app's ambient gradient, and the book
 * covers picked up the blue wash through it. Physical objects need a surface to
 * sit on, so this page carries a plain white one.
 */

import { useState } from 'react';
import dynamic from 'next/dynamic';
import { FileText, Image as ImageIcon, NotebookPen } from 'lucide-react';
import { FILES, KIND, type FileItem } from '@/lib/files';
import { Book } from '@/components/ui/book';

/** StPageFlip touches the DOM on mount, so the reader is browser-only. */
const FileBook = dynamic(() => import('@/components/files/FileBook'), { ssr: false });

const ICON = {
  worksheet: FileText,
  canvas: ImageIcon,
  notes: NotebookPen,
} as const;

export default function FilesPage() {
  const [open, setOpen] = useState<FileItem | null>(null);

  return (
    <main className="flex-1 min-w-0 overflow-y-auto bg-white" aria-label="Files">
      <div className="mx-auto w-full max-w-[1180px] px-10 py-10">
        <header className="mb-10">
          <h1 className="text-[30px] font-semibold leading-[1.15] tracking-[-0.02em] text-ink">
            Files
          </h1>
          <p className="mt-1.5 text-[14px] text-slate-blue">
            Worksheets, saved canvas working and notes from your sessions.
          </p>
        </header>

        <div className="flex flex-wrap gap-x-10 gap-y-12">
          {FILES.map((f) => {
            const kind = KIND[f.kind];
            const Icon = ICON[f.kind];
            return (
              <button
                key={f.id}
                onClick={() => setOpen(f)}
                className="group/book flex flex-col items-start text-left"
                aria-label={`Open ${f.name} — ${kind.label}, ${f.meta}`}
              >
                {/* `stripe`, not `simple`: the cover is two pieces — a band of
                    coloured cloth over a titled panel — and that construction is
                    what makes it read as a bound book rather than a coloured
                    rectangle. Colour still carries the kind; the title sits on
                    paper below it where it stays legible at any cover colour. */}
                <Book
                  variant="stripe"
                  title={f.name}
                  width={168}
                  color={kind.color}
                  textColor="#2B2D42"
                  textured
                  illustration={
                    <Icon
                      size={46}
                      strokeWidth={1.35}
                      style={{ color: kind.textColor, opacity: 0.9 }}
                    />
                  }
                />

                {/* The shelf line, and the label that belongs to the object above
                    it rather than printed on the cover. */}
                <span
                  aria-hidden="true"
                  className="mt-3 h-px w-[168px] bg-gradient-to-r from-muted-gray to-transparent"
                />
                <span className="mt-2 block max-w-[168px] text-[12.5px] font-semibold leading-snug text-ink">
                  {f.name}
                </span>
                <span className="mt-0.5 block text-[11px] text-slate-blue">{f.meta}</span>
              </button>
            );
          })}
        </div>
      </div>

      {open && <FileBook file={open} onClose={() => setOpen(null)} />}
    </main>
  );
}
