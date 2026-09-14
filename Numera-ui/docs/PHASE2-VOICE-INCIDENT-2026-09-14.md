# Phase 2 guided practice — 14 September 2026

**From:** Manav (frontend)
**For:** Chirudeva and Sanya, cc Aditya (the socket), Manjusha (reporter)
**Session logs:** `SESSIONe5a6c3e8504e4f779453082f5c12cc78` (ST002) and
`SESSIONd3204ad7d5fa41ab933221d3a8da875b` (ST016), VM journal, 07:44–08:03 UTC
**Frontend fixes:** `fe1c0c1`, `257c8fb` — deployed

---

## Summary

| # | Issue | Owner | State |
|---|---|---|---|
| 1 | The tutor's own voice transcribed as the student's answer, and the ladder escalated on it | Frontend | **Fixed and deployed** |
| 2 | Replies lost while the socket was between connections | Frontend | **Fixed and deployed** |
| 3 | A routing string — `"Scaffolded support for T01"` — spoken aloud to a student | **Chiru** | Open |
| 4 | The tutor sent the identical message four times in one question | **Sanya** | Open |
| 5 | `PARTIAL` downgraded to `UNCLEAR` on almost every turn | **Sanya** | Open |
| 6 | `consecutive_stuck_count` stays 0 through repeated failure | **Sanya** | Open |
| 7 | The voice socket closes every 55–106s, all lesson | **Unowned — Aditya?** | Open, cause unknown |

Manjusha's report was "Phase 2 is not working properly… it is not moving forward
unless refreshed". Two of the causes were ours and are fixed. The rest are below,
with the log lines.

---

## What actually happened

At **07:47:33**, one turn after a socket reconnect:

```
Flux EndOfTurn (turn 0, turn_id=TURN-VOICE-e56622-001,
  eot_conf=0.859, word_conf=0.9998): 'Scaffolded support for t zero one.'
```

**`word_conf=0.9998`.** The same student's real speech in the same session scored
`'Make'=0.379`, `'ease'=0.531`, `'January'=0.665`, `'manual'=0.597`. 0.9998 is not
a person speaking into a laptop microphone — it is clean synthesised audio. The
tutor's own TTS went out of the speakers and back in through the mic.

That echo was submitted as the student's answer, and the engine judged it:

```
07:47:38  scaffold_step_evaluated   question_id=Q-T01-001
          scaffold_id=SCF-T01-GENERAL-RULE  step_id=SCF-T01-GEN-S3
          step_satisfied=false  confidence=0.98
          detected_intent=SUBMITTING_ANSWER

07:47:38  guided_support_escalation_selected
          event_type=MAXIMUM_GUIDED_SUPPORT_PARALLEL
          next_stuck_count=2  next_scaffold_failure_count=2

07:47:38  student_model_event_response  payload_type=RESCUE
          rescue_type=PARALLEL_EXAMPLE  rescue_micro_skill_id=T01.M1
          routing_reason_code=PARALLEL_EXAMPLE_REQUIRED
```

So the parallel example Manjusha saw was served **for an answer the student never
gave**, and the "microskill id" she reported is `T01.M1` from that escalation.

Nothing in the backend did anything wrong in that chain. It was handed a
confident transcript and behaved correctly. The audio should never have reached
it, and that was ours — see "already fixed" below.

---

## 3. For Chiru — a routing string is being spoken to students

Separate from the echo, and it survives the echo fix.

The sentence the tutor said out loud was **"Scaffolded support for T01"**. That is
not student-facing copy. It reads as a routing `reason` of the same family as the
fixtures in `tests/test_session_events.py`:

```
"reason": "Student incorrect. Delivering support for retry."
"reason": "Delivering scaffolded support."
```

The frontend renders no `reason` field anywhere near the transcript — I checked
before raising this. It reached the student through the spoken channel.

**What I need:** whichever field carries the tutor's voice on a scaffolded turn
(`scaffold_step_voice`, or whatever feeds it when the Student Model returns
`SUPPORT_AND_RETRY` with a scaffold) should never be able to fall back to a
routing string. Even with the microphone fixed, a student hearing "Scaffolded
support for T zero one" is a bug on its own.

It may be Saravanan's if the string originates in the Student Model payload —
you can see which side it enters from far faster than I can.

---

## 4. For Sanya — the tutor repeated itself four times

One question, `Q-T01-001`, four turns, identical message:

