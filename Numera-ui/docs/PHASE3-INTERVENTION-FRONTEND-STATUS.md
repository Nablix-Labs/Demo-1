# Phase 3 intervention — frontend status

**Date:** 2026-09-07
**From:** Manav (frontend)
**To:** Chirudeva (tutor backend)
**Re:** your handoff of 7 Sep — "Phase 3 remediation — Manav handoff"
**Prior:** [BACKEND-ASKS-PHASE3-REMEDIATION.md](./BACKEND-ASKS-PHASE3-REMEDIATION.md)

---

## TL;DR

Wired against what you shipped, not against what I asked for. The `status`
deviation was real work on this side and worth the note you gave it — a build
reading `status` at the root would have found nothing and routed a paused
student straight back onto the question, silently.

Merged and typechecked. One ask back, at the bottom, and it is small.

| Your item | Frontend |
|---|---|
| 1. `payload_type` on every re-serve | Live. The checkpoint unlock was already merged and is now driven by it. |
| 2. `intervention_input_request` | Live. Popup opens from it, falls back to the six §11 codes when it is absent. |
| 3. `routing` + `status`, with the deviation | Handled. Reads both homes — see below. |
| 4. All of it on `GET /session` | Used. It is also the recovery path for a 409. |
| 5. `INTERVENTION_INPUT_SUBMITTED` | Sent over `/interaction`, REST only, `input_source: CHOICE`. |
| 6. `audio_ref: null` | Sent exactly as agreed. |
| Your answer on `session/start` | Taken as given: no special-casing, the reply routes it. |

---

## The `status` deviation

Not a problem, but it did move code. My `Phase3RoutingSource` read `routing`
and `status` as siblings of `student_model_event` at the response root, because
that is where the parser was already looking. Your handoff says `routing` is in
both places and `status` only on the event.

So the parser now resolves each one from wherever it lives — root first for
`routing`, event-only for `status` — and has tests that fail if either home
stops carrying it. `student_model_status` at the root is not needed; there is
nothing left for it to fix.

The verification you did against my parser is what caught this, and it caught
something that would not have shown up until a real exhausted student hit it in
front of Manjusha. Thank you for running it.

## `repair_cycle_no`

Left as `cycle: null`, as you shipped it. It is display-only and I would rather
render nothing than a number nobody computed. If `phase2_repair_count` gets
projected I will use it; I am not asking for it.

---

## What a student now sees

**The popup** opens on `INTERVENTION_INPUT_REQUIRED`, on
`next_action: COLLECT_INTERVENTION_INPUT`, or on `intervention_required: true`
with no `AWAIT_INTERVENTION_REVIEW` beside it. Any one is enough — a student owed
the popup gets it even if the other two are missing.

**Submitting** posts `INTERVENTION_INPUT_SUBMITTED` and closes onto a paused
screen, never back onto the question. The screen says a teacher is looking at
the topic, that nothing they did went wrong, and offers no retry — because
retrying is exactly what will not work.

**A 409 `INTERVENTION_REQUIRED`** no longer reaches the student as an error. It
was landing on the generic 409 copy, which tells them to *ask the team to reset
the topic* — wrong, and the opposite of what is happening. It now re-reads
`GET /session` and renders whichever paused state the record reports, which is
your own instruction: "Read the session and render the paused state."

Three states, not two, and the third is the one worth naming: **paused with the
popup already gone**. Your note that `intervention_input_request` disappears
rather than becoming a flag is what made me hold this as an explicit stage
instead of inferring it from the request's presence. Inferred, a reload on a
paused-but-unanswered case would have shown the student a working question the
backend 409s every answer to.

---

## The one ask back: `topic_id` and `micro_skill_id` on the request

Your TC-36 body carries both, and you validate both against the active case with
a 409 on a mismatch. **The frontend has no honest source for either.**

- `micro_skill_id` appears nowhere the browser can see — not on the session
  record, not on the §11 request as specified, not on the public journey
  (still narrowed to `topic_id`).
- The topic the frontend *thinks* it is on comes from navigation state that
  has a demo default in it. Sending it would occasionally be confidently wrong.

A guess is strictly worse than an omission here: your validation turns a wrong
value into a blocked student, and the block looks to them like the submission
failing. So today the frontend sends `intervention_id` and the reason codes, and
sends `topic_id` / `micro_skill_id` **only if `intervention_input_request`
carries them** — the code reads them from there already and drops them silently
when absent.

**Two ways to close it, your pick:**

1. Add `topic_id` and `micro_skill_id` to `intervention_input_request`. You have
   both on the case; we echo them back verbatim and your validation still means
   something. One field each, and it is the option I would take.
2. Resolve both from the active case when they are absent, and let the
   submission carry `intervention_id` alone.

Either works. What does not work is the current shape, where the two fields are
required of a client that cannot know them — that is a 422 waiting for the first
real exhausted student.

---

## Still unverified, and it needs both of us

Same as your side: no live repair chain. Everything here is tested against your
documented shapes and the TC fixtures, which is not the same as a real Student
Model walking first checkpoint → Repair 1 → Repair 2 → prerequisite →
exhaustion. When Saravanan's fields land I can do that pass in a day, same as
you said.

Reviewable now without a backend, no login:

- `/dev-screens/intervention` — the TC-33 and TC-34 popups, the exact submission
  payload, and the paused screen that follows.

---

## Not built, deliberately

`GO_TO_PREREQUISITE` is parsed and reaches the app, and then stops. Acting on it
means sending a student out of the topic they are in and into a different one
mid-session, with a banner promising they will come back — that is a navigation
change, not a rendering one, and building it blind against a chain nobody has
walked yet is how it gets built twice. It waits for the live pass.

