# Numera — project context

**Read this first.** Everything here is the stuff you cannot work out by reading
the code: who owns what, how the pieces are wired in production, and the traps
that have already cost somebody a day.

Last updated 31 July 2026.

---

## What it is

An AI maths tutor for KS3–KS4 students (UK, roughly ages 11–16). A student picks
a topic, takes a short diagnostic, watches an orientation, then works through
guided practice with a voice tutor and a drawing canvas.

Built by Nablix. Live at **https://nablix.ai/app/**.

---

## Who owns what

This matters more than it looks — most of the time lost on this project has gone
on debugging somebody else's layer.

| Area | Owner |
|---|---|
| Frontend (this repo) | **Manav** |
| Tutor Backend — interaction, sessions, phases | **Chiru**, **Sanya** |
| Voice — Deepgram STT, Cartesia/Inworld TTS, streaming server | **Aditya** |
| Student Model — Schema 3.0, learner journey events | **Saravanan** |
| RAG — question bank, hints, worked examples, visual cues | **Aditya** |
| Product / lead | **Manjusha** |

**Backend changes are allowed since 31 Jul (Manjusha), with one condition:
every backend change is its own clearly-labelled, individually revertible
commit — never mixed with frontend changes.** Before that the rule was
frontend-only. Design-level backend asks still go to `docs/BACKEND-ASKS-*.md`
with the owner named.

---

## Repos

`Demo-1` is a monorepo and is canonical:

```
Demo-1/
  Numera-ui/            ← this app (Next.js)
  nablix-backend/       ← FastAPI, all backend services
  nablix-authoring-ui/  ← internal content-authoring portal (separate Next app)
```

There is a standalone `Numera-ui` checkout elsewhere on the machine — it is a
**mirror**. Work in the monorepo.

Remote: `github.com/Nablix-Labs/Demo-1`, single branch `main`. Everyone pushes to
`main`; expect to `git pull --rebase` before every push.

---

## Production topology

Azure VM `74.162.34.219`, nginx in front. **This is not obvious and has already
produced one wrong diagnosis** — write it down before theorising.

| Port | Process | Serves |
|---|---|---|
| 8001 | uvicorn, **1 worker** | `/api/` — REST, and the in-memory session store |
| 8004 | standalone voice server | `/api/voice/stream` — the WebSocket |
| 8002 | — | `/` (the older mathtutor site) |
| 8000 | gunicorn, 4 workers | **nothing nginx routes to** — likely a leftover |

nginx routes `/api/voice/stream` → 8004 **before** `/api/` → 8001 (longest prefix
wins). The voice server then calls back into 8001 over HTTP loopback
(`NABLIX_MAIN_BACKEND_URL`), so REST and voice share one session store. Good —
but only because that env var is set correctly.

Two traps here:

- `/api/health` reports `"mode":"inprocess"` even though nginx sends the
  WebSocket to the separate 8004 service. The field is misleading.
- If anyone ever runs uvicorn with `--workers > 1`, sessions split across worker
  memory and voice breaks non-deterministically. See "session persistence" below.

Services: `nablix-backend.service`, `nablix-voice.service`. Env for both:
`/etc/nablix/backend.env`.

### The VM shuts down at midnight IST, every night

```
Jul 27 18:30 UTC → down    Jul 28 18:30 → down    Jul 29 18:30 → down
```

It only comes back when somebody starts it by hand. On 29 July it stayed off for
**nine hours** and was still off when the team started testing next morning —
which cost a whole morning of debugging a switched-off machine.

Almost certainly an Azure auto-shutdown policy. **If something is "completely
broken" before ~09:00 IST, check the machine is on before anything else.**

---

## Deploying the frontend

Full detail in `docs/DEPLOY.md`. The one-line summary and the one real trap:

```bash
rm -rf .next out
EXPORT_BASE_PATH=/app \
NEXT_PUBLIC_API_BASE_URL=/api \
NEXT_PUBLIC_ALLOW_ANON_TUTOR=true \
NEXT_PUBLIC_VOICE_TRANSPORT=server \
NEXT_PUBLIC_WS_URL=wss://nablix.ai/api/voice/stream \
npm run build

tar czf - -C out . | ssh -i ~/Downloads/Nablix-Dev-Ubu_key.pem \
  developer@74.162.34.219 'tar xzf - -C /var/www/numera/app'
```

