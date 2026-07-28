# Frontend test status

**2026-07-28 · Manav** · verified against the live VM (https://nablix.ai/app/), not locally.

Read the two lists below as: what is proven, and what nobody has checked yet.
The second list is where the next bug will come from.

---

## Verified working

Full run as a **basic-tier** student (same tier as Manjusha's account), end to end:

| # | Check | Result |
|---|---|---|
| 1 | Lands on the diagnostic, not the lesson | `/app/diagnostic/algebra/` |
| 2 | No mock `2x + 5 = 13` anywhere | pass |
| 3 | Tutor's opening message shown + spoken | pass |
| 4 | One question at a time | pass |
| 5 | Step rail is read-only (can't skip ahead) | pass |
| 6 | Transition paced by the voice | 6380 ms (was 420 ms) |
| 7 | Routes to orientation | pass |
| 8 | Arrival hand-off message | pass |
| 9 | Video → worked-example hand-off message | pass |
| 10 | YouTube embed, not the 163 MB MP4 | pass, no `<video>` element |
| 11 | Worked example on canvas, one step at a time | pass |
| 12 | Auto-advances to Phase 2 | orientation → `/app/` |
| 13 | Log out lands on `/login`, fully signed out | pass |
| 14 | No logout / voice picker / "Need help?" on login | pass |
| 15 | **JS errors across the whole run** | **none** |

Also verified:

- **Both diagnostic branches.** All answers correct → `DIAGNOSTIC_NO_GAPS` →
  Independent Practice. Wrong answers → gaps → orientation.
- **All 21 routes** serve and render, with zero JS errors.
- **Failure states.** With a deliberately invalid token, the lesson and practice
  screens show the backend's real reason and a working retry, instead of a blank
  canvas or "Loading question…" forever.
- **Login `Enter`** submits (it previously had no `<form>`, so only the button worked).
- **Responsive** at 390×760 and 1512×805.
- 73 unit tests, `tsc` clean, deployed bundle byte-checked against the local build.

---

## NOT tested — assume these are unproven

These need a human. They are the most likely source of the next report.

| Area | Why it's untested | What to check |
|---|---|---|
| **Voice input** | Can't speak into a mic from an automated browser | Muted really is silent; speech reaches the tutor and gets a reply |
| **Canvas OCR** | Needs real drawing input | Write working, tap Check, confirm the tutor marks it |
| **Guided practice (Phase 2)** | Flow reaches `/app/` but questions weren't answered against the backend | Answer a question, get a real tutor reply |
| **Teach-back** | Unreachable — the backend skips `TEACH_BACK` (backend ask #4) | Nothing to test until the backend routes into it |
| **Review / Challenge** | Render, but their logic wasn't driven | Complete a session and read the review |

A known-fragile detail: the mic mute fix closes a race between `stop()` and an
in-flight `getUserMedia`. It was verified by reading the code and removing the
render-loop that triggered it — **not** by a human muting mid-sentence. Worth an
explicit test.

---

## Backend state (2026-07-28, 14:00)

Probed live. Everything healthy except one thing.

| Endpoint | Status |
|---|---|
| `GET /api/health` | 200 |
| `POST /nablix-auth/auth/login` | 401 on bad creds — alive and correct |
| `POST /api/session/start` | 200 |
| `POST /api/hint/request` | 409 "Hints are not available during DIAGNOSTIC" — correct |
| `WS /api/voice/stream` | 404 on a plain GET — normal, it's WS-only |
| `POST /api/voice/tts` (no provider) | **502** |

### The one live problem

**Inworld has no credits.** From the backend log:

```
Inworld TTS failed: status=402
{"code":7,"message":"You have no credits remaining. Please add credits to continue using the service."}
```

39 TTS failures in 25 minutes, all this. `VOICE_TTS_PROVIDER` is set to
`inworld`, so any call without an explicit provider 502s too. This is billing,
not code — it worked before because the account had credits.

Provider check: **openai 200 · cartesia 200 · deepgram 200 · inworld 502.**

The frontend now names a provider explicitly, retries onto a working one, and
remembers the failure for the session — so students get a real tutor voice
rather than browser speech. That's a workaround, not the fix.

**Two asks:** top up Inworld, and point `VOICE_TTS_PROVIDER` at a provider that
works.

### Fixed since this morning ✅

- `DUPLICATE_REQUEST` session-start outage — `request_id` now carries a UUID
- `student_code` now ships on `/auth/login`

### Still open

See [BACKEND-NOW.md](./BACKEND-NOW.md): session resume, `TEACH_BACK` never
running, and the answer key being sent to the browser.

---

## How to re-run this

Deploy with the exact command in [DEPLOY.md](./DEPLOY.md) — a build without
`NEXT_PUBLIC_API_BASE_URL` silently runs the whole app on demo data.

```bash
npx tsc --noEmit && npx vitest run
```

Then load https://nablix.ai/app/ signed in and walk the table above.
