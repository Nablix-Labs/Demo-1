'use client';

/**
 * WriteNote — "I need to see this written down."
 *
 * Shown when the backend's reliability gate could not read the student well
 * enough to judge the maths, and asks for written evidence instead (revised
 * handoff, frontend §5).
 *
 * Deliberately not amber. The support ladder is about a student who is stuck;
 * this is about a tutor who could not hear or read them, and nothing has been
 * concluded about what they know. Amber would tell a student who answered
 * perfectly well that they needed help.
 *
 * `rose` because StickyNote's tones already mean something — rose is the one
 * that "expects an answer", which is exactly what this is asking for. A fifth
 * tone would say this is a fifth KIND of note, and it is not: it is the same
 * request for a response, arriving for a different reason.
 *
 * There is no dismiss control. A hint can be waved away because the student may
 * already have seen the point; this names the one action that will move the turn
 * forward, and hiding it leaves them stuck with no way back to it.
 *
 * A WRITE_AREA canvas action raises the same note for a different reason: the
 * tutor is asking for the rule in writing, rather than reporting that it could
 * not read one. The note is shared because the ASK is identical — a second
 * component would say these are two different requests when the student has the
 * same single thing to do.
 *
 * What is NOT shared is the wording. A WRITE_AREA action may carry `text`, and
 * that text can be the rule itself; putting it here would write the answer into
 * the very place the student is being asked to produce it. So the affordance
 * gets a fixed prompt and the action's text never reaches the screen — see
 * lib/tutorCanvasActions.
 */

import { PencilLine } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import StickyNote from '@/components/StickyNote';

/** Used when the tutor asked for writing but sent no wording of its own. */
const AFFORDANCE_PROMPT = 'Write your answer on the canvas.';

export default function WriteNote() {
  const instruction = useNumeraStore((s) => s.writeInstruction);
  const affordance = useNumeraStore((s) => s.writeAffordance);
  // The gate's own wording wins when there is one: it can say WHY it could not
  // read the student, which a fixed prompt cannot.
  const text = instruction ?? (affordance ? AFFORDANCE_PROMPT : null);
  if (!text) return null;

  return (
    <aside className="relative transition-all duration-300" aria-label="Write your answer">
      <StickyNote tone="rose" label="Write it down">
        <span className="flex items-start gap-2">
          <PencilLine size={15} strokeWidth={2.2} className="mt-[2px] shrink-0" />
          <span>{text}</span>
        </span>
      </StickyNote>
    </aside>
  );
}
