'use client';

/**
 * TEACH_BACK adapter — the single seam between the Teacher Mode screen and the
 * tutoring backend. The screen calls submitTeachTurn() and renders whatever
 * comes back; it never evaluates the explanation itself (that's the Tutor
 * Engine, owned by Chiru).
 *
 * The real backend contract isn't finalized yet, so this ships a mock that
 * drives a full, believable teach-back conversation with no backend. When the
 * real /interaction (TEACH_BACK) contract lands, only submitTeachTurn's body
 * swaps to the network call — the request/response shapes below are the
 * proposal we hand to Chiru (from the module doc's "Suggested Structured
 * Output"). Nothing else on the screen changes.
 */

export type TeachInputSource = 'TEXT' | 'VOICE' | 'CANVAS';

/** Status the backend tracks internally. Carried through but never shown to the student. */
export type TeachBackStatus =
  | 'NOT_STARTED'
  | 'IN_PROGRESS'
  | 'PARTIAL'
  | 'MASTERED'
  | 'MISCONCEPTION'
  | 'NEEDS_RETEACH';

/** What the tutor is doing this turn — drives small UI cues (e.g. a misconception challenge). */
export type TeachAction =
  | 'INVITE_EXPLANATION'
  | 'ASK_WHY_QUESTION'
  | 'ASK_FOR_EXAMPLE'
  | 'PRESENT_MISCONCEPTION'
  | 'REQUEST_SUMMARY'
  | 'GIVE_SMALL_HINT'
  | 'MICRO_RETEACH'
  | 'MOVE_TO_GUIDED_PRACTICE';

/** Backend phase the session should move to when the phase ends (null = stay in TEACH_BACK). */
export type TeachNextPhase =
  | 'GUIDED_PRACTICE'
  | 'CONCEPT_ORIENTATION'
  | null;

export interface TeachTurnRequest {
  session_id: string | null;
  student_id: string;
  current_phase: 'TEACH_BACK';
  input_source: TeachInputSource;
  text_input?: string;
  voice_transcript?: string;
  canvas_snapshot?: string | null;
  turn_number: number;
}

export interface TeachTurnResponse {
  /** The tutor's next message — shown verbatim as Numera's speech. */
  student_facing_response: string;
  action: TeachAction;
  /** Non-null only when the phase ends; the screen routes there. */
  next_phase: TeachNextPhase;
  status: TeachBackStatus;
  /** Internal, never rendered — kept so the real backend can populate them. */
  covered_concepts?: string[];
  missing_concepts?: string[];
  detected_misconceptions?: string[];
}

// ── Mock conversation ─────────────────────────────────────────────────────────
// A scripted role-reversal for the canonical "adding fractions" concept, tolerant
// of any student input so the flow always advances. turn_number 0 is the opening
// invite the screen shows on entry; each later turn responds to the student.

const MOCK_TURNS: TeachTurnResponse[] = [
  {
    student_facing_response:
      "Okay — you're the teacher now and I'm your student. Teach me how to add fractions with different denominators. Start with the main idea in your own words.",
    action: 'INVITE_EXPLANATION',
    next_phase: null,
    status: 'IN_PROGRESS',
  },
  {
    student_facing_response:
      'I think I follow. But why do the denominators need to be the same before we add?',
    action: 'ASK_WHY_QUESTION',
    next_phase: null,
    status: 'IN_PROGRESS',
    covered_concepts: ['common denominator'],
  },
  {
    student_facing_response:
      'That makes sense. Can you show me with an example — try 1/2 + 1/3 on the board or in words?',
    action: 'ASK_FOR_EXAMPLE',
    next_phase: null,
    status: 'IN_PROGRESS',
  },
  {
    student_facing_response:
      "So for 1/2 + 1/3, can I just add the tops and bottoms and get 2/5? That's easier, right?",
    action: 'PRESENT_MISCONCEPTION',
    next_phase: null,
    status: 'IN_PROGRESS',
  },
  {
    student_facing_response:
      'Ah, I see my mistake. Give me one short rule to remember for next time.',
    action: 'REQUEST_SUMMARY',
    next_phase: null,
    status: 'MASTERED',
  },
  {
    student_facing_response:
      "You explained what to do and why it works — and you caught my mistake. Nice teaching. Let's solve one together now.",
    action: 'MOVE_TO_GUIDED_PRACTICE',
    next_phase: 'GUIDED_PRACTICE',
    status: 'MASTERED',
  },
];

function mockTurn(turnNumber: number): TeachTurnResponse {
  const i = Math.min(turnNumber, MOCK_TURNS.length - 1);
  return MOCK_TURNS[i];
}

/** Small human-feeling delay so mock replies don't snap in instantly. */
const think = () => new Promise<void>((r) => setTimeout(r, 650));

/**
 * Submit one teach-back turn and get the tutor's next move.
 *
 * MOCK-ONLY for now (see file header). When the real contract lands, replace the
 * body with the network call and keep this signature.
 */
export async function submitTeachTurn(req: TeachTurnRequest): Promise<TeachTurnResponse> {
  await think();
  return mockTurn(req.turn_number);
}

/** The opening invite shown when Teacher Mode loads (turn 0), no student input yet. */
export function teachOpening(): TeachTurnResponse {
  return MOCK_TURNS[0];
}
