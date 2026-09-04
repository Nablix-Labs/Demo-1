# Phase 4 — Review & Feedback: backend asks for the new design

**From:** Manav (frontend)
**Date:** 4 Sep 2026
**Re:** the "PHASE 4 — REVIEW & FEEDBACK / What Is Algebra?" mockup

---

## TL;DR

The mockup keeps the **layout we already ship** — three columns, question rail on the
left, tutor stage in the middle, feedback rail on the right. Nothing structural has to
be rebuilt.

What it adds is almost entirely **new data**. Nine fields, one of which (the board
diagram) is a genuinely new contract rather than an extra string, and one open question
about whether "Live" means live.

I can build every part of this once the fields exist. None of them can be derived on the
client, and I've said why in each case — that's the part worth checking, because if any
of them *can* be derived I'd rather do that than have you author it.

---

## 1. What already works — please don't rebuild these

These are live today and the mockup needs no change to them:

| Mockup element | Existing field |
|---|---|
| Topic title ("What Is Algebra?") | `topic_title` |
| Mastery chip ("Nearly mastered") | `topic_outcome.mastery_status` |
| Next-step chip ("Complete topic") | `topic_outcome.recommended_next_action` |
| "Review progress 2 of 3" | derived from replay index / `tutor_replays.length` |
| Left rail, one row per Phase 3 question | `question_journey[]` |
| Which rows are replayable | `question_journey[].review_item_id` |
| Centre stage walkthrough + play/pause | `tutor_replays[].replay_steps[]` |
| "First error" card | `tutor_replays[].first_error.summary` |
| "Next practice focus" card | `student_insights.next_practice_focus` |
| "Repeated pattern" card (text only) | `student_insights.learning_pattern_summary` |
| End review / session close | existing `/session/complete-review` + `/session/end` |

The left rail's accessible name in the shipped build is already
`Questions in independent practice` — the same wording as the mockup. So this is an
evolution of the current screen, not a redesign.

---

## 2. Backend asks

### 2.1 A short skill label per question — `question_journey[].skill_label`

