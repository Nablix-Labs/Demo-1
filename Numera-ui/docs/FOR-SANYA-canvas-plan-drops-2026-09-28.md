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
