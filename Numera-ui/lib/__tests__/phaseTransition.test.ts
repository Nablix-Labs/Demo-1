import { describe, it, expect } from 'vitest';
import { phaseAnnouncement, withTransitionVoice } from '@/lib/phaseTransition';

describe('phaseAnnouncement', () => {
  it('announces when the reply moves the student into a new phase', () => {
    const a = phaseAnnouncement(
      {
        current_phase: 'GUIDED_PRACTICE',
        phase_transition_message: "Nice work. Let's practise together.",
      },
      'ORIENTATION',
    );
    expect(a).toEqual({
      text: "Nice work. Let's practise together.",
      voice: "Nice work. Let's practise together.",
    });
  });

  it('prefers the spoken wording when the backend sends one', () => {
    const a = phaseAnnouncement(
      {
        current_phase: 'GUIDED_PRACTICE',
        phase_transition_message: 'Phase 2: Guided Practice',
        phase_transition_voice: "Now let's work through some together.",
      },
      'ORIENTATION',
    );
    expect(a?.text).toBe('Phase 2: Guided Practice');
    expect(a?.voice).toBe("Now let's work through some together.");
  });

  it('stays silent when the phase has not changed', () => {
    // A backend that echoes the message on every turn of the new phase must not
    // make the tutor re-announce it each reply.
    expect(
      phaseAnnouncement(
        { current_phase: 'GUIDED_PRACTICE', phase_transition_message: 'Welcome to guided practice.' },
        'GUIDED_PRACTICE',
      ),
    ).toBeNull();
  });

  it('stays silent when there is no message', () => {
    expect(phaseAnnouncement({ current_phase: 'GUIDED_PRACTICE' }, 'ORIENTATION')).toBeNull();
    expect(
      phaseAnnouncement({ current_phase: 'GUIDED_PRACTICE', phase_transition_message: '   ' }, 'ORIENTATION'),
    ).toBeNull();
  });

  it('stays silent when the response carries no phase to compare', () => {
    // Without a phase we cannot tell a real transition from an echo.
    expect(phaseAnnouncement({ phase_transition_message: 'Welcome.' }, 'ORIENTATION')).toBeNull();
  });

  it('announces the very first phase of a fresh session', () => {
    const a = phaseAnnouncement(
      { current_phase: 'GUIDED_PRACTICE', phase_transition_message: 'Off we go.' },
      '',
    );
    expect(a?.text).toBe('Off we go.');
  });
});

describe('withTransitionVoice', () => {
  it('speaks the transition ahead of the reply as one utterance', () => {
    const a = { text: 'Phase 2', voice: "Let's practise." };
    expect(withTransitionVoice(a, 'What is 4y?')).toBe("Let's practise. What is 4y?");
  });

  it('leaves the reply untouched when there is no transition', () => {
    expect(withTransitionVoice(null, 'What is 4y?')).toBe('What is 4y?');
  });

  it('falls back to the transition alone when the reply is empty', () => {
    const a = { text: 'Phase 2', voice: "Let's practise." };
    expect(withTransitionVoice(a, '   ')).toBe("Let's practise.");
  });
});
