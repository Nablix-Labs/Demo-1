# Backend asks — 29 July 2026

**From:** Manav (frontend)
**Everything below was reproduced on the live VM** (`https://nablix.ai/app/`) against a
real signed-in student, not inferred from code. Request ids and question ids are
included so you can go straight to the log line.

There are four asks. One is blocking a student flow right now.

| # | For | What | Severity |
|---|---|---|---|
| 1 | **Saravanan** (Student Model) | A guided-practice question has no metadata — every answer on it fails | **Blocking** |
| 2 | **Chiru** (Tutor Backend) | Phase 2 scaffold fields aren't live yet; frontend is built and waiting | Blocking Phase 2 |
| 3 | **Sanya** (Tutor Backend) | Session resume, and a 409 that reports the wrong cause | High |
| 4 | **Aditya** (Voice) | Confirm the tier→provider mapping is what you expect | Confirmation only |

---

## 1. Saravanan — `ALG_1STEP_GP_F01` has no Student Model metadata

**This is the one to look at first.** It breaks guided practice for a real student
account today.

A student in `GUIDED_PRACTICE` submits an answer. `POST /api/interaction` returns:

```
409
{
  "error_code": "HTTP_ERROR",
  "message": "Student Model did not return metadata for ALG_1STEP_GP_F01.",
  "request_id": "REQCCC339F4",
  "timestamp": "2026-07-29T09:24:45Z"
}
```

Reproduced on `manav@example.com` / `ST015` / `SESSION015`. Every answer on that
question fails the same way, so the student cannot move forward — the tutor
simply stops responding to them.

The question was served by the backend itself: the student was routed into
guided practice, shown `Solve for x: x + 6 = 10` with `question_id:
ALG_1STEP_GP_F01`, and then the Student Model had nothing for it. So it is
reachable in the normal flow, not a stale id we invented.

**Ask:** either add the metadata for `ALG_1STEP_GP_F01`, or stop serving it. It
would also be worth checking whether other `ALG_1STEP_GP_*` ids are in the same
state, since this one was reached by simply playing the flow through once.

---

## 2. Chiru — Phase 2 scaffold response fields

The Phase 2 frontend handoff (§12) lists commits **`7dc6549`** and **`b56cb58`**
as prerequisites. Neither is in `Nablix-Labs/Demo-1` — `git cat-file` cannot
find them on `origin/main`. I also captured a live `/interaction` response and
none of the scaffold fields are present.

**What is already built and deployed on our side**, inert until you ship:

- `InteractionResponse` extended with the seven fields from §4 —
  `show_scaffold_panel`, `scaffold_id`, `current_scaffold_step_id`,
  `scaffold_step_number`, `scaffold_step_text`, `scaffold_step_voice`,
  `total_scaffold_steps`
- A one-step panel that renders exactly what it is given, with "Step 1 of 3"
- Voice following the authorised step (`scaffold_step_voice`, falling back to
  `message`)
- 13 acceptance tests from §10

**Ask:** push and merge those commits, then tell me and I'll integrate against a
real response the same day. Two things I'd like confirmed when you do:

- **One step per response.** `SessionRecord.scaffold_steps` currently carries the
  whole catalogue. We do not read it and never will — §9 forbids it — but it is
  being sent to the browser, so anyone with devtools can read every step of every
  scaffold. Worth removing from the student-facing payload.
- **`expected_response` must not appear on `InteractionResponse`.** §4 says the
  Student Model may supply it internally so the Tutor can grade. It must not
  travel any further than that.

---

## 3. Sanya — session resume, and a 409 that reports the wrong cause

**3a. Two different failures share one status code.** We were mapping `409` to
"you already have this topic in progress", which is right for the resume case
and badly wrong for anything else — the metadata failure in ask #1 came back as
`409` and students were told their topic was in progress. That was our bug and
it is fixed, but it cost real debugging time.

**Ask:** give the resume case its own `error_code` (e.g. `TOPIC_IN_PROGRESS`)
rather than sharing `HTTP_ERROR`. Then the frontend can branch on the code
instead of guessing from the message text.

**3b. Session resume, still open from 28 July.** A tutoring session lives in
backend memory and its id is not persisted anywhere the student can recover. A
returning student — anyone who reloads the page — has no way back into the
session they were in, and gets a 409 if they try to start the topic again.

Observed today: after completing orientation, navigating back to
`/app/orientation/algebra/` produced a `409` and the student was routed to the
diagnostic to start over.

**Ask:** either an endpoint to resume an in-progress session for a student, or a
documented way to end/reset one from the client so the student can start cleanly
instead of being stuck.

---

## 4. Aditya — tier → provider, please confirm

No bug here. We changed how the frontend picks a provider and I want you to
confirm it matches your intent before Manjusha tests it again.

**What the frontend now does**, on both transports:

| Tier (`identity.user_credentials.tier`) | Provider | Default voice |
|---|---|---|
| `premium`, `enterprise` | `cartesia` | Skylar — `db6b0ed5-d5d3-463d-ae85-518a07d3c2b4` |
| `basic` | `inworld` | `Ashley` |
| anything else / missing | none sent — backend default applies | — |

- The student never picks a provider, only a voice within their tier's provider.
- Nothing picked no longer means "server env default" — it means "my plan's
  voice", resolved on every call.
- **We removed the cross-provider fallback.** It used to switch to the first
  other provider in the catalogue on failure, which was OpenAI, and it never
  switched back. A premium student is now Cartesia or browser speech, never
  someone else's voice.

Verified live on a premium account: 24 TTS calls across a full diagnostic and
into guided practice, one voice throughout, including on the WebSocket:

```
wss://nablix.ai/api/voice/stream?session=SESSION015&student_id=ST015
  &tts_provider=cartesia&tts_voice=573e3144-a684-4e72-ac2b-9b2063a50b53
```

**Two asks:**

1. Confirm `basic → inworld` and `premium → cartesia` is right, and tell us what
   `enterprise` should be — we assumed Cartesia.
2. `VOICE_TTS_PROVIDER` on the VM still points at a provider that 502s when no
   provider is named. We always name one now so students are unaffected, but any
   other client hitting `/voice/tts` without one will fail. Worth repointing.

---

## What the frontend has already handled, for information

So nobody spends time on these:

- Diagnostic, orientation, guided practice, review and the library screens all
  render with zero JS errors across 21 routes, at desktop and mobile widths.
- Duplicated chat bubbles and the question disappearing from the canvas — both
  from Manjusha's 29 July recording — were frontend bugs and are fixed.
- The screens turning dark mid-session was WebGL context loss on our side.

## Still unproven, honestly

- The scaffold panel has never rendered a real backend response, because one
  does not exist yet (ask #2).
- Voice **input** (speaking to the tutor) and canvas OCR still need a human with
  a microphone and a stylus. Automated testing cannot cover them.
