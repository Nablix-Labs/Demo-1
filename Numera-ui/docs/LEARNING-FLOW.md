# Numera — Canonical Learning Flow

> Single source of truth for the adaptive learning funnel. Supersedes any older
> docs / ChatGPT threads where the flow differed. Confirmed with founder
> (WhatsApp, 2026-06-25).

## The flow

```
ONBOARD → MAIN DIAGNOSTIC ──┐  (one-time; places student at Topic N AND
                            │   serves as the topic-check for Topic N)
          ┌─────────────────┘
          ▼  TOPIC N: enter directly (no sub-diagnostic)
   ┌──────────────────── per-topic loop ───────────────────┐
   │                                                        │
   │   TOPIC DIAGNOSTIC      ← Topic N+1 onward ONLY         │
   │        │  small per-topic readiness check              │
   │        ├── knows concept  → GUIDED LEARNING (skip orient)│
   │        ▼                                                │
   │   CONCEPT ORIENTATION   (videos, weak concepts only)    │
   │        ▼                                                │
   │   GUIDED LEARNING       (AI teaches; "teach-while-learning")│
   │        ▼                                                │
   │   INDIVIDUAL PRACTICE   (test / independent attempt)    │
   │        ▼                                                │
   │   FEEDBACK & REVIEW  ◄── the decision point             │
   │        ├── can't solve      → GUIDED LEARNING           │
   │        ├── foundation weak   → CONCEPT ORIENTATION      │
   │        └── pass / mastery    → Topic N+1 ───────────────┘
```

## Stage definitions

| Stage | What it is | Frequency |
|---|---|---|
| **Onboard** | Registration + account setup | Once per student |
| **Main Diagnostic** | BIG placement assessment. Output = student level → **which topic they start at (Topic N)**. Also acts as the topic-check for Topic N (so Topic N is entered directly, no sub-diagnostic). | Once per student |
| **Topic Diagnostic** | SMALL per-topic readiness check. Runs **before every topic from N+1 onward**. Its result can route the student past Concept Orientation straight into Guided Learning. | Once per topic, from N+1 |
| **Concept Orientation** | Short concept videos. Entered only for the concepts the student is weak on. Skippable if the diagnostic says the concept is already known. | Per topic, conditional |
| **Guided Learning** | The live AI tutoring session — the core surface. "Teaching while learning." | Per topic |
| **Individual Practice** | The student solves on their own, tutor watches quietly. The *attempt*, not the judgment. | Per topic |
| **Feedback & Review** | **The decision point.** Evaluates the practice attempt, shows the student feedback, and routes them. Also where **mastery** is declared. | Per topic, loops |

## Decision logic (Feedback & Review → route)

Three exits, evaluated after each Individual Practice attempt:

1. **Can't solve** (concept understood, execution fails) → back to **Guided Learning**
2. **Foundation weak** (concept not understood) → back to **Concept Orientation**
3. **Pass / mastery** → **mastery** declared, advance to **Topic N+1**

The loop bounces only between Guided Learning and Concept Orientation. **There is
NO going back to the Main Diagnostic — ever.** The only recurring diagnostic is
the small per-topic one, and it runs *before* a topic, never as a failure path.

## Key invariants (don't get these wrong)

- **The starting topic is dynamic.** Topic N is an *output* of the Main
  Diagnostic, not a constant. "Is this the entry topic?" must be
  `topic === entryTopic`, **not** `topicIndex === 0`.
- **N vs N+1 rule:** the entry topic (N) skips its sub-diagnostic because the
  Main Diagnostic already covered it. Every later topic (N+1, N+2, …) runs its
  own Topic Diagnostic first.
- **Practice ≠ decision.** Practice is the attempt; Feedback & Review is the
  judge + router. Mastery is declared in Feedback & Review, not in Practice.
- The frontend is a display/interaction layer only; routing/scoring decisions
  are backend-driven. The frontend models the *shape* of the flow.

## Screen mapping (current Numera-ui)

| Stage | Route | Status |
|---|---|---|
| Onboard / Register | — | ❌ missing |
| Main Diagnostic | `/diagnostic` | ✅ |
| Topic Diagnostic | `/diagnostic/[topic]` | ✅ exists |
| Concept Orientation | `/orientation/[topic]` | ✅ |
| Guided Learning | `/` (root Lesson: voice agent + canvas) | ✅ |
| Individual Practice | `/practice` | ✅ |
| Feedback & Review | `/review` | ✅ |
| Extras (not in core flow) | keynotes, workbook, challenge, flagged, history, people, files | ✅ |

## Implementation gaps (frontend vs. this spec)

`lib/phases.ts` currently models a **linear, forward-only** funnel
(`diagnostic → orientation → workbook → practice → review`, terminal). It does
**not** yet model:

1. **The remediation loop** — `review` is a dead end (its only CTA links to
   `/keynotes`); the three-way branch doesn't exist in the frontend.
2. **Guided Learning as a gated phase** — the root Lesson isn't in the phase
   chain; `workbook` sits in its place but is a topic-picker, not teaching.
3. **Dynamic entry topic (N)** — diagnostic is a one-shot entry with no
   `entryTopic`; orientation is hardcoded to `/orientation/algebra`.
4. **Mastery state + Topic N+1 advance** — no mastery flag, no next-topic transition.
5. **Onboarding/registration screen.**

These are deliberately deferred ("unlocks would be backend-driven"), but #1–#4
are the adaptive core of the product and aren't represented in the frontend yet.

## Still-open product questions (need founder input)

- **Feedback & Review: AI-automated, human-in-the-loop, or hybrid?** Determines
  most of the downstream architecture.
- **Routing thresholds** — what score/signal triggers each of the three exits?
- **Loop termination** — if a student keeps failing, is there a max-attempts /
  escalation / floor? (Main Diagnostic is explicitly ruled out as a fallback.)
- **Mastery definition** — pass once, or sustained (pass N times / retention)?
- **Topic Diagnostic skip granularity** — can it skip only Orientation, or also
  skip Guided Learning into Practice?
