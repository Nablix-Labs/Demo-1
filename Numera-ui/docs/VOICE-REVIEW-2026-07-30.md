# Voice module — code review

**For:** Manjusha
**From:** Manav (frontend)
**Date:** 30 July 2026

You asked me to look at the backend and find why voice keeps breaking. This is
what I found reading the code. I changed nothing.

Two things up front, so you can weigh the rest properly.

**I have since got onto the VM and read the logs.** That changed the answer, so
please read the next section before the rest — the code findings are all real,
but none of them is what you hit this morning.

**I checked my own claims before writing this, and three of them were wrong.**
They are listed at the bottom rather than quietly dropped, because if I only
showed you the surviving findings the list would look more damning than the
evidence supports.

---

## What actually happened this morning: the VM was switched off

Nothing was broken. **The server was not running.**

```
shutdown  system down  Wed Jul 29 18:30 - 03:38  (09:07)
reboot    system boot  Thu Jul 30 03:38   still running
```

The machine was down for **9 hours and 7 minutes**, from 29 July 18:30 UTC to
30 July 03:38 UTC. In IST that is **00:00 to 09:08 on 30 July**.

You tested between 07:55 and 08:24 IST. That is squarely inside the outage.

Three independent confirmations:

- `journalctl` has exactly one line across that entire window — the box was off,
  not merely the service.
- nginx served **zero** requests before 03:38 UTC today.
- The first `/voice/stream` connection today is at 03:40:24, two minutes after
  boot.

So there were no voice answers because there was no server. "Tutor is
unavailable" was accurate — it just wasn't telling you why.

### This is a schedule, not an accident

```
Jul 27 18:30 → down    Jul 28 18:30 → down    Jul 29 18:30 → down
```

The VM shuts down at 18:30 UTC — **midnight IST — every single night.** It only
comes back when somebody starts it by hand. On the 28th someone noticed in 35
minutes. On the 29th nobody did, so it stayed off for nine hours and was still
off when you started testing.

That is almost certainly an Azure auto-shutdown policy left on the VM, probably
for cost. I could not read the Azure config from inside the box, so somebody
with portal access should confirm it.

**This is the single highest-value thing to fix in this document.** Not because
it is hard, but because it costs the team an entire morning of misdirected
debugging every time it happens, and it will keep happening at midnight IST. The
fix is either turning the schedule off, or setting the services to start on boot
and having the VM boot on a schedule ahead of the working day.

It is also worth saying plainly: **this was not Aditya's deploy and not the
frontend.** Nobody had broken anything.

### What that means for everything below

The code findings that follow are real defects I traced in source, and the log
evidence sharpens two of them considerably. But **none of them caused this
morning.** I had written finding 1 as the explanation for your report, on the
reasoning that Aditya's deploy restarted the backend and wiped your session. The
logs say otherwise: there was no deploy and no restart, because there was no
running machine. That inference was wrong and I have corrected it in place.

---

## The short version

One confirmed major problem, one probable, two medium. Not twelve bugs.

The honest summary is not a bug count. Turn detection rests on a single 1.5
second silence heuristic, there is no explicit end-of-turn signal, no barge-in
handling, and no session persistence. That is why it feels fragile — it is a
thin design more than it is buggy code.

| # | Finding | Severity | Verified? |
|---|---|---|---|
| 0 | **The VM shuts down at midnight IST every night** | **Major** | Yes, from logs — caused this morning |
| 1 | Sessions are lost on every restart — and it reboots daily | **Major** | Yes; 66 live 404s in the logs |
| 2 | Voice tutor calls time out at 15s; canvas gets 40s | ~~Probable major~~ Medium | Measured — has not fired yet |
| 2b | **Cartesia and Inworld ran out of credits on 28 July** | **High** | Yes, from logs |
| 3 | A fresh TLS handshake on every tutor turn | Medium | Yes |
| 4 | Frontend never signals end-of-turn (my gap) | ~~Medium~~ **Fixed** | Fixed 30 Jul, see below |

---

## 1. Sessions are lost on every restart — this is your "Tutor is unavailable"

This is the one that matches what you saw yesterday.

Tutoring sessions live in a plain dictionary in process memory:

```python
# app/services/session_service.py:53
_sessions: dict[str, SessionRecord] = {}
```

Nothing persists it and nothing reloads it. When the backend restarts, every
session in flight is gone.

There is a recovery path, but it only covers one hardcoded student:

```python
# app/services/session_service.py:113
_DEMO_STUDENT_ID = "ST001"

# app/services/session_service.py:193
if session is None and student_id == _DEMO_STUDENT_ID:
    session = _recover_demo_session(...)
if session is None or session.student_id != student_id:
    raise _session_not_found(session_id)
```

So the demo student survives a restart. A real account does not — it gets a hard
404, which surfaces as a 500 to the voice server, which sends the student:

