# Backend asks — Phase 3 repeated failure & prerequisite remediation

**Date:** 2026-09-06
**From:** Manav (frontend)
**To:** Chirudeva (Student Model orchestration / tutor backend)
**Spec:** *Phase 3 Repeated Failure & Prerequisite Remediation*, v3, 5 Sep 2026
**Test cases:** TC-18/19/20 revised, TC-26…36 new
**Frontend plan:** [PHASE3-REMEDIATION-FRONTEND-PLAN.md](./PHASE3-REMEDIATION-FRONTEND-PLAN.md)

---

## TL;DR

| # | Ask | Blocking | What it unblocks |
|---|-----|----------|------------------|
| 1 | Emit `RESUME_SAME_INDEPENDENT_QUESTION` as `payload_type` on every checkpoint re-serve | **Yes** | Student is not frozen on the checkpoint question |
| 2 | Add `intervention_input_request` to `PublicStudentModelPhasePayload` | **Yes** | The §11 difficulty popup |
| 3 | Add `routing` and `status` to `PublicStudentModelEvent` | **Yes** | Prerequisite journey, repair copy, paused screen |
| 4 | Send 2 and 3 on `GET /session`, not only on the event reply | **Yes** | Popup survives a reload / silent-mode stripping |
| 5 | Accept `INTERVENTION_INPUT_SUBMITTED` as an `interaction_type` on `/interaction` | **Yes** | Submitting the student's input |
| 6 | Decide `audio_ref` — the frontend cannot produce one | No | Voice evidence on the intervention case |

**Asks 1–3 are all one file:** `app/models/student_model_session.py`. Nothing in
the spec's routing reaches the browser today, and ask 1 is the one that turns a
live student freeze into normal behaviour.

The frontend work that depends only on `payload_type` is **built and merged**
(`lib/phase3Routing.ts`, the checkpoint unlock, `InterventionInputModal`). It is
inert until these land, and none of it computes repair or prerequisite logic —
per spec §12 that stays with you.

---

## The shared cause: the public projection drops everything new

The event you receive internally carries the full Schema 3.0 shape
(`StudentModelEvent`, `app/models/student_model_session.py:220-230`):

```python
journey_state: StudentModelJourneyState
phase_payload: StudentModelPhasePayload | None
event_result: dict[str, object] | None
routing: StudentModelRouting        # ← has next_action, reason_code, next_topic_id …
status: StudentModelStatus          # ← has intervention_required, status_code
```

What is sent to the browser is a different model
(`PublicStudentModelEvent`, `:261`):

```python
class PublicStudentModelEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    schema_version: Literal["3.0"]
    request_id: str
    processed_at: str
    journey_state: PublicStudentModelJourney          # only { topic_id }
    phase_payload: PublicStudentModelPhasePayload | None
```

`routing` and `status` are simply not on it, `journey_state` is narrowed to
`topic_id` alone (`:255-259`), and `PublicStudentModelPhasePayload` (`:246-252`)
keeps only `phase`, `payload_type`, `question_set`, `orientation_bundle`.

Every model on this path is `extra="forbid"`, so a field you add upstream is
**dropped silently** rather than passed through. That is the right default — it
is why nothing leaks — but it means each field the frontend needs has to be
named explicitly.

So of everything this change introduces:

| Signal | Reaches the browser? |
|---|---|
| `phase_payload.payload_type` | **Yes** |
| `phase_payload.intervention_input_request` | No — `extra="forbid"` |
| `routing.next_action` / `reason_code` / `next_topic_id` | No — not on the model |
| `status.intervention_required` / `status_code` | No — not on the model |
| `journey_state.phase_3_independent_practice.*` | No — journey narrowed to `topic_id` |
| `journey_state.repair_state_by_skill` | No — same |

`payload_type` surviving is what makes ask 1 a one-line change and the most
valuable of the six.

---

## 1. Emit `RESUME_SAME_INDEPENDENT_QUESTION` on every checkpoint re-serve

**Blocking. This is the one that strands a real student.**

Spec §9 and the locked rules make the checkpoint question immutable through the
repair chain:

> Its `question_id` and `question_usage_id` are preserved until the student
> answers it correctly or the topic is marked INTERVENTION_REQUIRED.

Phase 3's client-side lock is keyed by question id, and unlocks only when a
**different** id arrives. That is deliberate — it is what makes a duplicate or
out-of-order reply harmless (`lib/phase3.ts`, `phase3Locked`). But it means a
student coming back from Guided Repair #1 meets an id they have already
answered:

