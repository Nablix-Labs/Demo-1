# Topic transition — VM verification of the 13 Sep frontend reply

**Date:** 13 September 2026
**Verified against:** `main` @ `172f2f7`, and the live deployment at `https://nablix.ai/app/`
**Scope:** cross-checking Manav's `FOR-CHIRU-2026-09-13.md` against repo and VM ground truth
**Method:** repo inspection, full frontend test suite, live HTTP probes, and a browser
session against the deployed app

---

## Verdict in one line

The blank page is genuinely fixed and deployed. The static-export item is **not**
"refresh and deep-links only" as the reply frames it — it sits on the transition
path itself, and the premise used to downgrade it is disproven by direct
observation on the VM.

---

## 1. What the reply gets right

Every checkable claim holds. Nothing in the document is overstated.

| Claim | Evidence |
|---|---|
| `df4be24` on `main` | ancestor of `origin/main` |
| Deployed to `nablix.ai/app/` | live chunk `8475-cad0c03ef89fa19b.js` contains the post-fix `LearningSummary`, including the conditional `next_action_message` paragraph |
| Cause 1 fixed without an `'algebra'` fallback | `lib/topicDisplay.ts` degrades session title → curriculum title → raw code; `notFound()` survives only in `MockOrientation` |
| Cause 3 fixed by clearing, not guessing | `app/review/page.tsx:265` `setCurrentPhase('')`; `routeForPhase` returns `null` for an empty phase |
| Ask 3 is not reproducible | `skipsReplay` has exactly two non-test callers, both `replayIndex = … ? -1 : 0`. No congratulatory branch exists to fix. |
| `main` was red; `39e099b` fixes it | reproduced locally: **1 failed / 1300 passed of 1301**, on `interactionTurnContract.test.ts`, exactly as described |
| §4 residual is real | `app/login/page.tsx:66` routes off `res.last_journey_state?.current_phase` |

Two things the reply adds that the original Notion diagnosis missed, both correct:

- The same `notFound()` hit `/diagnostic/[topic]`, and `landingRoute` resolves an
  absent `entry_phase` to `DIAGNOSTIC` — so this was the first screen of *every*
  new topic, not only the orientation case.
- Refusing the hardcoded `['ALG-KS3-01', 'ALG-ORI-02', …]` list in
  `generateStaticParams` is the right call: it goes stale on the next curriculum
  addition and fails silently and identically to the bug it patches.

---

## 2. The claim that does not hold

From the reply, §1 Cause 2:

> "The reported bug is fixed regardless, because the transition itself is a
> client-side `router.push` — Next routes it in the browser with the bundle
> already loaded and **never requests that document**."

The final clause is false for Next 15 App Router, and it is the sentence that
downgrades static export to a deep-link-only concern.

### 2.1 The client router does request a per-route document — observed live

Loading `https://nablix.ai/app/orientation/ALG-ORI-02/` in a browser and reading
the network log, the app's client-side redirect to login produced:

```
GET https://nablix.ai/app/login/index.txt?_rsc=ZmCQ44b92m4mXe_R → 200 OK
```

That is the App Router fetching the RSC (flight) payload for the route it is
navigating to, client-side, in this exact static-export deployment. The same
fetch is what a `router.push('/orientation/<code>')` issues.

### 2.2 For a backend topic code, that request is answered wrongly — with a success status

```
/app/login/index.txt?_rsc=…                    → 200   5487b  text/plain  1:"$Sreact.fragment"…
/app/orientation/algebra/index.txt?_rsc=…      → 200   6674b  text/plain  1:"$Sreact.fragment"…
/app/orientation/ALG-ORI-02/index.txt?_rsc=…   → 200  10990b  text/html   <!DOCTYPE html>…
/app/diagnostic/ALG-ORI-02/index.txt?_rsc=…    → 200  10990b  text/html   <!DOCTYPE html>…
```

Exported routes return a flight payload. Backend topic codes return the app
shell as HTML under a **200 OK** — nginx's `try_files … /app/index.html`
laundering a miss into a success. The router receives an unparseable body with
no error status to detect.

This is specific to the `/app` location. The root site 404s correctly
(`https://nablix.ai/index.txt` → 404), so the fallback rule is the cause.

### 2.3 Therefore the target screen cannot render

No RSC payload for `ALG-ORI-02` exists anywhere on the server. App Router cannot
construct a route segment without one, however much of the bundle is already
loaded. So on the current deployment the transition to a backend topic code
**cannot** produce the orientation or diagnostic screen — whatever recovery path
the router takes.

