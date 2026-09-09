# Phase 3 remediation — Manav handoff

**Date:** 2026-09-07 · **From:** Chirudeva (tutor backend) · **Re:** your six asks of 6 Sep

## TL;DR

All six are in, in your names, not mine. Asks 1, 2, 4, 5 and 6 land exactly as
you wrote them. Ask 3 lands with one deviation you need to know about: `routing`
is published **twice** — inside `student_model_event` as you asked, and again at
the response root, because that is where `lib/phase3Routing.ts` actually reads
it. `status` could only go in the first place; the root name is taken.

The earlier draft of this document described a parallel `intervention` block
with `reason_options[].code/text`. That is gone. There is one vocabulary now and
it is yours.

**Verified against your parser, not against my own idea of it:** real responses
from `/session/start`, `/interaction` and `GET /session` were fed through
`phase3Destination()` and `interventionOptions()` from your merged
`lib/phase3Routing.ts`. `SERVE_QUESTION`, `RESUME_CHECKPOINT`,
`COLLECT_INTERVENTION` and `AWAIT_INTERVENTION_REVIEW` all come back right. That
check is what caught the root-`routing` problem below, so it was worth doing.

---

## 1. `payload_type` on every checkpoint re-serve — done

`PublicStudentModelPhasePayload.payload_type` now carries the spec's vocabulary
for Phase 3, derived by the backend before the event is stored:

| Value | When |
|---|---|
| `RESUME_SAME_INDEPENDENT_QUESTION` | the served question is `return_checkpoint.checkpoint_question_id` **and** already appears in `used_question_ids` (TC-26/28/32) |
| `FRESH_INDEPENDENT_QUESTION` | any other Phase 3 question set (TC-18) |
| `INTERVENTION_INPUT_REQUIRED` | automated remediation exhausted, input not yet given (TC-33/34/35) |

`resumesCheckpoint()` returns true on the second and later serves and false on
the first, which is what your lock needs. Every other phase keeps whatever
`payload_type` Student Model sent — `QUESTION_SET`, `ORIENTATION_BUNDLE`,
`RESCUE`, `REVIEW_SUMMARY` and the rest are unchanged, so nothing else moves.

`PREREQUISITE_REMEDIATION` is **not** emitted as a payload type. A prerequisite
journey is a different topic's orientation bundle; the signal is
`routing.next_action = START_PREREQUISITE_ORIENTATION`, which your parser
already checks. Ask if you want the payload type as well and I will add it.

## 2. `intervention_input_request` — done

On `phase_payload`, exactly the §11 shape:

```json
{
  "phase": "PHASE_3_INDEPENDENT_PRACTICE",
  "payload_type": "INTERVENTION_INPUT_REQUIRED",
  "question_set": null,
  "intervention_input_request": {
    "intervention_id": "INT-001",
    "prompt": "What are you finding difficult?",
    "selection_required": true,
    "voice_input_enabled": true,
    "voice_input_required": false,
    "selection_options": [
      {"code": "DONT_UNDERSTAND_QUESTION", "label": "I do not understand what the question is asking."},
      {"code": "DONT_KNOW_HOW_TO_START", "label": "I do not know how to start."},
      {"code": "CANNOT_APPLY_IDEA", "label": "I understand the idea, but I cannot use it in this question."},
      {"code": "WORDS_SYMBOLS_CONFUSING", "label": "The maths words or symbols are confusing."},
      {"code": "WORKING_MISTAKES", "label": "I keep making calculation or working mistakes."},
      {"code": "OTHER", "label": "Something else."}
    ]
  }
}
```

Those six codes are `DEFAULT_INTERVENTION_OPTIONS` from your file, character for
character, and they are the only codes a submission validates against. Your
fallback and my server list can no longer disagree. `label`, not `text`.

The student's own answer never comes back out — the popup block carries no
`feedback`. Once input is in, `intervention_input_request` disappears rather
than turning into a flag you have to check.

## 3. `routing` and `status` — done, with one deviation

`PublicStudentModelEvent` now carries both:

```jsonc
"routing": {
  "next_action": "COLLECT_INTERVENTION_INPUT",
  "reason_code": "AUTOMATED_REMEDIATION_EXHAUSTED",
  "next_topic_id": null,
  "next_topic_entry_phase": null,
  "return_topic_id": "ALG-ORI-02",
  "return_question_id": "Q-T02-004",
  "content_gap_detected": false
},
"status": { "intervention_required": true, "status_code": "OK" }
```

`reason` is not published — it is free prose written for a log, and you said you
would not show it to a student.

**The deviation.** Your `Phase3RoutingSource` reads `routing` and `status` at the
**root** of the response, as siblings of `student_model_event` — not inside it.
Your ask said "add to `PublicStudentModelEvent`". Both are now true for
`routing`: it is on the event *and* on the root of `SessionResponse` and
`InteractionResponse`.

`status` is only on the event. `SessionRecord.status` (`"started"`) and
`InteractionResponse.status` (`DUPLICATE_TURN` / `processed` / …) already own
that name at the root, and overloading it would break every existing caller. In
practice this costs you nothing: your status check is a fallback behind
`next_action`, and `COLLECT_INTERVENTION_INPUT` / `AWAIT_INTERVENTION_REVIEW`
are always set. If you want the status block at the root, name it something
else — `student_model_status` — and I will add it.

`return_topic_id` and `return_question_id` are filled from `return_checkpoint`
when Student Model does not send them, so the "you are coming back to…" banner
works today rather than after Saravanan ships. `resume_policy` is not published
— your parser does not read it; say the word if that changes.

