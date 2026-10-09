import clsx from 'clsx';
import type { Tone } from './ui';
import { PHASES } from '@/lib/derive';
import type { SkillStatus, TopicProgress } from '@/lib/types';

export const MASTERY_TONE: Record<TopicProgress['mastery_status'], Tone> = {
  MASTERED: 'good', IN_PROGRESS: 'info', REVIEW: 'warn', NOT_STARTED: 'neutral',
};
export const SKILL_TONE: Record<SkillStatus, Tone> = {
  INDEPENDENTLY_VERIFIED: 'good', VERIFIED_WITH_SUPPORT: 'warn', RESCUE_REQUIRED: 'bad', UNKNOWN: 'neutral',
};

export function PhaseDots({ t }: { t: TopicProgress }) {
  return (
    <ol className="mt-3 flex items-center gap-1" aria-label="Stages">
      {PHASES.map((p) => {
        const done = t.mastery_status === 'MASTERED' || t.phases_completed.includes(p.id);
        const now = t.current_phase === p.id;
        return (
          <li
            key={p.id}
            title={`${p.label}: ${done ? 'done' : now ? 'in progress' : 'to come'}`}
            className={clsx('h-1.5 flex-1 rounded-full', done ? 'bg-correct' : now ? 'bg-teal' : 'bg-line')}
          />
        );
      })}
    </ol>
  );
}

