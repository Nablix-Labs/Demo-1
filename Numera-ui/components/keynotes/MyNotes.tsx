'use client';

/**
 * "My notes": the key-note cards a student saved, and notes they wrote
 * themselves, grouped by topic. Storage is lib/myNotes (backend when it exists,
 * this browser until then — and the screen says which).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bookmark, Check, NotebookPen, Pencil, Plus, Trash2, X } from 'lucide-react';
import { useAuthStore } from '@/store/useAuthStore';
import {
  createNote, deleteNote, listNotes, notesApiEnabled, updateNote, type MyNote, type NewNote,
} from '@/lib/myNotes';
import type { KeyNote } from '@/lib/keynotes';
import { basePath } from '@/lib/runtimeConfig';

/** Notes for the signed-in student, with the actions the screens need. */
export function useMyNotes() {
  const studentCode = useAuthStore((s) => s.studentCode);
  const [notes, setNotes] = useState<MyNote[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listNotes(studentCode)
      .then((n) => { if (!cancelled) setNotes(n); })
      .catch(() => { if (!cancelled) { setNotes([]); setError('Your notes could not be loaded.'); } });
    return () => { cancelled = true; };
  }, [studentCode]);

  const run = useCallback(async <T,>(work: () => Promise<T>): Promise<T | null> => {
    setError(null);
    try { return await work(); } catch (e) {
      setError(e instanceof Error && e.message ? e.message : 'That change was not saved.');
      return null;
    }
  }, []);

  const add = useCallback((note: NewNote) => run(async () => {
    const saved = await createNote(studentCode, note);
    setNotes((prev) => [saved, ...(prev ?? [])]);
    return saved;
  }), [run, studentCode]);

  const edit = useCallback((id: string, patch: Partial<Pick<MyNote, 'topic' | 'text'>>) => run(async () => {
    const saved = await updateNote(studentCode, id, patch);
    setNotes((prev) => (prev ?? []).map((n) => (n.id === id ? saved : n)));
    return saved;
  }), [run, studentCode]);

  const remove = useCallback((id: string) => run(async () => {
    await deleteNote(studentCode, id);
    setNotes((prev) => (prev ?? []).filter((n) => n.id !== id));
    return true;
  }), [run, studentCode]);

  const savedFor = useCallback((keyNoteId: string) => (notes ?? []).find((n) => n.key_note_id === keyNoteId) ?? null, [notes]);

  /** Save a key-note card, or un-save it if it is already saved. */
  const toggleSaved = useCallback(async (k: KeyNote) => {
    const existing = savedFor(k.id);
    if (existing) await remove(existing.id);
    else await add({ topic: k.topic, text: '', key_note_id: k.id });
  }, [savedFor, add, remove]);

  return { notes, error, add, edit, remove, savedFor, toggleSaved };
}

export type MyNotesApi = ReturnType<typeof useMyNotes>;

const dateLabel = (iso: string) =>
  new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });

