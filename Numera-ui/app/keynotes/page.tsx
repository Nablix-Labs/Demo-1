'use client';

/**
 * Key Notes at a Glance — the revision notes, as a notebook.
 *
 * Revision notes ARE a notebook, so the page is one: two facing sheets of ruled
 * paper that a student turns through. Each topic runs from the front of its own
 * spread and continues onto another if it needs the room.
 *
 * This route leaves PageShell deliberately. The shared shell puts a translucent
 * glass panel over the app's ambient gradient, and paper seen through tinted
 * glass stops being paper — the whole point here is a surface that reads as a
 * physical sheet. Every other library route keeps the shell.
 */

import { useCallback, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { Volume2, Square, Bookmark, RotateCw } from 'lucide-react';
import { noteToSpeech, type KeyNote } from '@/lib/keynotes';
import { useKeyNotes } from '@/lib/useKeyNotes';
import MyNotes, { useMyNotes } from '@/components/keynotes/MyNotes';
import { basePath } from '@/lib/runtimeConfig';
import { cn } from '@/lib/cn';
import { speakTutor, stopTutorSpeech } from '@/lib/tts';
import { spreadsForAll, type Spread } from '@/lib/keynotes-paginate';
import TopicRail from '@/components/keynotes/TopicRail';
import { PAGE_HEIGHT } from '@/components/keynotes/Page';

/**
 * Browser-only: StPageFlip measures and mutates the DOM the moment it mounts,
 * so it cannot run during the static export. The placeholder holds the book's
 * exact footprint to stop the page reflowing when it arrives.
 */
const NotebookFlip = dynamic(() => import('@/components/keynotes/NotebookFlip'), {
  ssr: false,
  loading: () => (
    <div
      className="rounded-[28px] border-2 border-[#A9D3F2] bg-[#FDFBF7]"
      style={{ width: 1092, height: PAGE_HEIGHT + 12 }}
      aria-hidden="true"
    />
  ),
});

export default function KeyNotesPage() {
  const keyNotes = useKeyNotes();
  const mine = useMyNotes();
  const [tab, setTab] = useState<'notes' | 'mine'>('notes');
  const notes = keyNotes.status === 'ready' || keyNotes.status === 'sample' ? keyNotes.notes : [];
  const savedCount = (mine.notes ?? []).length;

  // pb-32 rather than the py-10 the top keeps. The dock is fixed 16px off the
  // bottom and stands 74px tall, so the last ~90px of a scrollable route sits
  // underneath it. Key Notes is where that bites: the page-turn control is the
  // final element, and it was rendering 96px behind the dock AND past the fold,
  // leaving no way to reach page 2 or 3. Measured on the live site, not guessed.
  return (
    <main
      className="flex-1 min-w-0 overflow-y-auto bg-[#F2F4F8] px-6 pt-10 pb-32"
      aria-label="Key Notes at a glance"
    >
      <div className="mx-auto w-full max-w-[1400px]">
        <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-[30px] font-semibold text-ink leading-[1.15] tracking-[-0.02em]">
              Key Notes at a glance
            </h1>
            <p className="text-[14px] text-slate-blue mt-1.5">
              {tab === 'notes' ? 'Quick revision from your lessons — read before your exam.' : 'Cards you saved and notes in your own words.'}
            </p>
          </div>
          <div className="flex rounded-full bg-white p-1 shadow-[0_1px_2px_rgba(27,42,74,0.06)]" role="tablist" aria-label="Notes">
            {([['notes', 'Key notes'], ['mine', `My notes${savedCount ? ` · ${savedCount}` : ''}`]] as const).map(([id, label]) => (
              <button
                key={id}
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={cn('rounded-full px-4 py-2 text-[13px] font-semibold transition-colors', tab === id ? 'bg-focus-navy text-white' : 'text-slate-blue hover:text-ink')}
              >
                {label}
              </button>
            ))}
          </div>
        </header>

        {tab === 'mine' ? (
          <MyNotes mine={mine} keyNotes={notes} onOpenKeyNote={() => setTab('notes')} />
        ) : keyNotes.status === 'loading' ? (
          <div className="h-[520px] max-w-[1092px] animate-pulse rounded-[28px] bg-white/70" aria-busy="true" aria-label="Loading key notes" />
        ) : keyNotes.status === 'ready' || keyNotes.status === 'sample' ? (
          <Notebook notes={keyNotes.notes} mine={mine} />
        ) : (
          <NoKeyNotes state={keyNotes.status} onRetry={keyNotes.reload} />
        )}
      </div>
    </main>
  );
}

/** Honest states for a real student: none yet, not available yet, or failed. */
function NoKeyNotes({ state, onRetry }: { state: 'empty' | 'unavailable' | 'error'; onRetry: () => void }) {
  const copy = {
    empty: ['No key notes yet', 'Finish a lesson and your revision notes for it appear here, including the mistakes worth remembering.'],
    unavailable: ['Key notes are on their way', 'Revision notes made from your own lessons will appear here soon. Until then, you can still write your own in My notes.'],
    error: ['Your key notes could not be loaded', 'Check your connection and try again.'],
  }[state];
  return (
    <div className="flex max-w-[1092px] flex-col items-center rounded-[28px] border-2 border-dashed border-[#C9DDF0] bg-[#FDFBF7] px-6 py-16 text-center">
      {/* eslint-disable-next-line @next/next/no-img-element -- static export */}
      <img src={`${basePath}/art/empty/hints.webp`} alt="" aria-hidden className="mb-4 h-28 w-28 object-contain" />
      <p className="text-[17px] font-semibold text-ink">{copy[0]}</p>
      <p className="mt-1.5 max-w-md text-[13.5px] leading-relaxed text-slate-blue">{copy[1]}</p>
      {state === 'error' && (
        <button onClick={onRetry} className="mt-5 inline-flex items-center gap-1.5 rounded-full bg-focus-navy px-4 py-2 text-[13px] font-semibold text-white">
          <RotateCw size={14} /> Try again
        </button>
      )}
    </div>
  );
}

function Notebook({ notes, mine }: { notes: KeyNote[]; mine: ReturnType<typeof useMyNotes> }) {
  const spreads = useMemo(() => spreadsForAll(notes), [notes]);
  const [index, setIndex] = useState(0);
  const [speakingId, setSpeakingId] = useState<string | null>(null);

  const note = notes.find((n) => n.id === spreads[index]?.topicId) ?? notes[0];

  const stop = useCallback(() => {
    stopTutorSpeech();
    setSpeakingId(null);
  }, []);

  const toggle = useCallback(
    (n: KeyNote) => {
      if (speakingId === n.id) {
        stop();
        return;
      }
      setSpeakingId(n.id);
      // The tutor's own voice, not the browser's — every other phase reads in
      // the student's tier provider and this page used to be the exception.
      speakTutor(noteToSpeech(n), () => setSpeakingId(null));
    },
    [speakingId, stop],
  );

  /** 1-based spread a topic opens on, for the contents page. */
  const pageOf = useCallback(
    (id: string) => spreads.findIndex((s) => s.topicId === id) + 1,
    [spreads],
  );

  const selectTopic = useCallback(
    (id: string) => {
      // Land on the topic's FIRST spread, so a student three pages into one
      // topic who picks another arrives at its beginning.
      const first = spreads.findIndex((s) => s.topicId === id);
      if (first >= 0 && first !== index) {
        stop();
        setIndex(first);
      }
    },
    [spreads, index, stop],
  );

  const onSpreadChange = useCallback(
    (next: number) => {
      // A turn that leaves the topic should not leave it still reading aloud
      // into a page that is no longer open.
      if (spreads[next]?.topicId !== spreads[index]?.topicId) stop();
      setIndex(next);
    },
    [spreads, index, stop],
  );

  const renderHeader = useCallback(
    (spread: Spread) => {
      const n = notes.find((k) => k.id === spread.topicId);
      if (!n || spread.page > 1) return null; // continuation sheets carry no title
      return (
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="min-w-0 text-[20px] font-semibold text-ink leading-tight tracking-[-0.01em]">
            {n.topic}
          </h2>
          <span className="flex flex-shrink-0 items-center gap-1.5">
          <button
            onClick={() => void mine.toggleSaved(n)}
            aria-pressed={Boolean(mine.savedFor(n.id))}
            aria-label={mine.savedFor(n.id) ? 'Remove from my notes' : 'Save to my notes'}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11.5px] font-semibold transition-colors',
              mine.savedFor(n.id) ? 'border-highlight-amber bg-highlight-amber/15 text-ink' : 'border-focus-navy text-ink hover:bg-focus-navy hover:text-white',
            )}
          >
            <Bookmark size={13} strokeWidth={1.9} fill={mine.savedFor(n.id) ? 'currentColor' : 'none'} className={mine.savedFor(n.id) ? 'text-highlight-amber' : ''} />
            {mine.savedFor(n.id) ? 'Saved' : 'Save'}
          </button>
          <button
            onClick={() => toggle(n)}
            aria-label={speakingId === n.id ? 'Stop reading' : 'Read out loud'}
            className="flex-shrink-0 inline-flex items-center gap-1.5 rounded-full border border-focus-navy px-3 py-1.5 text-[11.5px] font-semibold text-ink hover:bg-focus-navy hover:text-white transition-colors"
          >
            {speakingId === n.id ? (
              <>
                <Square size={12} strokeWidth={2.2} /> Stop
              </>
            ) : (
              <>
                <Volume2 size={13} strokeWidth={1.9} /> Read
              </>
            )}
          </button>
          </span>
        </div>
      );
    },
    [speakingId, toggle, mine],
  );

  return (
    <div className="flex gap-6 items-start">
      <TopicRail
        notes={notes}
        activeId={note.id}
        pageOf={pageOf}
        onSelect={selectTopic}
      />

      <NotebookFlip
        spreads={spreads}
        spreadIndex={index}
        onSpreadChange={onSpreadChange}
        renderHeader={renderHeader}
        // Verso carries the book, recto the topic — the convention a printed
        // book uses, and it stops the same line appearing twice.
        runningHead={(s, side) =>
          side === 'left'
            ? 'Key notes · today’s session'
            : `Topic ${String(notes.findIndex((k) => k.id === s.topicId) + 1).padStart(2, '0')} of ${String(notes.length).padStart(2, '0')}`
        }
      />
    </div>
  );
}
