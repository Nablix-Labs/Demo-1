# Numera — Demo Flow Build Plan

> Goal: wire the **existing screens** into the full adaptive loop from
> [LEARNING-FLOW.md](./LEARNING-FLOW.md) using **mock data + a demo director**,
> so the founder can click through a complete end-to-end journey — including all
> three Feedback & Review branches and N → N+1 progression — with **zero backend**.

## Demo success criteria (what the founder must be able to do)

1. Start fresh → onboard → take Main Diagnostic → get **placed at a topic (N)** that changes with the diagnostic result.
2. Walk Topic N straight through: Orientation → Guided Learning → Practice → Feedback & Review — **no sub-diagnostic on N**.
3. At Feedback & Review, see the **three branches** fire: *can't solve* → Guided, *foundation weak* → Orientation, *pass* → next topic.
4. Advance to **Topic N+1** and see the **sub-diagnostic** now run, and its result **skip Orientation** when "knows concept."
5. See a **progress indicator** showing where they are in the loop + which topic.
6. Drive any branch on demand from a **Demo Director** panel (no need to actually fail a question).

If a person off the street can click through all of that without us explaining, the demo is done.

## Design decisions (assumptions — flag if wrong)

- **Mock 3 topics** (e.g. Algebra → Linear Equations → Quadratics) with placeholder content each. Enough to show N, N+1, and skip-orientation.
- **Demo Director panel** is the centerpiece — a floating control to force outcomes. This is how we show branches without real scoring.
- **Onboarding = minimal mock** (name + Start). No real auth.
- **Keep existing `lucide-react` icons for the demo.** The no-icons rule in `rules.md` is a cosmetic cleanup; doing it now would burn demo time for no flow value. Strip icons in a post-demo pass.
- Frontend stays display-only; all "decisions" are mock/forced. Shape matches future backend.

---

## Build sequence

Each phase has a verify gate. Don't start the next until the current one passes in the browser (dev server on :3020).

### Phase 0 — Flow model foundation *(no UI yet)*
- `lib/topics.ts` — ordered topic list `[{ id, name, concepts[] }]`, 3 topics with mock content refs.
- Extend `store/useNumeraStore.ts`: `entryTopicId`, `currentTopicId`, `phase`, `masteryByTopic`, and per-topic visited flags. Persisted.
- `lib/flow.ts` — **pure state machine**: `nextStep(state, event) → { route, phase }`. Encodes the rules:
  - entry topic (N) skips sub-diagnostic; N+1+ runs it
  - sub-diagnostic result may skip Orientation
  - Review branches: `cant_solve → guided`, `foundation_weak → orientation`, `pass → next topic`
  - rewrites the linear `lib/phases.ts` into this loop model (or supersedes it).
- **Verify:** type-check passes; a scratch call of `nextStep` for each event returns the right route.

### Phase 1 — Onboarding entry
- Add `/onboard` (or `/start`): name field + "Start" → sets session, routes to `/diagnostic`.
- **Verify:** load `/onboard` → Start → lands on diagnostic.

### Phase 2 — Main Diagnostic → dynamic entry topic
- Wire diagnostic result → `entryTopicId` + `currentTopicId` via mock score buckets (low score → earlier topic, high → later).
- On finish, route into Topic N **directly** (skip sub-diagnostic).
- **Verify:** two different mock score paths land on two different topics.

### Phase 3 — Topic loop wiring
- Each screen (`/orientation/[topic]`, root `/` Lesson = Guided Learning, `/practice`, `/review`) reads `currentTopicId`, advances `phase` on completion, and routes via `nextStep`.
- Insert **Guided Learning (root Lesson)** as a real gated phase between Orientation and Practice.
- **Verify:** click straight through one full topic, Orientation → Review, no dead ends.

### Phase 4 — Feedback & Review decision + branches
- Replace the dead-end `/keynotes` CTA with the **3-way branch** driven by `nextStep`.
- On `pass`: set `masteryByTopic[current]=true`, advance `currentTopicId` to N+1.
- **Verify:** each of the three outcomes routes to the correct screen; pass advances the topic.

### Phase 5 — Sub-diagnostic for N+1
- Entering N+1 runs `/diagnostic/[topic]`; mock result either proceeds to Orientation or **skips to Guided Learning**.
- **Verify:** Topic N has no sub-diagnostic; Topic N+1 shows it; skip-orientation path works.

### Phase 6 — Demo Director + progress HUD *(the demo enabler)*
- Floating **Director panel**: set entry topic, **force Review outcome** (pass / can't-solve / foundation-weak), jump to any stage, **reset session**.
- **Progress HUD**: compact indicator — current topic (N), current phase, mastery ticks.
- **Verify:** every branch and the N→N+1 jump are reachable purely from the panel.

### Phase 7 — Mock content polish
- Give each of the 3 topics plausible mock content: diagnostic Qs, a video placeholder, a lesson problem, a practice worksheet, review marks.
- Make the loop *feel* real (names, numbers consistent across stages).
- **Verify:** full click-through of 2 topics end-to-end looks coherent on screen.

---

## Founder demo script (the exact click-path)

1. `/onboard` → enter name → **Start**.
2. Main Diagnostic → (Director preset: "weak") → placed at **Topic 1 (N)**.
3. Topic N: Orientation → Guided Learning lesson → Practice.
4. At Review, Director → force **"can't solve"** → routes back to Guided Learning. *(show remediation)*
5. Practice again → Review → Director → force **"foundation weak"** → routes to Orientation. *(show deeper remediation)*
6. Practice again → Review → Director → force **"pass"** → **mastery** ✓ → advances to **Topic N+1**.
7. Topic N+1: **sub-diagnostic runs** → Director: "knows concept" → **skips Orientation** straight to Guided Learning.
8. Show the **progress HUD** the whole time so the loop is legible.

## Scope guardrails (don't gold-plate)

- No real auth, no real scoring, no backend calls. Mock everything.
- No new screens except `/onboard` and the Director panel. Reuse what exists.
- Don't strip icons / refactor unrelated code during this — flow first, polish later.
- 3 topics is enough. Don't model a full curriculum.

## Open questions that could change the plan

- Should the Director panel be visibly **on** during the founder demo (transparent "this is mock"), or hidden behind a keypress so the demo looks production-like? Default: visible, labeled "Demo controls."
- Are the 3 mock topics fine as Algebra-family, or does the founder want a specific subject?
