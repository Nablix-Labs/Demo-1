/**
 * A backend topic code must never blank the screen.
 *
 * `next_topic_handoff` sends the student to `/orientation/ALG-ORI-02` — a
 * curriculum code from the Student Model. `getTopic` only knows the four mock
 * ids (`algebra`, `number`, `geometry`, `statistics`), so it returned
 * undefined, the client called `notFound()`, and with no `not-found.tsx` under
 * the route Next unmounted everything inside AppFrame: a blank white page at
 * the exact moment a student finishes a topic (Topic Transition Issue, 11 Sep
 * 2026).
 */
import { describe, expect, it } from 'vitest';
import { displayTopic } from '@/lib/topicDisplay';
import { getTopic } from '@/lib/curriculum';

describe('naming a topic the client has to render', () => {
  it('prefers the name the backend sent for this session', () => {
    // The session is the authority on what this topic is called — the mock
    // curriculum is a fixture and may disagree with the real content.
    expect(displayTopic('algebra', 'Linear Equations')).toEqual({
      id: 'algebra',
      title: 'Linear Equations',
    });
  });

  it('falls back to the curriculum entry when the session named nothing', () => {
    // `sessionTopicTitle` is null before the orientation bundle arrives, which
    // is most of the diagnostic.
    // Read through the same module the app does, so a curriculum rename does
    // not silently leave this asserting against a stale literal.
    expect(displayTopic('algebra', null).title).toBe(getTopic('algebra')!.title);
  });

  it('renders a backend code the curriculum has never heard of', () => {
    // The regression. Not found is not an error here: the id is a real topic,
    // it simply is not one of the four fixtures.
    expect(displayTopic('ALG-ORI-02', null)).toEqual({
      id: 'ALG-ORI-02',
      title: 'ALG-ORI-02',
    });
  });

  it('names that same code properly once the session says what it is', () => {
    expect(displayTopic('ALG-ORI-02', 'What Is Algebra?').title).toBe('What Is Algebra?');
  });

  it('does not resolve a name out of the code itself', () => {
    // QA row 42: inventing "Alg Ori 02" from the code puts a made-up topic name
    // in front of a student. The code is ugly and honest; a guess is neither.
    expect(displayTopic('ALG-ORI-02', '   ').title).toBe('ALG-ORI-02');
  });
});