- the lock holds,
- the canvas stays frozen showing *"Answer recorded."*,
- there is nothing to press.

Same dead end as the 4 Sep report
(`docs/bug-phase3-exhausted-blocks-review-2026-09-04.md`), reached a different way.

**Because the ids are identical by design, no id comparison on our side can tell
a re-serve from a duplicate reply.** `payload_type` is the only thing that can,
and it is already on the public model — so if you emit it, this works with no
further backend change. The frontend side is merged and waiting.

Needed on all three returns (TC-26, TC-28, TC-32):

```jsonc
"phase_payload": {
  "phase": "PHASE_3_INDEPENDENT_PRACTICE",
  "payload_type": "RESUME_SAME_INDEPENDENT_QUESTION",   // ← this
  "question_set": { "questions": [ /* the SAME Q-T03-024 */ ] }
}
```

We also read `RETURN_TO_SAME_PHASE_3_QUESTION` from `routing.next_action` if
ask 3 lands, but `payload_type` alone is sufficient and cheaper.

While you are there, the other three payload types from the spec would let us
drop the remaining guesswork: `FRESH_INDEPENDENT_QUESTION` (TC-18),
`PREREQUISITE_REMEDIATION` (TC-31), `INTERVENTION_INPUT_REQUIRED` (TC-33/34/35).
Today the frontend only ever sees `QUESTION_SET` / `ORIENTATION_BUNDLE`, which
is a different vocabulary from the spec's — worth confirming which one you
intend to be canonical.

---

## 2. Forward `intervention_input_request`

**Blocking for the popup.**

Spec §11 and TC-33 put the popup's content on the phase payload:

```jsonc
"phase_payload": {
  "phase": "PHASE_3_INDEPENDENT_PRACTICE",
  "payload_type": "INTERVENTION_INPUT_REQUIRED",
  "question_set": null,
  "intervention_input_request": {
    "intervention_id": "INT-T03-001",
    "prompt": "What are you finding difficult?",
    "selection_required": true,
    "voice_input_enabled": true,
    "voice_input_required": false,
    "selection_options": [ { "code": "...", "label": "..." }, … ]
  }
}
```

`PublicStudentModelPhasePayload` has no such field and is `extra="forbid"`, so
it is dropped. Please add it.

The component is built and works against the TC-33 and TC-34 fixtures at
**`/app/dev-screens/intervention`** (no login) — worth a look before you wire it,
so we agree on the shape.

Note we handle TC-34's omitted `selection_options` by falling back to the six
codes fixed in §11, so a payload without them is still usable. But we cannot
invent the `intervention_id`, and without it the submission in ask 5 has nothing
to attach to.

---

## 3. Forward `routing` and `status`

**Blocking for the remaining screens**, not for asks 1 and 2.

Spec §12 tells the frontend to "follow backend routing and display the
destination". We cannot follow what we cannot see. Adding `routing` and
`status` to `PublicStudentModelEvent` covers, in one change:

| `routing.next_action` | What we would do |
|---|---|
| `START_PREREQUISITE_ORIENTATION` | Route to `next_topic_id` at `next_topic_entry_phase`, with a banner naming `return_topic_id` so the student knows they are coming back |
| `RETURN_TO_GUIDED_LEARNING` | Say why we're going back; distinguish Repair #1 from #2 for display only |
| `COLLECT_INTERVENTION_INPUT` | Open the §11 popup |
| `AWAIT_INTERVENTION_REVIEW` | Show the paused state — and importantly *not* re-open the popup |
| `RETURN_TO_SAME_PHASE_3_QUESTION` | Belt-and-braces alongside ask 1 |

`status.intervention_required` and `status_code` matter for one specific reason:
after TC-36 the topic is still `INTERVENTION_REQUIRED`, so a screen driven by
the status alone would show the popup again to a student who has just filled it
in. We distinguish the two by `next_action`, which is why both are wanted
together.

If forwarding the whole `StudentModelRouting` is more than you want to expose,
the fields we actually read are: `next_action`, `reason_code`, `next_topic_id`,
`next_topic_entry_phase`, and — from TC-31/TC-32 — `return_topic_id`,
`return_question_id`, `resume_policy`. `reason` is free prose and we would not
show it to a student.

**Prerequisite:** we never call Saravanan's new endpoint, and don't intend to.
Per §8 the route is yours to resolve; we only render where you send us.

---

## 4. Put all of it on `GET /session` too

