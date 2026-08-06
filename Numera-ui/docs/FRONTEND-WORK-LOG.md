# Numera Frontend — What's Been Built

Owner: Manav (frontend)
Covers: 29 Jul – 5 Aug 2026
Status at time of writing: `9bc76fd` on `main`, deployed to `https://nablix.ai/app/`
Verification: **261 tests / 27 files passing**, `tsc --noEmit` clean, production build 38/38 pages

This is the frontend half of Guided Practice Phase 2 plus the voice and reliability
work around it. Each section says what it does and, where it matters, why it is
built that way — the reasoning is usually the part that gets lost.

---

## 1. Guided Practice — Phase 2

### Support ladder (`lib/supportLadder.ts`)

The five rungs, in order:

```
HINT → VISUAL_CUE → SCAFFOLD → PARALLEL_EXAMPLE → TUTOR_SOLVED
```

`availableSupport()` and `nextSupport()` decide what "Need help?" opens next, and
`LADDER_EXHAUSTED` covers the top of the ladder.

The frontend computes **no** pedagogy here — it reads `active_support_level` and
`highest_support_used` from the backend and renders the rung it is told. The ladder
is per-question: carrying `supportShown` across a question boundary would start the
next question at the scaffold and skip the hint the student should get first.

`POST /hint/request` was deleted in the backend's Schema 3.0 refactor (3 Aug), so
the client for it is gone rather than left in place — a dead endpoint that still
type-checks is an invitation to call it. Hints now arrive as the turn message when
`conversation_action` is `GIVE_HINT`.

### Floor control (`lib/tutorSpeech.ts`)

Stops the tutor talking over a student who is writing.

`setStudentWriting(true)` cancels speech in progress; `tutorSay()` **drops** rather
than queues while the student writes — a queued line arrives after the moment it
was about to teach, which is worse than not saying it. `MARK_SETTLE_MS = 700` lets
tutor canvas marks land before the voice describes them.

The critical detail: `onEnd` fires **even when the speech is silenced**. Without
that the voice turn machine never gets its callback and the mic is stranded — the
student can talk but nothing is listening.

### Question rendering (`lib/questionText.ts`, `components/QuestionDisplay.tsx`)

Three layouts, chosen from the text itself: `equation | cases | prose`.

Manjusha asked (29 Jul) for stacked cases to align vertically instead of running
together. The first attempt was inert because I'd matched a format the backend
doesn't send — live it arrives comma-separated on **one line**
(`"3 + 5, 9 + 5, 14 + 5. Use n for…"`). `splitInlineCases()` handles the real
format. Worth remembering: I reported that fixed before verifying it.

### Response ordering (`lib/responseGate.ts`)

Stops an older reply overwriting a newer one when responses race.

Keyed on `interaction_state_version` plus `accepted_turn_id`. It **fails open**:
version defaults to 0 and only increments on turns that mutate pedagogical state,
so consecutive responses can legitimately share a version. With no turn id to
disambiguate, rendering a possible duplicate beats freezing the lesson.

```ts
const turnId = response.accepted_turn_id;
if (!turnId) return true;   // fail open — freezing the lesson is worse
return !applied.appliedTurnIds.has(turnId);
```

Gate state resets on session boundaries (`setSessionId` / `clearSessionId`),
otherwise a new session inherits the last one's version and drops its first reply.

### Scaffold panel

Visibility follows **persisted** `active_scaffold`, not the per-turn event. Reading
it from the event made the panel vanish on the next reply, because that reply served
no new support even though the scaffold was still open.

The panel also moved out of the 234px chat column onto the canvas (Manjusha,
29 Jul) — a guiding question wrapped over four lines there and read as just another
chat bubble.

### Explain Again

Neither an answer nor a help escalation: no attempts, no support progression, no
scaffold changes. Sends `EXPLAIN_AGAIN` and renders what comes back.

Two bugs found and fixed here:

- It blanket-caught every error and silently replayed the held cue, so a 500, an
  auth rejection or a timeout looked identical to success — the student saw the old
  cue reappear and nobody learned the backend had failed. It now falls back only on
  404/405/422 (endpoint genuinely absent) and surfaces everything else.
- It was **invisible**. See §5.

### Inactivity nudge (`lib/inactivity.ts`, `hooks/useInactivityNudge.ts`)

One controller for the whole lesson, on a **single interval**. Independent timers
per input are how you nudge a student who is mid-sentence on one input because
another input's clock expired.

Suppressed while the student is drawing, typing or speaking; while a request is in
flight; while the tab is hidden; while disconnected. Re-checks the gate *after* the
claim returns, since the student may have started working during the round trip.

Presentation is one-way — only the acknowledgement is ever retried. Re-presenting
would say the same line twice for one silence.

