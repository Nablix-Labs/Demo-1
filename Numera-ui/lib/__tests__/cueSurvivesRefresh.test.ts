/**
 * The visual cue has to survive a refresh.
 *
 * Manjusha, 27 Aug: "after a refresh the visual cue is not shown on the screen
 * / on session restart." Her screenshot is the whole bug in one frame — the
 * restored transcript reads "Take a look at the visual cue on the screen. It
 * contrasts your single case with the general rule", and there is no cue.
 *
 * None of the visualCue* fields are persisted, and that is right: they are
 * per-turn support, and bringing a stale cue back would be worse than bringing
 * none. The cue is meant to come back from the BACKEND — which has it, as
 * `active_visual_cue` on the session record — and resume never read it.
 * `syncBackendSession` is the only thing resume runs, and it applies session
 * state, not support.
 *
 * The transcript coming back while the cue did not is what made this land so
 * badly: the tutor's wording now points at the support (Sanya, 12 Aug), so a
 * restored line refers out loud to something that is not there.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('@/lib/tts', () => ({ speakTutor: vi.fn(), stopTutorSpeech: vi.fn() }));

const { useNumeraStore } = await import('@/store/useNumeraStore');
const { applyServedCue } = await import('@/lib/interactionPresentation');

const CUE = {
  show: true,
  cue_id: 'VC-T01-002',
  cue_type: null,
  description: 'Contrasts one specific case with the general rule.',
  asset_url: null,
  actions: null,
};

beforeEach(() => {
  useNumeraStore.setState({
    visualCueVisible: false,
    visualCueType: null,
    visualCueDescription: null,
    visualCueId: null,
  });
});

describe('a cue the backend still has open', () => {
  it('goes back on screen, with its authored wording', () => {
    applyServedCue(CUE);
    const s = useNumeraStore.getState();
    expect(s.visualCueVisible).toBe(true);
    expect(s.visualCueDescription).toBe(CUE.description);
  });

  it('keeps the cue id, which is what makes it an authored cue at all', () => {
    // cue_type is null on the real Topic 1 cues, so it cannot serve as the
    // evidence — only cue_id can.
    applyServedCue(CUE);
    expect(useNumeraStore.getState().visualCueId).toBe('VC-T01-002');
  });

  it('renders text-only rather than nothing when no asset was forwarded', () => {
    applyServedCue(CUE);
    const s = useNumeraStore.getState();
    expect(s.visualCueVisible).toBe(true);
    expect(s.visualCueDescription).toBeTruthy();
  });
});

/**
 * Asserted against the source: resume is a whole hook away from a unit test,
 * and the symptom is a missing card rather than an error, which is how it went
 * unnoticed. What must not regress is that resume reads the field at all.
 */
describe('resume reads the record’s open cue', () => {
  it('applies active_visual_cue off the resumed record', async () => {
    const { readFileSync } = await import('fs');
    const { resolve } = await import('path');
    const source = readFileSync(resolve(process.cwd(), 'hooks/useDemoTutor.ts'), 'utf8');
    const resume = source.slice(source.indexOf('export async function resumeSession'));
    const body = resume.slice(0, resume.indexOf('\n}'));
    expect(body).toContain('rec.active_visual_cue');
    expect(body).toContain('applyServedCue');
  });
});
