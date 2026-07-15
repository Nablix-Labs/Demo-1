/**
 * toSessionSummary — derives the Review-screen summary from the /session/end
 * response. Covers the explicit-summary path, the derived path, and the
 * "no usable session" guard.
 */

import { describe, it, expect } from 'vitest';
import { toSessionSummary, type SessionEndResponse } from '@/lib/api';

// Minimal ended-session record; only the fields toSessionSummary reads matter.
function record(overrides: Partial<SessionEndResponse> = {}): SessionEndResponse {
  return {
    session_id: 'sess-1',
    student_id: 'ST001',
    concept_id: 'ALG_LINEAR_ONE_STEP',
    interaction_mode: 'VOICE',
    current_phase: 'REVIEW',
    current_question: 'x + 4 = 9',
    question_id: 'Q1',
    question_number: 1,
    voice_state: {} as SessionEndResponse['voice_state'],
    canvas_state: {} as SessionEndResponse['canvas_state'],
    ui_state: '',
    message: 'Session ended.',
    show_canvas: true,
    show_hint_button: true,
    show_visual_cue: false,
    show_scaffold_panel: false,
    scaffold_steps: [],
    allow_text_input: true,
    allow_voice_input: true,
    hint_count: 0,
    status: 'ended',
    mode: '',
    canvas_submissions: [],
    ...overrides,
  };
}

describe('toSessionSummary', () => {
  it('returns null when there is no usable session', () => {
    expect(toSessionSummary(null)).toBeNull();
    expect(toSessionSummary(undefined)).toBeNull();
    expect(toSessionSummary(record({ session_id: '' }))).toBeNull();
  });

  it('prefers an explicit backend summary object', () => {
    const s = toSessionSummary(record({
      hint_count: 1,
      attempt_count: 2,
      summary: { attempts: 5, hints_used: 3, status: 'completed' },
    }));
    expect(s).toMatchObject({ attempts: 5, hints_used: 3, status: 'completed' });
  });

  it('derives attempts from attempt_count and hints from hint_count', () => {
    const s = toSessionSummary(record({ hint_count: 4, attempt_count: 7 }));
    expect(s).toMatchObject({ attempts: 7, hints_used: 4, question: 'x + 4 = 9', status: 'ended' });
  });

  it('falls back to canvas_submissions length when attempt_count is absent', () => {
    const s = toSessionSummary(record({
      hint_count: 2,
      canvas_submissions: [{}, {}, {}] as SessionEndResponse['canvas_submissions'],
    }));
    expect(s?.attempts).toBe(3);
    expect(s?.hints_used).toBe(2);
  });

  it('defaults counts to zero when nothing is provided', () => {
    const s = toSessionSummary(record());
    expect(s).toMatchObject({ attempts: 0, hints_used: 0 });
  });
});
