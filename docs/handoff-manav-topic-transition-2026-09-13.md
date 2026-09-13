# Topic transition — Manav handoff

**Date:** 2026-09-13 · **From:** Chirudeva · **Re:** your reply of 13 Sep,
`Numera-ui/docs/FOR-CHIRU-2026-09-13.md`
**Evidence:** `docs/topic-transition-vm-verification-2026-09-13.md`
**Backend half:** `docs/topic-transition-plan-chiru-saravanan-2026-09-13.md`

## TL;DR

I checked your reply against the VM and the deployed bundle rather than against
the diff. Every checkable claim in it holds, and your two departures from the
Notion fix plan — no `'algebra'` fallback, no hardcoded `generateStaticParams`
list — are improvements, not shortcuts. Four things for you:

1. **One sentence in Cause 2 is wrong, and it is the sentence that downgrades
   the item.** Static export is on the transition path, not only on refresh and
   deep-links. §1.
2. **I am not picking the route shape yet, and I want item 6 done first** —
   because item 6 is what decides item 1. §2, then §3.
3. **No curriculum endpoint.** Saravanan is not building one; that answers your
   question at the end of Cause 2. §3.
4. **Item 8 is blocked, not yours.** I am routing it to Manjusha. §5.

Nothing needed on ask 3 (`skipsReplay`) or on red `main` — both confirmed
settled, detail at the end.

---

## 1. Cause 2 — the transition path, not just refresh

Your reply says:

> "The reported bug is fixed regardless, because the transition itself is a
> client-side `router.push` — Next routes it in the browser with the bundle
> already loaded and **never requests that document**."

The final clause is false for the Next 15 App Router. Loading
`https://nablix.ai/app/orientation/ALG-ORI-02/` with the network panel
recording, the app's client-side redirect to login produced:

```
GET https://nablix.ai/app/login/index.txt?_rsc=ZmCQ44b92m4mXe_R → 200 OK
```

That is the client router fetching the RSC payload for the route it is
navigating to, in this exact static-export deployment. A
`router.push('/orientation/<code>')` issues the same fetch.

And for a backend topic code, that fetch is answered wrongly under a success
status:

```
/app/login/index.txt?_rsc=…                    → 200   5487b  text/plain  1:"$Sreact.fragment"…
/app/orientation/algebra/index.txt?_rsc=…      → 200   6674b  text/plain  1:"$Sreact.fragment"…
/app/orientation/ALG-ORI-02/index.txt?_rsc=…   → 200  10990b  text/html   <!DOCTYPE html>…
/app/diagnostic/ALG-ORI-02/index.txt?_rsc=…    → 200  10990b  text/html   <!DOCTYPE html>…
```

Exported routes return a flight payload. Backend codes return the app shell as
HTML under **200 OK** — `try_files … /app/index.html` laundering a miss into a
success, so the router gets an unparseable body and no error status to detect.
It is specific to the `/app` location: `https://nablix.ai/index.txt` 404s
correctly.

No RSC payload for `ALG-ORI-02` exists on the server, so the App Router cannot
construct that route segment however much of the bundle is loaded. A hard load
of `/app/orientation/ALG-ORI-02/` confirms what comes back:
`app/page-3b83a0438f7b0fb7.js`, the chunk for the **root** route — the guided
lesson, not orientation.

What is still unproven, stated as such: the router's exact recovery behaviour on
a 200-with-HTML flight response (silent hard navigation vs. error boundary). I
could not establish it without entering credentials. If it hard-navigates, the
student lands on the guided lesson for the new topic instead of its orientation
or diagnostic — the same class of failure as the 2026-07-28 report.

Your `app/not-found.tsx` is the right call and is why the next unhandled id will
be a readable screen. It is the floor, as you said, not the fix.

---

## 2. Item 6 first — make nginx 404 a missing `*/index.txt`

Do this before anything else, for two reasons.

**It is correct regardless of route shape.** A router that can see the miss
degrades far better than one that cannot. Right now every miss under `/app` is
a 200.

**It is the gate on item 1.** The only argument against the sentinel catch-all
is that it depends on nginx answering RSC requests correctly — which is exactly
the part that is silently wrong today. Fix that and the argument either
evaporates or is confirmed. I would rather decide the route shape from an
observation than from a design argument, and this is the observation.

The config is only on the VM; there is nothing in the repo to change. The `/app`
location's `try_files` currently falls through to `/app/index.html` for
everything. It should keep doing that for navigation requests and stop doing it
for `*/index.txt`.

Verify with the appendix of the VM doc:

```bash
curl -s -H 'RSC: 1' -o /dev/null -w '%{http_code} %{size_download}b %{content_type}\n' \
  'https://nablix.ai/app/orientation/algebra/index.txt?_rsc=x'
curl -s -H 'RSC: 1' -o /dev/null -w '%{http_code} %{size_download}b %{content_type}\n' \
  'https://nablix.ai/app/orientation/ALG-ORI-02/index.txt?_rsc=x'
```

Line 1 must stay `200 … text/plain`. Line 2 must become `404`.

**Then send me one line: what the router does on that 404.** That closes item 1
and I will come back with the shape.

---

## 3. Item 5 — the route shape, after item 6

Not decided yet, on purpose. Both of your options are sound and I do not want to
pick between them on an argument when item 6 turns it into a measurement.

**First, the answer to your question:** no, there will be no curriculum-codes
endpoint. `GET /authoring/topics` already returns them, admin-scoped, but the
build-time `generateStaticParams` option it would serve is the weakest of the
three: it needs build-time network access to the Student Model, and it still
goes stale between deploys — a topic added after the last build fails
identically to today's bug. That is the failure mode you rejected the hardcoded
list for, with more machinery attached. So the choice is your two options, and
neither needs an endpoint.

