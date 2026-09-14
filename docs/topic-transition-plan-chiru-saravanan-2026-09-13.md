# Topic transition — implementation plan, Chirudeva and Saravanan

**Date:** 13 September 2026
**Source:** `docs/topic-transition-vm-verification-2026-09-13.md` §4
**Frontend half:** `docs/handoff-manav-topic-transition-2026-09-13.md`
**Ownership:** Chirudeva → `nablix-backend` (tutor) · Saravanan →
`mathtutor-student` (Student Model + curriculum) · Manav → `Numera-ui`

---

## Context

The blank-page bug is fixed and deployed. Two of its three causes are closed
properly. The third — static export — is not confined to refresh and deep-links
as the 13 Sep frontend reply frames it; it sits on the transition path itself.
And nobody has walked a real `next_topic_handoff` in either direction, because
the only test student's handoff is `null`.

The VM verification lists eight open items. After tracing the code, **one should
be deleted and one is asking for the wrong thing.** This document covers the five
that belong to us. Manav's four are in his own handoff.

---

## What changed after reading the code

| §4 item | Status after tracing |
|---|---|
| 1. Route shape | Held open deliberately. The sequencing in C1 makes it cheap to close. |
| 2. Second test student | Real, but **"never started a topic" is not what produces a handoff** — S1. |
| 3. `CONTENT_GAP` / `RESCUE_REQUIRED` | Root cause is one line. It is a **read**, not a design argument — S2. |
| 4. Expose curriculum topic codes | **Cut** — S3. A version already exists, and the option that needed it is the weakest one. |
| 9. Red `main` | Done in `39e099b`. |

---

## Chirudeva

### C1 — Item 1 stays open; close it *after* Manav's nginx fix, not before

The only argument against the sentinel catch-all is that it *"depends on nginx
answering RSC requests correctly, which is precisely the part that is silently
wrong today"* (VM doc §4.1). Manav's item 6 fixes exactly that, is correct
regardless of route shape, and is independent of it.

**Order: nginx fix → observe → then pick.** That turns a design argument into an
observation. Manav's handoff is written to this sequence.

The costs, recorded so the decision does not have to be re-derived later:

**Query param** (`/orientation?topic=ALG-ORI-02`) — one static file per route,
correct for any code forever, no nginx dependency, and it deletes item 4.
Non-obvious costs, all in `Numera-ui`:

- `lib/usePhaseRouting.ts:162` compares `target !== pathname`. `usePathname()`
  strips the query, so `'/orientation?topic=X' !== '/orientation'` stays true
  forever → **infinite `router.push` loop**. One line, but a trap rather than a
  detail.
- No `useSearchParams` anywhere in the repo today. Under `output: 'export'` it
  needs a `<Suspense>` boundary or the build fails, and there is no in-repo
  pattern to copy.
- `lib/__tests__/nextTopicHandoff.test.ts` asserts the literal URLs
  (`:24, :31, :41, :78`); `lib/__tests__/routeMatching.test.ts:53` asserts the
  nested form. Both get rewritten.

**Sentinel catch-all** — URLs unchanged, tests unchanged, no Suspense. Its whole
cost is the nginx behaviour that item 6 is fixing anyway.

**Build-time `generateStaticParams`** — reject. It needs the item-4 endpoint,
build-time network access to the Student Model, and it *still* goes stale between
deploys: a topic added after the last build fails identically to today's bug.
That is the failure mode the hardcoded-list proposal was rejected for, with more
machinery attached.

> Skipped: building both shapes so the decision can be deferred indefinitely.
> Add when the nginx observation genuinely fails to settle it.

### C2 — Item 3, tutor-backend half: change nothing yet

The restore guard is `nablix-backend/app/services/interaction_service.py:1438`
`_raise_content_gap` (409 `CONTENT_GAP`), reached from
`_initialize_restored_schema_phase` at `:1527-1534` and `:1631-1636`. Its
docstring at `:1444-1447` states the rule correctly. It stays.

The asymmetry is on this side too: `start_session`
(`app/services/session_service.py:708`) accepts the same upstream state. Its only
check is `_validate_session_opened_payload` (`:896`), whose phase-agreement test
at `:906-913` never looks at `content_gap_detected`, `status_code`, or
`rescue_state_by_skill`. That escape hatch is `73bd0f0` — the 4 Sep fix.

**Do not align the two paths pre-emptively.** The divergence originates upstream
(S2) and should disappear once the upstream answer is single-valued. After
Saravanan's diagnostic, re-check both paths and change only whichever is still
wrong. Aligning first re-introduces the bug that stranded ST015.

### C3 — Relay the S1 correction

The ask as written to Saravanan ("a student who has never started a topic") will
not unblock the transition test on its own. Send S1.

---

## Saravanan

### S1 — One new student, through the endpoint that already exists

`POST /admin/students` (`app/api/routers/admin.py:102` →
`app/services/identity_service.py:149`, body `StudentIn` at
`app/schemas/identity.py:54`) already creates a student with a chosen
`student_code`. Admin JWT; router-level `require_role("admin")` at `admin.py:24`.

> Skipped: a fixture or seed script. `app/seed.py:81` `seed_sample_student` does
> not set `student_code` and does not commit — it is the wrong tool. Write a
> script when this is needed a third time.

**The correction.** A fresh student does not, by itself, produce a
`next_topic_handoff`. The handoff is emitted only on review completion, and only
when `ContentRepository.next_topic_code(topic_pk)`
(`app/content/repository.py:327`) returns a successor —
`app/services/session_handlers.py:1468` in `handle_review_completed`. ST015's is
`null` because ST015 is on the **last** content-backed topic, not because of
anything to do with freshness.

