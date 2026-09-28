# Canvas teaching plan: what is sent vs what is shown (28 Sep 2026)

Evidence, not theory: every planner draft from 26–27 Sep, fetched from OpenAI's
stored responses by the `request_id` in the backend log (52 drafts, 75
operations). Plus two live turns on `sanya1` (ST013), session
`SESSION190cab991e2c4d10bcb3990dc88aa107`, Q-T02-005, turns
`TURN-MANAV-AUDIT-001` and `-002`.

## Backend: about 1 plan in 4 never leaves the server

`_validate_draft` is all-or-nothing. If one operation fails, the whole plan
becomes `null`, including every valid operation beside it, and nothing is logged.

Of 52 drafts:

| Why the whole plan is dropped | Drafts |
|---|---|
| `HIGHLIGHT`/`CIRCLE` carries an `evidence_ref` (non-write ops must have `null`) | 6 |
| `CONNECT` in zone `REASONING` (validator only accepts `QUESTION`) | 3 |
| targets a non-maths token (`Write`, `calculating`, `using`, `algebraic`…) | 4 |
| `CONNECT` with no `evidence_ref` | 1 |
| unparseable | 1 |

That is 14 out of 52, before counting runtime checks I can't replay offline
(speech-anchor sync, current-turn evidence).

Live example, `TURN-MANAV-AUDIT-001`: the draft was
`WRITE_MATH r\times r` in REASONING **plus** `CONNECT` from the `r²` token in
zone REASONING. The CONNECT fails the zone rule, so the good `r × r` write went
too, and the response had `canvas_teaching_plan: null`.

Asks (backend, Sanya):

1. Drop only the failing operation, and only drop a beat when it has no
   operations left.
2. Log each rejection with the operation kind and the rule it failed. Right
   now "sent but not shown" can't be told apart from "never sent".
3. Align the prompt with the validator. The model consistently (a) puts
   `evidence_ref` on attention marks and (b) puts `CONNECT` in REASONING,
   because it is connecting a question token to a reasoning note. Either tell
   it the exact rule, or accept REASONING-zone CONNECT when it has a
   `scene_slot`.

## Live run, 28 Sep 06:18–06:27 UTC: 5 of 5 confirmation plans dropped

Logged in as `sanya1` on Demo 1, session `SESSION3b1e51a3ae9846dfb811625e7e88e616`,
Q-T02-005. Each correct answer was typed in the UI, and I read the response
and the planner draft for every turn:

| Student said | Planner drafted | Response `canvas_teaching_plan` |
|---|---|---|
| 4n means 4 multiplied by n | `WRITE_MATH 4n=4\times n` + `CONNECT` QTOKEN:8,9 in **REASONING** | `null` |
| pq means p multiplied by q | `WRITE_MATH p\times q` + `CONNECT` QTOKEN:10 in **REASONING** | `null` |
| r squared means r multiplied by r | `WRITE_MATH r^2=r\times r` + `CONNECT` QTOKEN:11 in **REASONING** | `null` |
| c/d means c divided by d | `WRITE_MATH \frac{c}{d}=c\div d` + `CONNECT` QTOKEN:12–14 in **REASONING** | `null` |
| 2(x + 1) means … | `WRITE_MATH 2(x+1)` + `CONNECT` QTOKEN:17–19 in **REASONING** | `null` |

The drafts are exactly the teaching we want: a confirmed note plus an arrow
from the token it came from. Every one is lost to a single rule in
`_operation_is_authorized`: `CONNECT` requires `zone == "QUESTION"`. The model
always says REASONING, because the arrow ends in the reasoning note. Because
`_validate_draft` is all-or-nothing, the valid `WRITE_MATH` goes too.

The model also invents `scene_slot` names (`reasoning_4n`, `confirmed_pq_meaning`,
`reasoning-note-1`, `reasoning_trail`). The frontend only knows the six slots in
`config/canvasTeachingSceneSlots.json`. It falls back to the reasoning trail for
any other name, so this is harmless, but the prompt should list the allowed
slot ids.

**Smallest fix:** accept `CONNECT` with `zone` REASONING (or ignore `zone` for
CONNECT, since it has no zone-level meaning), and drop failing operations
individually. Either one alone would have put all five notes on screen.

## Advance turns (live, 28 Sep, `4y` on Q-T02-001 → Q-T02-003)

- **Previous question's tokens in the new question's `question_anchors`.** The
  reply that moves to Q-T02-003 lists `Q-T02-001:QTOKEN:2/4/6/8/12` with
  Q-T02-001's offsets alongside Q-T02-003's own tokens. They can never slice
  back to the new text. The frontend now drops foreign-question tokens, but the
  list should only carry the new question's anchors.
- **Confirmation content.** The same reply writes `y → changes` as four
  separate notes (one per `y`) and also `notation → changes`. "notation" isn't
  a changing quantity, so that's wrong teaching content. One note per idea
  would read better.
- Frontend side, fixed: all 15 parts of that confirmation share one
  `confirmed_component_id`, and a dedupe meant for re-confirmation on a later
  turn kept only the first highlight. Every part of a batch now applies, and
  the question is held on screen while they are written.

## Frontend: fixed in this commit

- **Raw LaTeX on the board.** A `WRITE_MATH` in a `handwritten` scene slot
  (every `generic_confirmation`) was drawn as a text mark with the LaTeX
  source. The live `TURN-MANAV-AUDIT-002` plan would have written
  `\frac{c}{d}=c\div d` on the canvas. It now converts simple LaTeX to
  handwriting (`c/d = c ÷ d`, `r × r`, `r²`) and typesets anything else with KaTeX.
- **"Look at the question" did nothing.** 8 of the 9 zone-level
  `FOCUS`/`HIGHLIGHT` operations target `ZONE:QUESTION` ("Which number is
  multiplying x here?"). They drew nothing; now the question strip pulses.
- **Console.** A plan the frontend refuses now logs one
  `[canvas-plan] not drawn: …` line (or `stopped: the scene moved on`) with its
  ids, so the next report can be answered from the console.

## Checked and fine

- The voice server spreads the whole backend response into its frame, so
  voice turns carry the plan.
- `scene_revision` equals `interaction_state_version`, and `source_turn_id`
  equals `accepted_turn_id` on live responses.
- `FOCUS` is `PULSE` in 30 of 32 drafted uses, so a brief pulse is what the
  planner asks for, not a frontend loss.
