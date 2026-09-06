# Phase 2 support presentation — design

**Date:** 2026-09-06
**Author:** Manav (frontend)
**Requested by:** Manjusha, WhatsApp 5 Sep
**Status:** design, awaiting approval — nothing built yet

---

## What was asked

> We need to organize phase 2 better, currently it's very cluttered, can you do
> something […] I was thinking only the latest one we should show, like hint1,
> hint 2, visual cue, parallel ex, tutor solve — only one at a time (the latest)
> should be visible. The rear should be stacked, if the student wants to see he
> can click and see […] If you have better ideas please work it out […] We need
> to fine tune scaffolding ui a bit better […] Overall phase 2 ui elements should
> be organized in a much better way.

Her screenshot has a GUIDED STEP panel, a VISUAL CUE note and a "LET ME SHOW YOU"
walkthrough on screen at the same time, over the canvas the student is meant to
be writing on.

---

## The problem, precisely

Nothing owns "what support is on screen". The decision is split across three
files that do not consult each other:

| Where | Rule it enforces |
|---|---|
| `components/SupportLane.tsx:81` | A rescue hides the write note, hint and cue |
| `store/useNumeraStore.ts:1300-1308` | Showing a cue clears the hint (one direction only — hiding the cue does not bring it back) |
| `store/useNumeraStore.ts:1739-1749` | A new rescue step clears hint, write instruction, scaffold and cue |
| `components/Canvas/index.tsx:252` | The scaffold hides during a rescue |
| `lib/rescueMode.ts` | Stepwise rescue beats the legacy card |

What follows from that:

- **`WriteNote`, `HintNote` and `VisualCue` have no mutual exclusion at all.**
  All three can be up together, and with a worked example that is four cards.
  `SupportLane.tsx:56-59` records this measured at 918px in a 900px window, with
  the bottom card's controls below the fold and unclickable.
- **The scaffold is not in the lane.** It renders on the canvas under the
  question strip (`Canvas/index.tsx:252-256`), so no lane rule can reach it.
- **Dismissing destroys.** The X on a hint or cue clears the store field. A
  student who closes a hint and then wants it back has no way to get it.
- **There is no history.** `supportShown` (`store:543`) holds one rung and is
  written only from the Phase 3 path (`useDemoTutor.ts:1148`). On the guided
  screen it is never set.

`lib/rescueMode.ts` already solved this shape of problem once, for rescue only:
before it, five things independently decided whether a rescue was running and
every reported symptom was two of them disagreeing. This design generalises that
cure to the whole ladder.

---

## The model

Two tiers, because two genuinely different things are being shown.

### Tier 1 — instructions

What the student is meant to be doing **now**. Always visible, never collapsed,
never in the deck.

- **`ScaffoldPanel`** — the guided step. Stays on the canvas under the question.
- **`WriteNote`** — the write instruction. Keeps its own slot at the top of the
  lane.

`SupportLane.tsx:76-80` already argues this for the write note: *"above the
ladder, not part of it — a WRITE instruction is the tutor saying it could not
read the student, and it names the action that moves the turn on. Below a hint
it would read as the least urgent thing on screen when it is the only one that
unblocks them."* The same argument applies to the guided step, and Manjusha's
own message omits scaffolding from the stack list.

### Tier 2 — the support deck

Help that has been **offered**. One card visible, the rest retrievable.

```
HINT → VISUAL_CUE → PARALLEL_EXAMPLE → TUTOR_SOLVED
```

`SUPPORT_ORDER` already exists (`lib/supportLadder.ts:28`) as
`['HINT','VISUAL_CUE','SCAFFOLD','PARALLEL_EXAMPLE','TUTOR_SOLVED']`. It loses
`SCAFFOLD`, which is now tier 1. The remainder is exactly Manjusha's list.

**"Latest" means most recently arrived**, with ladder rank breaking ties between
rungs that arrive on the same turn. Arrival order is what the word means, and it
stays correct if the backend ever delivers out of ladder order — which the
frontend must not assume, since the ladder rule is documented as backend
behaviour, not something we can enforce.

---

## `lib/supportDeck.ts`

One module answers *which rung is showing*. Every render site asks it rather
than deciding for itself. This is the architectural point of the change; the
visual result follows from it.

```ts
/** The tier-2 subset of SupportRung — SUPPORT_ORDER without SCAFFOLD. */
export type DeckRung = 'HINT' | 'VISUAL_CUE' | 'PARALLEL_EXAMPLE' | 'TUTOR_SOLVED';

/**
 * Rungs currently held, oldest first: the stored arrival order, filtered to
 * those whose content is actually live. Order is remembered; membership is
 * derived. So a rung the backend has cleared leaves the deck on the next read
 * without anything having to remember to remove it.
 */
export function deckRungs(state: DeckState): DeckRung[];

/** The single rung to render: the opened one, else the latest. */
export function visibleRung(state: DeckState): DeckRung | null;

/** The rest, for the "Earlier help" strip. */
export function collapsedRungs(state: DeckState): DeckRung[];

/** Human label for a chip. */
export function rungLabel(rung: DeckRung): string;
```

**The deck holds which rungs exist and in what order — never their content.**
Content stays exactly where it lives today (`visibleHint`, `visualCue*`,
`guidedRescue`, `rescueSteps`). Duplicating it would create a second thing to
keep in step and a new class of clearing bug; the deck is an index, not a store.

### State

Two new fields on `useNumeraStore`:

- `supportDeck: DeckRung[]` — arrival **order** only. A rung that arrives again
  moves to the end; it has just been offered, so it is the latest. Membership is
  not read from here directly: `deckRungs()` filters this list against live
  content, so this field can safely hold a rung whose content has since gone.
- `openedRung: DeckRung | null` — `null` means "show the latest". Set when the
  student clicks a chip.

Both join the existing question-change clear block (`store:1087-1135`) alongside
the fields they index. Neither is persisted, matching every other support field.

---

## Rendering

`SupportLane` becomes three parts:

```
┌──────────────────────┐
│ WriteNote            │  tier 1 — only when a write instruction is live
├──────────────────────┤
│ the visible card     │  exactly one of HintNote / VisualCue /
│                      │  RescueNote / RescueSteps
├──────────────────────┤
│ Earlier help         │  chips for collapsedRungs(), hidden when empty
│ [Hint] [Visual cue]  │
└──────────────────────┘
```

Clicking a chip sets `openedRung`. The open card gains a "Back to latest"
control; the chip for the latest rung sits in the strip while an older one is
open, so there are two ways back.

The lane keeps its current position, `panelSide` mirroring and bounded scroll.
With one card the scroll cap should stop mattering, but it stays — a single
walkthrough on a short window can still overflow, and removing it would be
removing a fix.

### The rescue rule, restated

The deck subsumes `SupportLane.tsx:81`. Today opening a rescue **destroys** the
rungs above it; now it **demotes** them to chips. That satisfies the original
reasoning — they are no longer competing instructions beside the thing the tutor
is actually doing — while letting a student re-read the hint they were given.

**`legacyRescueVisible` precedence is untouched.** The legacy `guided_rescue`
payload carries every step including the answer, so rendering it beside a
stepwise walkthrough hands over the answer that walkthrough is deliberately
releasing one step at a time. The deck treats both as the single `TUTOR_SOLVED`
entry and lets `lib/rescueMode.ts` keep deciding which component renders it.

---

## Behaviour changes

**Dismiss collapses instead of destroying.** The X on `HintNote` (`:58`) and
`VisualCue` (`:83`) moves that rung to the strip rather than clearing its store
field. Nothing the tutor has offered becomes unrecoverable. `WriteNote` and
`ScaffoldPanel` have no dismiss today and gain none — they are instructions.

**A new rung snaps the view to itself**, even if the student is reading an older
card. Support arrives in response to something the student did or asked for, so
the new offer is the answer to their most recent action; leaving it behind a
chip would hide the thing they just requested. The card they were reading is one
click away in the strip.

---

## Scaffolding

Manjusha's second ask. The guided step currently renders as another card
competing with the support notes for the same attention.

The change is a treatment, not a rebuild: give the guided step a visual identity
as an **instruction** rather than a sticky note, so "what to do" and "help
available" stop reading as the same kind of object. The step counter stays; the
no-next-button contract stays (the backend releases the next step on the next
turn, `ScaffoldPanel.tsx:8-22`).

Deliberately modest, and flagged for Manjusha to look at on the dev screen
before it goes further. Restyling it blind is how it ends up wrong twice.

---

## Edge cases

| Case | Behaviour |
|---|---|
| A rung's content is cleared by the backend (e.g. cue hidden) | It leaves the deck. `deckRungs` derives from live content, so the index cannot outlive what it points at. |
| `openedRung` is no longer in the deck | Falls back to the latest. Never renders an empty card. |
| Deck has one entry | No strip. One card, as today. |
| Deck is empty | Lane renders nothing but the write note, if any. |
| Phase 3 | Unchanged — every support surface is already suppressed there, and this design does not touch those gates. |
| Duplicate/replayed turn re-sends the same rung | Moves to latest; the deck is a set by rung, so it cannot grow unboundedly. |

---

## Testing

`lib/supportDeck.ts` is pure and gets real unit tests: ordering, latest
selection, same-turn tie-breaking by ladder rank, re-send behaviour, fallback
when `openedRung` is stale, clear on question change, and that rescue precedence
is preserved.

This repo has no `.tsx` test setup and this change does not add one. The visual
half is verified through **`/dev-screens/support-deck`**, a fixture screen in the
pattern of `/dev-screens/phase4` — every rung combination selectable, no login
and no backend.

That screen is also how Manjusha reviews this. It works with the VM down, which
matters: the VM is currently unreachable.

---

## Out of scope

- **Nablix Assist** (`components/support/*`) — product/human support, a separate
  code path from the learning ladder. Untouched.
- **A z-index constants refactor.** Every layer value in the app is an inline
  literal and there is no documented convention; that is worth fixing and is not
  this change.
- **Phase 3.** Support is already suppressed there.
- **The support ladder's backend contract.** `PARALLEL_EXAMPLE` still has no
  response field of its own (`docs/PHASE2-GUIDED-BACKEND-ASKS.md` C7). This
  design presents what arrives; it does not add rungs the backend cannot send.

---

## Open question

Her screenshot shows a scaffold, a cue and a walkthrough together, which
`7e486df` (4 Sep, "Make guided rescue an exclusive presentation mode") should
already prevent — both gates read `rescueSteps.length > 0`, which is still true
on the final step shown in her screenshot.

So either that build was not live when she looked, or the rule is being defeated
somewhere. The deployed build id settles it in one request and the VM is down,
so it is unresolved. **It does not block this design** — the clutter it
addresses is the un-excluded hint/cue/write trio, which is real on any build —
but if the rule is genuinely broken there is a bug to find underneath the
redesign, and it should be checked before this is called done.