So the requirement is: **a student who reaches review on a topic that has a
successor.** A brand-new student satisfies this for free — with no journey row,
`handle_session_opened` (`app/services/session_handlers.py:1346-1359`) creates a
Phase 0 journey at `next_topic_code(None)`, the *head* of the ordering. One
student unblocks Phases 0–3 verification **and** the transition walk.

Confirm the head is not also the tail before handing the student over:

```sql
SELECT t.topic_code FROM learning.topics t
WHERE t.topic_code IS NOT NULL
  AND EXISTS (SELECT 1 FROM nablix_content.micro_skills ms
              WHERE ms.topic_id = t.topic_code AND ms.status = 'ACTIVE')
ORDER BY t.topic_id;
```

Two or more rows → the new student will produce a handoff. One row → the
transition is untestable until a second topic has ACTIVE micro-skills, and *that*
is the blocker to report back.

Reusing an existing student is the longer path: `DELETE
/admin/students/by-code/{code}/transactions?dry_run=false` (`admin.py:118-136` →
`app/services/student_data_purge.py:45`) clears the transaction tables but **not**
`journey_state` (`student_data_purge.py:26-33`), so the student is not actually
fresh.

### S2 — Item 3: one read decides it, before any code changes

Both paths hit the same physical condition — no servable independent question —
and answer differently:

- `QUESTION_SET_REQUESTED` → `_content_gap()`
  (`app/services/session_handlers.py:90-113`) → `CONTENT_GAP` /
  `FRESH_CONTENT_UNAVAILABLE` / `WAIT_FOR_CONTENT`.
- `SESSION_OPENED` → `build_open_payload` → `_phase3`
  (`app/services/session_open.py:251`), whose exhausted branch at **`:278-279`**
  is bare:

```python
if not question_set.get("questions"):
    return _review(journey, block)
```

`_review` (`:285`) returns `REVIEW_SUMMARY` with no flag and the default
`StatusBlock()` is clean, so exhausted Phase 3 becomes REVIEW silently —
regardless of any outstanding `RESCUE_REQUIRED`.

**`:278` does not distinguish "nothing left to do" from "something left to do and
no content for it".** The `target` list built three lines above it
(`remaining_micro_skill_ids or target_micro_skill_ids`) is exactly that
distinction, and the branch ignores it.

**Do this first, and only this:** capture ST015's `SESSION_OPENED` response and
read `remaining_micro_skill_ids` off `journey_state` at that moment.

- **Empty** → REVIEW is correct, and `T01.M7`'s `RESCUE_REQUIRED` is stale state
  on a side-channel that no longer gates anything. The fix is to clear rescue
  state when its skill leaves the remaining set. Chiru's guard needs no change.
- **Non-empty, containing `T01.M7`** → REVIEW is a lie, and `:278` must branch on
  `target` to the `_content_gap` answer. Coordinate with C2 before shipping:
  `start_session` (`session_service.py:755-776`) already handles
  content-gap-with-no-payload without stranding, so confirm ST015 lands on the
  question-less session carrying `CONTENT_GAP_MESSAGE` and not on a 409.

> Skipped: a guard at `SESSION_OPENED` added on judgment. Both sides already
> agreed not to, and refusing that payload is what stranded ST015 on 4 Sep.

### S3 — Item 4 is cut

No new curriculum-codes endpoint. It exists only to serve the build-time
`generateStaticParams` option, which C1 rejects on the merits; the query-param
and sentinel options both work for any code without it.

A version already exists if it is ever wanted: `GET /authoring/topics`
(`app/api/routers/authoring.py:44,71` → `AuthoringRepository.list_topics()`),
admin-scoped, returning `topic_id` as the long code. Re-scoping that is a smaller
change than a new route.

Answer to Manav's question: *no endpoint — the route shape is being fixed so that
it does not need one.*

---

## Verification

**S1** — create the student, `POST /session/start` as them, confirm a Phase 0
diagnostic journey at the head topic. Drive to review completion and confirm
`POST /session/{session_id}/review/complete` returns a non-null
`next_topic_handoff` carrying both `topic_id` and `entry_phase`.
`nablix-backend/app/services/session_service.py:2481-2530` raises 503
`NEXT_TOPIC_HANDOFF_INVALID` rather than returning a half-built one, so a 200
with a handoff is proof rather than an indication.

**S2** — the diagnostic is a read and needs no verification. If it leads to a
change at `session_open.py:278`, the existing pins are
`nablix-backend/tests/test_content_gap_surfacing.py` (`:82, :170-187, :253,
:285`) and `tests/test_session_events.py:2633-2642`. A change that moves none of
those has not changed behaviour.

**C2** — after S2, re-run `test_content_gap_surfacing.py` and confirm the restore
path and `start_session` now agree for identical upstream state. That agreement
is the acceptance criterion, not a particular diff.

**End-to-end, which closes the whole thread** — new student → complete topic 1
review → follow the handoff → land on the new topic's orientation or diagnostic,
not the guided lesson. In the browser network panel, the `index.txt?_rsc=`
request for the new topic must return `text/plain`, not `text/html`. That single
request is the entire static-export bug.

---

## Scope

No new endpoints. No new scripts. No new dependencies. Two files may change
(`session_open.py:278` and wherever rescue state is cleared), and only if the S2
read says so.
