# Open backend issues — 22 August 2026

From Manjusha's Topic 1 session this evening (6:30–6:38 PM), traced against the
frontend before being filed here. Frontend faults found in the same pass are at
the bottom, with what was done about them, so this reads as one triage rather
than a list of other people's problems.

Owners: **Chirudeva** (orchestration, session/turn state), **Sanya** (tutor
engine, wording, canvas actions), **Aditya** (voice pipeline, streaming server).

---

## 1. The tutor cannot see the canvas, so it re-asks the same question

**Owner: Aditya** (transport decision), then whoever reads the snapshot.
**Severity: high — this is the one the tester actually hit.**

Manjusha wrote `n + 5` on the canvas, said *"I fully written that in the Canvas.
Please check the Canvas."*, and the reply was the question she had just answered,
repeated almost verbatim:

> You've identified the fixed part as 5, which is great! Now, can you write the
> general rule for this si…
>
> **YOU:** I fully written that in the Canvas. Please check the Canvas.
>
> You've identified the fixed part correctly as 5! Now, can you write the general
> rule for this situation using n?

**Frontend half, confirmed and owned by us:** on a voice turn the canvas is never
sent at all. `sendCanvasSubmission` exists in `hooks/useWebSocket.ts` and is
returned from the hook, but `app/page.tsx` destructures only `sendAudioChunk` and
`sendControl` — nothing in the app calls it. The canvas reaches the backend by
exactly one route: tapping **Check**, which goes over REST
(`useDemoTutor.submitCanvasWork` → `/canvas/submit`). A student who writes and
then *speaks* has submitted nothing.

This matches what Aditya found independently from the server side: the canvas
branch never runs, because the snapshot is expected on the `stop` frame and the
lesson client never attaches one (only teach-back does, via a different API).

**What we need from Aditya before wiring it:** which transport is the real one.

- `canvas_submission` is already in this hook's documented out-schema, so
  wiring it up invents nothing — but it is not what the server's canvas branch
  reads.
- The `stop` frame is what the server reads, but on the Flux path the client
  only sends `stop` from the watchdog rescue; Flux reports end-of-turn itself.
  So there is no ordinary `stop` to attach a snapshot to.

Pick one and we will wire it the same day. Guessing risks shipping a build where
the canvas still is not read, which is indistinguishable from today.

**Also worth deciding (Chirudeva):** whether a spoken *"check the canvas"* should
force a canvas read. Right now nothing connects the sentence to the action.

---

## 2. `"Tutor unavailable. Please try again."` collapses five failures into one string

**Owner: Aditya.** Carried over from 21 Aug; re-confirmed, not yet fixed.

`streaming_server.py:963`, a blanket `except Exception` around the whole turn.
Five unrelated causes produce the identical message: a non-200 from
`/voice/transcript`, the 40s timeout, a missing `turn_id`, a canvas-submit
failure, and a plain network blip. The string cannot distinguish them, which is
why it keeps being re-triaged from scratch.

The canvas branch is ruled out (see §1 — it never runs). The candidate with
history is the missing `turn_id`: the server latches it off a text frame and
clears it after each turn, and that failure was 11-for-11 on the VM on 7 Aug
behind this same string. The frontend side is done — `sendTurnContext()` is
paired with every `beginListeningTurn()` at all eight sites, and warns when a
frame is dropped on a closed socket.

**Ask:** distinct codes per branch. Anything is better than one string.

---

## 3. Replies are slow, and the tutor call is now the whole budget

**Owner: Aditya to measure, Sanya if it is the engine.**

Manjusha, on the question arriving: *"It came after some time."*

Aditya's own numbers: the tutor call is 2.8–11.4s and is the slowest thing left
in the pipeline. His correction to the earlier budget matters here — the 4.5s
silence fallback is **Nova-3 only**; on the Flux path there is no silence timer
at all and detection is under a second. So on Flux the latency is the tutor call
and nothing else.

Two consequences:

- `TURN_RESCUE_MS` at 60s is sized for a path we are moving off. The 40s timeout
  stands; the 4.5s does not.
- Nobody should conclude anything until the **p90 of the tutor call** is
  measured. 2.8s and 11.4s are very different products and the range spans both.

**Frontend note:** the 700ms `MARK_SETTLE_MS` delay before narrating a mark is
not a contributor at this scale, and is deliberate.

---

## 4. Phase 4 review contract — four fields still missing

**Owner: Chirudeva.** Unchanged from the earlier ask, still open. The review
arrives on the session record rather than its own endpoint, and four fields the
frontend renders are absent.

---

## 5. Canvas rescue presentation — two unresolved items in the 22 Aug handoff

**Owner: Chirudeva.** The renderer half is built (flag off by default,
`NEXT_PUBLIC_CANVAS_RESCUE_PRESENTATION`). Two things block turning it on:

