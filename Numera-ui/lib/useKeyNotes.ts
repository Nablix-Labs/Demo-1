'use client';

/**
 * The key notes this screen shows, and where they came from.
 *
 *  - API off (local demo): the sample notebook, as before.
 *  - API on: GET /students/me/key-notes for the student's latest session.
 *    `unavailable` when the endpoint does not exist yet (404/405) — the screen
 *    says notes are on their way rather than showing sample cards as if they
 *    were the student's. `empty` for a real student with none yet.
 */
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { KEY_NOTES, keyNoteFromApi, type ApiKeyNote, type KeyNote } from '@/lib/keynotes';
import { useNumeraStore } from '@/store/useNumeraStore';

export type KeyNotesState =
  | { status: 'loading' }
  | { status: 'sample'; notes: KeyNote[] }
  | { status: 'ready'; notes: KeyNote[] }
  | { status: 'empty' }
  | { status: 'unavailable' }
  | { status: 'error'; message: string };

const apiOn = Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

export function useKeyNotes(): KeyNotesState & { reload: () => void } {
  const sessionId = useNumeraStore((s) => s.sessionId ?? s.endedSessionId ?? null);
  const [state, setState] = useState<KeyNotesState>(apiOn ? { status: 'loading' } : { status: 'sample', notes: KEY_NOTES });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!apiOn) return;
    let cancelled = false;
    setState({ status: 'loading' });
    api.get<{ notes?: ApiKeyNote[] } | ApiKeyNote[]>('/students/me/key-notes', { params: sessionId ? { session_id: sessionId } : {} })
      .then((res) => {
        if (cancelled) return;
        const raw = Array.isArray(res.data) ? res.data : res.data.notes ?? [];
        const notes = raw.map(keyNoteFromApi);
        setState(notes.length ? { status: 'ready', notes } : { status: 'empty' });
      })
      .catch((err: { response?: { status?: number } }) => {
        if (cancelled) return;
        const status = err.response?.status;
        if (status === 404 || status === 405) setState({ status: 'unavailable' });
        else setState({ status: 'error', message: 'Your key notes could not be loaded.' });
      });
    return () => { cancelled = true; };
  }, [sessionId, nonce]);

  return { ...state, reload: () => setNonce((n) => n + 1) };
}