**`NEXT_PUBLIC_*` are inlined at build time.** A build missing
`NEXT_PUBLIC_API_BASE_URL` compiles, deploys, loads — and silently runs the whole
app on mock data, showing demo content like `2x + 5 = 13` and never calling the
backend. This has happened twice. Always run both checks in `DEPLOY.md`.

`tar xzf` overwrites but never deletes, so orphaned chunks accumulate in
`/var/www/numera/app/_next/static/chunks/` across deploys. Harmless, worth an
occasional clean.

SSH key: `~/Downloads/Nablix-Dev-Ubu_key.pem`, user `developer`. Password auth is
disabled; `sudo` needs a password.

---

## Architecture

Next.js 15 App Router, **static export** (`output: export`), served by nginx from
a subpath. No server runtime — every dynamic route needs `generateStaticParams`.

State is Zustand with `persist` + `skipHydration`:

- `useNumeraStore` — session, phase, transcript, canvas, visual cues, scaffold
- `useAuthStore` — token, tier, student identity
- `useMicLevel` — mic meter

### Phase lifecycle

The **backend owns the phase**. The frontend follows it and never decides it.

```
/session/start
  → DIAGNOSTIC        → /session/{id}/diagnostic/complete
  → CONCEPT_ORIENTATION → /orientation/start → /orientation/complete
  → GUIDED_PRACTICE
  → INDEPENDENT_PRACTICE
  → TEACH_BACK (backend has never routed into this yet)
```

`usePhaseRouting` re-asserts the backend's phase on every path change, so
navigating to a screen you have not reached bounces you back. That is correct
behaviour, not a bug — it is why the sidebar's links looked "dead".

`applyBackendPhase` in the store is the single place that applies a phase update.
Both transports (REST and WebSocket) go through it. It clears the question only
on a real phase change, and clears the visual cue when the question id or phase
changes.

Student Model **Schema 3.0**: `student_model_event.phase_payload.{question_set,
orientation_bundle}`.

### Voice

Two transports, chosen by `NEXT_PUBLIC_VOICE_TRANSPORT`:

- `rest` — browser `webkitSpeechRecognition` for STT, REST for TTS
- `server` — raw PCM16 16kHz mono over the `/voice/stream` WebSocket, Deepgram
  STT server-side. **This is what production uses.**

`effectiveVoice()` in `lib/tts.ts` is the single source of truth for
provider+voice on **both** transports. Tier → provider:

| Tier | Provider | Default voice |
|---|---|---|
| all tiers (31 Jul, Manjusha) | `inworld` | Ashley |

(Cartesia was premium/enterprise until 31 Jul; it ran out of credits twice in
four days at ~7.5x Inworld's price. It remains the degradation target in
`lib/tts.ts` — flipping `TIER_PROVIDER` in `lib/voiceOptions.ts` switches back.)

The student picks a voice within their tier's provider, never a provider. There
is deliberately **no cross-provider fallback** — it used to silently switch to
OpenAI and never switch back, which is what "the voice keeps changing" was.

Turn detection is entirely Deepgram's `UtteranceEnd` after 1.5s of silence.
`lib/turnWatchdog.ts` is a 45s rescue (moves with the backend tutor-call timeout) for when that never fires — read the
comment in that file before changing the window; it is load-bearing.

---

## Traps that have already cost time

Roughly in order of how much.

**A bug in someone else's layer looks like a bug in yours.** The 409 below
surfaced as "Tutor unavailable", which reads as a voice bug, which read as a
frontend bug. Get logs before forming a theory. Twice now a plausible mechanism
has been fitted to a symptom and been wrong.

**Stale `.next` cache.** Deleting `.next` while `next dev` is running produces
500s and bizarre stale renders. `pkill -f "next dev"` first, then `rm -rf .next`,
then restart.

