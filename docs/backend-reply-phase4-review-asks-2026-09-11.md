# Backend reply — Phase 4 review asks, 11 September 2026

**From:** Chirudeva (tutor backend)
**For:** Manav, cc Saravanan (ask 4)
**Re:** `Backend asks — Phase 4 Review, 11 September 2026`
**Date:** 11 Sep 2026

---

## Summary

| # | Ask | Verdict |
|---|---|---|
| 1 | `recommended_next_action` routing verb | Shipped `d317456`. Nothing further. |
| 2 | Topic title on `Phase4ReviewResponse` | Shipped `d317456`. Nothing further. |
| 3 | Wrong Phase 3 attempt produced no replay | **Correct as specified.** The disqualifier is no stored work. One-line change so the logs say which attempt next time. |
| — | `next_action_message` never reaches the screen | **Move it to `LearningSummary`.** Go ahead — no backend change. |
| 4 | Session phase vs journey phase | **The session is authoritative.** Stop routing off `last_journey_state`. One real question for Saravanan underneath it. |
| — | Answer-key leak on DIAGNOSTIC | Already closed, structurally, and already tested. Details below so it can be struck off. |

Thank you for the re-verification table, and for deleting the `WAIT_FOR_*` filter
rather than keeping it as a belt. That was the right read: the closed set is a
contract precisely so there is only one copy of the rule.

---

## 3. The empty `tutor_replays` is correct — the attempt has no work to replay

Not a generation gap. Stop treating an empty `tutor_replays` as suspicious.

A wrong Phase 3 attempt is disqualified from replay in exactly three cases, all in
`_replay_item` (`app/services/phase4_context_builder.py:92`):

1. **no stored work artifact**
2. no `question_usage_id`
3. no detected error that maps to a micro-skill

For `ATTEMPT-001` on `Q-T01-009` it is the first. Work artifacts are only ever
created on the **canvas** submission path, and only in Phase 3
(`app/services/canvas_service.py:350-364`):

```python
if (
    session.current_phase == "INDEPENDENT_PRACTICE"
    and request.submission_role == "STANDALONE_ATTEMPT"
    and ocr.raw_ocr_text.strip() != ""
):
    work_artifact_id = await _store_work_artifact(...)
```

`Q-T01-009` is the **choice** question — the one from the 4 Sep report, the only
item ever served to ST015 in Phase 3 (`served_question_ids: ["Q-T01-009"]`). A
choice answer is submitted off the canvas path, so nothing was handwritten, so
there is no PDF, so there is no work to replay. A tutor replay walks through what
the student wrote; on a multiple-choice tap there is nothing to walk through. The
attempt still counts as evidence — it is in `whole_topic_evidence` and it is the
one row in your `question_journey` — it simply has nothing to render as a
correction.

`review_item_id: null` follows from the same thing: the id is minted per replay
item, so no replay item means no id. That field is doing its job.

**The rendering, though, is a real bug, and it's yours.** §8.8's "no wrong
answers" path is being chosen off `tutor_replays.length === 0`. That is the wrong
predicate — it means "nothing replayable", not "nothing wrong". The field that
answers your actual question is already on the response:

```ts
question_journey.some(row => row.evaluation !== "CORRECT")
```

`question_journey` carries every Phase 3 attempt with its evaluation
(`session_service.py:1201-1220`), replayable or not. Branch on that and ST015
stops getting a congratulatory summary on a topic they got wrong. No backend
release needed.

**One change made:** `phase4_replay_item_skipped` logged only `attempt_id`, and
`attempt_id` sequences restart per question — so the log could not answer "which
attempt was skipped, and why". It now carries `question_id` and
`question_usage_id` alongside the reason. Next time this comes up you can get the
answer out of the VM logs without either of us reading the builder.

### `next_action_message: null` — different root, and already gone

Not related. `next_action_message` is the one field on `topic_outcome` that is
*generated* rather than forwarded (`phase4_review.py:19-26`), and the guardrail
you quoted is exactly what fired: thin evidence, one wrong attempt, nothing
honest to personalise on. It came back populated on your re-verify because
`d317456` stopped the merge in `generate_phase4_review_for` from overwriting the
generated message with the request's `topic_outcome`. Nothing left open here.

---

## `next_action_message` on `LearningSummary` — yes, move it

Go ahead, and I'd say the payload already argues for it. The field hangs off
`topic_outcome`, beside `mastery_status` and `recommended_next_action` — all three
are statements about the **topic**, not about any one replay. Rendering it inside
`FeedbackRail` couples a topic-level sentence to a replay that may not exist, and
the no-wrong-answers run is exactly when an encouraging next step is most worth
saying. Your call, but it's the right one.

---

## 4. Route off the session. The journey row is the pre-session snapshot.

**`/session/start` is authoritative. Stop routing off `last_journey_state`.**

