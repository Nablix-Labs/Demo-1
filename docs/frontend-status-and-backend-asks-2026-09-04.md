# Frontend status & backend asks — 4 Sep 2026

**From:** Manav (frontend)
**For:** Sanya and Chirudeva
**Covers:** the guided rescue work shipped today, one live backend fault we hit
while verifying it, and what Phase 4 needs to match the new design.

Everything below is deployed to `https://nablix.ai/app/`.

---

## Part 1 — Guided rescue: shipped

Chirudeva's 4 Sep note asked for rescue to be treated as an exclusive mode. It
is, and it is live. Nothing here needs backend work — this section is so you
know what the client now guarantees, and which of your fields it now depends on.

**What changed**

1. **One rescue implementation at a time.** When `tutor_canvas_actions` carries a
   usable rescue action, the stepwise component renders and `guided_rescue`
   stands down. The client used to render both, on the written assumption that
   you never send both at once — the duplicated panels were that assumption
   failing. It is now a rule the client enforces rather than a hope.
2. **The rungs above a rescue are cleared** when one opens — hint, visual cue,
   write instruction and scaffold — once, on the first step, so a hint picked up
   between step 1 and step 2 survives.
3. **One child-facing chat message** on a rescue turn. `support_message` no
   longer reaches the transcript; rescue content lives in the panel and on the
   canvas.
4. **Every new rescue step is spoken, exactly once**, after its visual renders,
   keyed on `action_id` so reconnects and re-renders cannot replay it. This was
   the silent "Let me show you": there was no speech call anywhere on the rescue
   path at all.
5. **Normal submission is blocked while a rescue is on screen** — chat and voice
   both, with "Follow this example, then tap Next step." No `/interaction`
   answer is sent, so nothing re-evaluates the original question or re-opens the
   scaffold.
6. **Next step** sends exactly one `rescue/advance`, disables while pending,
   replaces the visible step, and speaks the new one.

**Two fields of yours that this now depends on**

- `RescueStepResponse.completed` — **we now read it.** It had existed since the
  endpoint shipped and was read by nothing. It is what ends a walkthrough:
  inferring the end from `step_index === total_steps` is impossible when
  `total_steps` is null, which left those rescues offering "Next step" forever
  with no way back. Please keep sending it.
- `rescue_id` on every rescue action. An action without one renders nothing and
  is logged as unusable — it cannot be acknowledged, advanced or superseded.

**Canvas ink for tutor-solved steps** is now width-bounded and wraps. Long
authored steps were being drawn as a single line that ran under the rescue panel
and was clipped mid-word. No change needed from you — but it does mean a
sentence-length `text` renders as two or three lines rather than running off the
board, which is worth knowing when authoring them.

**Verified in the browser against the deployed build**, not just in tests: one
panel, one transcript message, one TTS request per step, one advance request per
press, chat and mic both inert during a rescue.

---

## Part 2 — A live fault we hit, which is yours

While verifying the above on `nablix.ai/app` this afternoon, guided practice
broke in a way that is not frontend:

```
POST /api/interaction  →  500 Internal Server Error
POST /api/interaction  →  409 Conflict
(after that: the session stops issuing /interaction at all)
```

Session: `SESSION99918a95b9f34858aacf03a3ba594d01`, topic ALG-ORI-01,
phase `GUIDED_PRACTICE`, around 12:45–12:50 UTC on 4 Sep.

The 500 body still carries a `message` field — `"Something went wrong. Please
try again."` — so from the wire it looks like a normal reply until you check the
status. The client discards it correctly.

The 409 that follows is the guided-practice turn conflict we have hit before
(the one `cad2484` used to fix, reverted 31 Jul). Once it fires, the session is
effectively dead: typing produces no further request at all, and only a reload
recovers.

Twenty-five backend commits landed on the guided evaluator today, so this may be
new. Flagging it rather than diagnosing it — **this blocks any rescue or review
testing on the VM**, ours and yours.

Two smaller notes from the same session, both of which look intentional but are
worth confirming:

- `rescue/advance` and `rescue/render-ack` both return **409** for a `rescue_id`
  the backend does not know. That is correct behaviour and our button now
  recovers from it — noted only so nobody chases it as a bug.
- **"Explain again" does not apply `tutor_canvas_actions`.** Its reply carries
  them and the client ignores them on that path. If Explain Again is ever meant
  to re-render support, tell us and we will wire it; right now it is silently
  dropped and I would rather that were a decision than an oversight.

---

## Part 3 — Phase 4 review: the new design

The Phase 4 screen has been rebuilt to the 4 Sep mockup and is deployed. You can
see it **without logging in and without any backend**:

> **https://nablix.ai/app/dev-screens/phase4**

That route is a fixture. It renders the target design with placeholder data, so
you can check the asks below against the thing they are for. The checkbox at the
top switches to the "every question correct" path (§8.8).

