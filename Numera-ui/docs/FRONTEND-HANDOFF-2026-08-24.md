# Frontend handoff — 24 August 2026

Canvas evidence, voice turns, and the canvas rescue presentation.

Written after implementing the frontend half of the **Connected Tutor Evidence**
handoff (`b99daa4`) and the **Canvas Rescue Integration** handoff, and reading
both against the backend rather than against their prose.

Shipped on `main`:

| Commit | What |
| --- | --- |
| `0a2c2b6` | pen-down no longer strands the student's microphone |
| `525a02c` | canvas sent on a **voice** turn |
| `6e446b8` | canvas sent on **typed** turns and hint requests |
| `1d54f49` | addendum to the 22 Aug backend issues |

900 tests pass, `tsc` clean, build compiles. **Not yet deployed — the dev VM
(74.162.34.219) has been unreachable since last night**: 100% packet loss, SSH
times out, `https://nablix.ai/app/` returns nothing. The build is made and
waiting. Whoever can restart it, please do — everything below is on `main` but
none of it is in front of a tester until then.

---

## 1. The tutor could not see the canvas on most turns

**This is the one Manjusha hit**, and it was bigger than it looked.

She wrote `n + 5`, said *"I fully written that in the Canvas. Please check the
Canvas."*, and was read back the question she had just answered.

Whether the tutor can see the board is decided by one field on the interaction
request:

```
canvas_state present
  → collect_canvas_evidence runs OCR        (interaction_service.py:277)
  → has_canvas_evidence = True              (interaction_service.py:3282)
  → review_canvas_math runs                 (classifier.py:4880)
  → mistake classified, target narrowed     (canvas_annotations.plan_canvas_draw)

canvas_state absent
  → review_canvas_math returns None, immediately
  → no canvas review, no classification, nothing to point at
  → the tutor answers as if the board were blank
```

The frontend was sending `canvas_state` from **one of eight** `/interaction`
call sites — the REST voice turn. Typed answers, hint requests and explain-again
all omitted it. That is every turn a student takes with the keyboard.

Fixed in `525a02c` (voice, over the socket) and `6e446b8` (typed + hints). It is
now built in one place, `lib/canvasEvidence.ts`, so "which turns carry the
canvas" has a single answer instead of eight.

**Two limits had to be mirrored client-side, because attaching evidence
everywhere is what makes them reachable.** Both are in
`canvas_evidence.validate_canvas_payload`:

- **>10,000 stroke points → 413.** Trimmed to the newest whole strokes. The
  snapshot still shows everything, so an over-full board loses the precision to
  circle a symbol in the earliest lines, not the ability to be read. Whole
  strokes only — a truncated stroke puts a spatial token on geometry that stops
  mid-symbol, which is worse evidence than omitting it.
- **>500 canvas events → 413**, *and* `validate_canvas_event_order` separately
  requires `order_index` to be contiguous **from zero**. Trimmed events are
  renumbered. Keeping their original indices would have been a 422 arriving
  suddenly, late in a long question, looking nothing like a size problem.

The pre-existing voice path had the first of these already and was one busy
canvas away from failing every spoken answer.

A blank board now sends nothing rather than an empty `canvas_state` — an empty
one still sets `has_canvas_evidence`, which runs OCR over nothing and invites the
tutor to comment on working that does not exist.

---

## 2. Sanya — `MIXED` is not on the wire

**Not broken. A trap in the handoff, filed before someone hits it.**

The connected-evidence handoff introduces `MIXED` as an input source, "used when
the same accepted turn contains multiple evidence sources, such as voice plus
canvas or typed text plus canvas".

`MIXED` was added to `ai_engine/schemas.py:68` only. The wire enum is still:

```python
# app/models/fields.py:94
InputSource = Literal["TEXT", "VOICE", "CANVAS", "CHOICE", "SYSTEM"]
```

A client that follows the handoff literally **422s every answer** before the
tutor ever sees it. The frontend therefore keeps sending `TEXT` / `VOICE` and
lets `canvas_state` carry the evidence — which works, because
`has_canvas_evidence` is derived from the payload, not from the source label.

**Ask:** decide which it is. If `MIXED` is meant to reach the wire,
`models/fields.py` needs it and orchestration needs to accept it. If it is meant
to stay internal and be derived server-side, the handoff should say so — right
now it reads like a client instruction.

---

## 3. Sanya — the token / span / whole-line rendering work does not exist

The handoff asks the frontend to render three target kinds:

> Token target: render over the token bounding box.
> Character span target: render over the estimated span region.
> Whole-line target: render the whole line only when no reliable token/span target exists.

`plan_canvas_draw` already resolves all three into **one normalised box** before
anything reaches the wire — token geometry first, then `_span_target_box`, then
`_whole_region_draw`. `TutorElement` is untouched by `b99daa4`.

So the frontend cannot tell the three apart, does not need to, and the existing
renderer already draws the result correctly. **The box simply gets narrower.**
Nothing to build, and nothing blocking here.

This is a good outcome — the targeting decision belongs where the OCR confidence
lives. Flagging only so it is not tracked as outstanding frontend work.

---

## 4. Aditya — three replies

**`student_speaking` is already handled and shipped.** It went in on 22 Aug
(`079eb57`). If you saw it logged as an unknown message type, you were testing
an older bundle — likely the same one that predates the deploy still blocked by
the VM. It uses the same decision function as the partial-transcript path, with
the text test replaced by the StartOfTurn fact, since Flux has already
established speech by the time it declares a turn start.