`repair_cycle_no` is not surfaced, so `GO_TO_PREREQUISITE`'s sibling
`GO_TO_GUIDED_REPAIR` still gives you `cycle: null`. It is display-only and
Student Model does not send a per-cycle number yet; I did not want to invent
one. `phase2_repair_count` (0–2) exists on the journey if you decide you want it
projected.

## 4. All of it on `GET /session` too — done

The projection happens once, before the event is stored on the session record.
So the same `payload_type`, `intervention_input_request`, `routing` and `status`
appear identically on `/session/start`, `GET /session/{id}`, `/session/end`,
`/interaction` and `/canvas/submit`. A reload on the intervention state still
asks the question.

**One extra fix you did not ask for but needed.** Phase 3 normally strips
`student_model_event` from interaction replies (`phase3_silent`) — that is what
would have swallowed the popup on the very turn that triggers it, leaving the
student on a locked screen with nothing to press. Silence exists to keep an
answer key off a live question; a halted topic has no live question, so a halted
session is now exempt. You get the popup on the reply itself, not only after a
re-read.

## 5. `INTERVENTION_INPUT_SUBMITTED` on `/interaction` — done

There is no separate endpoint. `POST /interaction`, normal bearer token, exactly
your TC-36 body:

```json
{
  "session_id": "SESSION…",
  "student_id": "ST440",
  "interaction_type": "INTERVENTION_INPUT_SUBMITTED",
  "input_source": "CHOICE",
  "turn_id": "TURN-…",
  "current_phase": "INDEPENDENT_PRACTICE",
  "concept_id": "ALG_LINEAR_ONE_STEP",
  "question_id": "Q-T02-004",
  "hint_count": 0,
  "intervention_id": "INT-001",
  "topic_id": "ALG-ORI-02",
  "micro_skill_id": "T02.M1",
  "selected_reason_codes": ["DONT_KNOW_HOW_TO_START", "WORDS_SYMBOLS_CONFUSING"],
  "voice_input": {
    "provided": true,
    "audio_ref": null,
    "transcript": "I understand the example, but I get confused about which operation to use."
  }
}
```

- `input_source: CHOICE` without `selected_option_id` is accepted for this type
  only — the choices are reason codes, not a question's options.
- `session_id`, `student_id`, `turn_id`, `current_phase`, `concept_id`,
  `question_id` and `hint_count` are the ordinary `/interaction` envelope. Send
  a real `turn_id`; a repeat of the same one is a duplicate turn as usual.
- `topic_id` and `micro_skill_id` are checked against the active case, not
  trusted. A mismatch is a 409, not a silent overwrite.
- Duplicate codes are deduplicated and sorted. Codes outside the six are 422.
- An empty `selected_reason_codes` is 422 — §11 requires a selection.

**The reply confirms what you asked it to confirm.** `routing.next_action`
becomes `AWAIT_INTERVENTION_REVIEW`, `status.intervention_required` stays
`true`, `phase_payload` becomes `null`, and the controls stay off. Your parser
returns `AWAIT_INTERVENTION_REVIEW`, so the popup closes onto the paused state
and does not reopen. Submitting resumes nothing.

This is REST only. Nothing rides a `tutor_response` voice frame, so
`voiceSupportFrame.ts` needs no new entry. If that ever changes I will tell you
before it ships.

**While paused**, every learning route returns 409 with
`error_code: INTERVENTION_REQUIRED` — `/interaction` answers, `/canvas/submit`,
orientation, rescue, review. `INTERVENTION_INPUT_SUBMITTED` is the single
exception, and reads (`GET /session`, `/session/end`) always work.

## 6. `audio_ref` — accepted as null

`{"provided": true, "audio_ref": null, "transcript": "…"}` is valid and is what
reaches Student Model. No upload endpoint, no retention question, no field
quietly filled with something that is not an audio reference. If the recording
itself is ever wanted, that is separate work as you said.

---

## Your question back: `POST /session/start` for a paused student

**It succeeds and returns them to the paused state.** No 503, no lock-out. The
response carries the intervention payload above, `question_id: null`,
`current_phase: INDEPENDENT_PRACTICE` and the controls off, so you can show them
where they are. If they had already submitted, it comes back as
`AWAIT_INTERVENTION_REVIEW` and the popup does not reopen.

Same for a content gap, which is a different thing and does not create a case:
`content_gap_detected: true` with no intervention block.

## Errors

| Response | What to do |
|---|---|
| 401 | Re-authenticate and retry. |
| 404 | Wrong session/student pair. |
| 422 | Bad or empty reason codes, or a field that is not in the envelope. |
| 409 `INTERVENTION_REQUIRED` | A learning action while paused. Read the session and render the paused state. |
| 409 on submission | Case/topic/skill mismatch, or different evidence for a case already submitted. Read current state; never overwrite silently. |
| 409 `JOURNEY_VERSION_CONFLICT` | Reopen the topic via `/session/start`, then retry the same evidence unchanged. |
| 503 | Upstream. Keep the student's words on screen and retry the same submission — identical retries are idempotent and send at most one upstream event. |

## Status and what is still unverified

Backend-side this is done and tested: 719 of 720 tests in `tests/` pass; the one
failure (a Phase 2 duplicate-turn test) is unrelated and fails on a clean
checkout of `main` too.
38 of those cover this work specifically, and they assert your field names, so a
rename that would strand you fails in CI rather than in a browser.

Not yet verified, and it needs both of us: a live repair chain against a real
Student Model. Saravanan's upstream contract is still proposed, so what runs
today is the backend's side of it against a fake boundary. Once his fields land
we can walk the whole chain — first checkpoint → Repair 1 → same checkpoint →
Repair 2 → same checkpoint → prerequisite → same checkpoint → exhaustion — in a
session, in a day.

Nothing in `Numera-ui` was changed. Your merged work should light up as-is.