A hard load of `/app/orientation/ALG-ORI-02/` confirms what the server hands
back: it loads `app/page-3b83a0438f7b0fb7.js`, the chunk for the **root** route
— the guided lesson, not orientation.

### 2.4 What is still unproven — stated plainly

- **The router's exact recovery behaviour** on a 200-with-HTML flight response
  (silent hard navigation vs. error boundary). Establishing it needs an
  authenticated session inside the app; I cannot enter credentials.
- **The joined-up path.** Nobody has walked a real `next_topic_handoff`, Manav
  included — he says so in the reply: ST015's handoff is `null`.
- **Inference, flagged as such:** if the router hard-navigates, the student lands
  on the guided lesson for the new topic instead of its orientation or
  diagnostic. That is the same class of failure as the 2026-07-28 report
  (student shown the guided lesson, never the diagnostic).

---

## 3. Conclusion

- The reported symptom — the blank white page — is fixed, deployed, and verified.
- Two of the three causes are closed properly, and the reply's departures from the
  Notion fix plan are improvements, not shortcuts.
- The third cause is open and **more serious than the reply records**: it is not
  confined to refresh and deep-links, it is on the transition path.
- The transition end-to-end remains untested by anyone, in either direction.

---

## 4. Pending work

### Chirudeva — one decision

1. **Pick the static-export route shape.** Both options in the reply are sound;
   the VM evidence favours the **query param** (`/orientation?topic=ALG-ORI-02`):
   one static file and one RSC payload, correct for any code forever. It closes
   the deep-link failure and the client-navigation failure together. The sentinel
   catch-all still depends on nginx answering RSC requests correctly, which is
   precisely the part that is silently wrong today.

### Backend — Saravanan

2. **A second test student who has never started a topic.** Blocks Phases 0–3,
   and blocks verification of this fix: without a non-null `next_topic_handoff`
   nobody can walk the transition. Asked for independently by both sides now.
3. **The `CONTENT_GAP` / `RESCUE_REQUIRED` question.** ST015 is in
   `CONTENT_GAP` / `FRESH_CONTENT_UNAVAILABLE` with `T01.M7` still
   `RESCUE_REQUIRED`, while the Student Model answers `SESSION_OPENED` with
   `REVIEW`. The restore path refuses that payload; the session path accepts it.
   Unanswered since 11 Sep. Both sides agree not to guard it unilaterally —
   refusing it is what stranded ST015 on 4 Sep.
4. **Can the curriculum's topic codes be exposed on an endpoint?** If yes, a build
   step can generate `generateStaticParams` honestly and item 1 stops being a
   design argument.

### Frontend — Manav

5. **Implement the chosen route shape** once item 1 is decided. Until then the
   transition is unverified on the VM, not fixed.
6. **Make nginx 404 a missing `*/index.txt`** instead of returning 200 with the
   shell. Independent of item 1 and worth doing regardless: a router that can see
   the miss degrades far better than one that cannot.
7. **Walk the transition end-to-end** as soon as item 2 lands — a real handoff,
   observed, not verified in parts.
8. **The `landingRoute` residual (§4 of the reply).** `app/login/page.tsx` routes
   off `last_journey_state` first and `/session/start` corrects afterwards; for
   ST015 the interim destination is `/practice`, an error state for an exhausted
   student. Invisible on a fast connection, a broken screen that self-repairs on
   a slow one. `/session/start` can take 7+ seconds entering REVIEW, so this needs
   a holding state — Manjusha's call, correctly not built unilaterally.

### Not blocking

9. `main` was red since Thursday on a stale assertion in
   `interactionTurnContract.test.ts` (Sanya's `f747c2a` added `highlighted: true`
   to a resolved `INSERT_LABEL` and updated only one of the two test files).
   Fixed in `39e099b`. Reproduced and confirmed.

---

## Appendix — how to re-run these checks

```bash
# RSC payload shape: exported route vs backend topic code
curl -s -H 'RSC: 1' -o /dev/null -w '%{http_code} %{size_download}b %{content_type}\n' \
  'https://nablix.ai/app/orientation/algebra/index.txt?_rsc=x'
curl -s -H 'RSC: 1' -o /dev/null -w '%{http_code} %{size_download}b %{content_type}\n' \
  'https://nablix.ai/app/orientation/ALG-ORI-02/index.txt?_rsc=x'

# What is actually exported on the VM
ssh developer@74.162.34.219 'ls /var/www/numera/app/orientation/'
```

The browser half: open `https://nablix.ai/app/orientation/ALG-ORI-02/` with the
network panel recording and look for the `index.txt?_rsc=` request and its
content type.