```json
{ "type": "error", "message": "Tutor unavailable. Please try again.", "fallback_mode": "TEXT" }
```

**Correction.** I first wrote that this explained your morning — Aditya deploys,
the backend restarts, your session is wiped. The logs disprove it: there was no
deploy and no restart, because the machine was off (finding 0). I was fitting a
mechanism to a symptom without evidence, which is the same habit that sent me to
Saravanan over the 409 last week.

**The logs make it worse, though, not better.** The failure is live and it is the
single largest category in three days of logs:

```
66 × status=404  {"message":"Session with ID SESSION001 was not found."}
```

Sixty-six real voice turns lost to this.

Finding 0 compounds it directly. The VM reboots **every night**, so every session
is destroyed nightly by design. Anyone who leaves a tab open overnight, or whose
browser restores a session id from storage, returns to a session the server has
never heard of — 404, "tutor unavailable."

This is the same gap I raised as ask 3b in `BACKEND-ASKS-2026-07-29.md`, still
open. It also means **any deploy during a demo kills every student mid-lesson.**

**What it needs:** session state in a store that outlives the process, or at
minimum a resume endpoint so a student can be put back into their session
instead of being told the tutor is down.

---

## 2. Voice tutor calls are given 15 seconds; canvas is given 40

The voice server calls the tutor over HTTP using one shared client:

```python
# app/services/voice/streaming/streaming_server.py:107
_backend_http_client = httpx.AsyncClient(base_url=MAIN_BACKEND_URL, timeout=15.0)
```

Canvas submissions override that to 40 seconds. The voice transcript call does
not, so it inherits 15. I checked that this is really how httpx behaves rather
than assuming:

```
client default timeout: Timeout(timeout=15.0)
post() timeout default: USE_CLIENT_DEFAULT   → inherits the client's value
```

A tutor turn that takes 16 seconds raises, gets caught, and the student sees the
same "Tutor unavailable" message as above.

**I have now measured this**, over 121 real tutor calls from three days of logs:

```
n=121   min=3ms   median=3793ms   p90=6254ms   max=12519ms
```

**Downgrading this from "probable major" to medium.** No call has yet hit the
15s ceiling, and there is not a single timeout in the logs. It did not cause your
morning and it has not caused anything else so far.

It is still worth fixing, because the headroom is thinner than it looks. The
slowest real call was **12.5 seconds against a 15-second limit** — 17% margin. A
slightly longer question, a slower day at the model provider, or one retry, and
this starts firing. When it does it will look exactly like finding 1 from the
student's side, which will make it needlessly hard to tell apart.

There is also no principled reason a voice turn gets 15 seconds when a canvas
turn doing comparable work gets 40.

---

## 2b. Cartesia and Inworld both ran out of credits on 28 July

This one is not in the code at all, and I only found it in the logs. You said on
WhatsApp that Deepgram is unpaid and the others are paid. The logs disagree —
**both paid providers hit zero.**

Cartesia, 29 failures:

```
status=402 {"error_code":"quota_exceeded",
            "message":"This request requires approximately 58 credits
                       but you have 1 remaining."}
```

Inworld, 12 failures:

```
status=403 {"code":7,
            "message":"You have no credits remaining.
                       Please add credits to continue using the service."}
```

All of them are dated **28 July**, so this is not what happened this morning —
the pre-warm on today's boot succeeded against Inworld, so there are credits now.
But it is worth knowing for three reasons.

**It looks exactly like a voice bug.** The tutor's text arrives normally and no
audio follows. From the outside that is indistinguishable from "voice is broken
again," and I expect some of the "voice keeps collapsing" reports trace to this
rather than to code.

**We are one balance away from it recurring**, with no warning before it happens
and nothing in the product that says why. Right now it degrades silently.

**The env is pointed at the cheaper provider.** `/etc/nablix/backend.env` has:

```
VOICE_TTS_PROVIDER=inworld
VOICE_TTS_VOICE=Ashley
```

That is the `basic` tier default. It only applies when the client names no
provider — our frontend always names one, so students are unaffected today. But
it means the server-side default is the account that hit zero first.

**Ask:** somebody should check the balance on both accounts and set up a billing
alert. This is a five-minute fix that removes a whole category of confusing
failure.

---

## 3. Every tutor turn opens a new TLS connection

Both paid TTS adapters build a brand new HTTP client inside the streaming call:

```python
# app/services/voice/adapters/cartesia_tts_adapter.py:184
async with httpx.AsyncClient(timeout=15.0, headers={...}) as stream_client:
```

Same at `inworld_tts_adapter.py:199`.

There is a shared warm client and a startup pre-warm designed to avoid exactly
this — but they only serve the non-streaming path, and the streaming path is the
only one ever taken. So the optimisation is dead code and every single tutor
reply pays a full handshake, roughly 300–500ms on top of the actual speech
generation.