```
07:54:35  guided_state_evaluated  tutor_message_sha256=60d58ee1…1fcfbb4
07:55:33  guided_state_evaluated  tutor_message_sha256=60d58ee1…1fcfbb4
07:55:53  guided_state_evaluated  tutor_message_sha256=60d58ee1…1fcfbb4
07:57:05  guided_state_evaluated  tutor_message_sha256=60d58ee1…1fcfbb4
```

Same hash, four separate turns, with different student input each time —
`student_input_sha256` differs on all four. The engine noticed at 07:55:53 and
logged it:

```
prompt_similarity=1.0   repeated_question=true
```

…then said the same thing again at 07:57:05 anyway.

This is what Manjusha is describing as the hints being irrelevant — her words:
"misconception mapping is going wrong from Sanya, that's why it's showing
irrelevant hints". A student who answers three different things and gets the same
sentence back four times has no way to move, which is most of why the lesson felt
stuck even on turns where the transport was working.

`pedagogy_archetype=AFFIRM_THEN_ISOLATE` and
`pedagogical_move=ACKNOWLEDGE_AND_PROBE` on every one of those turns.

---

## 5. For Sanya — `PARTIAL` is being downgraded to `UNCLEAR`

On six consecutive turns:

```
raw_student_state=PARTIAL   → student_state=UNCLEAR   confidence 0.94–0.99
raw_student_state=UNCLEAR   → student_state=UNCLEAR
```

`diagnostic_focus=INPUT_AMBIGUITY` throughout. The raw classification says the
student is partly right; the applied state says we could not understand them.
Those are different pedagogical situations and deserve different replies — and it
is very likely *why* the same message keeps coming back, since
`ACKNOWLEDGE_AND_PROBE` is a reasonable move for genuine ambiguity and the wrong
one for a partly-correct answer.

Worth checking whether the downgrade is deliberate on low STT confidence. If it
is, it fired on turns where confidence was 0.94+.

---

## 6. For Sanya — `consecutive_stuck_count` never moves

It is `0` on every `guided_turn_diagnostics` line in this session, including the
turns where `next_scaffold_failure_count` reached 2 and the ladder escalated all
the way to a parallel example.

We had been planning frontend behaviour for a stuck student off this field. As it
stands it would never fire. Before we build on it: is it meant to count here?

---

## 7. Unowned — the voice socket closes every minute

Not a frontend decision, and I could not find what does it.

```
07:46:18 closed → 07:46:20 reopened
07:47:15 closed → 07:47:16 reopened
07:49:02 closed → 07:49:03 reopened
07:50:26 closed → 07:50:28 reopened
07:50:58 closed → 07:51:00 reopened
07:52:11 closed
```

55–106s apart, for the whole lesson, on both students' sessions.

**Ruled out:** nginx — `/api/voice/stream` has `proxy_read_timeout 86400`. Also
the client re-creating it: the effect that opens the socket has stable
dependencies, so it is not React churn.

**What fits:** audio frames stop flowing whenever the tutor is speaking or a turn
is processing, and the gaps fall exactly there — an idle socket dropped somewhere
in the path. I have added a 20s keepalive as a mitigation, labelled as a
mitigation in the code because it is not a diagnosis.

Aditya — is there an idle timeout on the streaming server, or in front of it?

---

## Already fixed, so nobody re-investigates it

Both deployed.

**The echo.** `ws.onopen` set the voice status to "listening" unconditionally, so
every reconnect reopened the microphone gate while TTS audio buffered from before
the drop was still playing. With the socket dropping every minute, that was a
recurring window. It now checks whether the tutor is still audible first.

**The lost replies.** A `tutor_response` arriving while the socket was between
connections had nowhere to land. The backend had done its part every time —
`guided_canvas_actions_planned` with `SHOW_PARALLEL` and
`validation_rejections=0`, a HINT on `SUPPORT_AND_RETRY`, and the voice server
logging "Text sent to frontend" for all of them. Only a page refresh went and
read what was already sitting on the session record.

The client now does what the refresh did: re-reads `GET /session` on reconnect,
and again before the stall rescue apologises. That is the whole of "it is not
moving forward unless refreshed".

**One correction to my own first read:** I said this looked like an nginx idle
timeout. It is not — I checked the config before touching it, and `86400` rules
it out. The cause of item 7 is still unidentified.

---

## What I need back

1. **Chiru** — item 3, the routing string in the spoken channel.
2. **Sanya** — items 4, 5, 6. Item 4 is the one Manjusha is feeling.
3. **Aditya** — item 7, if there is an idle timeout on your side.

Nothing else is blocked on either of you. The frontend side of this is done and
live.
