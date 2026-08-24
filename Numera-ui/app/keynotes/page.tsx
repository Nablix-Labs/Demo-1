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
import { Volume2, Square } from 'lucide-react';
import { KEY_NOTES, noteToSpeech, type KeyNote } from '@/lib/keynotes';
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
  const spreads = useMemo(() => spreadsForAll(KEY_NOTES), []);
  const [index, setIndex] = useState(0);
  const [speakingId, setSpeakingId] = useState<string | null>(null);

  const note = KEY_NOTES.find((n) => n.id === spreads[index]?.topicId) ?? KEY_NOTES[0];

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
      const n = KEY_NOTES.find((k) => k.id === spread.topicId);
      if (!n || spread.page > 1) return null; // continuation sheets carry no title
      return (
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="min-w-0 text-[20px] font-semibold text-ink leading-tight tracking-[-0.01em]">
            {n.topic}
          </h2>
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
        </div>
      );
    },
    [speakingId, toggle],
  );

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
        <header className="mb-8">
          <h1 className="text-[30px] font-semibold text-ink leading-[1.15] tracking-[-0.02em]">
            Key Notes at a glance
          </h1>
          <p className="text-[14px] text-slate-blue mt-1.5">
            Quick revision from today’s session — read before your exam.
          </p>
        </header>

        <div className="flex gap-6 items-start">
          <TopicRail
            notes={KEY_NOTES}
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
                : `Topic ${String(KEY_NOTES.findIndex((k) => k.id === s.topicId) + 1).padStart(2, '0')} of ${String(KEY_NOTES.length).padStart(2, '0')}`
            }
          />
        </div>
      </div>
    </main>
  );
}
