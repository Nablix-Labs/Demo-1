import { describe, expect, it } from 'vitest';
import { AxiosError, AxiosHeaders } from 'axios';
import {
  restoredLines, sendWithOneResend, teachBackFailure, teachBackFailureMessage, teachBackPayload,
} from '@/lib/teachback/connected';

const session = {
  sessionId: 'SES-1', studentId: 'ST015', conceptId: 'ALG_NOTATION', hintCount: 2,
  turnId: 'turn-7', previousTutorTurnId: 'tutor-6',
};

function axiosError(status: number | undefined, data?: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  return new AxiosError('failed', 'ERR', config, undefined, status === undefined ? undefined : {
    status, statusText: '', headers: {}, config, data,
  });
}

describe('teachBackPayload', () => {
  it('sends a typed explanation as a Teach-Back submission with no question and no canvas', () => {
    const p = teachBackPayload({ text: '  you undo the plus by taking away  ', source: 'TEXT' }, session);
    expect(p).toEqual({
      session_id: 'SES-1', student_id: 'ST015', interaction_type: 'TEACH_BACK_SUBMISSION', input_source: 'TEXT',
      text_input: 'you undo the plus by taking away', current_phase: 'TEACH_BACK', concept_id: 'ALG_NOTATION',
      question_id: null, hint_count: 2, turn_id: 'turn-7', previous_tutor_turn_id: 'tutor-6',
    });
    expect(p).not.toHaveProperty('canvas_state');
    expect(p).not.toHaveProperty('canvas_snapshot_id');
  });

  it('sends speech as a final voice transcript with its confidence', () => {
    const p = teachBackPayload({ text: '3x means three times x', source: 'VOICE', confidence: 0.82 }, session);
    expect(p).toMatchObject({ input_source: 'VOICE', voice_transcript: '3x means three times x', transcript_final: true, transcript_confidence: 0.82 });
    expect(p).not.toHaveProperty('text_input');
  });

  it('drops a confidence outside 0–1 instead of sending something the backend rejects', () => {
    expect(teachBackPayload({ text: 'x', source: 'VOICE', confidence: 7 }, session)).not.toHaveProperty('transcript_confidence');
    expect(teachBackPayload({ text: 'x', source: 'VOICE', confidence: null }, session)).not.toHaveProperty('transcript_confidence');
  });
});

describe('restoredLines', () => {
  it('rebuilds the conversation from history, skipping system lines', () => {
    expect(restoredLines({
      message: 'ignored when there is history',
      conversation_history: [
        { role: 'system', content: 'rules' },
        { role: 'assistant', content: 'Your turn to be the teacher!' },
        { role: 'user', content: 'You divide both sides' },
        { role: 'assistant', content: 'Why both sides?' },
      ],
    })).toEqual([
      { role: 'tutor', text: 'Your turn to be the teacher!' },
      { role: 'student', text: 'You divide both sides' },
      { role: 'tutor', text: 'Why both sides?' },
    ]);
  });

  it('falls back to the opening message', () => {
    expect(restoredLines({ message: 'What is the main idea?', conversation_history: [] }))
      .toEqual([{ role: 'tutor', text: 'What is the main idea?' }]);
    expect(restoredLines({ message: '' })).toEqual([]);
  });
});

describe('teachBackFailure', () => {
  // The backend's real error body (nablix-backend main.py _error_response).
  const body = (message: string, error_code = 'HTTP_ERROR') => ({ error_code, message, field: null, timestamp: 't', request_id: 'r' });

  it('retries what may not have been saved', () => {
    expect(teachBackFailure(axiosError(undefined))).toBe('retry'); // network / timeout
    expect(teachBackFailure(axiosError(503, body('Teach-Back context or student evidence is missing.')))).toBe('retry');
    expect(teachBackFailure(axiosError(409, body('Teach-Back recovery is pending; refresh the session before submitting another turn.')))).toBe('retry');
    expect(teachBackFailure(axiosError(409, body('Journey version changed.', 'JOURNEY_VERSION_CONFLICT')))).toBe('retry');
    expect(teachBackFailure(new Error('turn could not be synchronised'))).toBe('retry');
  });

  it('resends when the tutor reply, not the student, failed the backend checks', () => {
    expect(teachBackFailure(axiosError(422, body('A graded verdict must quote a current-target claim.', 'INVALID_TEACH_BACK_REPLY')))).toBe('retry');
  });

  it('discards what the backend refused for good', () => {
    expect(teachBackFailure(axiosError(422, body('Realtime results require a text or voice Teach-Back submission without canvas.')))).toBe('discard');
    expect(teachBackFailure(axiosError(422, body('Field required', 'VALIDATION_ERROR')))).toBe('discard');
    expect(teachBackFailure(axiosError(409, body('turn_id was already accepted with different Teach-Back evidence.')))).toBe('discard');
    expect(teachBackFailure(axiosError(409, body('The authoritative session is outside Teach-Back.')))).toBe('discard');
    expect(teachBackFailure(axiosError(409, body('Realtime result belongs to an inactive Teach-Back target.')))).toBe('discard');
    expect(teachBackFailure(axiosError(409, body('Teach-Back has no unfinished target.')))).toBe('discard');
  });

  it('still reads a raw FastAPI detail', () => {
    expect(teachBackFailure(axiosError(409, { detail: 'The authoritative session is outside Teach-Back.' }))).toBe('discard');
  });

  it('recognises a teacher pause', () => {
    expect(teachBackFailure(axiosError(409, body('paused', 'INTERVENTION_REQUIRED')))).toBe('paused');
  });

  it('never shows server text to the student', () => {
    for (const a of ['retry', 'discard', 'paused'] as const) {
      expect(teachBackFailureMessage(a)).not.toMatch(/409|422|503|Teach-Back evidence|status/i);
    }
  });
});

describe('sendWithOneResend', () => {
  const invalid = () => axiosError(422, { error_code: 'INVALID_TEACH_BACK_REPLY', message: 'bad reply' });

  it('resends once after an invalid tutor reply or a server error, then succeeds', async () => {
    for (const first of [invalid(), axiosError(503, { error_code: 'HTTP_ERROR', message: 'x' }), axiosError(undefined)]) {
      let calls = 0;
      const out = await sendWithOneResend(async () => { calls++; if (calls === 1) throw first; return 'ok'; }, 0);
      expect(out).toBe('ok');
      expect(calls).toBe(2);
    }
  });

  it('gives up after the second failure', async () => {
    let calls = 0;
    await expect(sendWithOneResend(async () => { calls++; throw invalid(); }, 0)).rejects.toBeTruthy();
    expect(calls).toBe(2);
  });

  it('never resends a conflict or a refused answer: those refresh first', async () => {
    for (const err of [
      axiosError(409, { error_code: 'HTTP_ERROR', message: 'Teach-Back recovery is pending' }),
      axiosError(422, { error_code: 'VALIDATION_ERROR', message: 'Field required' }),
    ]) {
      let calls = 0;
      await expect(sendWithOneResend(async () => { calls++; throw err; }, 0)).rejects.toBe(err);
      expect(calls).toBe(1);
    }
  });
});