**Nothing about the activity is transmitted.** No strokes, keystrokes, partial text,
pointer paths or mic data. The client claims; the backend validates the silence
against its own clock and treats client timing as telemetry.

It stays dormant without a server policy — no local defaults. Inventing a threshold
would interrupt the first student who paused to think, on a number nobody agreed.

---

## 2. Voice

### Half-duplex mic gating

Manjusha reported the tutor and student talking over each other. On the `server`
transport the mic stayed open while the tutor spoke, so Deepgram transcribed the
tutor's own voice and answered it — an echo loop.

```ts
const listening = !micMuted && voiceStatus === 'listening' && !tutorSpeaking;
```

Two signals, not one. `speaking` is set the moment the reply lands, not when audio
starts — those are seconds apart (synthesis + buffering) and the mic was catching
the tutor's opening words in that window.

### Turn rescue (`lib/turnWatchdog.ts`)

`TURN_RESCUE_MS = 45_000`. The voice server has exactly one way to decide the
student stopped talking: Deepgram's UtteranceEnd at `utterance_end_ms=1500`. When
that event doesn't arrive — noisy room, dropped frame, reconnect — the turn never
completes and the student waits forever.

The window is 45s for a specific reason, documented in full at the top of that file:
the server's `stop` handler cancels its Deepgram receiver after 10s, and that task
is what runs the tutor turn when UtteranceEnd *did* fire. Firing early would cancel
a reply mid-flight and break a response that currently works. 1.5s + 40s tutor
timeout = 41.5s, so 45s leaves 3.5s of margin. A test enforces that it outlasts the
slowest possible reply.

### Double transcript bubble

The WS path called `addTranscriptMessage` where the REST path committed in place, so
the partial and the final both stayed on screen — and because Deepgram revises as it
goes, they often disagreed ("How to put this" above "How to do this question?",
Manjusha, 4 Aug). Now `commitPartialTranscript` on both transports.

### Voice consistency

The tutor keeps one voice through a Cartesia outage rather than switching mid-lesson,
and a stale picker choice can't outlive a provider switch.

---

## 3. Reliability and error handling

### Errors name what actually failed

Everything used to fall back to "Sorry — I couldn't reach the tutor just now."
That sentence describes a network problem. A 500, 502 or 422 is **not** a network
problem — the request arrived and the server broke on it — and describing it as
unreachable sends whoever is testing to check the frontend and the wifi while the
fault sits in a service log nobody opened.

Now attributed by status: timeouts (408/504) first, since "took too long" is more
actionable than "hit an error"; 5xx names the service; 429 says wait; 422 says
contract mismatch and that retrying will fail identically. Only a genuinely
incomplete request says "couldn't reach".

The 504 case was initially swallowed by a `>= 500` branch ordered above it — caught
by a test I wrote for exactly that.

### Session start

De-duplicated at **module scope**, not in a ref. A component ref does not survive a
remount, and AuthGate swaps children for a spinner whenever auth state changes. A
screen that starts a session on mount and remounts in a loop fires `/session/start`
continuously — that exhausted the backend's `SESSION001–SESSION999` range on 28 Jul
and 500s every request until the service restarts.

A failed start now says what happened and offers a retry, instead of leaving the
student on a blank canvas with no question and no way out.

### Expired login

A stored-but-invalid token used to fall through to the mock access chain, letting
yesterday's student straight into the lesson where session start then 401'd into a
dead-end card. Expired login now goes to `/login`.

### Canvas submission

Locked while a submission is in flight, and it no longer reports success it can't
confirm.

---

## 4. Sanya's six review points (`74d54a0`)

All six were real. I checked each against the code before touching anything.

| # | Issue | Why it mattered |
|---|-------|-----------------|
| 1 | Text + Explain Again sent no `turn_id` | Backend had nothing to dedupe on; a retry was indistinguishable from a second answer. Added `beginSubmissionTurn()`. |
| 2 | Explain Again bypassed the ordering guard | A cached replay keeps its original version, so re-pressing rendered the same reply twice. |
| 3 | `SYSTEM` / `INACTIVITY_NUDGE` / `NUDGE_PRESENTED` missing from types | Keeping `SYSTEM` distinct from the student stops a nudge counting as a learner interaction downstream. |
| 4 | Inactivity rules existed but nothing fed them | Dead code. Now mounted on the lesson. |
| 5 | `PRESENTED_UNACKNOWLEDGED` counted in learner history | Until the backend confirms, the two sides disagree that the turn happened. Narrowed to `PRESENTED`. |
| 6 | Explain Again swallowed real failures | See §1. |

---

## 5. 5 August — Sanya's live test

### "I can't see the Explain again button"

