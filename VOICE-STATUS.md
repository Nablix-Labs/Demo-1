# Voice Pipeline — What's Fixed (Frontend) and What's Left (Backend)

*Status as of 8 Aug 2026. Source: the full-stack voice audit of 7 Aug (45 findings:
17 frontend, 13 voice server, 12 main backend, log-verified on the VM) — PDF with
file:line detail is with Manav. Frontend fixes are on `main`; deploy to the VM is
pending only because the VM is offline.*

---

## ✅ Done — frontend (Numera-ui)

### Crashes that were firing in production (verified dead in VM logs)
| Fix | Was |
|---|---|
| `turn_context` frames sent at socket open and every turn | `turn_id` never sent on the WS transport → every voice turn failed ("turn_id is required", 11 failures on 7 Aug, zero after deploy) |
| `sessionId` persisted | ~164 session starts/day → resume storm → `SESSION_RESUMED` 500s (backend enum fix is the other half, deployed 11:34) |
| Nudge guarded on missing tutor turn | Idle students produced a 422 storm (`previous_tutor_turn_id: null`) |

### Deadlock-proofing the audio player (`lib/tts.ts`) — commit `9c8729b`
Every no-audio failure now funnels to `onIdle`, so **"stuck on Speaking… forever" is
structurally impossible**:
- No MediaSource / MP3-in-MSE (iPhone Safari < 17.1) → reply is voiced through the
  REST fallback chain instead of a silent dead lesson.
- Refused `audio.play()` (autoplay policy) → fallback voice, not a swallowed rejection.
- 12s arrival guard: `tutor_response` with no audio ever playing → words spoken via
  fallback. (This was the unguarded phase after the watchdog stands down.)
- `stopTutorSpeech()` now silences the streaming player too → no more two tutor
  voices at once (hint playing on top of the streamed reply).
- Generation counter → a superseded reply's async callbacks can't touch the current one.
- New test suite pins the invariant (onIdle always fires, whatever the failure).

### Socket lifecycle (`hooks/useWebSocket.ts`)
- Reconnect timer is cancellable + exponential back-off capped at 30s. It used to be
  an unowned `setTimeout` that outlived the page → duplicate live sockets, doubled
  audio, sockets opening after navigation.
- Auth closes (4401/4403) stop reconnect-looping; the student is told to log in.
- Socket-identity guard on every handler; `onerror` handler added.
- Disconnect mid-turn → "say that again" in chat instead of a silently dropped turn.
- 45s watchdog now carries the turn id it armed for (a stray echo-final can no longer
  fire `stop` into a different turn) and has an 8s post-rescue grace: if the `stop`
  yields nothing, the student gets the failure copy and the mic reopens. **"Processing…
  forever" is gone.**
- WS-path stale-session recovery: "session not found" errors drop the dead session and
  a fresh one starts (previously only clearing localStorage recovered).
- Audio chunks of a rejected stale `tutor_response` are discarded, not spliced into
  the next reply.
- `expects_student_response` / `allow_voice_input` honoured → no more transcribing room
  noise after a reply that wants no answer.
- Voice-picker changes reconnect the socket (voice actually changes mid-session).
- Store selectors instead of whole-store subscription → no full-lesson re-render per
  partial transcript.

### Microphone (`hooks/useVoiceStream.ts`, `VoiceBar`)
- Denied/missing mic is **surfaced** ("Microphone is blocked" + how to fix) instead of
  a false "Listening…" — this was most of "the tutor is ignoring me".
- Server transport keeps the mic hardware open all session; turn-taking gates only
  transmission. The old per-turn teardown cost 100–400ms per turn and **ate the first
  syllable of every answer** — a major source of garbled Deepgram transcripts.
- Echo suppression unchanged (frames captured while the tutor speaks are dropped).

### Session & review UX
- Refresh mid-lesson rehydrates via `GET /session/{id}` (was: blank lesson, every
  turn silently dropped). Backend-404 on resume → clean fresh start.
- Review page: `/session/end` 409 now shows "Nothing to review yet" + a way back to
  the lesson (was: silently rendered DEMO worksheets as the student's real results,
  wedged forever — Aditya's report, 7 Aug). Commit `0003078`.
- Failed canvas submit tells the student their written work wasn't seen.
- Initial voice status is `idle` — no capturing before a socket exists.
- Heavy frame logging (`[voice ←/→]` with full JSON + `request_id`) stays ON for the
  testing phase, per team request.

### Frontend items deliberately NOT done
- **Barge-in** (student interrupting the tutor mid-sentence): frontend groundwork is in
  place (persistent mic + transmit gate) but it needs the server work below first —
  interrupting today would hit the `turn_id=None` race and kill the session.

---

## 🔧 To do — voice server (`streaming_server.py`) — **Aditya**

Ordered by impact. 1 and 2 are the whole ballgame.

1. **Server-side cancellable silence timer.** Finalization currently depends 100% on
   Deepgram's `UtteranceEnd`. It didn't arrive on **13 of 53 turns on 7 Aug** — those
   students waited the full 45s for the frontend watchdog. A ~2s server-side timer
   (reset on each transcript segment, finalize on expiry) turns a 45s stall into 2s
   on a quarter of all turns. Already assigned in the handoff doc.
2. **Move `process_and_respond` out of the Deepgram receiver loop** (`:404`). The
   tutor call runs *inside* the receiver, so nothing reads Deepgram for 7–21s per
   turn — and the stop-handler's `asyncio.wait_for(receiver, 10s)` (`:523`) actually
   measures the tutor pipeline: on timeout it **cancels replies that already
   succeeded** (3× on 7 Aug, incl. the 11:41 "Streaming TTS failed"). Run the tutor
   call as its own task; delete the 10s cancel.
3. **`except` on the stop-path's `process_and_respond`** (`:543` has `try/finally`,
   no `except`) — one bad turn currently unwinds and **closes the whole session**
   with no error frame.
