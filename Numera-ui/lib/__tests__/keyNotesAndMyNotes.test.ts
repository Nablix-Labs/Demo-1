import { beforeEach, describe, expect, it } from 'vitest';
import { keyNoteFromApi } from '@/lib/keynotes';
import { createNote, deleteNote, listNotes, updateNote } from '@/lib/myNotes';

describe('keyNoteFromApi', () => {
  it('maps the backend fields onto the notebook card', () => {
    const k = keyNoteFromApi({
      topic_code: 'ALG-ORI-02', topic: 'Reading algebraic notation', meaning: '3x means 3 × x',
      how_to_start: 'Look for a number next to a letter.', steps: ['Read it as times'], be_careful: ['3x is not 3 + x'],
      tips: [], formula: 'ab = a × b', example: ['3y = 3 × y'], exam_tip: 'Write the × if unsure.', flagged: true,
    }, 0);
    expect(k).toEqual({
      id: 'alg-ori-02', topic: 'Reading algebraic notation', meaning: '3x means 3 × x',
      howToStart: 'Look for a number next to a letter.', steps: ['Read it as times'], beCareful: ['3x is not 3 + x'],
      tips: [], formula: 'ab = a × b', example: ['3y = 3 × y'], examTip: 'Write the × if unsure.', flagged: true,
    });
  });

  it('never throws on a sparse note', () => {
    const k = keyNoteFromApi({ topic: '' }, 3);
    expect(k.topic).toBe('Key note');
    expect(k.steps).toEqual([]);
    expect(k.flagged).toBe(false);
    expect(k.id).toBeTruthy();
  });
});

describe('my notes (browser storage until the backend exists)', () => {
  beforeEach(() => localStorage.clear());

  it('creates, edits and deletes, newest first, per student', async () => {
    const a = await createNote('ST015', { topic: 'Fractions', text: '  halves are 2 quarters  ', key_note_id: null });
    const b = await createNote('ST015', { topic: 'Algebra', text: '', key_note_id: 'alg-ori-02' });
    expect(a.text).toBe('halves are 2 quarters');
    expect((await listNotes('ST015')).map((n) => n.id)).toEqual([b.id, a.id]);
    expect(await listNotes('ST030')).toEqual([]); // another student sees nothing

    const edited = await updateNote('ST015', a.id, { text: 'one half = two quarters' });
    expect(edited.text).toBe('one half = two quarters');
    expect(edited.created_at).toBe(a.created_at);

    await deleteNote('ST015', b.id);
    expect((await listNotes('ST015')).map((n) => n.id)).toEqual([a.id]);
  });

  it('survives corrupt storage', async () => {
    localStorage.setItem('numera.mynotes.ST015', '{not json');
    expect(await listNotes('ST015')).toEqual([]);
  });
});
