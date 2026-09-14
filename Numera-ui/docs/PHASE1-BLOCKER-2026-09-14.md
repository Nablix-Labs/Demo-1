# Phase 1 → Phase 2 is blocked for everyone — 14 September 2026

**From:** Manav (frontend)
**For:** Sanya
**Reported by:** Sanya ("i am not able to go ahead from phase 1", 15:27 +04)
**Broken since:** 11:24 UTC (15:24 +04). Still broken at time of writing.
**Cause:** PR #21 — a schema change that shipped without the file that applies it.

---

## Summary

`POST /orientation/complete` returns **503** for every student. Nobody can leave
Phase 1. The Student Model 500s because its ORM declares a column the database
does not have.

| | |
|---|---|
| Missing column | `nablix_content.question_guided_start_prompts.canvas_submission_required` |
| Introduced by | PR #21 `d7db4e0` "Scope guided prompts by phase", merged 13:32 +04 |
| Deployed | 10:41 UTC — `mathtutor-student.service` restarted |
| First failure | 11:24 UTC — the first student to finish orientation afterwards |
| Occurrences | 54 |

Nothing on the frontend is involved. The frontend deployed at 08:18 UTC, three
hours before the first failure, and its only part in this was bad error copy —
fixed separately, see the last section.

---

## Evidence

Tutor backend (`nablix-backend.service`), 11:24:42 UTC:

```
Request: POST /session/SESSION6f525173d4e24beba35dd9044b9f279b/orientation/complete
adapter_error  adapter_name=student_model
  url=https://nablix.ai:8080/session/event status=500 body=Internal Server Error
  payload={'event_type': 'ORIENTATION_COMPLETED', 'topic_id': 'ALG-KS3-01',
           'student_id': 'ST019', 'expected_journey_version': 3,
           'target_micro_skill_ids': ['T01.M1' … 'T01.M7']}
method=POST path=…/orientation/complete status_code=503
```

Student Model (`mathtutor-student.service`), same second:

```
app/services/session_handlers.py:217  handle_orientation_completed
  app/content/serialize.py:187        serialize_guided_set
  app/content/serialize.py:155        repo.guided_start_prompt_for_question(...)
  app/content/repository.py:108

sqlalchemy.exc.ProgrammingError: (psycopg.errors.UndefinedColumn)
  column question_guided_start_prompts.canvas_submission_required does not exist
[parameters: {'question_id_1': 'Q-T01-001', 'phase_1': 'PHASE_2_GUIDED_LEARNING'}]
```

The live table, checked directly:

```
start_prompt_id · question_id · phase · tutor_prompt · canvas_action · active
```

Six columns. `canvas_submission_required` is not one of them. `app/content/models.py:385`
declares it `nullable=False`.

---

## Root cause

PR #21 added the column to the ORM and shipped the alembic revision
`migrations/versions/0028_guided_canvas_submission_policy.py`.

It did **not** ship `migrations/sql/0028_guided_canvas_submission_policy_up.sql`.

Every migration from 0004 to 0027 has that `_up.sql` / `_down.sql` pair, and those
are what actually get applied on the VM. 0028 is the only one without it, so it
fell outside the path the schema is deployed through. The code went out; the
column never did.

---

## Do NOT run `alembic upgrade head`

I suggested this before checking, and it is wrong. On the VM:

```
identity.alembic_version  →  0003
migration files present   →  0004 … 0028
```

Alembic believes the database is at 0003. It is not — the schema is current,
applied through the SQL pairs. `upgrade head` would replay twenty-five migrations
against a database that already has them.

---

## The fix

The body of 0028. Both statements are idempotent and touch one table:

```sql
ALTER TABLE nablix_content.question_guided_start_prompts
  ADD COLUMN IF NOT EXISTS canvas_submission_required BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE nablix_content.question_guided_start_prompts
   SET canvas_submission_required = TRUE
 WHERE phase = 'PHASE_2_GUIDED_LEARNING'
   AND question_id IN ('Q-T01-001', 'Q-T01-006');
```

```bash
sudo -u postgres psql -d mathtutor     # paste the two statements
sudo systemctl restart mathtutor-student.service
```

Then please add `migrations/sql/0028_guided_canvas_submission_policy_up.sql` and
its `_down.sql`. Without them the next person who builds the database from the
SQL directory gets this same outage.

---

## Blast radius

`serialize_guided_question` is called from six places in `session_handlers.py`,
not only `ORIENTATION_COMPLETED`. Every Phase 2 guided question serve runs the
same query, so Phase 1 → 2 **and** Phase 2 turns are both affected. Worth a pass
over Phase 2 after the column lands, rather than assuming orientation was the
only casualty.

---

## One process note

Deploying the service does not apply migrations. The code went out at 10:41 and
nothing failed until a student walked into it at 11:24. Forty-three minutes of
green, then a hard outage — and because both a frontend and a backend deploy
happened today, the first assumption in the group was that the frontend broke it.

A startup check that refuses to boot when the ORM and the schema disagree would
have caught this at 10:41 with a clear message, instead of at 11:24 as a 503 in
a student's face. Not mine to build — raising it for whoever owns deploy.

---

## The frontend's part in this, for completeness

`OrientationClient.tsx` caught the 503 with a bare `catch {}` and told the
student *"Couldn't mark this as done. Please try again."* — so Sanya retried
seven times in three minutes against a server that could not succeed, and the
status never reached the console. It read as a frontend fault when it was not.

Fixed in `9f32c94`, deployed. Both orientation calls now go through
`studentFacingError`, which names the failing service, and log the status. The
same 503 today would say *"The tutor service hit an error on its side. Nothing
you did."*

This did not cause the block and does not fix it. The column does.

---

## Still open from this morning

Separate from the above, items 4–6 in `PHASE2-VOICE-INCIDENT-2026-09-14.md` are
still yours and still open — identical `tutor_message_sha256` on four turns with
differing student input, `raw_student_state=PARTIAL` downgraded to `UNCLEAR` at
0.94+ confidence, and `consecutive_stuck_count` stuck at 0 through repeated
failure. Manjusha's note about misconception mapping producing irrelevant hints
most likely sits with those.