I also suspect sockets leak here: the client is opened inside an async generator,
and if the consumer is cancelled part-way the generator is not closed
deterministically. That would fit the "works for a while, then stops until
restart" pattern. **That part is inference, not verified** — I could not
reproduce it without a running instance.

---

## 4. We never told the server the student finished speaking — fixed 30 July

**This one was mine, and it is now done.**

The server supports an explicit `stop` message. Our frontend never sent it:
`sendControl` was exported from `hooks/useWebSocket.ts` and called nowhere.

So turn completion rested entirely on Deepgram noticing 1.5 seconds of silence
(`utterance_end_ms=1500`). If that event did not fire — noisy room, dropped
message, a reconnect that discarded the utterance — the turn never completed and
the student waited with no way to force their answer through.

**What I did not do, and why it matters to you.** The obvious fix is to send
`stop` when the student mutes. That would have been a regression. The server's
stop handler cancels its Deepgram receiver task after 10 seconds
(`streaming_server.py:503`), and that task is exactly what runs the tutor turn
when UtteranceEnd *did* fire. A student who mutes impatiently while the tutor is
thinking would have killed a reply that works today — audio chunks delivered,
no `tutor_audio_end`, interface hung. That trades a rare failure for a common
one.

**What I did instead.** A rescue timer (`lib/turnWatchdog.ts`). It arms when the
student's speech is transcribed and disarms the moment the tutor replies. Only
if it expires — meaning the turn is genuinely stuck — does it send `stop`.

The window is 20 seconds, derived so it cannot cancel anything still in flight:

```
  1.5s   UtteranceEnd silence threshold
+ 15.0s  the tutor HTTP call's own timeout (finding 2)
= 16.5s  by which the server has sent either tutor_response or error
```

Both of those disarm the timer, so 20s leaves 3.5s of margin. Nine tests cover
it; six of them assert it does *not* fire, because over-eagerness is the
expensive failure here.

**Honest scope.** This is a rescue, not a cure. It converts "the student waits
forever" into "the student waits twenty seconds, then the answer goes through."
Twenty seconds is still bad — it is just recoverable. A proper fix needs the
server to accept an explicit end-of-turn, which means sorting out the 10-second
cancel first. That part is backend.

**One consequence for the backend team.** Now that we can send `stop`, two
hazards I had listed as dormant become reachable — see the section below.

---

## Smaller things, worth logging but not urgent

- **Adapters register only if their API key exists at import time**
  (`cartesia_tts_adapter.py:220`). A missing environment variable does not fail
  loudly — it silently drops every premium student to browser speech at request
  time. This should fail at startup instead.
- **`get_tts_adapter` is cached permanently** (`core/adapter.py:63`). One bad
  adapter instance stays bad until the process restarts.
- **Two different `.env` files.** `core/config.py:7` loads
  `knowledge-base/ingestion/.env` first and only falls back to the root `.env`.
  The voice module can end up reading a different key set than the rest of the
  app.
- **Low transcript confidence is measured and then ignored.**
  `streaming_server.py:675` computes `needs_clarification`, then the transcript
  is submitted as the student's answer regardless. A mis-transcription becomes a
  wrong answer marked against the student. Given we are teaching children, this
  one matters more than its severity suggests.
- **Raw binary audio frames skip the auth check** (`streaming_server.py:587`).
  The JSON path checks the access token; the bytes path does not.
- **The websocket defaults `student_id` to `"ST001"`.** A client that omits it
  writes real voice turns onto the mock student.
- **The app calls itself over HTTP.** `/api/health` reports `"mode":"inprocess"`,
  so the voice server runs inside the main app but still POSTs to
  `127.0.0.1:8000`. Harmless at one worker. The moment anyone adds a second
  uvicorn worker, the loopback call can land on a worker whose memory has no such
  session — and finding 1 becomes constant instead of occasional.
- **`MATH_NORMALIZATIONS`** (`streaming_server.py:~110`) is eight hardcoded
  strings. Everything else normalises to nothing.

---

## What I checked that turned out to be fine

Recording these so nobody re-investigates them.

- **Echo feedback.** The mic stays open while the tutor speaks, which would let
  the tutor hear itself and answer itself. We request `echoCancellation: true`
  (`useVoiceStream.ts:125`), so this is handled. Residual risk only at high
  speaker volume; the server has no barge-in guard as a backup.
- **Deepgram idling out.** I thought a silent mic would drop the connection. It
  does not — the browser streams silent audio continuously while unmuted, so
  Deepgram stays fed. There is a real idle window while muted, but it self-heals
  on the next chunk.
