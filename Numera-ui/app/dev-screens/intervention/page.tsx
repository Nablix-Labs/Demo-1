'use client';

/**
 * /dev-screens/intervention — the Phase 3 difficulty popup on a fixture.
 *
 * The backend half does not reach the browser yet: `intervention_input_request`
 * would be dropped by `PublicStudentModelEvent`, which is `extra="forbid"` and
 * carries no such field (nablix-backend/app/models/student_model_session.py:246).
 * So this is how the popup is reviewed and demoed until that projection is
 * widened — same arrangement as /dev-screens/phase4, and under /dev-screens,
 * which AppFrame already treats as pre-auth and full-bleed.
 *
 * Two fixtures because the difference is invisible from inside the component
 * and is exactly what §11 turns on:
 *   - TC-33 sends the six selections.
 *   - TC-34 sends none. The popup must still be usable, or a student the system
 *     has already given up on gets a dead submit button.
 */

import { useState } from 'react';
import Link from 'next/link';
import InterventionInputModal, {
  type InterventionInputSubmission,
} from '@/components/InterventionInputModal';
import type { InterventionInputRequest } from '@/lib/phase3Routing';

/** TC-33, verbatim. */
const TC33: InterventionInputRequest = {
  intervention_id: 'INT-T03-001',
  prompt: 'What are you finding difficult?',
  selection_required: true,
  voice_input_enabled: true,
  voice_input_required: false,
  selection_options: [
    { code: 'DONT_UNDERSTAND_QUESTION', label: 'I do not understand what the question is asking.' },
    { code: 'DONT_KNOW_HOW_TO_START', label: 'I do not know how to start.' },
    { code: 'CANNOT_APPLY_IDEA', label: 'I understand the idea, but I cannot use it in this question.' },
    { code: 'WORDS_SYMBOLS_CONFUSING', label: 'The maths words or symbols are confusing.' },
    { code: 'WORKING_MISTAKES', label: 'I keep making calculation or working mistakes.' },
    { code: 'OTHER', label: 'Something else.' },
  ],
};

/** TC-34 — no `selection_options` at all. */
const TC34: InterventionInputRequest = {
  intervention_id: 'INT-T03-002',
  prompt: 'What are you finding difficult?',
  selection_required: true,
  voice_input_enabled: true,
  voice_input_required: false,
};

export default function InterventionDevScreen() {
  const [fixture, setFixture] = useState<'TC33' | 'TC34'>('TC33');
  const [sent, setSent] = useState<InterventionInputSubmission | null>(null);

  return (
    <div className="min-h-full bg-reading-surface p-6">
      <div className="flex items-center gap-4 mb-5">
        <Link href="/" className="text-[12px] font-semibold text-learning-blue hover:underline">
          ← Back
        </Link>
        <span className="text-[12px] text-slate-blue">Phase 3 intervention input (fixture)</span>
        <button
          onClick={() => { setFixture((f) => (f === 'TC33' ? 'TC34' : 'TC33')); setSent(null); }}
          className="lg-chip rounded-full px-3 py-1.5 text-[12px] font-semibold text-ink/80 hover:text-ink"
        >
          {fixture === 'TC33' ? 'TC-33 — options sent' : 'TC-34 — no options (fallback)'}
        </button>
      </div>

      {sent ? (
        <div className="max-w-[560px] rounded-xl border border-muted-gray bg-white p-5">
          <p className="text-[13px] font-semibold text-ink mb-1">
            Recorded. The topic stays paused — §11: submitting does not resume learning.
          </p>
          <p className="text-[12px] text-slate-blue mb-3">
            This is the payload that would go to the event endpoint:
          </p>
          <pre className="text-[11.5px] text-ink bg-reading-surface rounded-lg p-3 overflow-x-auto">
            {JSON.stringify(sent, null, 2)}
          </pre>
          <button
            onClick={() => setSent(null)}
            className="mt-3 text-[12px] font-semibold text-learning-blue hover:underline"
          >
            Show the popup again
          </button>
        </div>
      ) : (
        <InterventionInputModal
          request={fixture === 'TC33' ? TC33 : TC34}
          onSubmit={(input) => setSent(input)}
        />
      )}
    </div>
  );
}
