# End-to-end verification — 26 Aug 2026

Run against **https://nablix.ai/app/** in a real signed-in session
(`ST015`, `SESSION04b34eb3…`, Phase 2 `GUIDED_PRACTICE`, topic `ALG_LINEAR_ONE_STEP`),
driving the live UI with Playwright and reading the live session record and
request payloads. Not a status-code sweep — every claim below was produced by
doing the thing on the deployed build.

Frontend: `npx tsc --noEmit` clean, **912 tests pass** (94 files).
Deployed: build of 26 Aug, chunk `8124-546fd947348fc34f.js` serving 200.

---

## 1. The headline: the canvas loop works end to end

Wrote `n + 4` by hand on the live canvas and pressed **Check**:

| Stage | Result |
|---|---|
| Payload built by the frontend | 6 strokes, 86 points, **10 canvas events, `order_index` 0–9 contiguous** |
| `POST /canvas/submit` | **200 `processed`**, `tutor_turn_id` returned |
| Mathpix OCR | `raw_ocr_text: "n+4"`, `detected_equation: "n+4"`, **confidence 1.0**, MathML emitted |
| Canvas memory | stored under `Q-T01-004` |
| Tutor annotation | red ellipse drawn **on the student's writing** — region `x 0.102, y 0.255, w 0.524, h 0.357`, which is exactly where the ink is |
| Tutor reply | "Which option represents every possible starting value?" |
| `POST /voice/tts` | 200 with audio |

The `order_index` contiguity contract that `validate_canvas_event_order` enforces
holds on live traffic. This is the first time the round trip has been confirmed
against the real backend — it was blocked on auth in the last pass.

**Auth is no longer blocking.** `student_code` now arrives (`ST015`) and
`GET /session/{id}?student_id=ST015` answers 200. The 401/403 that killed
`/session/start` last time did not reproduce. Note the JWT `sub` is still a
user id (`556`), not an `ST###` — the mapping now works, the shape is unchanged.

---

## 2. Two frontend defects found and fixed (deployed)

Commit `7b4503a`.

### 2.1 The tutor's markdown reached the student as characters

Asked to explain its answer, the tutor replied:

> can you explain why `**n + 4**` works for any starting value?

The chat rendered the asterisks. The emphasis lands on the mathematical object
the tutor wants looked at, which is the one part that must not arrive looking
like syntax. The same string is handed to TTS, so the markers were also going
to the speech engine.

Fixed: chat bubbles and the session trail now render the emphasis; speech is
given the words alone. Only `**bold**` is handled — it is the only marker the
tutor emits.

### 2.2 Two canvas controls were visible and unclickable

The paper-style and canvas-help FABs sat underneath the "Need help?" Nablix
Assist launcher. Both are `bottom-6 right-*` in the same corner and the pill
wins on z-index. Measured at 1440×900: the pill covered 24–74px up from the
bottom edge, the FABs sat at 24–64px, and `elementFromPoint` on either one
returned the pill.

Fixed and **re-verified live after deploy**: both FABs now sit at y 774 and
each hit-tests to itself.

---

## 3. Backend findings — for the owners

### 3.1 An unreadable canvas fails the whole submission (Chiru)

`POST /canvas/submit` answers **503 `ADAPTER_UNAVAILABLE`** with
`error_info={'id': 'image_no_content'}` whenever the OCR provider finds nothing
legible. Established by controlled experiment, not inference:

| Image sent | Result |
|---|---|
| Two zigzag scribbles, 2396×1800, transparent bg | 503 `image_no_content` |
| Same scribbles flattened onto white | 503 `image_no_content` |
| Same scribbles at 400×301, 800×601, 1200×902, 1600×1202, 2000×1503 | 503 at **every** size |
| Blank white page, 2396×1800 | 503 `image_no_content` |
| Legible "n + 4", 400×200 | **200 processed** |
| Legible "n + 4", 2396×1800 | **200 processed** |