**Blocking, and from experience rather than theory.**

A fresh Phase 3 question has already arrived once with its options stripped from
the event reply and present only on the session record — the recovery was to
re-read `GET /session`, which is not stripped.

If `intervention_input_request` goes the same way, the popup never opens and the
student sits on a locked screen with no visible reason. It also has to survive a
reload: a student who refreshes on the intervention state must still be asked.

So please carry the new payload on the session record as well as the event
reply. The frontend will prefer the session record where both are present.

---

## 5. Accept `INTERVENTION_INPUT_SUBMITTED` on `/interaction`

**Blocking for submitting the input.**

The spec says this is "a CHANGE to the existing Student Model/event-processing
flow, not another new endpoint" — agreed, but that is *your* event endpoint. The
frontend has no Student Model client at all: it talks only to the tutor backend
(`/session/*`, `/interaction`, `/canvas/submit`, `/voice/*`). So we still need a
route to reach it.

Cheapest path, and our preference: accept it as a new `interaction_type` on
`/interaction`, which already carries auth, session and turn plumbing. Our union
is `lib/api.ts:344-364`; adding one value there is trivial on our side.

What we would send, matching TC-36:

```jsonc
{
  "interaction_type": "INTERVENTION_INPUT_SUBMITTED",
  "input_source": "CHOICE",
  "intervention_id": "INT-T03-001",
  "topic_id": "ALG-KS3-03",
  "micro_skill_id": "T03.M5",
  "selected_reason_codes": ["DONT_KNOW_HOW_TO_START", "WORDS_SYMBOLS_CONFUSING"],
  "voice_input": {
    "provided": true,
    "audio_ref": null,
    "transcript": "I understand the example, but I get confused about which operation to use."
  }
}
```

Confirm the reply keeps `intervention_required: true` and
`next_action: AWAIT_INTERVENTION_REVIEW` per TC-36 — we rely on that to close the
popup onto the paused state rather than back onto the question. Submitting must
not resume the student (§11), and we will not treat it as if it had.

**One more thing:** this must travel over REST, not the voice frame.
`lib/voiceSupportFrame.ts` is a hand-maintained allow-list that silently drops
fields it does not know about — three REST-fine / voice-broken bugs so far. If
any of this ever rides a `tutor_response` frame, tell us and we will add it
there explicitly.

---

## 6. `audio_ref` — we cannot produce one

**Not blocking. Needs a decision, not code.**

Spec §11 and TC-36 include `voice_input.audio_ref`. There is no audio upload
anywhere in the frontend — no upload endpoint, no `FormData`, and neither voice
path retains audio (`useVoiceTurn` discards the stream after the turn;
`useVoiceStream` sends chunks and keeps nothing). The only evidence blob we
persist today is the canvas PNG.

We can produce a good `transcript` — that half works now, and it is the part a
reviewer actually reads.

**Proposal:** we send `{ "provided": true, "audio_ref": null, "transcript": … }`
and you accept a null `audio_ref`. If the recording itself is genuinely wanted
on the intervention case, that is an upload endpoint plus retention and consent
questions, and should be scoped separately rather than assumed.

---

## What we have already built

Merged, typechecked, 1155 tests passing. None of it decides anything — §12 is
respected throughout.

| | |
|---|---|
| `lib/phase3Routing.ts` | Reads the destination. 20 tests from the literal TC-18/19/20/26–36 outputs, written both as you send them today and as the spec describes them. Unrecognised values degrade to `UNKNOWN` — a renamed enum leaves the screen alone rather than sending the student somewhere. |
| Checkpoint unlock | `hooks/useDemoTutor.ts`. Waiting on ask 1. |
| `components/InterventionInputModal.tsx` | §11 popup. Waiting on asks 2 and 5. |
| `/app/dev-screens/intervention` | TC-33 and TC-34 fixtures, no login. |

Once asks 1–5 land we can verify the whole repair chain against a live session
the same day.

---

## One question back to you

The spec's §10 says the topic is marked `INTERVENTION_REQUIRED` and "the
automated learning route pauses until the intervention is reviewed/resolved".
What should `POST /session/start` do for a student in that state?

Asking because the 4 Sep report found `session/start` returning a 503 for a
student whose journey had nowhere to go, which locked them out of the topic
entirely. A paused-for-intervention student is a similar shape, and it would be
good to settle it before it becomes the same bug: our preference is that
`session/start` succeeds and returns them to the paused state, so we can show
them where they are rather than an error.