Not a state bug. `TeachBack` pins "Explain it back" to `top-[22px] right-[34px]` at
**z-20**; the question strip is `top-[26px] right-[34px]` at **z-10** with
"Explain again" at its right end. Same corner — TeachBack won the z-index and the
button rendered *underneath* it.

The strip now reserves 150px. "Explain it back" measures **131px** with the app's own
stylesheet, so that clears it with 19px to spare. It also stops a long question
running under that button.

My first attempt at this was a real fix to the wrong thing: the button had also been
gated on a visual cue having arrived, so it only appeared after the student climbed
the ladder as far as `VISUAL_CUE`. That gate made sense when `EXPLAIN_AGAIN` didn't
exist on the backend and the only thing the button could do was re-show a held cue.
It exists now, so the control needs only a tutor turn to replay. Both changes are in,
but the overlap was the reason she couldn't see it.

### "The tutor starts speaking randomly if you don't type"

`presentInactivityNudge` called `tutorSay()` and nothing else — the nudge was
**spoken but never written to the transcript**. The tutor's voice arrived with
nothing on screen accounting for it, and nothing to scroll back to. Fixed; a line
the student can see is a nudge, a voice alone is an interruption.

### Open: four identical nudges

The per-turn cap is 2 and four appeared, so either the counter is being reset or a
second controller is mounted. I could not determine which from the code — nothing
visible writes `lastTutorTurnId` on the nudge path. Rather than guess, each claim now
logs its controller id and count:

- two different controller ids → double mount
- one id counting past 2 → the reset

Reproduce with the console open and it will be sitting there.

---

## 6. What I did not build

PR #65 (merged by Sanya, 5 Aug) shipped the nudge claim/present/acknowledge wiring
and policy adoption. I had independently written the same thing and **discarded
mine** on discovering it. `986e184` onwards is only the two fixes above on top of
her implementation.

---

## 7. Open items for the backend

Nothing here is a frontend fix.

1. **Nudge threshold is 20s** (`guided_learning.py:86`, from the last tutor
   response). That is ordinary thinking time on a maths problem, so the tutor
   interrupts a student working it out in their head. With `cooldown_ms: 30_000` and
   2 per turn it can fire twice in the first ~50 seconds. Pedagogy call, not mine.
2. **`_contextual_nudge_message` returns a fixed string**, which is why all four
   nudges were word-for-word identical. Repeating one sentence isn't four nudges.
3. **Anonymous session start is dead** (`SESSION_OPENED` 401), which blocks
   unauthenticated smoke tests.
4. **`student_code`** — JWT `sub` is a user id, not `ST###`, so the hardcoded `ST001`
   cannot be replaced without a backend change. It is a known-wrong value for any
   real student and 403s `STUDENT_FORBIDDEN`.
5. **VM auto-shutdown at midnight IST** still costs a deploy window most days.

Full gap analysis: `docs/PHASE2-GUIDED-BACKEND-ASKS.md`.

---

## 8. Modules added this cycle

| File | Purpose |
|------|---------|
| `lib/tutorSpeech.ts` | Floor control — who may talk |
| `lib/supportLadder.ts` | The five support rungs |
| `lib/responseGate.ts` | Response ordering, fails open |
| `lib/inactivity.ts` | Nudge rules, pure functions |
| `lib/questionText.ts` | Question layout detection |
| `lib/turnWatchdog.ts` | Voice turn rescue |
| `hooks/useInactivityNudge.ts` | The one live controller |
| `components/QuestionDisplay.tsx` | Three question layouts |

Plus 10 test files. The rules live in pure functions so every branch is checkable
without timers or a browser.

---

## 9. Deploy

Static export, `basePath=/app`, nginx at `https://nablix.ai/app/`.

`NEXT_PUBLIC_*` is inlined at **build** time — a build missing
`NEXT_PUBLIC_API_BASE_URL` silently runs on mock data. There is now a guard screen
for that rather than a lesson full of fake content.

```bash
EXPORT_BASE_PATH=/app NEXT_PUBLIC_API_BASE_URL=https://nablix.ai/api npm run build
tar czf - -C out . | ssh -i ~/Downloads/Nablix-Dev-Ubu_key.pem \
  developer@74.162.34.219 'tar xzf - -C /var/www/numera/app'
```

Students must hard-refresh — the export caches.

---

## 10. Verification standard

Every change above is covered by `tsc --noEmit`, the vitest suite, and a production
build before it ships. Live behaviour that needs a real microphone (the echo fix) is
still unconfirmed — it is correct by construction and by test, but nobody has heard
it work.

Two things I got wrong that are worth keeping in mind: I reported the alignment fix
to Manjusha before verifying it against what the backend actually sends, and I fixed
the Explain Again *condition* before finding the real cause was the *overlap*. In
both cases the code reading was right and the assumption about the environment was
wrong. Logs and screenshots first.