export default function MyNotes({ mine, keyNotes, onOpenKeyNote }: {
  mine: MyNotesApi;
  keyNotes: KeyNote[];
  onOpenKeyNote: (id: string) => void;
}) {
  const [draft, setDraft] = useState<{ id: string | null; topic: string; text: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const topics = useMemo(() => {
    const set = new Set(keyNotes.map((k) => k.topic));
    (mine.notes ?? []).forEach((n) => set.add(n.topic));
    return [...set];
  }, [keyNotes, mine.notes]);

  if (mine.notes === null) {
    return <div className="h-64 animate-pulse rounded-[24px] bg-white/70" aria-busy="true" aria-label="Loading your notes" />;
  }

  const groups = topics
    .map((topic) => ({ topic, notes: mine.notes!.filter((n) => n.topic === topic) }))
    .filter((g) => g.notes.length);

  const save = async () => {
    if (!draft || !draft.text.trim() || !draft.topic.trim()) return;
    const ok = draft.id
      ? await mine.edit(draft.id, { topic: draft.topic.trim(), text: draft.text.trim() })
      : await mine.add({ topic: draft.topic.trim(), text: draft.text.trim(), key_note_id: null });
    if (ok) setDraft(null);
  };

  return (
    <section aria-label="My notes" className="max-w-[1092px]">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <p className="text-[13px] text-slate-blue">
          {notesApiEnabled
            ? 'Saved to your account.'
            : 'Saved in this browser for now. They will move to your account when it is ready.'}
        </p>
        {!draft && (
          <button
            onClick={() => setDraft({ id: null, topic: topics[0] ?? '', text: '' })}
            className="inline-flex items-center gap-1.5 rounded-full bg-focus-navy px-4 py-2 text-[13px] font-semibold text-white hover:opacity-90"
          >
            <Plus size={15} /> New note
          </button>
        )}
      </div>

      {mine.error && <p role="alert" className="mb-4 rounded-xl bg-[#FFE9D6] px-4 py-2.5 text-[13px] text-[#8A4B08]">{mine.error}</p>}

      {draft && (
        <div className="mb-6 rounded-[20px] border-2 border-[#A9D3F2] bg-[#FDFBF7] p-5">
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-[12px] font-semibold uppercase tracking-wider text-slate-blue" htmlFor="note-topic">Topic</label>
            <input
              id="note-topic"
              list="note-topics"
              value={draft.topic}
              onChange={(e) => setDraft({ ...draft, topic: e.target.value })}
              placeholder="Which topic is this for?"
              maxLength={80}
              className="min-w-[220px] flex-1 rounded-lg border border-muted-gray bg-white px-3 py-2 text-[14px] text-ink outline-none focus:border-focus-navy"
            />
            <datalist id="note-topics">{topics.map((t) => <option key={t} value={t} />)}</datalist>
          </div>
          <textarea
            value={draft.text}
            onChange={(e) => setDraft({ ...draft, text: e.target.value })}
            placeholder="Write it in your own words, the way you would explain it to a friend…"
            aria-label="Your note"
            maxLength={2000}
            rows={5}
            autoFocus
            className="mt-3 w-full resize-y rounded-lg border border-muted-gray bg-[repeating-linear-gradient(transparent,transparent_27px,#DCE9F5_28px)] px-3 py-1.5 text-[15px] leading-[28px] text-ink outline-none focus:border-focus-navy"
          />
          <div className="mt-3 flex items-center justify-end gap-2">
            <span className="mr-auto text-[12px] text-slate-blue">{draft.text.length} / 2000</span>
            <button onClick={() => setDraft(null)} className="inline-flex items-center gap-1 rounded-full border border-muted-gray px-3.5 py-1.5 text-[13px] font-semibold text-ink">
              <X size={14} /> Cancel
            </button>
            <button
              onClick={() => void save()}
              disabled={!draft.text.trim() || !draft.topic.trim()}
              className="inline-flex items-center gap-1 rounded-full bg-focus-navy px-4 py-1.5 text-[13px] font-semibold text-white disabled:opacity-40"
            >
              <Check size={14} /> Save note
            </button>
          </div>
        </div>
      )}

      {groups.length === 0 && !draft ? (
        <div className="flex flex-col items-center rounded-[24px] border-2 border-dashed border-[#C9DDF0] bg-[#FDFBF7] px-6 py-14 text-center">
          {/* eslint-disable-next-line @next/next/no-img-element -- static export */}
          <img src={`${basePath}/art/empty/hints.webp`} alt="" aria-hidden className="mb-4 h-24 w-24 object-contain" />
          <p className="text-[16px] font-semibold text-ink">No notes yet</p>
          <p className="mt-1.5 max-w-sm text-[13px] leading-relaxed text-slate-blue">
            Press <b>Save</b> on a key note to keep it here, or write your own with <b>New note</b>.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-7">
          {groups.map((g) => (
            <div key={g.topic}>
              <h3 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-slate-blue">{g.topic}</h3>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {g.notes.map((n) => {
                  const card = n.key_note_id ? keyNotes.find((k) => k.id === n.key_note_id) : null;
                  return (
                    <article key={n.id} className="flex flex-col rounded-[18px] border border-[#DCE9F5] bg-[#FDFBF7] p-4 shadow-[0_1px_0_rgba(27,42,74,0.04)]">
                      <div className="mb-2 flex items-center gap-2 text-[11.5px] font-semibold text-slate-blue">
                        {n.key_note_id ? <Bookmark size={13} className="text-highlight-amber" fill="currentColor" /> : <NotebookPen size={13} />}
                        {n.key_note_id ? 'Saved key note' : 'My note'} · {dateLabel(n.updated_at)}
                      </div>
                      {n.key_note_id ? (
                        <>
                          <p className="text-[14.5px] font-semibold text-ink">{card?.topic ?? n.topic}</p>
                          {card?.formula && <p className="mt-1.5 rounded-md bg-white px-2 py-1 font-mono text-[13px] text-ink">{card.formula}</p>}
                          {card?.meaning && <p className="mt-1.5 line-clamp-3 text-[13px] leading-relaxed text-slate-blue">{card.meaning}</p>}
                          {!card && <p className="mt-1.5 text-[13px] text-slate-blue">This card is not in your current key notes.</p>}
                        </>
                      ) : (
                        <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-ink">{n.text}</p>
                      )}
                      <div className="mt-auto flex items-center gap-1 pt-3">
                        {n.key_note_id && card && (
                          <button onClick={() => onOpenKeyNote(card.id)} className="rounded-full px-2.5 py-1 text-[12px] font-semibold text-focus-navy hover:bg-white">Open</button>
                        )}
                        {!n.key_note_id && (
                          <button onClick={() => setDraft({ id: n.id, topic: n.topic, text: n.text })} className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[12px] font-semibold text-focus-navy hover:bg-white">
                            <Pencil size={12} /> Edit
                          </button>
                        )}
                        {confirmDelete === n.id ? (
                          <span className="ml-auto flex items-center gap-1">
                            <button onClick={() => { void mine.remove(n.id); setConfirmDelete(null); }} className="rounded-full bg-[#C8452B] px-2.5 py-1 text-[12px] font-semibold text-white">Delete</button>
                            <button onClick={() => setConfirmDelete(null)} className="rounded-full px-2.5 py-1 text-[12px] font-semibold text-ink">Keep</button>
                          </span>
                        ) : (
                          <button onClick={() => setConfirmDelete(n.id)} aria-label={n.key_note_id ? 'Remove from my notes' : 'Delete note'} className="ml-auto rounded-full p-1.5 text-slate-blue hover:bg-white hover:text-[#C8452B]">
                            <Trash2 size={14} />
                          </button>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