1. **No transport for `RESCUE_STEP_ADVANCE` or the renderer acknowledgements.**
   The handoff fixes both bodies exactly but not where they go — no endpoint, no
   agreed frame name. They currently go out over the voice socket as
   `rescue_step_advance` / `rescue_render_ack` and will be ignored by a server
   that does not know them. Nothing breaks; the step simply does not advance.
2. **`TUTOR_ANCHOR:ORIGINAL:<question_id>` does not resolve.** It appears in the
   handoff as a `return_target_object_id`, but it is not a shape `resolveTarget`
   knows, so it cannot be focused. It is queued and retried rather than dropped,
   per §4, but it will never resolve until we agree what that id points at.
   `TUTOR_ANCHOR:WRITE_RULE:<q>` from the tutor-solved example does work.

**Also flagged (Sanya):** the reveal safety rule has five conditions, of which
the renderer can only check three (type, mode, final step). That
`approved_answer_reveal` was supplied and that `text` is exactly
`current_step_text` are facts the client cannot see and remain guaranteed
upstream. A payload that asks to reveal without satisfying the checkable three
renders as an ordinary step and logs loudly.

---

## 6. Student code still shows as TC 001 / ST001 after refresh

**Owner: Chirudeva.** The JWT `sub` is a user_id, not a `ST###` student code, so
the frontend has nothing to resolve the real code from and the hardcoded value
cannot be removed without a backend change. Reported repeatedly by testers as a
frontend bug; it is not.

---

## Frontend faults found in the same pass — fixed here

**A. The tutor went permanently silent after the student wrote on the canvas.**
`setStudentWriting(true)` fires on pen-down (§1, "remain silent while the student
writes"). The only things that ever cleared it were the Check button, Explain
Again, and loading a fresh question — none of which a student answering by voice
touches. So writing and then speaking left it stuck `true`, and `tutorSay` drops
every utterance while it is: the tutor rendered text it never spoke, for the rest
of the question. This is very likely Manjusha's *"after tutor writing something
breaks from frontend, it's not listening"*.

Fixed: a student `transcript_final` now hands the floor back, on the same
reasoning Explain Again already uses — a student talking to the tutor is not
mid-stroke. Regression test in `lib/__tests__/tutorSpeech.test.ts`.

**B. The canvas is never submitted on a voice turn.** Frontend half of §1 above.
Not fixed pending the transport decision, because the two candidate wire formats
would ship differently and only one of them works.

---

# Addendum — 24 August 2026

From reading the connected-evidence work (`b99daa4`) against the frontend.

## 7. `MIXED` is not on the wire, and the handoff reads as if it is

**Owner: Sanya.** Not broken — a documentation trap, filed before someone hits it.

The handoff introduces `MIXED` as an input source "used when the same accepted
turn contains multiple evidence sources, such as voice plus canvas". `MIXED` was
added to `ai_engine/schemas.py:68` only. The wire enum is still
`TEXT|VOICE|CANVAS|CHOICE|SYSTEM` (`models/fields.py:94`), so a client that
follows the handoff literally 422s every answer before the tutor sees it.

The frontend therefore keeps sending `TEXT` / `VOICE` and lets `canvas_state`
carry the evidence. If `MIXED` is meant to reach the wire, `models/fields.py`
needs it too and orchestration needs to accept it; if it is meant to stay
internal and be derived server-side, the handoff should say so.

## 8. Every canvas-bearing turn now costs an OCR pass

**Owner: Aditya to measure, Chirudeva if it needs a cache.** New, and caused by
our fix — flagged rather than left to be discovered.

Attaching `canvas_state` to typed answers and hint requests (§1's frontend half,
now done) means `collect_canvas_evidence` runs the vision adapter on those turns
too. `snapshot_store.build_reference` keys on `submission_id`, not on the image,
so an unchanged board is re-OCR'd on every turn that mentions it.

This matters because of §3: the tutor call is already p90 17.8s, and OCR is now
in front of it on more turns than before. It is still the right trade — the
alternative is the tutor being blind, which is the bug we started from — but if
the p90 moves, this is the first place to look. A content hash on the snapshot
would make repeat reads free.

## 9. Where the frontend now stands on the connected-evidence handoff

For the record, so nobody re-files these:

- **Evidence attached to typed and voice turns** — done (`6e446b8`), with the
  413 limits in `canvas_evidence.validate_canvas_payload` mirrored client-side
  and trimmed events renumbered to satisfy `validate_canvas_event_order`.
- **Token / span / whole-line target rendering** — no frontend change needed.
  `plan_canvas_draw` resolves all three into one normalised box before the wire;
  `TutorElement` is untouched by `b99daa4`. The existing renderer already draws
  it and the box simply gets narrower.
- **Separate tutor / support / student layers, student ink never mutated** —
  already true and unchanged.
- **Queue rather than drop an action whose target is missing** — already true
  (`pendingRescueActions`, capped at 12).
- **OCR regions, spatial tokens, token ids, character spans** — not ours to
  send. Chirudeva owns these; the frontend supplies the snapshot, strokes and
  ordered canvas memory, and the backend derives the rest.
