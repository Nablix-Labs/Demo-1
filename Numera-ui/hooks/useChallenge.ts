'use client';

/**
 * useChallenge — drives Group Challenge Mode while a challenge is active.
 *
 * Stands in for the Group Session Server + Group AI Tutor: peers join, the AI
 * posts live commentary, spotlights work on the shared board, and sends the
 * local student private feedback. All mock/timer-based for now; the real
 * server plugs in behind the same store actions.
 */
import { useEffect } from 'react';
import { useNumeraStore } from '@/store/useNumeraStore';

const PEERS = [
  { id: 'p-aisha', name: 'Aïsha', color: '#2563eb' },
  { id: 'p-liam', name: 'Liam', color: '#d97706' },
  { id: 'p-wei', name: 'Wei', color: '#0d9488' },
  { id: 'p-fatima', name: 'Fatima', color: '#7c3aed' },
];

const COMMENTS: { text: string; tone: 'observe' | 'encourage' | 'hint' }[] = [
  { text: 'I can see two strong starts already. Keep going.', tone: 'encourage' },
  { text: 'A common trap here is changing only one side of the equation.', tone: 'observe' },
  { text: 'Nice — someone just isolated the x term cleanly.', tone: 'encourage' },
  { text: 'If you feel stuck, try subtracting 5 from both sides first.', tone: 'hint' },
  { text: 'Good reasoning on the board. Who wants to explain the next step?', tone: 'observe' },
];

export function useChallenge() {
  const challengeActive = useNumeraStore((s) => s.challengeActive);

  useEffect(() => {
    if (!challengeActive) return;
    const { upsertParticipant, addCommentary, setSpotlight, setPrivateFeedback } =
      useNumeraStore.getState();

    const timeouts: ReturnType<typeof setTimeout>[] = [];
    const intervals: ReturnType<typeof setInterval>[] = [];

    // Peers join, staggered
    PEERS.forEach((p, i) =>
      timeouts.push(setTimeout(() => upsertParticipant({ ...p, cursor: null }), 500 + i * 700))
    );

    // AI welcome + rolling commentary
    timeouts.push(setTimeout(() =>
      addCommentary({ text: 'Welcome everyone. Solve it on your own canvas — I am watching and will help.', tone: 'observe' }), 400));
    let ci = 0;
    intervals.push(setInterval(() => { addCommentary(COMMENTS[ci % COMMENTS.length]); ci += 1; }, 6500));

    // Shared-board spotlights (good = named, mistake = anonymous)
    timeouts.push(setTimeout(() =>
      setSpotlight({ kind: 'good', caption: 'Strong first step — subtracting 5 from both sides.', studentName: 'Aïsha' }), 8000));
    timeouts.push(setTimeout(() =>
      setSpotlight({ kind: 'mistake', caption: 'A common slip — only one side was changed. Can you spot it?', studentName: null }), 17000));

    // Private feedback to this student only
    timeouts.push(setTimeout(() =>
      setPrivateFeedback('You are on the right track. Now divide both sides by 3.'), 11000));

    return () => {
      timeouts.forEach(clearTimeout);
      intervals.forEach(clearInterval);
    };
  }, [challengeActive]);
}
