# Backend reply — Phase 4 review asks

**From:** Chirudeva (tutor backend)
**For:** Manav, cc Sanya
**Re:** `frontend-status-and-backend-asks-2026-09-04.md` and
`phase4-review-mockup-backend-asks-2026-09-04.md`
**Date:** 5 Sep 2026

---

## What shipped today

Four of the nine, on `deva/phase4-review-fields`:

| # | Field | Where |
|---|---|---|
| 1 | `question_journey[].skill_label` | rail row |
| 3 | `first_error.why_it_matters` | card |
| 5 | `topic_outcome.next_action_message` | card |
| 6 | `replay_steps[].stage_label` | stage strip |

All four are optional and null by default. A review generated before the tutor starts
populating them is byte-identical to what you get today, so there is no ordering
dependency between our release and yours.

Two notes on shape:

- **`stage_label` is per-step, not a fixed review-level list.** You said a hardcoded
  five-stage stepper lies when a replay has three steps or seven — agreed, so the model
  labels the steps a replay actually has and returns null for a step with no distinct
  stage. There is no `stage` enum alongside it; `phase4Stages.ts` reads the label, so an
  enum would be a field nobody consumes.
- **`skill_label` is keyed on `(question_usage_id, attempt_id)` internally,** not
  `question_id`. `attempt_id` sequences restart per question, so `question_id` does not
  identify a rail row. You do not see this — the label arrives already merged onto the
  journey row. The one consequence: a row whose `question_usage_id` is null (the service
  omits it for some attempts) cannot be matched and gets no label. That degrades to the
  row you render today.

## Ask #9 — already shipped, before this doc was written

`aa90b2e` / `df54b27`. The board contract is live with the exact closed vocabulary you
proposed: `value_row`, `brace`, `expression`, `label`, `struck`, `boxed`, `example`, with
`board` optional per step and `tutor_write` as the fallback. Your §2.3 answer is yes —
that vocabulary covers Topic 1 as authored. If you need a kind we don't have, adding one
is a backend release with no frontend release, as you designed it.

## One thing we need from you

**`phase4FromSession.ts` drops four of the five new fields**, so three of the four we just
shipped will render nothing until it is widened. It needs two changes, not one:

1. the raw wire type `SessionPhase4Review` (`:41-75`) does not declare them; and
2. the mapping rebuilds `first_error` (`:103-106`), `topic_outcome` (`:182-185`) and
   journey rows (`:132-137`) field by field.

Dropped: `why_it_matters`, `next_action_message`, `skill_label` (and `error_pattern` when
it lands). Only `stage_label` survives, via the wholesale `replay_steps` pass-through at
`:107`. `lib/api.ts` already types all of them and the components already read them, so
this is the mapper only.

We deliberately did not touch it — it is your file.

## Your five questions

1. **Is "Live" actually live?** Presentational. Replays stay pre-authored and performed
   client-side. No streaming contract, no backend work. Style the pill however you like.
2. **Does `PARTIAL` get a tutor replay?** No — replays follow a wrong submission, per §3.
   Your conservative reading was right; treat it as decided so you can build the third
   status without a second round-trip. `PARTIAL` itself is not ours (see below).
3. **Are the five stages fixed or per-replay?** Per-replay, as above.
4. **Does the board vocabulary cover Topic 1?** Yes, and it is already shipped.
5. **`duration_ms` only, or pre-rendered audio + cues?** **Neither is coming — drop the
   scrubber, the time readout and CC.** Taking you up on your own offer rather than
   shipping a control that lies. TTS runs at playback; the review is generated and
   persisted ahead of time, so at generation there is no audio to measure, and the
   adapters' own `duration_seconds` is itself a byte-length estimate. An estimated clock
   drifts against the speech it is scrubbing. If pre-rendered audio gets funded this
   becomes real, and we will come to you before assuming you still want it.

## Ask #4 — `error_pattern`: not yet, and here is the honest reason

We can count. We cannot currently prove that the count belongs to the signature.

`whole_topic_evidence.misconception_recurrence_counts` is an aggregate per
`misconception_id`. It establishes that *some* mistake recurred N times. It does not bind
a generated signature, a count, and a set of `question_ids` to the *same* recurring
mistake — a validator built on it would happily accept a plausible-sounding "n × 4"
attached to an unrelated misconception's count. That is a claim about a child's learning
that the evidence does not support, so it is worse than the card being absent.

What unblocks it: the backend deriving deterministic Phase 3 error candidates — signature,
occurrence count and question ids computed together from the attempts — with the tutor
narrowed to selecting one exact candidate, validated by identity. That is real work and it
is ours. Until then `learning_pattern_summary` stays as the fallback and null
`error_pattern` keeps the card hidden, exactly as your §2.6 specified.

## Ask #2 — `PARTIAL` is Student Model, escalated

`TopicAttemptRecord.evaluation` is `CORRECT | INCORRECT | WRONG` and there is no score or
rubric anywhere on the payload to derive a middle state from. Raised with Saravanan. When
it arrives we widen the literal and pass it through; the replay answer above (no replay)
already holds, so your rail work is not blocked twice.

## Ask #8 — correcting the record

Your doc attributed the snapshot and error regions to us, and we initially agreed. Both
readings were wrong, so for the record:

**Inside a live session we already have both.** The page image is in `snapshot_store`, and
`SessionRecord.ocr_result` carries complete OCR regions as normalised `{x, y, w, h}` 0–1
boxes — the exact shape you asked for.

**Neither is durable.** The upstream artifact contract stores `combined_pdf_base64`,
`per_page_ocr_text` and `combined_ocr_text` — PDF and OCR *text* only, no image and no
regions — and Phase 4 reads durable topic history, not session state.

So this is a cross-service contract change, not something either side ships alone, and the
substantive work is reliable attempt-to-region linkage rather than plumbing. Nobody should
be waiting on Saravanan for it in its current framing, and nobody should expect it from us
as a small addition.

## Not in this delivery

- **The Phase 3 exhaustion bug.** Separate thread. The upstream half — recommending REVIEW
  when independent practice runs out — is Saravanan's. Your point 2 is ours and we agree
  with it: `resolve_transition` currently returns `None` and only logs, which is what
  leaves `current_phase: INDEPENDENT_PRACTICE` with `question_id: null`. A phase with no
  question is not a state any client can render honestly, and we will fix that on the
  session record regardless of how the routing half lands.
- **Your Part 2 `/interaction` 500 + 409** — taken as retracted per your own follow-up.

## Verification

Backend: 40 focused Phase 4 tests and 681 in the full suite. The one failing test,
`test_duplicate_turn_repeats_the_response_without_new_openai_work`, fails identically on
clean `main` and is unrelated to any of this.

End-to-end against a live session is still blocked by the Phase 3 exhaustion bug, so
nothing here has been proven against a real session record — only against the test suite.
We will verify on the VM the day a session can reach Review.
