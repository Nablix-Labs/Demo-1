# TEACH_BACK (Learning by Teaching) — Frontend Design

Owner: Manav (frontend). Date: 2026-07-16.
Source: `Learning_by_Teaching_Module.docx` + `Learning_by_Teaching_Ownership_and_Tasks.docx`.

## Scope

Frontend-only implementation of the `TEACH_BACK` phase: a dedicated **Teacher
Mode** screen where the student teaches the tutor after the concept-orientation
video. The frontend renders tutor turns, collects the student's response
(text / voice / canvas), and follows the phase the backend returns. It does
**not** evaluate the explanation — that's the Tutor Engine (Chiru).

Built to run standalone in mock mode now, with a thin adapter for the single
backend call so only the adapter changes when Chiru's contract lands.

New flow: `DIAGNOSTIC → CONCEPT_ORIENTATION → TEACH_BACK → GUIDED_PRACTICE → INDEPENDENT_PRACTICE → REVIEW`

## Route & flow integration (touches existing code)

- New route: `app/teach/[topic]/page.tsx` + `app/teach/[topic]/TeachBackClient.tsx`.
- Insert `teach` into the manual flow (`lib/flow.ts`): `orientation → teach → guided`.
  `routeFor('teach', topicId)` → `/teach/${topicId}`. Orientation's `finish()`
  (`OrientationClient.tsx:87`) changes `goStage('guided')` → `goStage('teach')`.
- Backend phase routing (`lib/usePhaseRouting.ts`): add `TEACH_BACK → /teach/[topic]`
  and put `TEACH_BACK` in `PHASE_ORDER` between `CONCEPT_ORIENTATION` and `GUIDED_PRACTICE`.
- `lib/phases.ts`: add `teach` (prereq: `orientation`) so `PhaseGate` protects the route.

## Screen layout

Purpose-built, chat-forward, reusing existing pieces:

- **Role-reversal intro** on entry — warm, brief: "Now you're the teacher.
  Teach me what you just learned."
- **Transcript** of the back-and-forth (reuse `components/MediaPanel/Transcript`),
  showing **one tutor question at a time** (the latest tutor message is the
  current prompt).
- **Input dock:** `ChatInput` (text) + mic / `VoiceBar` (voice) + `DrawingCanvas`
  with `submitCanvasWork` (canvas) so the student can explain *and* show working.
- **Header framing:** "Teacher Mode — you're teaching Numera."
- Aesthetic: distinct from the lesson (role-reversal cue), calm and playful,
  not evaluative. No visible scores/rubrics/checklists (guardrail).

## Data flow & adapter

Single adapter `lib/teachback/teachApi.ts` → `submitTeachTurn(payload)`.

**Request (proposed):**
```
{ session_id, student_id, current_phase: 'TEACH_BACK', input_source: 'TEXT'|'VOICE'|'CANVAS',
  text_input? , voice_transcript? , canvas_snapshot? , turn_number }
```

**Response (from the doc's "Suggested Structured Output"):** the frontend only
consumes:
- `student_facing_response` → shown as the next tutor message
- `next_phase` (nullable) → route when present
- `next_action` → whether the conversation continues

Backend-internal fields (`teach_back_status`, `covered_concepts`,
`missing_concepts`, `detected_misconceptions`, `ready_for_guided_practice`) are
carried in the type but never shown to the student.

A **mock implementation** behind the adapter returns a scripted teach-back
sequence (invite → why → example → misconception challenge → summary → pass) so
the whole screen works with no backend. Real impl swaps in when the contract lands.

Session/turn state (turn history, current status) lives in the store, ephemeral,
mirroring how the tutor transcript already works.

## Routing outcomes

- `next_phase = GUIDED_PRACTICE` → advance to guided.
- `next_phase = CONCEPT_ORIENTATION` → back to orientation (major misconception).
- **MICRO_RETEACH / retry** (no forward `next_phase`, `next_action` signals reteach)
  → stay on `/teach`, show the reteach message inline, continue the conversation.
  Not a separate page.

Backend-driven navigation reuses `usePhaseRouting`; in mock mode the screen
navigates on the mock's returned phase.

## Out of scope (other owners)

Evaluation/scoring, silence-timing beyond existing voice turn-detection,
student-model updates (Tamil), safety check (Manjusha), lesson-content /
approved-misconception payloads (Aditya).

## Testing

- Unit: adapter response → UI mapping (status / next_phase → render / navigate).
- Playwright: full mock conversation drives `orientation → teach → guided`.