So you do not have to re-derive it when the decision lands, here is what I found
in the code for each.

### If query param — `/orientation?topic=ALG-ORI-02`

One static file per route and correct for any code forever. The URL construction
is genuinely centralised, which is the good news:

- `lib/usePhaseRouting.ts:41-48` `PHASE_ROUTE` — the main table, behind
  `landingRoute` (`:71-81`), `handoffDestination` (`:95-101`), `routeForPhase`
  (`:140-142`), and the `usePhaseRouting()` hook (`:146-164`).
- `lib/flow.ts:38-53` `routeFor` — the demo flow's second copy of the same three
  URLs, consumed by `lib/useFlowNav.ts:42,50`.

Plus six hardcoded literals: `components/workbook/TopicBook.tsx:262,304`,
`app/orientation/[topic]/OrientationClient.tsx:202,736`, `lib/phases.ts:48,54`,
`app/dev-screens/page.tsx:43-46,54`.

Three things that are not obvious from the URL table:

- **`lib/usePhaseRouting.ts:162` compares `target !== pathname`.**
  `usePathname()` strips the query, so `'/orientation?topic=X' !== '/orientation'`
  stays true forever → infinite `router.push` loop. One line, but it will not
  announce itself.
- **There is no `useSearchParams` anywhere in `app/`, `components/` or `lib/`
  today.** Under `output: 'export'` it needs a `<Suspense>` boundary or the build
  fails, and there is no in-repo pattern to copy.
- **Two tests assert the literal URLs.**
  `lib/__tests__/nextTopicHandoff.test.ts:24,31,41,78` and
  `lib/__tests__/routeMatching.test.ts:53`. `phaseRoutingExemptions.test.ts:16`
  iterates topic paths too.

`components/AppFrame.tsx:25` `FOCUS_ROUTES` actually gets *simpler* — with the
query stripped, `/orientation` matches directly.

### If sentinel catch-all

URLs unchanged, both test files unchanged, no Suspense, no loop trap. Its whole
cost is the nginx behaviour, which item 6 has already fixed by then.

### Either way

The four `generateStaticParams` copies —
`app/orientation/[topic]/page.tsx:6-8`, `app/diagnostic/[topic]/page.tsx:5-7`,
`app/teach/[topic]/page.tsx:6-8`, `app/workbook/[topic]/page.tsx:6-8`, all
byte-identical — are still mapping `CURRICULUM` from `lib/curriculum.ts:42`, the
**mock fixture** (`algebra`, `number`, `geometry`, `statistics`). Four HTML files
per route, none of them a backend code. Whichever shape wins, that fixture stops
being the source of topic routes.

---

## 4. Item 7 — walk it end-to-end, once Saravanan's student lands

One correction to the ask as it was written, because it changes what to expect.

"A student who has never started a topic" is the right thing to ask for, but not
for the reason given. A fresh student does not produce a handoff by being fresh:
`next_topic_handoff` is emitted only on review completion, and only when the
current topic has a content-backed successor. ST015's is `null` because ST015 is
on the **last** topic, not because of anything about its history.

What makes the new student work is that with no journey row it starts at the
*head* of the curriculum ordering — so completing that topic's review does
produce a handoff. Saravanan is confirming the head is not also the tail before
handing the student over; if it is, the transition is untestable until a second
topic has active content, and that becomes the blocker rather than the student.

When you walk it: the thing to watch is the `index.txt?_rsc=` request for the
new topic. `text/plain` means the route exists and the transition is genuinely
fixed. `text/html` under a 200 means we are still where we are today. That single
request is the whole bug.

---

## 5. Item 8 — the `landingRoute` residual: blocked, not yours

Agreed with you completely, including not building it. `app/login/page.tsx:66`
routes off `res.last_journey_state?.current_phase` and `/session/start` corrects
afterwards; for ST015 the interim destination is `/practice`, an error state for
an exhausted student — invisible on a fast connection, a broken screen that
self-repairs on a slow one. `/session/start` taking 7+ seconds entering REVIEW is
expected and is not going to shrink, so the holding state is the real answer and
it is a design call. I am routing it to Manjusha. Nothing for you until it comes
back.

---

## Settled, nothing for you

**Ask 3 (`skipsReplay`)** — not reproducible, confirmed independently.
`skipsReplay` has exactly two non-test callers, both
`replayIndex = … ? -1 : 0`. There is no congratulatory branch to fix.

**Red `main`** — reproduced: 1 failed / 1300 passed of 1301, on
`interactionTurnContract.test.ts`, exactly as you described. Sanya's `f747c2a`
added `highlighted: true` to a resolved `INSERT_LABEL` and updated only one of
the two test files. Your `39e099b` fixes it. Confirmed.

**Causes 1 and 3** — both verified on the deployed bundle, not just in the diff.
Live chunk `8475-cad0c03ef89fa19b.js` carries the post-fix `LearningSummary`
including the conditional `next_action_message` paragraph. `lib/topicDisplay.ts`
degrades session title → curriculum title → raw code with `notFound()` surviving
only in `MockOrientation`, and `app/review/page.tsx:265` clears the phase rather
than guessing it. Clearing was the right call and it is the answer I gave you,
applied.

Two things your reply adds that the original diagnosis missed, both correct: the
same `notFound()` hit `/diagnostic/[topic]`, and `landingRoute` resolves an
absent `entry_phase` to `DIAGNOSTIC` — so this was the first screen of *every*
new topic, not only the orientation case.
