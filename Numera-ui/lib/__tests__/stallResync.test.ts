/**
 * A stalled turn must recover without the student refreshing the page.
 *
 * Manjusha, 14 Sep: "Basically it is not moving forward unless refreshed…
 * Initially I got stuck up after scaffold, got parallel example only at
 * refresh. Then now after hint 1 hint 2 also is delivered after refresh."
 *
 * The VM logs for that session show the backend DID its part — 07:47:38,
 * `guided_canvas_actions_planned` with `action_types: ["SHOW_PARALLEL"]` and
 * `validation_rejections: 0`, and at 07:54:09 a HINT on `SUPPORT_AND_RETRY` —
 * and the voice server logged "Text sent to frontend" for every turn. The
 * support existed and was sent; the screen simply never showed it.
 *
 * Whatever drops it on the wire, the client already knows how to recover: a
 * refresh reads GET /session, which carries the live state and is not subject
 * to whatever the turn payload lost. So the rescue should do what the refresh
 * does, rather than leaving the student to discover F5.
 *
 * `resumeSession` cannot be that call. It returns early once `backendSession`
 * is set — it exists for opening a stored session on a cold load, and a
 * mid-lesson stall is the opposite case.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const source = readFileSync(join(process.cwd(), 'hooks/useDemoTutor.ts'), 'utf8');
const resync = source.slice(source.indexOf('export async function resyncSession'));

describe('resyncSession', () => {
  it('exists as its own entry point, separate from resume', () => {
    expect(source).toContain('export async function resyncSession');
  });

  it('does not refuse to run once a session is already loaded', () => {
    // The bug this whole file is about: `resumeSession` guards on
    // `store.backendSession` and would no-op at exactly the moment we need it.
    const body = resync.slice(0, resync.indexOf('\n}\n'));
    expect(body).not.toContain('store.backendSession) return');
  });

  it('applies the record through the same path a refresh uses', () => {
    const body = resync.slice(0, resync.indexOf('\n}\n'));
    expect(body).toContain('getSession');
    expect(body).toContain('syncBackendSession');
    // The support a refresh restores has to come back too, or the resync
    // recovers the question and still loses the hint that prompted it.
    expect(body).toContain('active_visual_cue');
  });

  it('never replaces a transcript that already has content', () => {
    // The student's own conversation is on screen; a resync mid-lesson must
    // not overwrite it with the server's history.
    const body = resync.slice(0, resync.indexOf('\n}\n'));
    expect(body).toContain('transcript.length === 0');
  });
});

describe('the turn rescue', () => {
  const ws = readFileSync(join(process.cwd(), 'hooks/useWebSocket.ts'), 'utf8');

  it('resyncs before telling the student something went wrong', () => {
    // Apologising for a turn the backend actually completed is the worst of
    // both: the support is sitting on the session record unread, and the
    // student is told it failed.
    expect(ws).toContain('resyncSession');
  });
});

describe('reconnecting the voice socket', () => {
  const ws = readFileSync(join(process.cwd(), 'hooks/useWebSocket.ts'), 'utf8');
  const onopen = ws.slice(ws.indexOf('ws.onopen ='), ws.indexOf('ws.onmessage ='));

  it('does not hand the floor back while the tutor is still audible', () => {
    // The echo. VM log, 14 Sep 07:47:33, one turn after a reconnect:
    //   Flux EndOfTurn ... word_conf=0.9998: 'Scaffolded support for t zero one.'
    // 0.9998 is clean synthesised audio, not a person — the tutor's own voice,
    // captured and transcribed as the student's answer. The backend judged it,
    // failed the scaffold step, and escalated to a parallel example for an
    // answer the student never gave.
    expect(onopen).toContain('aiSpeaking');
    expect(onopen).not.toMatch(/^\s*setVoiceStatus\('listening'\);\s*$/m);
  });

  it('re-reads the session, because a reply during the gap is simply lost', () => {
    // This socket reconnects every 60-85s on the VM, all lesson long. A
    // tutor_response landing in that window has nowhere to arrive, and only a
    // refresh went looking for it.
    expect(onopen).toContain('resyncSession');
  });
});
