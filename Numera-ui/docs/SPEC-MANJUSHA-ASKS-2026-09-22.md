# Spec — Manjusha's three asks of 22 Sep 2026

**Status:** spec only, nothing built. · **Author:** Manav (frontend) · 23 Sep 2026

> "We need to change phase 1, phase 2. We need more tutor writing on the canvas
> with proper explanation and clear presentation (diff ink and simple way)
> similar to phase 4 review. And a small change in phase 0 suggested: question
> changes are not recognizable, like from q1 to 2; I leave it to you how to make
> it understandable for the user that it has changed."

Three asks, three different sizes. In order of what they actually need:

| # | Ask | What it is | Blocked on |
|---|---|---|---|
| 1 | Phase 0: make the question change visible | Frontend only, small | Nothing |
| 2 | Phase 1: more tutor writing, like Phase 4 | Content plus a small frontend change | Sanya's worked-example steps |
| 3 | Phase 2: more tutor writing, like Phase 4 | Content plus one contract field | `docs/PHASE2-CONTENT-CONTRACT-FOR-SANYA.md` |

---

## 1. Phase 0 — the question change is not recognisable

### What happens today

`app/topic-diagnostic/DiagnosticClient.tsx`. The student taps an option, the tutor speaks a transition line, and when the audio ends the next question replaces the current one **in place**: same layout, same option styling, no motion. The only things that change are the counter text ("Question 2 of 8"), one more segment of the progress bar, and the question text. All three are quiet, and the options look identical from one question to the next, so a student mid-thought sees "the same screen" and re-reads.

### Proposed change

Three small signals, all CSS, no new state and no timers beyond what exists.

1. **The question block enters.** Wrap the counter, question and options in a container keyed by `question_id`, with a 0.45 s fade-and-rise animation on mount (the `teach-fade-up` pattern already in `globals.css`). The old question disappears and the new one visibly arrives, rather than the text swapping under the eye.
2. **The counter flashes.** Render the question number as a chip ("2 / 8") that fills highlight-amber for ~0.8 s on mount, then settles to the current quiet style. The number is what tells the student where they are; make it the thing that moves.
3. **Announce it.** A visually hidden `aria-live="polite"` line reading "Question 2 of 8" on the keyed container, so screen readers hear the change too. The existing aria-live paragraph carries the transition message only.

Optional fourth, if 1 to 3 are not enough on the tablet: keep the chosen option highlighted for the whole transition (it already is), and add a one-line label under the progress bar that reads "Next question" during the dwell, replaced by the new counter when the question lands.

### Not proposed

- A full-screen interstitial or a "Question 2" splash. It adds a tap or a wait to a screen whose only job is eight quick answers.
- Changing the transition timing. Sanya asked on 28 Jul for the swap to wait for the spoken line, and that still holds.
- Touching the mock diagnostic. It is mock-only and not a live screen.

### Motion rules

Reduced-motion users get no animation, matching the existing `@media (prefers-reduced-motion: reduce)` blocks. Animations are CSS keyframes, not `requestAnimationFrame`, because the embedded browser pane suppresses rAF (`numera-repos` trap).

### Size

About 20 lines in `globals.css` and 10 in `DiagnosticClient.tsx`. Verifiable with the live diagnostic on a fresh `student_code` (a used one 409s).

---

## 2. Phase 1 — more tutor writing, like Phase 4 review

### What Phase 4 review does that Phase 1 does not

Both use the same engine: `useWorkedExamplePlayer` pacing steps against narration, `TutorLayer` revealing each mark as an ink wipe, `TutorHandOverlay` on the nib. The difference is in `lib/phase4Board.ts` versus `lib/workedExampleSheet.ts`:

| | Phase 4 review board | Phase 1 worked example |
|---|---|---|
| Working | **Accumulates**: each line is added under the last, so the student can check a line against the one that produced it | **One step per sheet**: each step replaces the last (by design, "the steps are separate ideas") |
| Layout | Lines centred as a block, capped gap, size shrinks only when lines would collide | One `screen_content` block per step |
| Ink | Navy only | Navy only |
| Emphasis | None yet | None |

