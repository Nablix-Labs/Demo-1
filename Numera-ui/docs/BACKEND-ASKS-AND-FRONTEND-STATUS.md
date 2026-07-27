# Numera — Backend asks & frontend status

**Date:** 2026-07-27
**Trigger:** Manjusha's frontend feedback (tutor writing overlap, canvas in Phase 1 orientation, word-problem questions, voice variants) plus the `AUTHENTICATION_FAILED` error reported on 2026-07-26.
**Scope:** What the frontend has shipped, and what the backend has to do for each item to actually work end to end. Written so the backend sections can be handed off directly.
**Frontend commits:** `826b68f` (canvas / orientation / word problems / auth copy, merged as PR #38) and `a786a5d` (voice variant picker). Both on `main`. Frontend only — no `nablix-backend/` file was changed.

---

## TL;DR

| # | Item | Frontend | Backend | Owner |
|---|------|----------|---------|-------|
| 1 | Auth — `AUTHENTICATION_FAILED` on a correct answer | ✅ Error copy fixed | ❌ **Blocker** — needs `/nablix-auth` proxy | Chirudeva |
| 2 | Tutor voice variants | ✅ Picker shipped | ❌ No per-request voice selection exists | Aditya |
| 3 | Word-problem questions | ✅ Renders any wording | ⬜ Just serve the text | Saravanan |
| 4 | Tutor writing on the canvas | ✅ Renderer + overlap fix | ⬜ `canvas_draw` producer still TODO | Saravanan / AI |
| 5 | Phase 1 concept check | ✅ Built with demo content | ⬜ Should serve question + drawing later | Saravanan |

**Only #1 and #2 are blocking.** #3 needs nothing but content. #4 and #5 are existing TODOs with a contract note attached.

---

# 1. Auth — `AUTHENTICATION_FAILED` (BLOCKER)

## What was reported

Voice appeared broken while chat worked. The error:

```json
{
  "error_code": "AUTHENTICATION_FAILED",
  "message": "student_model rejected request url=https://nablix.ai:8080/interaction status=401
              body={\"error_code\":\"INVALID_TOKEN\",\"message\":\"Invalid authentication token.\"}
              payload={'event_type': 'CORRECT_ATTEMPT', 'evaluation': 'CORRECT',
                       'current_phase': 'GUIDED_PRACTICE', 'independent_correct_in_session': 1}"
}
```

## This is not a voice bug

Read the payload: `event_type: CORRECT_ATTEMPT`, `independent_correct_in_session: 1`. This fires on the **first correct answer** of a session, when the backend posts a progress event to `student_model`. Voice simply happened to get the first right answer.

**Chat will fail identically the moment it gets one right.** "Works in chat" is currently luck, not a difference in behaviour — both go through `/interaction`.

## Root cause

The tutoring endpoints only check that a bearer is *present*. `student_model` at `https://nablix.ai:8080` actually **validates** it. The frontend currently sends the placeholder `ANON_ACCESS_TOKEN = 'anonymous-testing'` (`lib/api.ts`), enabled by `NEXT_PUBLIC_ALLOW_ANON_TUTOR`, because the VM has no working login: nginx has no `/nablix-auth` → `nablix.ai:8080` route, so `/nablix-auth/auth/login` 404s and no real JWT is ever issued.

**No frontend change can satisfy this.** A real token has to exist.

## What backend needs to do

1. **Add the nginx proxy** on the VM: `/nablix-auth/` → `https://nablix.ai:8080/`. Login then works, a real JWT is issued, and the frontend automatically stops sending the placeholder (a real token always takes precedence — see the interceptor in `lib/api.ts`).
2. Once that is live, `NEXT_PUBLIC_ALLOW_ANON_TUTOR` should be dropped from the build.

## Design question worth deciding

Should a failed **progress/telemetry** event fail the student's whole turn?

Right now a `student_model` 401 turns into `AUTHENTICATION_FAILED` for the entire `/interaction` call, so the student gets an error instead of feedback on a correct answer. Logging the failure and degrading would keep tutoring alive when the analytics service is down or misconfigured. Worth a call — it is a resilience decision, not a bug.

## Frontend side — done

`AUTHENTICATION_FAILED` was not even in the `ApiError` union, and the raw developer message (`student_model rejected request url=… status=401 …`) was shown to students under *"couldn't reach the tutor — please try again"* — advice that can never succeed. `studentFacingError()` in `lib/api.ts` now maps it to sign-in copy; the technical detail stays in the session trail and console.

---

# 2. Tutor voice variants (BLOCKER for the feature)

## The ask

Manjusha: *"For testing only — we need to give the options for the student to select the voice variants."*

## Frontend — done

A picker in the tutor panel header (speaker icon, next to ⋮), listing the providers actually registered on the voice server. The selection persists and is sent on **both** voice paths.

## Backend — nothing supports this yet

| Where | Today |
|---|---|
| `VoiceTTSRequest` (`app/models/voice.py:17`) | Only `text`. No voice or provider field. |
| `synthesize_speech()` (`app/services/voice/streaming/streaming_server.py:234`) | Takes only `text`; reads `voice_config.DEFAULT_TTS_PROVIDER` / `.TTS_VOICE`. |
| `app/services/voice/core/config.py:13,23` | `VOICE_TTS_PROVIDER` / `VOICE_TTS_VOICE` — process-level env, read once at import. |
| `/voice/stream` WS | Declares only `session`, `session_id`, `student_id`. |

So changing the tutor's voice today means **editing env vars and restarting the voice server**, and it changes the voice for everyone at once.

The adapters already accept a `voice` argument — `cartesia`, `inworld`, `deepgram` and `openai` all take one and fall back to their own default. It is simply never plumbed through from the API.

## What backend needs to do

1. Add optional `provider` and `voice` to `VoiceTTSRequest`.
2. Pass them through `synthesize_speech(text, provider=None, voice=None)` → `get_tts_adapter(provider or DEFAULT_TTS_PROVIDER)` → `generate_speech(voice=voice or TTS_VOICE, …)`. **Fall back to the env defaults when absent** so existing callers are unaffected.
3. Same for the WS: read `tts_provider` and `tts_voice` query params on `/voice/stream`.

## The frontend is already sending exactly these names

- `POST /voice/tts` → `{ "text": "...", "provider": "cartesia", "voice": "<id>" }`
- `/voice/stream?session=…&student_id=…&tts_provider=cartesia&tts_voice=<id>`

Both are **inert today and harmless**: Pydantic ignores unknown fields and FastAPI ignores undeclared query params. They start working the moment the backend reads them — **no further frontend change or redeploy needed.** When nothing is selected, neither field is sent at all, so the default request shape is byte-for-byte unchanged.

Until then the panel shows an on-screen "**not applied yet**" notice, so a tester who picks a voice and hears no change knows it is a missing backend field, not a broken UI.

## Note on the voice lists

Only verifiable IDs are listed: each adapter's own documented default, plus OpenAI's published set (`nova`, `alloy`, `echo`, `fable`, `onyx`, `shimmer`). Cartesia identifies voices by opaque UUID and Inworld/Deepgram by catalogue names not present in this repo, so those get a paste-your-own-ID field rather than guessed IDs that would fail at the provider. **If you have canonical voice lists, send them and they can be added as presets.**

---

# 3. Word-problem questions

## The ask

Manjusha: *"For phase 2 guided learning we currently show `x + 9 = 12`. If the question is a word problem, will this be handled automatically from your side?"* — e.g. *"a box starts with four fixed counters and receives 5 additional counters, then how would you write it as an equation?"*

## Answer: yes, automatically. Nothing more is needed from the frontend.

## What was wrong

Two bugs cancelling each other out:

- `syncBackendSession` **stripped** a leading `"solve for x:"` off `current_question`.
- The canvas header then **hardcoded** `Solve for x:` back on, in a maths serif, on one non-wrapping line.

A word problem therefore rendered as *"Solve for x: a box starts with four counters…"* in a serif font, unwrapped.

## Fixed

The backend's wording is now kept **verbatim**, and each screen decides presentation from the text itself (`lib/questionText.ts`):

- **Bare equation** (`x + 4 = 9`) → gets the `Solve for x:` lead-in and maths type.
- **Anything carrying its own words** → shown exactly as sent, as prose that wraps.

Applied in the canvas header, the practice header and the PDF export. Covered by unit tests.

## What backend needs to do

Only this: **send the question with its own wording.**

- ✅ A bare equation: `x + 4 = 9`
- ✅ A fully worded problem: `A box starts with four counters and receives 5 more. How would you write that as an equation?`
- ❌ Do **not** send a `"Solve for x:"` prefix expecting the UI to strip it — it no longer does, and it would be shown twice.

---

# 4. Tutor writing on the canvas

## Frontend — overlap fixed

Manjusha reported tutor writing overlapping. The cause was structural, not a stray coordinate: `text` and `math` marks were **centre-anchored**, so the coordinate producer picked a centre `x` without any way to know how wide the rendered glyphs would be. The left edge landed wherever it landed.

Reported case: an arrow ending at `x = 0.61` and `{ kind: "math", x: 0.68, tex: "x = 9 - 4", size: 28 }`. The maths rendered ≈0.135 wide, putting its left edge at ≈0.61 — exactly under the arrowhead. A narrower expression (`2x = 8`) cleared it, which is why a structural bug looked intermittent.

**Written marks now anchor at their LEFT edge** — where the pen touches down — so a mark occupies `[x, x + width]` and cannot creep backwards.

| | math left edge | arrow tip | |
|---|---|---|---|
| Before | 478.8px | 488px | −9.2px → overlap |
| After | 528px | 488px | +40px clear |

Pointing marks (`arrow`, `ellipse`, `line`, `rect`) are unchanged — they target a precise spot and must never be nudged.

## ⚠ Contract change for the producer

`docs/TUTOR-CANVAS-WRITE-SPEC.md` §3.3 is updated. **This changes what the backend must emit**, and was done now precisely because the producer does not exist yet — it would be a breaking change later.

- To write next to something ending at `x₀`, set `x` a little past it (`x₀ + 0.03`). No more guessing a centre.
- Budget width to the right: roughly `0.02 × characters` at `size: 24`. A long expression at `x = 0.9` runs off the canvas.
- Stack successive worked lines at the **same `x`** with `y` ≈0.10–0.12 apart — they then read as left-aligned working.
- **The frontend does not resolve collisions.** It renders exactly what is sent; non-overlapping layout is the producer's responsibility. (Reasoning for that decision is in §7 — auto-nudging would move marks away from what the tutor is describing aloud.)

## Still outstanding (pre-existing)

1. The **`canvas_draw` producer itself** — generating valid `TutorElement[]` from the tutor's intent, and validating geometry server-side before relaying.
2. **The §6 coordinate-anchoring decision**, still open and worth a call before the producer is built:
   - **A. Fixed regions** — simplest; tutor writes in a defined working area.
   - **B. Frontend sends anchors** — frontend reports bounding boxes of the question/regions.
   - **C. OCR bounding boxes** — `/canvas/submit` returns per-step boxes so the tutor can circle the student's *actual* writing. Richest, and the only option that supports "correct this specific mistake".

The frontend can already render anything in the §3 contract, over the WS (`{"type": "canvas_draw", …}`) or attached to an `/interaction` response.

---

# 5. Phase 1 orientation — concept check

## The ask

Manjusha: *"In phase 1 orientation, once the video is over can we display the canvas in the same phase?"* and *"after the video, only tutor will be writing. Phase 2 — both tutor and student can write. Phase 3 — only the student will write."*

## Frontend — done

Once the orientation content finishes — for a video, the moment playback ends — the tutor poses one concept question and works it through on a canvas, **still inside the orientation phase** (no phase-graph change). Write permissions now follow her rule exactly:

| Phase | Screen | Who writes |
|---|---|---|
| 1 · Concept orientation | `/orientation/[topic]` | **Tutor only** |
| 2 · Guided practice | `/` | **Both** |
| 3 · Independent practice | `/practice` | **Student only** |

All three verified in the browser.

## What backend could do later

The concept-check question and its drawing are currently **demo content** in `lib/demoContent.ts` (`ORIENTATION_CHECK`), one per topic. Eventually the backend should serve:

- the concept-orientation question for the topic, and
- the accompanying `canvas_draw` batch (§4 above),

at which point the demo content becomes the mock-mode fallback, exactly like every other entry in that file. **Not blocking** — the feature is demonstrable today.

---

# Summary of what to action

**Chirudeva**
1. nginx `/nablix-auth/` → `https://nablix.ai:8080/` on the VM — unblocks login, real JWTs, and the correct-answer path.
2. Decide whether a failed `student_model` progress event should fail the student's turn.

**Aditya**
3. Accept `provider` + `voice` on `VoiceTTSRequest` and `tts_provider` / `tts_voice` on `/voice/stream`, defaulting to the env values. Frontend already sends them.
4. Send canonical Cartesia / Inworld / Deepgram voice lists if you have them.

**Saravanan**
5. Serve `current_question` with its own wording — bare equation or full word problem, no strippable prefix.
6. Build the `canvas_draw` producer against the **updated** §3.3 (left-edge anchoring) and decide §6 anchoring.
7. Later: serve the Phase 1 concept-check question + drawing.
