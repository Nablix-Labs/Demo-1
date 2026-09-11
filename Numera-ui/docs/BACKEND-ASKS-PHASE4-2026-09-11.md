# Backend asks — Phase 4 Review, 11 September 2026

**From:** Manav (frontend)
**For:** Chiru (Tutor Backend), with one item for Saravanan

Everything below was reproduced against the live VM (`https://nablix.ai/api/`)
on a real signed-in student — `manav@example.com`, `ST015`, topic `ALG-KS3-01`,
journey version 27 — not inferred from code. Payload excerpts are copied from
the actual `/session/start` response.

The frontend side of all of this is already fixed and deployed (`ed28049`,
`efff58b`, `ee034b7`). The client was dropping four fields you *were* sending;
that was mine and it is done. What is left below is yours.

| # | What | Severity |
|---|---|---|
| 1 | `recommended_next_action` carries a routing verb, so the end-of-review button asked a child to "Wait for student response" | **High — student-facing** |
| 2 | No topic title on `Phase4ReviewResponse`, so every review is headed "This topic" | Medium |
| 3 | A wrong Phase 3 attempt produced no tutor replay | Question first |
| 4 | Session phase and journey phase disagree on the same student | Low — Saravanan |

---

## 1. `recommended_next_action` is being fed the routing verb

**Where.** `app/services/session_service.py:1127`:

```python
request = build_phase4_review_request(
    history,
    filter_replay_attempts(history.attempts),
    event.journey_state.mastery_status,
    event.routing.next_action,        # ← this
)
```

That argument lands on `TopicOutcome.recommended_next_action`
(`phase4_context_builder.py:163`), which the review screen renders as the label
on the button that **ends the review**.

**What arrives.** For ST015:

```json
"topic_outcome": {
  "mastery_status": "NEARLY_MASTERED",
  "recommended_next_action": "WAIT_FOR_STUDENT_RESPONSE",
  "next_action_message": null
}
```

`routing.next_action` is the Student Model's own vocabulary — I have also seen
`WAIT_FOR_CONTENT` on this account. These are instructions to the tutor loop,
not to the learner. Rendered, the student got a primary button reading
**"Wait for student response"**, directly under a second button already labelled
"End review".

This also explains why the vocabulary looked undocumented: we were reading the
routing enum, not an action enum. `START_NEXT_TOPIC` appears in your example
because that is the one value where the two happen to overlap.

**Ask.** Pass a real next action — whatever the Student Model means by "what
this student should do after this topic" — and please write down the closed set
of values. The frontend renders the token directly, so the vocabulary is a
contract.

**Stopgap in place, please tell me when to remove it.** `studentFacingAction()`
in `lib/phase4FromSession.ts` maps the `WAIT_FOR_*` family back to the generic
`CONTINUE` and passes every other token through untouched. It is deliberately
narrow — mapping unknown tokens onto invented wording is how we ended up with a
review headed "Linear equations" for a session about something else (QA row 42).

---

## 2. `Phase4ReviewResponse` never sends the topic title

**What happens.** Every live Phase 4 review is headed **"This topic"**, and the
Topic Learning Summary repeats it.

**Why.** The only human-readable topic name the backend has ever sent is the
orientation video's title, which the client digs out of
`student_model_event.phase_payload.orientation_bundle`. At Review that payload is:

```json
"phase_payload": {
  "phase": "REVIEW",
  "payload_type": "REVIEW_SUMMARY",
  "question_set": { "questions": [] },
  "orientation_bundle": null
}
```

So there is nothing to read. `journey_state.topic_id` is `"ALG-KS3-01"` — a
code, not something to show a student.

**You already build the title.** `Phase4ReviewRequest.topic_info.title` is
required and non-empty (`phase4_review.py:14`), and
`build_phase4_review_request` raises rather than fabricate it. It simply is not
on `Phase4ReviewResponse`, so it never reaches the browser.

