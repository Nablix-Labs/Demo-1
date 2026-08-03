# Topic 1 Phase 2 (Guided Learning) — frontend behaviour + what the backend needs to expose

**Written by:** Manav (frontend) · 3 Aug 2026
**Against:** `main` @ `9b08e78` (Chiru's Schema 3.0 refactor, merged 1–3 Aug)
**For:** Chirudeva (tutor backend), Sanya (content), Manjusha (visibility)
**Frontend status:** implemented and merged as `cb5bc7b` — see Part F

This is a read of the Phase 2 Guided Learning spec against the backend as it
stands today. Most of the spec's *concepts* already exist server-side — the gap
is almost entirely about **what reaches the frontend on the `/interaction`
response**. Several asks below are pass-throughs of data the backend already
computes and then drops.

**Read Part F first if you are planning the Demo-4 backend work.** It is the
per-field contract: what the frontend already does with every response field it
receives, so you can see exactly which behaviour switches on when a field starts
arriving. Nothing in Part F needs a frontend change to activate — the handling is
merged and inert until the data shows up.

---

## Part A — What changed in Chiru's refactor (verified, not assumed)

Six commits, ~1,700 lines net removed. Verified by reading the diffs and running
the suite.

| Change | Effect |
|---|---|
| `interaction_service.py` no longer imports `get_next_question` | **The guided-practice bank fallback is gone.** |
| `_start_legacy_session` replaced with a hard 409 (`session_service.py:170`) | `initial_phase` sessions are rejected outright. |
| `app/api/hint.py`, `app/services/hint_service.py`, `app/models/hint.py` deleted | **`POST /hint/request` no longer exists.** |
| `HINT_REQUEST` removed from `InteractionType` | No interaction type for an explicit hint request. |
| `InputSource` gains `CANVAS` | Canvas turns are now first-class. |
| `turn_id` / `previous_tutor_turn_id` / `transcript_final` on requests; `accepted_turn_id` / `tutor_turn_id` / `retry_safe` / `attempt_increment` on responses; new `StaleTurnResponse` | The turn-sync contract landed. |

**The `ALG_1STEP_GP_F01` 409 that killed sessions on 29 and 31 July should be
fixed by this.** The mechanism that caused it — advancing onto a Qdrant bank
question and then validating that id against the authored `question_set` — no
longer exists in the code path. Worth one confirming run on the VM before we
call it closed.

The new 409 is a different, healthy thing: a stale-turn guard that returns
`StaleTurnResponse` and tells the client to retry. It does not kill the session.

### Test state on `main`

`pytest tests/` → **37 failed, 277 passed**. Breakdown:

- **28** — shared fixtures still call `/session/start` with `initial_phase`, which
  now correctly 409s. Stale tests, not broken code.
- **2** — reference the removed `get_next_question` / assert old hint routing.
- **6** — same fixture cascade in `test_validation.py` / `test_session.py`.
- **1** — `test_cors_allows_local_frontend_preflight`: my local `.env` override,
  pre-existing, not Chiru's.

So: **no evidence of a real regression**, but the suite needs updating before it
can catch the next one. Right now it's red, which means it protects nothing.

`test_retrieval_gated_on_guided_hint` fails with zero RAG documents returned —
that may just be Qdrant being unreachable from my machine. Needs checking on the
VM, not from here.

### Frontend state against this backend

`tsc --noEmit` clean, **124/124** vitest passing. The frontend never sends
`initial_phase` and only sends `ANSWER_SUBMISSION`, so nothing else breaks.

---

## Part B — What is broken right now

### B1. "Need help?" cannot request new support — partially worked around

`hooks/useDemoTutor.ts` called `POST /hint/request`. That endpoint was deleted.
Every press 404'd and the student saw "no hint available" regardless of what
support the tutor had actually authorised.

**Worked around in `cb5bc7b`, but only halfway.** The frontend now climbs the
rungs the turn response already carries — the GIVE_HINT message, the visual cue,
the scaffold step — one at a time, resetting per question. The dead endpoint
client is deleted. So the button no longer lies.

What it still cannot do is **ask for support the backend hasn't already sent**.
Escalating a student up the ladder is the Tutor Backend's decision — it depends
on attempt history and the Student Model — and there is no longer any way for the
student to trigger that decision without submitting an answer, which costs them
an attempt.

**Ask:** one request meaning "give me the next approved support item", carrying
no answer. Either `HINT_REQUEST` back as an `interaction_type` on `/interaction`,
or a small `POST /support/next`. Either shape is fine. It should return
`attempt_increment: 0` and whichever rung it authorised.

---

## Part C — What Phase 2 needs that the response doesn't carry

The spec's language is all about **partial credit inside a single question**:

> "Your letter and fixed number are right. Let us check only the operation."

Today `InteractionResponse` gives the frontend `message`, `conversation_action`,
`answer_value_confirmed` (a bool) and `hint_count`. That is enough to print a
sentence. It is **not** enough to draw:

```
n  -  5
✓  ?  ✓
```

Ranked by how much of the spec each one unblocks.

### C1. Per-turn classification and partial-credit detail — **the big one**

The backend already computes this. `GuidedEvaluation` (`models/guided_learning.py`)
carries `student_state: CORRECT | PARTIAL | WRONG | STUCK | UNCLEAR` — exactly
the spec's four branches — plus `ActiveTeachingObjective` with
`confirmed_concept_ids` and `missing_concept_ids`, which *is* the spec's
`resolved_answer_steps` / `first_unresolved_answer_step`. `selected_error_code`
is right there too.

None of it reaches `InteractionResponse`.

**Ask:** add three pass-through fields —

```
guided_student_state:      "CORRECT" | "PARTIAL" | "WRONG" | "STUCK" | "UNCLEAR"
active_teaching_objective: { confirmed_concept_ids[], missing_concept_ids[] }
selected_error_code:       string | null
```

This should be close to free — the values already exist on `TutorResult` inside
`run_tutor_pipeline` and are discarded when the response is assembled.

Without it we cannot build AFFIRM-THEN-ISOLATE, which is most of sections 3B, 4B
and 7 of the spec. With it, nearly all of it becomes frontend work.

### C2. Which rung of the ladder we're on

`SupportUsed` (`NONE / HINT / VISUAL_CUE / SCAFFOLD / PARALLEL_EXAMPLE /
TUTOR_SOLVED`) already matches the spec's section 6 ladder exactly. But the
frontend only sees `hint_count: int` — an integer, not a rung.

**Ask:** `current_support_level` and `highest_support_used` (both `SupportUsed`)
on the response. The spec uses highest-support-used to pick Phase 3 difficulty,
so we'd also want it on the phase-completion payload.

### C3. Explain Again must not count as an attempt

Spec: *"Replays the current concept visually without counting as an attempt."*

`attempt_increment` exists on the response and can be `0`, so the backend side is
half-built. What's missing is a request that means "replay, don't grade" — there
is no interaction type for it.

**Ask:** an `EXPLAIN_AGAIN` interaction type (or a flag) that returns the current
visual cue with `attempt_increment: 0`.

### C4. STUCK escalation — 1 → 2 → 3

Spec: first STUCK narrows the question, second opens the scaffold, third routes
to prerequisite repair.

`GuidedStudentState` has `STUCK`, and `GuidedSupportEvent` has
`GUIDED_SUPPORT_ESCALATION_REQUIRED` / `MAXIMUM_GUIDED_SUPPORT_REQUIRED`, so the
machinery exists. What the frontend can't see is the **consecutive** STUCK count,
and there's no field naming the prerequisite to repair (spec: `T01.M2 — Identify
the changing quantity`).

**Ask:** `consecutive_stuck_count: int`, and on the third, a
`prerequisite_repair: { micro_skill_id, return_to_question_id }`.

I'd rather the counter lived in the backend than in the frontend — it has to
survive a reconnect, and our store doesn't persist across a dropped socket.

### C5. Structured scaffold slots and option tiles

`ScaffoldPanel.tsx` exists and works, but `scaffold_step_text` is a plain string.
The spec needs typed slots:

```
Scaffold Step 3 — "Complete the structure."
   n  [operation]  5
   tiles:  +   −   ×
```

**Ask:** on each scaffold step, a `response_kind` (`"free_text" | "choice" |
"slot_fill"`) and, for `choice`, the options. Also the spec's rule that the
assembled answer **disappears** before the final independent rewrite — that's a
step-level flag, something like `clears_previous_slots: true`.

### C6. A typed vocabulary for visual cue actions

`VisualCue.actions` is `list[dict[str, object]]` — untyped. The spec asks for
specific animations: the left value cycling `3 → 9 → 14 → n`, the three plus
signs pulsing once, dimming the changing values.

We can render any of those, but not against an untyped dict — we'd be
pattern-matching on keys and it would silently break the first time content
changed a name.

**Ask:** a small closed vocabulary agreed between Sanya and me, e.g.
`{ op: "cycle" | "pulse" | "dim" | "highlight", target: string, values?: string[] }`.
Three or four verbs covers everything in this spec. Happy to draft it.

### C7. Parallel example — no support at all

Rung 5 of the ladder (split canvas, structurally similar problem) has no
representation anywhere in the response. Lowest priority — it's the rung we reach
least often — but flagging it so it isn't discovered late.

---

## Part D — Frontend work, no backend needed

For completeness, so nobody waits on us. All of this is mine:

- Question strip, evidence area, work area, build strip layout (section 2)
- Silence-while-writing: suppress tutor speech once the student starts drawing
- Highlight → pause → speak sequencing
- Never auto-erasing student work; correction drawn beside the attempt
- Tutor marks in accent colour and not student-erasable
  (`TutorLayer.tsx` / `TutorMathOverlay.tsx` already do this)
- Interactive counter widget for Q-T01-006
- Progress rail showing question progress, not mastery labels

The tutor-writing contract (`CanvasDrawPayload` / `TutorElement`) is in good
shape — normalised coordinates, `highlight` and `math` kinds, `append` vs
`replace`. Everything the spec draws is expressible in it today.

---

## Part F — Frontend behaviour contract (start here for Demo-4 planning)

What the frontend does with each field today. Everything marked **live** is
merged in `cb5bc7b` and working; everything marked **inert** is written, tested
and waiting for the field to start arriving — no frontend change needed to
switch it on.

### Fields we consume today

| Response field | What the frontend does | State |
|---|---|---|
| `message` / `message_voice` | Shown in the transcript and spoken. Speech is dropped (not queued) if the student is mid-stroke. | live |
| `conversation_action == "GIVE_HINT"` | The message is stored as rung 1 of the support ladder, so "Need help?" can re-open it. | live |
| `canvas_draw[]` | Rendered on a separate non-erasable tutor layer, revealed like handwriting. When present, speech is delayed ~700 ms so the mark lands before it is described. | live |
| `show_visual_cue` / `visual_cue` | Opens the cue card; also becomes rung 2 of the ladder and the source for "Explain again". | live |
| `show_scaffold_panel` + `scaffold_step_*` | Renders the one authorised step on the canvas. Rung 3 of the ladder. | live |
| `current_question` / `question_id` | Drives the question strip. A null question on a phase change clears it; a null mid-phase does not. | live |
| `question_set` on the session record | Denominator for the progress rail. Hides if absent — it will not invent a position. | live |
| `turn_id` / `tutor_turn_id` / `status` | Full turn-sync contract: stale and duplicate turns are dropped without appending or speaking. | live |
| `expects_student_response` / `allow_voice_input` | Half-duplex mic gating. The mic reopens from the speech-end callback, which fires even when speech was silenced. | live |
| `attempt_increment` | Read, but nothing sends a request that would produce `0` yet (see C3). | live |

### Behaviour that is written and waiting on a field

| Behaviour | Switches on when we receive | Ask |
|---|---|---|
| AFFIRM-THEN-ISOLATE (`✓ ? ✓` under a partial answer) | `guided_student_state` + `active_teaching_objective.{confirmed,missing}_concept_ids` | C1 |
| Ladder rung shown in the UI, Phase 3 difficulty carry-over | `current_support_level` / `highest_support_used` | C2 |
| Explain Again as a real replay rather than a local re-show | an `EXPLAIN_AGAIN` request returning `attempt_increment: 0` | C3 |
| STUCK 1 → 2 → 3 routing and prerequisite repair | `consecutive_stuck_count`, `prerequisite_repair` | C4 |
| Build-strip slots and operation tiles | `response_kind` + options per scaffold step | C5 |
| Cue animations (cycling, pulsing, dimming) | a typed `visual_cue.actions` vocabulary | C6 |
| Parallel example (split canvas) | any field at all — nothing exists today | C7 |

### Rules the frontend enforces on its own

No backend involvement needed; listed so nothing double-implements them.

- Tutor speech stops the moment the student starts writing, and is **not**
  replayed when they stop — the spec says wait for them to submit or ask.
- Tutor marks are drawn on a layer the student cannot erase; student work is
  never auto-erased, and corrections are drawn beside the attempt.
- The canvas locks while a submission is in flight, and unlocks on failure with
  the student's work intact.
- The support ladder never walks backwards, and resets per question.
- The progress rail is read-only — it reports progress, it does not let a
  student skip ahead of the phase the backend has them in.

### One thing to be careful of

If you add the `/support/next` request (B1), it must **not** be routed through
the same path as an answer submission. The whole point of the Need Help control
is that it does not cost an attempt, and the spec is explicit that Explain Again
doesn't either. `attempt_increment: 0` on both.

---

## Part E — Content, not code (Sanya)

Section 8 of the spec lists these itself:

- `Q-T01-002` error mappings — `ERR-T01-ROLES-SWAPPED`, `ERR-T01-OPERATOR-AS-VALUE`
- Scaffold `SCF-T01-IDENTIFY-M-PLUS-7`, with steps specific to `m + 7`
- `SCF-T01-COUNTER-RULE` for Q-T01-006

---

## Summary

| # | Ask | Effort | Unblocks |
|---|---|---|---|
| C1 | `guided_student_state` + `active_teaching_objective` + `selected_error_code` | Small (pass-through) | AFFIRM-THEN-ISOLATE, most of the spec |
| B1 | A request for the next support item, `attempt_increment: 0` | Small | Asking for help without spending an attempt |
| C2 | `current_support_level` / `highest_support_used` | Small | Ladder UI, Phase 3 difficulty |
| C3 | `EXPLAIN_AGAIN` with `attempt_increment: 0` | Small | Explain Again as a real replay |
| C6 | Typed visual cue action vocabulary | Small | Section 3C animations |
| C4 | `consecutive_stuck_count` + `prerequisite_repair` | Medium | STUCK 1→2→3 routing |
| C5 | Typed scaffold slots and tiles | Medium | Build strip |
| C7 | Parallel example surface | Medium | Ladder rung 5 |

**C1 is the one to do first.** It is a pass-through of values
`run_tutor_pipeline` already computes and discards, and it unblocks
AFFIRM-THEN-ISOLATE — which is most of sections 3B, 4B and 7 of the spec, and the
single biggest difference between "wrong, try again" and the tutor the spec
describes. B1 is next, and cheap.

The frontend handling for every row above is already merged and tested, so each
one lights up as soon as the field arrives — no coordinated release needed, and
they can land in any order.

Anything ambiguous here, ping me and I'll adjust the frontend to whatever shape
suits the backend — the shapes above are suggestions, not requirements. The only
hard constraint is the one in Part F: help and replay must not cost an attempt.

Also worth doing regardless: fixing the 28 stale `initial_phase` fixtures so the
suite is green again and can catch the next regression.