4. **Per-utterance `turn_id`.** It's latched per-connection and cleared to `None`
   after each turn (`:419`, `:551`); the client re-sends only at idle. A student
   talking over the tutor ⇒ `turn_id=None` ⇒ error ⇒ (via #3) dead session. This is
   why "turn_id is broken *again*" keeps recurring. Mint/carry it per utterance, and
   stamp `turn_id` on `tutor_audio_chunk`/`tutor_audio_end` so the client can drop
   stale audio deterministically.
5. **Structured error frames**: include `error_code`, `turn_id`, `retry_safe`,
   `request_id` (all currently flattened to "Tutor unavailable. Please try again.").
   The main backend already produces a good envelope — forward it, don't discard it.
6. **`_safe_send` guard** (check `client_state` before every `ws.send_json`) — kills
   the "Cannot call send once a close message has been sent" class; abort TTS
   streaming early on client disconnect.
7. `turn_already_processed` is write-only — actually consume it in the stop handler
   (`if final_transcript and not turn_already_processed:`) to stop double-processing
   trailing finals.
8. Guard the `start`-handler Deepgram connect with try/except (the auto-connect path
   has one); gate the 40 English keyterms on `language == "en"`.
9. Detect duplicate connections per session (close the older one) — two tabs /
   StrictMode currently interleave transcripts and 409 each other.
10. Transcript cap: truncate/summarize before POSTing — a >500-char utterance
    currently 422s the whole turn.

## 🔧 To do — main backend — **Chirudeva / backend team**

1. **Tutor-call latency** (`n=25` on 7 Aug: median 7.7s, p90 15.7s, max 20.8s before
   TTS). Profile where it goes: LLM call vs Student-Model round-trips vs retries.
2. **Student-Model auth** — the `401 INVALID_TOKEN` incidents (5 on 7 Aug + the
   evening login outage). The browser token is latched once at WS connect and
   forwarded forever; no refresh path exists. Long session ⇒ token expires ⇒ every
   Student-Model call 401s and surfaces as a login failure. Needs a refresh frame or
   per-turn token, and a distinct `AUTH_REFRESH_REQUIRED` error code. Also: the 401
   detail currently leaks the student's utterance (PII) into the response.
3. **Adapter retry budget**: 20s × 3 attempts × up to 3 sequential events per turn
   (180s worst case) vs the voice server's 40s timeout — the backend commits events
   after the client gave up ⇒ state divergence ⇒ 409s. Per-turn deadline < 40s; no
   timeout-retry on mutating events.
4. **`/voice/transcript` 409 destroys the recovery payload** (`voice_service.py:81`):
   return the full `StaleTurnResponse` (with `expected_previous_tutor_turn_id`) like
   `/interaction` does — this is the "409 session-killer" mechanism. Also populate
   `expected_previous_tutor_turn_id` on success responses (hardcoded `None` today).
5. **Un-endable session** (Aditya's find, 7 Aug): the auto-transition to REVIEW
   (`session_service.py:470`) doesn't check `per_question_history`, but
   `end_session()` rejects empty ones → 409 forever. Frontend now shows an honest
   empty state, but the transition itself should not create un-endable sessions.
6. **Enum landmine class** (the `SESSION_RESUMED` failure mode, still armed for the
   next new code): Student-Model `reason_code` is accepted as `str` but re-validated
   against the enum *after* the event is committed → any future code = 500 with the
   turn permanently lost. Map unknown codes to `None` + warn. Same for
   `extra="forbid"` on the Student-Model response model (one new field ⇒ every turn
   503s).
7. **In-memory sessions**: every backend restart kills all live sessions with
   unclear errors. Persist (Redis/Postgres), or short-term emit a distinct
   `SESSION_LOST` code (the frontend now recovers when it can *detect* this).
8. Session mutations outside the interaction lock (phase transitions during a 7–20s
   turn get clobbered → ghost questions / 409s); duplicate-turn retry can 500 when
   the dedupe cache misses; dead duplicate nudge implementations
   (`interaction_service.py:1614/1655` shadowed by `:1836/:1871`) should be deleted.
9. `/voice/tts` and the `/voice` routes have no auth dependency (unauthenticated paid
   TTS endpoint); session ownership is decided entirely by client-supplied
   query-string ids — derive `student_id` from the token.

---

*Deploy note: frontend commits `0003078` + `9c8729b` are on `main`, built, and will
be shipped to the VM the moment it's back online (it went dark ~22:45 IST on 7 Aug).*