**Ask.** Forward `topic_info` (or just `title`) on `Phase4ReviewResponse`.

**Please don't suggest the client resolve it from the topic code.** That is
exactly QA row 42: the client guessed a name from its own table and confidently
labelled a review "Linear equations" when the student had spent the lesson on
"What Is Algebra?". I would rather print "This topic" than guess again.

---

## 3. A wrong Phase 3 attempt produced no replay — is this expected?

Asking before calling it a bug, because I may be misreading the contract.

ST015's review contains exactly one journey row, and it is wrong:

```json
"question_journey": [{
  "question_id": "Q-T01-009",
  "question_usage_id": "QU-T01-009-P3",
  "attempt_id": "ATTEMPT-001",
  "evaluation": "INCORRECT",
  "independent_success": false,
  "review_item_id": null,
  "skill_label": "Identify general rules"
}],
"tutor_replays": []
```

My understanding is that `tutor_replays` = `filter_replay_attempts` = Phase 3
attempts that are wrong. This attempt is Phase 3 and wrong, but produced no
replay and no `review_item_id`.

So the student sees the Learning Summary only — no journey rail with a
correction, no tutor replay — on a topic where they got the question wrong.
That renders as §8.8's "no wrong answers" path on a run that had one.

**Ask.** Either confirm this is correct (and tell me what disqualifies the
attempt — no work artifact? no detected errors?) so I can stop treating an empty
`tutor_replays` as suspicious, or treat it as a generation gap.

Related and possibly the same root: `next_action_message` came back `null`
even though `configs/phase4_review.yaml:31` instructs the model to author one.
Your guardrail allows null "when the evidence does not support a personalised
claim", so this may just be that rule firing on thin evidence — worth a glance
while you are in there.

---

## 4. Saravanan / Chiru — session phase and journey phase disagree

Low severity, but it makes the app visibly jump on login.

For the same student, at the same moment:

- `POST /auth/login` → `last_journey_state.current_phase = "PHASE_3_INDEPENDENT_PRACTICE"`
- `POST /session/start` → `current_phase = "REVIEW"`, `reason_code: "SESSION_RESUMED"`

The frontend follows both, in that order: `landingRoute` sends the student to
`/practice` off the journey, then `usePhaseRouting` follows the session record
and moves them to `/review`. The student watches the app change its mind.

Both behaviours are individually correct, so I have not changed anything. **Which
one should the client treat as authoritative on login?** If it is the session,
I will stop routing off `last_journey_state`.

Context that may be the cause: this student is in a content gap —
`status_code: CONTENT_GAP`, `reason_code: FRESH_CONTENT_UNAVAILABLE`,
`rescue_state_by_skill.T01.M7.status: RESCUE_REQUIRED`, and
`phase_payload.question_set.questions` empty. If resuming into REVIEW is the
deliberate handling of "no fresh independent question available", say so and I
will document it rather than treat it as drift.

---

## Not asks — for completeness

**Four fields I was dropping, now fixed client-side.** `first_error.why_it_matters`,
`topic_outcome.next_action_message`, `question_journey[].skill_label` and
`PARTIAL` as a distinct evaluation were all arriving correctly and being
discarded by the client adapter. `skill_labels` in particular is working exactly
as designed — the merge onto each journey row at `session_service.py:1158-1200`
is clean. Sorry for any time lost if this was ever reported to you as missing.

**No answer-key leak on this payload.** The old concern about
`tutor_view.answer_spec.canonical_answer` reaching the browser does **not**
apply at Review: `tutor_view` is absent from the `/session/start` response
entirely. It still needs re-checking on a DIAGNOSTIC payload, which I could not
reach on this account — flagging so it is not lost, not asking for anything yet.

**A second test student would help.** `ST015` resumes into REVIEW, so Phases 0–3
cannot be exercised live with it. A student who has never started a topic would
let me verify the diagnostic → orientation → guided → independent chain against
real payloads instead of demo data.