Not size, not transparency, not encoding — purely whether the image contains
readable content. So a student who taps Check with a doodle, a stray mark, or
an accidentally blank canvas gets a hard service error. **"OCR read nothing"
is a normal tutoring outcome, not an adapter outage** — it should come back as
a 200 the tutor can respond to ("I couldn't read that — can you write it a bit
larger?"), not a 503.

The frontend degrades correctly today: the ink is kept, the toolbar re-enables,
and the chat says "The tutor service hit an error on its side." But that copy
is wrong for this case, and the frontend cannot tell the difference from a
generic 503.

### 3.2 `show_scaffold_panel: true` with nothing behind it (Chiru / Sanya — row 21)

Live session record right now:

```
show_scaffold_panel:        true
scaffold_id:                null
current_scaffold_step_id:   null
scaffold_total_steps:       0
delivered_scaffold_step_ids: []
```

The flag is on; there is no step to show. The frontend renders nothing rather
than an empty panel, which is the correct degradation — but this is why
scaffolding "isn't appearing". Either send the step with the flag, or don't
raise the flag.

### 3.3 `per_question_history` is empty after 7 attempts (Chiru — row 17)

Live session: `attempt_count: 7`, `hint_count: 2`, `canvas_submissions: 1`,
`per_question_history: []`. This is the exact precondition for the un-endable
session already logged as row 17 — worth confirming whether the auto-transition
to REVIEW still skips the check.

---

## 4. Row-by-row status — Manav's items

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Tutor writing on canvas, Phase 2 | **Working** | Tutor drew its annotation on the student's handwriting, positioned from the OCR region |
| 2 | Content approver frontend | **Ready, waiting on backend** | Portal on the v3 contract, all 15 screens on mock data; endpoints not built |
| 3 | Hint sticky note | Verified | `components/HintNote.tsx` |
| 4 | No initiation message P2/P3 | Verified | `lib/phaseHandoff.ts` + tests; live session spoke "Let's resume with this question…" |
| 5 | Tutor voice exhausts mid-session | **Not confirmed either way** | `/voice/tts` 200 on every turn in this run; needs a long session to reproduce. Aditya's half |
| 6 | Utterance drop-off | **Not confirmed either way** | Same — needs sustained voice traffic |
| 12/13 | Student / parent dashboard | Not started | Low priority, no endpoint |
| 21 | Scaffolding positioning | **Blocked on backend** | See §3.2 — the flag arrives without a step |
| 22 | Hints titled as visual cues | Fixed | `lib/cueLabel.ts` — labels by `cue_id`, which is what distinguishes an authored cue from the tutor's own words |
| 23 | Option click passed to tutor | Verified live | Tutor: "You selected option B, which is good!" |
| 24 | Options missing in Phase 3 | Fixed | `app/practice/page.tsx:318`; options render live |
| 31 | Phase-2 resume line not voiced | Verified live | Line spoken, `/voice/tts` 200 |
| 32 | Canvas cleared on next question | Fixed | `store/__tests__/backendPhase.test.ts` |
| 33 | "Explain it back" was a local mock | Fixed | Sends `TEACH_BACK_SUBMISSION` to `/interaction` |
| 34 | Session validation / JWT | **Passing now** | `student_code` arrives, session calls 200. See §1 |
| 37 | Orientation video / tutor voice overlap | Fixed | Line completes, *then* the video starts; pressing play hushes the tutor |
| 38 | "Explain again" — browser voice, then real TTS | **Working as designed — needs a decision** | The acknowledgement uses the browser voice deliberately, so it starts on the click instead of after a TTS round trip. If the two-voice effect is unacceptable it is a one-line change — Manjusha's call |
| 42 | "Linear equations" hardcoded in Review | Fixed | Header reads "Review & feedback / today"; falls back to the date when the backend sends no title |
| 44 | Worked examples — resume / start again | **Code present, needs retest** | Previous / Pause-Continue / Next / Start again / Skip all wired; could not reach the screen (session past that phase) |

### Also verified live, unrelated to a row

- **Dock no longer covers the canvas toolbar.** All ten drawing controls plus
  Check hit-test to themselves.
- **Key Notes page-turn control is reachable.** Scrolled to the bottom: pager
  at y 710–746, fully in view, hit-tests to itself.
- Review, Workbook, History, Key Notes: layout clean at 1440×900, no horizontal
  overflow, dock clear of content on every one.

---

## 5. What is not covered

- **Voice exhaustion and utterance drop-off (rows 5, 6)** need a long live
  session with sustained speech. One pass of scripted turns will not reproduce
  them.
- **The markdown fix is unit-tested and shipped** (the regex is confirmed in the
  deployed bundle) but the tutor's replies during the post-deploy pass carried
  no emphasis, so the rendering was not observed on the live site.
- **Orientation and Phase 1** screens were unreachable — the test session is
  past them and phase routing correctly pushes back to the lesson.