**FOCUS_ROUTES skip `AuthGate`.** Some routes deliberately bypass auth.

**Session-start storms.** Guard session creation; it is easy to fire several.

**WebGL context eviction.** Browsers cap simultaneous WebGL contexts and evict
the oldest. An evicted canvas keeps its last pixels and silently ignores draws —
that was the "sometimes it goes dark mode" report. `ShaderBackground` now handles
`webglcontextlost`/`restored`.

**Tailwind arbitrary descendant variants outrank utilities on the element.**
`[&_h1]:text-[40px]` on a parent beats `text-2xl` on the `h1` itself. This is
used deliberately in `CenteredScreen` to set one type scale for eleven screens.

**JWT `sub` is a user id, not a `ST###` student code.** The hardcoded `ST001`
cannot be removed without a backend change. See
`docs/BACKEND-ASKS-PHASE-0-1.md`.

**`_DEMO_STUDENT_ID = "ST001"`** gets session recovery on the backend. Real
accounts do not. So the demo student behaves differently from every real user.

---

## Open backend issues

Full writeups in `docs/BACKEND-ASKS-2026-07-29.md` and
`docs/VOICE-REVIEW-2026-07-30.md`.

**1. The `ALG_1STEP_GP_F01` 409 — highest priority, still unfixed.**
Guided practice serves the next question from Aditya's Qdrant bank
(`question_bank.json:87`) and overwrites `session.question_id`, then validates
that id against the Student Model's `question_set`, which never contained it
(`interaction_service.py:1067` serves, `:183` rejects). Result: 409, and the
session is unrecoverable. **This is what killed a live lesson on 29 July.**
The error message blames the Student Model for an id the Tutor Backend generated
itself, which has already sent two people to the wrong owner. Chiru/Sanya.

**2. Session persistence.** `_sessions: dict[str, SessionRecord] = {}` in
`session_service.py:53`. No persistence, no reload. Every restart — and the VM
reboots nightly — destroys every session. No resume endpoint. Sanya.

**3. Voice tutor calls time out at 15s; canvas gets 40s.** Measured over 121 real
calls: median 3.8s, p90 6.3s, max 12.5s. Has not fired yet, but 17% headroom.

**4. TTS billing.** Cartesia and Inworld both hit zero credits on 28 July.
Degrades silently and looks exactly like a voice bug. Needs balance alerts.

**5. Deepgram `KeepAlive` is never sent**, so an unfed socket is killed after
~10s (`NET-0001`, four times in three days).

**6. Per-turn TLS handshake.** Both streaming TTS adapters build a fresh
`httpx.AsyncClient` per call, defeating the shared client and the startup
pre-warm.

---

## Testing

```bash
npm test              # vitest, 116 tests
npx tsc --noEmit      # must be clean
npx next build        # must succeed before any deploy
```

Playwright MCP for live browser checks. The Chrome extension has an OAuth account
mismatch on this machine — use Playwright.

Never tested, be honest about it: voice **input** with a real microphone, canvas
OCR, and teach-back (the backend has never routed into that phase).

---

## Doc index

| Doc | What it is |
|---|---|
| `DEPLOY.md` | Deploy command and the mock-mode trap |
| `VOICE-REVIEW-2026-07-30.md` | Voice module review with VM log evidence |
| `BACKEND-ASKS-2026-07-29.md` | The four current backend asks, by owner |
| `LEARNING-FLOW.md` | Phase-by-phase product flow |
| `TEST-STATUS.md` | What is covered and what is not |
| `TUTOR-CANVAS-WRITE-SPEC.md` | Tutor drawing on the canvas |
| `TEACH-BACK-FRONTEND-DESIGN.md` | Teach-back design, not yet reachable |
| `VOICE-AUDIT-AND-PLAN.md` | Earlier voice audit |
| `DEMO-FLOW-PLAN.md` | Demo script |

---

## Keeping this file honest

Add to it when you learn something that was not obvious from the code — an
ownership boundary, a production quirk, a trap that cost you time. Do not add
things the code already says; that rots. If a fact here turns out to be wrong,
correct it in place rather than adding a second version.