So "similar to Phase 4" means: **accumulate the working down the page, and use a second ink for the thing being talked about.**

### Proposed change

1. **Accumulate by default.** Give the orientation player a `mode: 'accumulate'` that reuses `lib/phase4Board.ts` line placement, so a six-step worked example builds into one board rather than six sheets. Keep `sheet` mode for steps that are genuinely separate ideas (the "Decoding compact notation" example is six unrelated facts and should stay one per sheet). The choice is per worked example, not global.
2. **Different ink per role.** Each step may carry an `emphasis` role from the same vocabulary as Phase 2 (`CHANGE` amber, `FIXED` teal, `CONCLUSION` navy with a box). The renderer maps role to colour; content never sends hex. Without a role, a step writes in navy as today.
3. **Simple way.** Cap the number of lines on one board at what fits at the roomy size (today's `SIZE_ROOMY` and `LINE_GAP_MAX` already do this); beyond that, start a second board rather than shrinking the writing.

### What it needs from content (Sanya)

The orientation bundle's `WORKED_EXAMPLE.steps[]` already has `screen_content` and `narration_text`. Two optional additions per step:

```jsonc
{ "step_id": "S3", "screen_content": "+4 → stays fixed", "narration_text": "…",
  "emphasis": "FIXED",        // CHANGE | FIXED | CONCLUSION | null
  "box": false }
```

and one optional field per worked example: `"presentation": "accumulate" | "sheet"` (default `sheet`, so nothing changes until content opts in).

### Size

Frontend: one to two days, mostly wiring the Phase 4 placement into the orientation player and adding the role-to-colour map shared with Phase 2. Content: re-authoring the "many cases, one rule" worked example as an accumulating board, which is the whiteboard photo Manjusha sent on 23 Sep.

---

## 3. Phase 2 — more tutor writing, like Phase 4 review

Fully specified in `docs/PHASE2-CONTENT-CONTRACT-FOR-SANYA.md` (23 Sep). Summary of what Manjusha's ask maps to:

- **"More tutor writing on the canvas"** is the board script: one trail line per stage of the Phase 2 doc, written on the student's page as the student unlocks it. The rendering exists (`tutor_canvas_actions`, `INSERT_LABEL` / `INSERT_MATH` on `TUTOR_ANCHOR:WRITE_RULE:{n}`); the lines have to be authored per question.
- **"Diff ink"** is the one contract addition: `role` (`CHANGE` / `FIXED` / `CONCLUSION`) on an action, plus `box` for the final rule. Same vocabulary as Phase 1 above, so the student sees one colour language across the lesson.
- **"Proper explanation"** is already the Tutor Solved rung: one authored step per turn, written as ink, narrated, each step ending in a prediction question.
- **"Simple way"** is the rule that the backend never sends coordinates or colours. It names a token or a slot and the frontend lays it out.

Nothing in Phase 2 can show more writing until the board script content exists. The frontend side is ready today except the `role` colour map, which is shared with ask 2 and is the same small change.

---

## Suggested order

1. Phase 0 change (ask 1). Small, unblocked, visible on the next deploy.
2. The shared `role` colour map, so both Phase 1 and Phase 2 ink can carry meaning.
3. Phase 1 accumulate mode, against the "many cases, one rule" example once Sanya re-authors it.
4. Phase 2 board scripts as content lands, question by question.

## Open questions for Manjusha

- Phase 0: is the fade-and-rise plus flashing counter enough, or do you want the "Next question" label as well?
- Phase 1: should accumulate become the default for every worked example, or stay opt-in per example? I lean opt-in, because the notation example reads better one fact at a time.
- Ink: three colours (amber changing, teal fixed, navy conclusion) is what the Phase 2 doc uses. Confirm that is the palette for Phase 1 too, so it is one language.