The two are not in conflict; they are two different moments. `last_journey_state`
on the login response is the journey row as persisted *before* this session
opened. `/session/start` sends `SESSION_OPENED` to the Student Model and returns
the phase the Student Model answers with. Anything that advances the journey
advances it at `SESSION_OPENED`, so the login snapshot is stale by construction —
not wrong, just earlier.

The specific pairing you saw is explicitly allowed in our validator
(`session_service.py:881-883`):

```python
if payload.phase != expected_phase and not (
    expected_phase == "PHASE_3_INDEPENDENT_PRACTICE" and payload.phase == "REVIEW"
):
    raise HTTPException(status_code=503, ...)
```

That allowance is commit `73bd0f0`, *"allow transition to review when phase 3
questions are exhausted"* — the fix for your 4 Sep blocking report, where a
Phase 3 student with no questions left got a 503 on `/session/start` and could
not open the topic at all. Running out of Phase 3 questions is how a topic
finishes, so the journey row still reading `PHASE_3` while the payload says
`REVIEW` is the intended, tested shape. Document it rather than treat it as drift.

So: `landingRoute` should read the session, or wait for it. Nothing for you to
reconcile — there is only one authority, and it is the one you already follow
second.

### The one real question, and it is Saravanan's

Worth separating from the routing answer, because it is a different problem
wearing the same symptom.

ST015 is not only *exhausted*, they are in a **content gap** with a rescue still
outstanding: `status_code: CONTENT_GAP`, `reason_code: FRESH_CONTENT_UNAVAILABLE`,
`rescue_state_by_skill.T01.M7.status: RESCUE_REQUIRED`. The Student Model is
answering `SESSION_OPENED` for that student with a `REVIEW` / `REVIEW_SUMMARY`
payload, and we accept it and generate a Phase 4 review for a topic whose
remediation never happened.

Our own restore path refuses to do that
(`interaction_service.py:1425-1427`):

> FRESH_CONTENT_UNAVAILABLE is an authoritative answer — the question does not
> exist — so it must never be re-requested in a loop, and never be laundered into
> MASTERED, REVIEW, or a Phase 4 review.

Two paths, two answers, same condition. **Saravanan — which is right?** If a
content gap with `RESCUE_REQUIRED` outstanding is *meant* to route to REVIEW,
say so and I will relax the restore-path guard to match and write it down. If it
is not, the fix belongs on your side of `SESSION_OPENED`, not ours.

I have deliberately **not** added a guard at `SESSION_OPENED` on my own judgment.
Refusing that payload is precisely how ST015 got stranded on 4 Sep, and I am not
re-introducing a blocking bug to enforce a rule nobody has confirmed yet.

---

## Not asks — closing three of them out

**Answer-key leak on DIAGNOSTIC: closed, and not payload-specific.** `tutor_view`
cannot reach the browser on any payload. The public projection is a structural
allowlist, not a filter — `PublicStudentModelQuestion` (`student_model_session.py:281`)
is `question_id` + `student_view` with `extra="forbid"`, so there is no payload
type on which a tutor field could appear. The diagnostic case is already pinned:
`test_session_start_uses_schema_3_diagnostic_contract_by_default`
(`tests/test_session_events.py:1024`) starts a Phase 0 session and asserts
`tutor_view`, `canonical_answer`, `accepted_answers` and `potential_errors` are
absent from the serialised response text. Strike it off — no account access needed.

**`PARTIAL` will never appear at Review.** Handling it is harmless, but don't wait
for it: `TopicAttemptRecord.evaluation` is `Literal["CORRECT", "INCORRECT", "WRONG"]`
(`topic_event_history.py:43`), and `question_journey` is built straight from those
rows. `PARTIAL` is a **Phase 2 guided** `student_state`, not a Phase 3 evaluation —
it lives in the guided classifier and never reaches a topic attempt record. The
distinct-evaluation branch in your review adapter is dead code at Review.

**The 7-second `GET /session` is real and expected.** Review generation runs
synchronously inside the request that first enters REVIEW — an LLM call plus
persistence, behind the session lock. Keep the skeleton. If it becomes a problem
in front of students rather than in testing, say so and we'll talk about
generating it on the transition instead of on the read; it isn't worth
restructuring on a timing note alone.

**A second test student:** agreed, and it is the single thing most limiting what
either of us can verify — Phases 0–3 currently cannot be exercised against real
payloads at all. Provisioning is Student Model side. **Saravanan, can we get one
student who has never started a topic?**

---

## Changes in this reply

One, and it is a log field:

- `app/services/phase4_context_builder.py` — `phase4_replay_item_skipped` now
  logs `question_id` and `question_usage_id` beside the reason. No behaviour
  change; the three skip cases are unchanged and still covered by
  `tests/test_phase4_context_builder.py:106-142`.

40 Phase 4 tests and 51 session-event tests pass.

Nothing else in this document needs backend code. Asks 3 and the
`next_action_message` placement are frontend changes; ask 4's routing answer is a
frontend change; ask 4's underlying question is Saravanan's.