**The canvas is now wired, over `canvas_submission` as you specified.** Sent at
StartOfTurn, once per turn, only when the student has actually drawn, with
`transcript_final` as a fallback. The frame's `png` field already matches what
your latch reads, so nothing changes on your side. `stop` was a dead end for the
reason you found independently — on the Flux path the client only sends `stop`
from the watchdog rescue, so there is no ordinary `stop` to attach a snapshot to.

**The turn handlers cannot come down yet — I think this one is wrong.** You said
`tutor_turn_committed` and the turn-context resend are now informational because
your server mints turn ids and no longer reads them off client frames. That is
true *of your server*. But `lastTutorTurnId` — the value `tutor_turn_committed`
maintains — is sent as `previous_tutor_turn_id` by **nine REST `/interaction`
call sites** in `useDemoTutor.ts` plus `useInactivityNudge.ts`. Those go to
Chirudeva's backend, not the voice server, and a null there already produced a
422 on every nudge tick on 7 Aug.

Removing them would fix nothing and re-break idle students on the REST path.
They stay until Chirudeva confirms his side does not need the pointer either.

**Barge-in session: yes.** One thing to know before we sit down, because it
changes what we will see. `app/page.tsx:255` gates `setTransmitting` on
`voiceStatus === 'listening' && !tutorSpeaking` — so **the client stops sending
audio frames while the tutor is speaking.** That is deliberate echo suppression,
but it means Flux may never receive audio to run StartOfTurn on during playback,
which would explain why barge-in-over-audio has not fired in any real session.
If nothing happens when you talk over the tutor, check whether frames are being
transmitted at all before checking whether the message was ignored. If that is
the cause, it is mine to fix.

---

## 5. Aditya / Chirudeva — every canvas-bearing turn now costs an OCR pass

**New, and caused by our fix.** Flagged rather than left to be discovered.

Attaching `canvas_state` to typed answers and hint requests means
`collect_canvas_evidence` runs the vision adapter on those turns too.
`snapshot_store.build_reference` keys on `submission_id`, not on the image, so an
unchanged board is re-OCR'd on every turn that mentions it.

This matters because of the latency work: the tutor call is already p90 17,809ms
(median 6,463ms, max 30,445ms, traced to prompt cache misses), and OCR is now in
front of it on more turns than before.

It is still the right trade — the alternative is the tutor being blind, which is
the bug we started from. But if the p90 moves, look here first. A content hash on
the snapshot would make repeat reads free.

---

## 6. Chirudeva — canvas rescue presentation is built and blocked

The renderer half of the rescue handoff is done and behind a flag
(`NEXT_PUBLIC_CANVAS_RESCUE_PRESENTATION`, **off by default**, as the handoff
specifies). Anchors register before the action applies, steps append in order,
student ink is never mutated, actions whose target is missing are queued rather
than dropped, and answer reveal is gated.

Two things block turning it on, and both are yours:

1. **No transport for `RESCUE_STEP_ADVANCE` or the renderer acknowledgements.**
   The handoff fixes both bodies exactly, but not where they go — no endpoint, no
   agreed frame name. They currently go out over the voice socket as
   `rescue_step_advance` / `rescue_render_ack` and will be ignored by a server
   that does not know them. Nothing breaks; the step simply never advances.
2. **`TUTOR_ANCHOR:ORIGINAL:<question_id>` does not resolve.** It appears in the
   handoff as a `return_target_object_id`, but it is not a shape `resolveTarget`
   knows, so "Return to original" cannot focus it. It is queued and retried
   rather than dropped, but it will never resolve until we agree what that id
   points at. `TUTOR_ANCHOR:WRITE_RULE:<q>` from the tutor-solved example does
   work today.

**Also for Sanya:** the reveal safety rule has five conditions, of which the
renderer can check three — type is `TUTOR_SOLVED_STEP`, mode is `TUTOR_SOLVED`,
and it is the final authored step. That `approved_answer_reveal` was supplied,
and that `text` is exactly `current_step_text`, are facts the client cannot see
and remain guaranteed upstream. A payload asking to reveal without satisfying the
checkable three renders as an ordinary step and logs loudly rather than
revealing.

---

## 7. Still open from earlier, unchanged

- **`"Tutor unavailable. Please try again."` collapses five failures into one
  string** (`streaming_server.py:963`, blanket `except Exception`). **Aditya.**
  Distinct codes per branch — anything is better than one string.
- **Phase 4 review contract — four fields still missing.** **Chirudeva.** The
  review arrives on the session record rather than its own endpoint.
- **Student code still shows as ST001 after refresh.** **Chirudeva.** The JWT
  `sub` is a user_id, not a `ST###` code, so the frontend has nothing to resolve
  the real code from. Repeatedly reported by testers as a frontend bug; it is
  not, and cannot be fixed here without a backend change.

---

## What is *not* the frontend's to send

Recording this so it stops being re-assigned. The connected-evidence handoff
lists OCR regions, spatial tokens, token ids, character spans and stable canvas
object ids under work to be done — **Chirudeva owns all of these**, and the
handoff says so in its own Chirudeva section.

The frontend supplies exactly three things, and now supplies them on every turn
that has them: the **snapshot**, the **strokes**, and the **ordered canvas
memory**. Everything else in `canvas_evidence` is derived server-side from those.