The rail rows read **"Question 3 / Find a rule"**, not the full question text. Today we
render `question_text`, which is the whole prompt ("Which is the general rule: 12 + 4 or
n + 4? Explain briefly.") and does not fit a rail row.

```jsonc
"question_journey": [
  { "question_id": "...", "skill_label": "Add a fixed number", ... }
]
```

**Why not client-side:** truncating the question text gives "Which is the general
rul…", which is not a skill name. The label is a description of what the question
*tests* — that's micro-skill metadata you already hold, and §8.9 forbids us showing the
micro-skill id itself, so we need the human-readable form.

**Ask:** 2–4 words, student-facing, no ids.

---

### 2.2 A `PARTIAL` evaluation state

The mockup has **three** statuses with a legend: `Correct` (green), `Partial` (amber),
`Needs review` (red). Question 2 is Partial.

Today `Phase4Evaluation` is `CORRECT | INCORRECT | WRONG` and the client collapses it to
a boolean.

```jsonc
"evaluation": "CORRECT" | "PARTIAL" | "INCORRECT"
```

**Why not client-side:** "partially correct" is a grading judgement. We have no score,
no rubric and no per-component breakdown on this payload — inventing a middle state from
what we have would be the client re-deciding a mark you already made.

**Decision needed:** does `PARTIAL` get a replay? The mockup shows Q2 as Partial with
**no** red dot and it isn't the selected row, which reads like "no replay". Please
confirm — §3 currently says replays follow a *wrong* submission and nothing else, and I
don't want to widen that on my own.

---

### 2.3 A structured board diagram — the big one

This is the only ask that is a new contract rather than a new string.

The centre board in the mockup is not text. It is:

- three value nodes (`2`, `5`, `8`) with labelled down-arrows (`changes`)
- a brace across them labelled `+ 4  + 4  + 4`
- a second brace labelled `stays the same`
- a **struck-through wrong answer** `n × 4` in red
- a **boxed correct rule** `Rule: n + 4` in green
- a worked-example chip: `Try n = 6: 6 + 4 = 10`

Today each step gives us one flat string:

```jsonc
{ "sequence_no": 1, "narration": "...", "tutor_write": "n + 4" }
```

`tutor_write` can render a line of handwriting. It cannot express arrows, braces,
groupings, strike-throughs or colour semantics.

**Proposal — add an optional `board` to each replay step:**

```jsonc
{
  "sequence_no": 3,
  "narration": "So the rule is n plus four.",
  "tutor_write": "Rule: n + 4",
  "board": {
    "elements": [
      { "kind": "value_row",  "values": ["2", "5", "8"], "arrow_label": "changes" },
      { "kind": "brace",      "over": "value_row", "labels": ["+ 4", "+ 4", "+ 4"] },
      { "kind": "brace",      "over": "brace",     "label": "stays the same" },
      { "kind": "struck",     "text": "n × 4", "tone": "error" },
      { "kind": "boxed",      "text": "Rule: n + 4", "tone": "correct" },
      { "kind": "example",    "text": "Try n = 6:\n6 + 4 = 10" }
    ]
  }
}
```

**Why not client-side:** we would have to parse `"n × 4"` out of the narration, infer
that it is the wrong answer, infer that `n + 4` is the right one, and infer the grouping
structure over the values. That is the tutor's explanation being reverse-engineered from
its own prose — exactly the class of client-side re-decision that produced the rescue
bugs we just spent this week fixing.

**Fallback I will build regardless:** when `board` is absent, the step renders as today
(`tutor_write` as one handwritten line). So this can land incrementally, step type by
step type, without breaking the screen.

**Ask:** confirm the element vocabulary above covers Topic 1, or send back the set you'd
rather author against. The exact names don't matter to me; a **closed, typed set** does,
because an open-ended one puts the layout decisions back on the client.

---

### 2.4 "Your work" — an image snapshot and the error region

The mockup shows the student's own handwriting (`n × 4`) **circled in red**, inline,
with the caption *"This is a snapshot of your original answer. It will remain locked."*

Today `work_artifact` gives us `pdf_url` + `page_count`. A PDF is right for download; it
is wrong for a small inline panel, and it carries no error location.

```jsonc
"work_artifact": {
  "artifact_id": "...",
  "page_count": 1,
  "pdf_url": "...",
  "snapshot_image_url": "https://.../attempt-3.png",   // NEW
  "error_regions": [                                   // NEW
    { "x": 0.31, "y": 0.42, "w": 0.34, "h": 0.19, "tone": "error" }
  ]
}
```

**Why not client-side:** we have the student's strokes in the session, but not which
strokes constitute the error — that's the OCR/grading result, which lives with you.
Normalised 0–1 boxes, please, so the highlight survives whatever size we render at.

**Note:** the "Locked" affordance already exists on our side; nothing needed for it.

---

### 2.5 "Why it matters" — `first_error.why_it_matters`

New card. The mockup reads: *"Multiplication changes the size. We need the pattern to
increase by the same amount."*

This is a **conceptual** explanation of why the error is an error. `first_error.summary`
is a *description* of the error ("The first error was using n × 4 instead of adding 4") —
the mockup shows both, as separate cards, and they say different things.

```jsonc
"first_error": {
  "summary": "The first error was using \"n × 4\" instead of adding 4.",
  "why_it_matters": "Multiplication changes the size. We need the pattern to increase by the same amount.",
  "student_page_no": 1
}
```

**Why not client-side:** it's subject-matter explanation. We'd be writing maths content.

---

### 2.6 "Repeated pattern" — a count, not just prose

The mockup asserts a **number**: *"This 'n × 4' error has appeared in 2 other
questions."*

Today `learning_pattern_summary` is free prose and we print it verbatim.

```jsonc
"error_pattern": {
  "signature": "n × 4",
  "occurrence_count": 2,
  "question_ids": ["...", "..."]     // for our own linking, never displayed (§8.9)
}
```

**Why not client-side:** we only ever receive the replays, which are the *wrong*
submissions of this session. Counting occurrences across the topic — and deciding two
errors are the *same* error — is Student Model work.

**Keep `learning_pattern_summary`** as the fallback: where the engine can't assert a
signature, we render the prose exactly as we do now, and §7.6C's "null rather than a
claim" rule still holds. Null `error_pattern` ⇒ card hidden.

---

### 2.7 "Next action" — an encouraging sentence

The mockup's green card reads: *"Great progress! You are nearly there. Complete the
remaining question to finish this topic."* plus a **Continue review** button.

`topic_outcome.recommended_next_action` is a short label ("Complete topic") — right for
the header chip, too terse for this card.

```jsonc
"topic_outcome": {
  "mastery_status": "Nearly mastered",
  "recommended_next_action": "Complete topic",
  "next_action_message": "Great progress! You are nearly there. Complete the remaining question to finish this topic."
}
```

**Why not client-side:** it's personalised on progress ("nearly there", "the remaining
question"). Templating it here means the client asserting how well the student did.

---

### 2.8 Replay stage names — the bottom stepper

The mockup has a five-stage stepper: **Spot the pattern → Find the error → Build the
rule → Try an example → Takeaway**, with a tick on completed stages and the current one
highlighted.

Our steps carry `sequence_no` but no stage identity.

```jsonc
"replay_steps": [
  { "sequence_no": 1, "stage": "SPOT_PATTERN",  "stage_label": "Spot the pattern", ... },
  { "sequence_no": 2, "stage": "FIND_ERROR",    "stage_label": "Find the error",   ... }
]
```

**Why not client-side:** we'd be numbering steps 1..n and hoping there are exactly five,
in that order. If a replay has three steps or seven, a hardcoded stepper lies about
where the student is.

**Question:** are the five stages **fixed for every replay**, or per-replay? If fixed,
send them once at the review level and I'll map steps onto them. If they vary, per-step
is right. Either works — I need to know which.

---

### 2.9 Playback: time, audio, captions

The mockup's transport bar shows `01:48 / 04:32`, a scrubber, −10s / +10s, **1.25×**
speed, volume, and **CC**.

Our player today is **step-based**: it advances on a timer per step, with no total
duration, no audio track and no caption cues. Every control in that bar implies real
timed media.

Minimum to make the bar honest:

```jsonc
"replay_steps": [
  { "sequence_no": 1, "duration_ms": 21000, ... }
]
```

…which gives us total duration, a scrubber, seek and speed, with narration spoken
through the existing TTS path.

For **CC** and true audio scrubbing we'd want a pre-rendered track instead:

```jsonc
"replay_audio": {
  "url": "https://.../replay-3.mp3",
  "duration_ms": 272000,
  "cues": [ { "start_ms": 0, "end_ms": 4200, "text": "Look at how each number changes." } ]
}
```

**My recommendation:** ship `duration_ms` first. It unlocks the scrubber, the time
readout, seek and speed with no new infrastructure. Pre-rendered audio + cues is a
bigger piece and I'd rather it be its own decision than a hidden dependency of this
screen.

**If neither is coming,** tell me and I'll drop the scrubber, the time readout and CC
from the design rather than ship controls that don't do anything.

---

### 2.10 Open question: is "Live" actually live?

The centre panel is headed **"Tutor live review"** with a `Live` pill and *"Tutor is
explaining in real time"*, plus a broadcast icon.

Today a replay is **pre-authored**: `replay_steps[]` arrives complete on the session
record and we play it back. That is not live, and the two readings need different
backends:

- **(a) Presentational** — "live" is styling on the existing playback. **No backend work.**
  This is what I'd assume unless told otherwise.
- **(b) Genuinely streamed** — steps arrive over the voice socket as the tutor generates
  them. That needs a streaming contract, ordering/identity guarantees, and a
  reconnect story — i.e. the same machinery as stepwise rescue, and a real piece of work
  on both sides.

**Please pick.** I don't want to build (a) and have QA file it as broken, or scope (b)
when nobody asked for it.

---

## 3. Full proposed payload

Additions marked `// NEW`. Everything unmarked exists today and is unchanged.

```jsonc
{
  "student_id": "ST001",
  "topic_id": "ALG-ORI-01",
  "topic_title": "What Is Algebra?",

  "topic_outcome": {
    "mastery_status": "Nearly mastered",
    "recommended_next_action": "Complete topic",
    "next_action_message": "Great progress! You are nearly there. Complete the remaining question to finish this topic."   // NEW 2.7
  },

  "question_journey": [
    {
      "question_id": "Q-T01-001",
      "question_text": "Find a rule for: 2 + 4, 5 + 4, 8 + 4",
      "skill_label": "Add a fixed number",        // NEW 2.1
      "evaluation": "CORRECT",                     // NEW value: "PARTIAL" (2.2)
      "review_item_id": null
    }
  ],

  "tutor_replays": [
    {
      "review_item_id": "RI-3",
      "question_id": "Q-T01-003",
      "attempt_id": "AT-9",
      "artifact_id": "ART-9",
      "question_text": "Find a rule for: 2 + 4, 5 + 4, 8 + 4",

      "first_error": {
        "summary": "The first error was using \"n × 4\" instead of adding 4.",
        "why_it_matters": "Multiplication changes the size. We need the pattern to increase by the same amount.",  // NEW 2.5
        "student_page_no": 1
      },

      "replay_steps": [
        {
          "sequence_no": 1,
          "stage": "SPOT_PATTERN",                 // NEW 2.8
          "stage_label": "Spot the pattern",       // NEW 2.8
          "duration_ms": 21000,                    // NEW 2.9
          "narration": "Look at how each number changes.",
          "tutor_write": "2 → 5 → 8",
          "board": { "elements": [ /* NEW 2.3 */ ] }
        }
      ],

      "work_artifact": {
        "artifact_id": "ART-9",
        "page_count": 1,
        "pdf_url": "https://.../work.pdf",
        "snapshot_image_url": "https://.../attempt-9.png",                       // NEW 2.4
        "error_regions": [ { "x": 0.31, "y": 0.42, "w": 0.34, "h": 0.19 } ]      // NEW 2.4
      }
    }
  ],

  "student_insights": {
    "strength_summary": "...",
    "development_summary": "...",
    "learning_pattern_summary": "This \"n × 4\" error has appeared in 2 other questions.",
    "recent_improvement_summary": null,
    "next_practice_focus": "Focus on expressions with a fixed number added. We'll build confidence with more examples.",
    "personalised_notes": []
  },

  "error_pattern": {                               // NEW 2.6
    "signature": "n × 4",
    "occurrence_count": 2,
    "question_ids": ["Q-T01-004", "Q-T01-006"]
  },

  "key_takeaways": ["..."]
}
```

---

## 4. Priority

If this lands in pieces, this order gives the most visible progress per unit of work:

1. **2.1 skill labels** + **2.2 PARTIAL** — the left rail is the most visibly different part, and both are small.
2. **2.5 why it matters**, **2.6 error pattern**, **2.7 next action message** — three text fields, three new cards, right rail done.
3. **2.8 stage labels** — bottom stepper.
4. **2.4 snapshot image + error regions** — "Your work" panel.
5. **2.9 `duration_ms`** — makes the transport bar honest.
6. **2.3 board elements** — the biggest, and the one that most changes how the review *reads*.

---

## 5. What I'll do on the frontend

- Every new field is **optional**, and the screen degrades to today's rendering when it's
  absent — I'm not shipping anything that throws or blanks on a missing field.
  (We've had live outages from exactly that, so this isn't negotiable on my side.)
- No backend ids on screen — §8.9 and §9.3 still hold. `question_ids` in `error_pattern`
  are for linking only.
- `PARTIAL` gets its own colour and legend entry; whether it becomes replayable waits on
  your answer in 2.2.
- The board renderer will render the element kinds it knows and **skip** ones it doesn't,
  so you can add kinds without a frontend release.

---

## 6. Answers I need before I start

1. **2.10** — is "Live" presentational, or genuinely streamed?
2. **2.2** — does `PARTIAL` get a tutor replay?
3. **2.8** — are the five stages fixed for every replay, or per-replay?
4. **2.3** — does the element vocabulary cover Topic 1, or do you want a different set?
5. **2.9** — `duration_ms` only, or pre-rendered audio + caption cues?

Everything else I can start on as soon as the fields exist.
