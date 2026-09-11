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
| 1 | `recommended_next_action` carries a routing verb, so the end-of-review button asked a child to "Wait for student response" | ~~High~~ **Resolved** |
| 2 | No topic title on `Phase4ReviewResponse`, so every review is headed "This topic" | ~~Medium~~ **Resolved** |
| 3 | A wrong Phase 3 attempt produced no tutor replay | **Still open** |
| 4 | Session phase and journey phase disagree on the same student | **Still open** — Saravanan |

---

## Status — updated 11 September 2026, after PR #271

Chiru shipped **asks 1 and 2** the same day (`d317456`, merged and already
deployed to the VM). Re-verified against the live API on ST015:

| Field | Before | Now |
|---|---|---|
| `topic_outcome.recommended_next_action` | `WAIT_FOR_STUDENT_RESPONSE` | `CONTINUE` |
| `phase4_review.topic_info.title` | absent | `"What Is Algebra?"` |
| `topic_outcome.next_action_message` | `null` | populated |

The frontend side is deployed too (`8280a35`): `sessionTopicTitle` reads
`topic_info.title` once the orientation bundle is gone, and the client's
`WAIT_FOR_*` workaround has been **removed** — the backend owns that vocabulary
now, and keeping a second copy of the rule is how the two drift apart.

**On the backend suite:** 42 tests pass across the four files PR #271 touched.
The full suite reports 861 passed / 26 failed, but every one of those 26 is
under `app/services/rag/` and fails *identically on the pre-merge commit*
(`4050422`) with a connection refused to `localhost:8002`. They are
environmental and pre-existing — **not** PR #271.

`student_facing_next_action` went further than this document asked for: a closed
derived set (`START_NEXT_TOPIC` / `PRACTISE_AGAIN` / `KEEP_LEARNING` /
`CONTINUE`), unmapped verbs falling back to `CONTINUE` *and logged*, and a note
pointing at `topic_summary_insights.generate_recommended_next_action` so the
table gets retired rather than grown. The closed set is what made it safe to
delete the client-side guard.

### Still open

**Ask 3** — unchanged. PR #271 was scoped to asks 1 and 2, so nothing was
skipped; the question below still needs an answer.

**Ask 4** — unchanged, and still Saravanan's call.

**New, and small: `next_action_message` never reaches the screen for this
student.** It renders only inside `FeedbackRail`, which requires a selected
replay — and `tutor_replays` is empty on the no-wrong-answers path, so the
sentence is generated and then discarded on exactly the run that went best.
Moving it onto `LearningSummary` is a UI decision rather than a backend one, so
the frontend has not changed it unilaterally. Say the word either way.

**Timing note, not a defect:** `GET /session` at Review can exceed 7 seconds
while the review generates. Students see the skeleton, so nothing is broken —
worth knowing when testing, because a short wait makes the screen look like it
fell back to the old review.

---

## 1. `recommended_next_action` is being fed the routing verb — RESOLVED

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

**Done, and the stopgap is gone.** `student_facing_next_action()` in
`phase4_context_builder.py` now translates the routing verb and exposes the
closed set as `STUDENT_FACING_NEXT_ACTIONS`, derived from the map so the two
cannot drift. The client-side `WAIT_FOR_*` filter has been deleted (`8280a35`) —
with the vocabulary owned server-side, a second copy of the rule is a liability
rather than a safety net. Tests now pin the pass-through, prose included.

---

## 2. `Phase4ReviewResponse` never sends the topic title — RESOLVED

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

**Done.** `topic_info` is on the response and overwritten from the request after
generation, so the model cannot invent a topic name. `sessionTopicTitle` reads
it once the orientation bundle is gone (`8280a35`); the bundle still wins where
both exist, so the header does not change wording mid-journey.

The client still does **not** resolve a name from the topic code, and should not
start: that is QA row 42, where it guessed from its own table and labelled a
review "Linear equations" for a student who had spent the lesson on "What Is
Algebra?". Printing "This topic" was the better failure, and now neither is
needed.

---

## 3. A wrong Phase 3 attempt produced no replay — is this expected? (STILL OPEN)

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

## 4. Saravanan / Chiru — session phase and journey phase disagree (STILL OPEN)

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