**What is already built and needs nothing from you:** the three-column layout,
the header chips, the question rail with three statuses and a legend, the Live
header, the work-snapshot panel, the transport bar, the stage strip, and all five
feedback cards.

**Everything new is optional and degrades.** A payload with none of the fields
below renders exactly what shipped before — no blanks, no throws. That is
deliberate: a missing field has become a live outage here more than once, so
nothing on this screen requires a field to exist.

### The asks, shortest first

Full detail, with a complete example payload, is in
`docs/phase4-review-mockup-backend-asks-2026-09-04.md`. Summary:

| # | Field | Where | Why we cannot derive it |
|---|---|---|---|
| 1 | `question_journey[].skill_label` | rail row | Truncating the prompt gives "Which is the general rul…", which names nothing |
| 2 | `evaluation: "PARTIAL"` | rail row | A middle state is a grading judgement; we hold no score or rubric |
| 3 | `first_error.why_it_matters` | card | Subject-matter explanation — we would be writing maths content |
| 4 | `error_pattern {signature, occurrence_count}` | card | We only receive this session's wrong submissions; "same error" is not a string match |
| 5 | `topic_outcome.next_action_message` | card | Personalised on progress — templating it is the client asserting how well they did |
| 6 | `replay_steps[].stage_label` | stage strip | Five hardcoded names lie when a replay has three steps or seven |
| 7 | `replay_steps[].duration_ms` | transport | Without it there is no honest clock or scrubber |
| 8 | `work_artifact.snapshot_image_url` + `error_regions[]` | work panel | We have the strokes, not which of them are the error |
| 9 | `replay_steps[].board` | centre board | See below |

**On (9), the board.** This is the only ask that is a new contract rather than an
extra string, and the only part of the design not yet built. The mockup's centre
has labelled arrows, two braces, a struck-through `n × 4` in red and a boxed rule
in green. Today each step gives us one flat string (`tutor_write`), which renders
one line of handwriting. To produce the diagram from what we have, we would have
to parse `"n × 4"` out of the narration and infer which expression is the wrong
one — reverse-engineering the tutor's explanation from its own prose. That is the
same class of client-side re-decision that produced the duplicated rescue panels
in Part 1. A typed element set is proposed in the detailed doc; the existing
one-line rendering stays as the fallback, so it can land incrementally.

**Two places we chose honesty over matching the mockup pixel-for-pixel**, and you
can see both on the fixture route by pressing "Continue review":

- Replay 1 has durations and stage labels, so it shows `0:00 / 1:48` and named
  stages. Replay 2 has neither, so it shows numbered steps and **no clock**.
- The bar under the board is a progress indicator, not a scrubber. Dragging
  implies a seek that needs per-step timings we may not have.

Both upgrade automatically when the fields arrive — no frontend release needed.

### Five questions we need answered

1. **Is "Live" actually live?** The panel says "Tutor is explaining in real
   time". Today replays are pre-authored and performed client-side. If that is
   what "Live" means, there is no backend work. If steps are meant to *stream*,
   that needs a contract, ordering guarantees and a reconnect story — the same
   machinery as stepwise rescue. We have built the first and want to be told
   before scoping the second.
2. **Does `PARTIAL` get a tutor replay?** Right now the client gives it none, on
   the §3 rule that replays follow a wrong submission and nothing else. That is
   the conservative reading, not a decision.
3. **Are the five stages fixed for every replay, or per-replay?** If fixed, send
   them once at review level and we will map steps onto them.
4. **Does the proposed board vocabulary cover Topic 1?** The names do not matter
   to us; a *closed, typed* set does, because an open one puts layout decisions
   back on the client.
5. **`duration_ms` only, or pre-rendered audio + caption cues?** Recommendation:
   `duration_ms` first. It unlocks the clock and progress with no new
   infrastructure. Real captions are a bigger piece and deserve their own
   decision rather than being a hidden dependency of this screen.

---

## Part 4 — Standing asks, unchanged

- **`/nablix-auth` and the student-model token.** The anon bearer still fails at
  student-model on the first *correct* answer (`AUTHENTICATION_FAILED`, from
  `nablix.ai:8080` rejecting the placeholder). Frontend already maps that code to
  sign-in copy rather than "couldn't reach the tutor", but no frontend change can
  satisfy it.
- **Please tell us before renaming an enum or dropping a field.** Everything we
  read is now defensive and degrades rather than throwing, but a rename still
  turns a working card into a blank one, and we usually find out from QA.

---

## What we are waiting on, in priority order

1. The `/interaction` 500 + 409 in Part 2 — blocks all testing on the VM.
2. Answers to the five questions in Part 3.
3. Phase 4 fields 1–5 (five small text/enum fields, three cards and the rail).
4. Phase 4 fields 6–8.
5. The board contract (9).

Nothing in Part 1 is blocked. Everything in Part 3 is built and waiting for data.
