/**
 * A student's own notes: key-note cards they saved, and notes they wrote.
 *
 * Persisted by the backend once it exists (BACKEND ask: Saravanan, student
 * data): GET/POST /students/me/notes, PATCH/DELETE /students/me/notes/{id}.
 * Switch on with NEXT_PUBLIC_NOTES_API=true. Until then the notes are kept in
 * this browser, per student, and the screen says so — they do not follow the
 * student to another device.
 */
import { api } from '@/lib/api';

export interface MyNote {
  id: string;
  /** Topic the note belongs to (a key-note topic, or the student's own). */
  topic: string;
  /** The student's text; empty for a saved key-note card with no comment. */
  text: string;
  /** Set when this note saves a key-note card. */
  key_note_id: string | null;
  created_at: string;
  updated_at: string;
}

export type NewNote = Pick<MyNote, 'topic' | 'text' | 'key_note_id'>;

export const notesApiEnabled = process.env.NEXT_PUBLIC_NOTES_API === 'true';

const keyFor = (studentCode: string | null) => `numera.mynotes.${studentCode || 'guest'}`;

function readLocal(studentCode: string | null): MyNote[] {
  try {
    const raw = localStorage.getItem(keyFor(studentCode));
    const list = raw ? (JSON.parse(raw) as MyNote[]) : [];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function writeLocal(studentCode: string | null, notes: MyNote[]): void {
  try {
    localStorage.setItem(keyFor(studentCode), JSON.stringify(notes));
  } catch {
    throw new Error('Your notes could not be saved in this browser.');
  }
}

const newId = () => `NOTE-${typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : Date.now().toString(36)}`;

export async function listNotes(studentCode: string | null): Promise<MyNote[]> {
  if (notesApiEnabled) return (await api.get<{ notes: MyNote[] }>('/students/me/notes')).data.notes;
  return readLocal(studentCode);
}

export async function createNote(studentCode: string | null, note: NewNote): Promise<MyNote> {
  if (notesApiEnabled) return (await api.post<MyNote>('/students/me/notes', note)).data;
  const now = new Date().toISOString();
  const saved: MyNote = { id: newId(), ...note, topic: note.topic.trim(), text: note.text.trim(), created_at: now, updated_at: now };
  writeLocal(studentCode, [saved, ...readLocal(studentCode)]);
  return saved;
}

export async function updateNote(studentCode: string | null, id: string, patch: Partial<Pick<MyNote, 'topic' | 'text'>>): Promise<MyNote> {
  if (notesApiEnabled) return (await api.patch<MyNote>(`/students/me/notes/${encodeURIComponent(id)}`, patch)).data;
  const notes = readLocal(studentCode);
  const i = notes.findIndex((n) => n.id === id);
  if (i < 0) throw new Error('That note no longer exists.');
  notes[i] = { ...notes[i], ...patch, updated_at: new Date().toISOString() };
  writeLocal(studentCode, notes);
  return notes[i];
}

export async function deleteNote(studentCode: string | null, id: string): Promise<void> {
  if (notesApiEnabled) { await api.delete(`/students/me/notes/${encodeURIComponent(id)}`); return; }
  writeLocal(studentCode, readLocal(studentCode).filter((n) => n.id !== id));
}
