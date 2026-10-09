import { describe, expect, it } from 'vitest';
import { AxiosError, AxiosHeaders } from 'axios';
import {
  restoredLines, teachBackFailure, teachBackFailureMessage, teachBackPayload,
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
  it('retries what may not have been saved', () => {
    expect(teachBackFailure(axiosError(undefined))).toBe('retry'); // network / timeout
    expect(teachBackFailure(axiosError(503, { detail: 'Teach-Back context is unavailable.' }))).toBe('retry');
    expect(teachBackFailure(axiosError(409, { detail: 'Teach-Back recovery is pending; refresh the session before submitting another turn.' }))).toBe('retry');
    expect(teachBackFailure(axiosError(409, { error_code: 'JOURNEY_VERSION_CONFLICT' }))).toBe('retry');
    expect(teachBackFailure(new Error('turn could not be synchronised'))).toBe('retry');
  });

  it('discards what the backend refused for good', () => {
    expect(teachBackFailure(axiosError(422, { detail: 'canvas is not accepted' }))).toBe('discard');
    expect(teachBackFailure(axiosError(409, { detail: 'turn_id was already accepted with different Teach-Back evidence.' }))).toBe('discard');
    expect(teachBackFailure(axiosError(409, { detail: 'The authoritative session is outside Teach-Back.' }))).toBe('discard');
    expect(teachBackFailure(axiosError(409, { detail: 'Realtime result belongs to an inactive Teach-Back target.' }))).toBe('discard');
  });

  it('recognises a teacher pause', () => {
    expect(teachBackFailure(axiosError(409, { error_code: 'INTERVENTION_REQUIRED' }))).toBe('paused');
  });

  it('never shows server text to the student', () => {
    for (const a of ['retry', 'discard', 'paused'] as const) {
      expect(teachBackFailureMessage(a)).not.toMatch(/409|422|503|Teach-Back evidence|status/i);
    }
  });
});