- **The frontend is not the cause of the transcription outage Aditya reported.**
  It sends `audio_chunk` frames correctly — 83 frames in 8 seconds, verified on
  the live VM on 29 July — and does not use `webkitSpeechRecognition` on the
  server transport.

---

## Two hazards that just stopped being dormant

I originally listed these as dead code, because they sit behind the `stop`
message and we never sent it. **Finding 4 changed that on 30 July.** They are now
reachable and should go on the backend list.

Both live in the server's `stop` handler:

- **Two coroutines can write to the same websocket.** `UtteranceEnd`
  auto-triggers a tutor turn from inside the Deepgram receiver task
  (`streaming_server.py:377`) while the main loop can trigger one from `stop`
  (`:521`). Nothing serialises them, and concurrent `send_json` on one Starlette
  socket is not safe.
- **The 10-second finalisation timeout cancels a reply mid-stream.**
  `streaming_server.py:503` waits 10s for the receiver task, then cancels it. If
  that task is inside a tutor turn, the student gets audio chunks and never gets
  `tutor_audio_end`.

**How exposed are we in the meantime?** Low, by construction. The watchdog only
sends `stop` after 20 seconds with no reply — a point at which the server has
already resolved or abandoned the turn, so there is nothing left to cancel or
collide with. But that safety comes from my timing argument, not from anything
the server enforces. If the tutor timeout in finding 2 is ever raised above 15
seconds, **the 20-second window must be raised with it**, or the rescue starts
cancelling healthy replies. That coupling is written into
`lib/turnWatchdog.ts` and asserted in its tests so it cannot be changed
silently, but whoever touches the backend timeout needs to know it exists.

The clean resolution is for the server to serialise turn handling and to treat
`stop` as "finalise what you have" rather than "cancel after 10 seconds". Then
the frontend can send it immediately on mute and the 20-second wait disappears
entirely.

---

## One process note

`origin/main` has had no new commits since my UI change on 29 July at 20:38.
Aditya's most recent commit anywhere in the repo is `c23f183`, 27 July. There are
no other remote branches.

So whatever went out "last night" is not in `Nablix-Labs/Demo-1`.

**The logs settle this too, and in his favour: nothing went out.** There was no
deploy on 29 July — the machine was shut down at 18:30 UTC and did not come back
until 03:38 the next morning. The backend on the VM matches `origin/main`. Aditya
did not push because there was nothing to push, and he did not break the voice.

Still worth keeping the habit of pushing before deploying, so the running backend
always corresponds to a reviewable commit. But there is no discrepancy to chase
here, and nobody should be treating this as one.

---

## If I were picking an order

1. **Turn off the nightly shutdown** (finding 0). Minutes of work, and it is the
   only item here that actually cost us a morning. Until it is done, every
   morning before 09:00 IST is a coin flip.
2. **Check the Cartesia and Inworld balances and add billing alerts**
   (finding 2b). Five minutes, removes a whole class of confusing failure.
3. **Session persistence** (finding 1). 66 lost turns in three days, and the
   nightly reboot guarantees more.
4. **The 15s / 40s timeout mismatch** (finding 2). Not urgent — 12.5s worst
   observed against a 15s limit — but the margin is thin and it will be
   misdiagnosed as finding 1 when it goes.
5. **The two `stop` hazards**, now that finding 4 has made them reachable.
6. **Connection reuse in the TTS adapters** (finding 3).

Items 1 and 2 are not code. They are the two that would have saved the most time,
which is worth noticing on its own — we spent a morning debugging a switched-off
machine.

Happy to take any of the frontend-side items. For the backend ones I only looked
— I have not touched that code.

---

## How I checked

Everything above marked "from logs" comes from the VM itself:

```bash
ssh -i <key>.pem developer@74.162.34.219
sudo journalctl -u nablix-voice --since "3 days ago"    # 4020 lines
last -x reboot shutdown                                  # the outage window
sudo ss -lntp | grep -E ":8000|:8001|:8004"              # process topology
```

Worth recording the topology, because it is not obvious and it cost me a wrong
theory. There are **three** listeners:

| Port | Process | Serves |
|---|---|---|
| 8001 | uvicorn, 1 worker | `/api/` — REST, and the session store |
| 8004 | standalone voice server | `/api/voice/stream` — the WebSocket |
| 8000 | gunicorn, **4 workers** | nothing nginx routes to |

I initially suspected the four gunicorn workers were splitting the session store
between REST and voice. They are not: `NABLIX_MAIN_BACKEND_URL` points the voice
server at 8001, the same process nginx uses for `/api/`, so both see the same
sessions. Worth confirming before anyone else has the same idea.

Two loose ends nobody should chase without checking first: the gunicorn cluster
on 8000 is not referenced anywhere in the nginx config and may be a leftover, and
`/api/health` reports `"mode":"inprocess"` even though nginx sends the WebSocket
to the separate 8004 service — so that field is misleading.
