# Phase 4 frontend changes — artifact-free tutor replays (#294 / #310)

Branch: `codex/fix-phase3-stall-and-choice-review`. Backend counterpart: wrong
multiple-choice attempts now produce a grounded `TutorReplay` with no
`work_artifact` (nothing was drawn, so there is no PDF or page to show).

Everything below is a consequence of one contract change: `work_artifact` and
`artifact_id` became nullable. The frontend previously assumed an artifact was
always present and manufactured an empty one to keep that assumption true.

## 1. `lib/api.ts` — `Phase4Replay.work_artifact` / `artifact_id` nullable

`work_artifact: Phase4WorkArtifact | null`, `artifact_id: string | null`.

**Why:** the type has to say what the backend can actually send. Left
non-nullable, every consumer would keep type-checking against a shape that does
not exist at runtime for choice-only questions — the compiler would sign off on
code that reads `.pdf_url` from `null`.

## 2. `lib/phase4FromSession.ts` — stop inventing an empty artifact

`toReplay` used to always build a `work_artifact` object, filling `pdf_url: ''`
and `page_count: 0` when the backend sent nothing. It now maps an absent
artifact to `null`, and `artifact_id` defaults to `null` instead of `''`.

**Why:** "no work was submitted" and "work exists but the URL did not come
through" are different facts, and the old defaulting collapsed them into one.
Callers could not distinguish a degraded artifact from an absent one, so neither
could the UI. Preserving `null` keeps the distinction the backend now makes.
The `SessionPhase4Review` raw input type was widened the same way, because the
JSON genuinely contains `null`.

## 3. `lib/phase4Review.ts` — `openingPageNo` returns 1 with no artifact

Added an early `if (replay.work_artifact === null) return 1;`.

**Why:** the following line reads `replay.work_artifact.page_count`. Without the
guard this is a runtime TypeError on exactly the new case. Returning 1 matches
the function's existing "never discard a replay over a page problem" behaviour —
the page number is irrelevant when there is no document, and callers already
treat 1 as the harmless default.

## 4. `components/Phase4/TutorStage.tsx` — destructure defensively

`} = replay.work_artifact ?? {};` with `pdf_url: pdfUrl = ''` and
`page_count: pageCount = 0`.

**Why:** the component destructures the artifact at the top of render, so a
`null` would throw before anything paints. The defaults route straight into the
states the component already has — `!pdfUrl` renders the existing "Your original
work is not available for this question." panel, and `pageCount > 1` keeps the
page selector hidden. No new empty state was added; the absent-artifact case
lands in the one that was already written for a missing PDF. The tutor
explanation and audio are untouched, so an artifact-free replay is still fully
selectable and playable — which is the point of the fix.

## 5. Tests

- `phase4Contract.test.ts` / `phase4FromSession.test.ts`: two tests asserted the
  invented empty artifact (`pdf_url === ''`, `page_count === 0`). They now assert
  `work_artifact` is `null`. **Why:** they were pinning the behaviour this change
  deliberately removes; leaving them would have locked in the bug.
- `phase4Review.test.ts`: new case — `openingPageNo` on an artifact-free replay
  returns 1. **Why:** covers the guard in §3, which is the one branch that would
  otherwise crash in production.

## Verification

`npm test` — 1365 passed (137 files). `npm run build` — clean, type-checked.

## Deliberately not done

- No new "no work submitted" empty state. The existing missing-PDF panel says the
  right thing; a second one would be two components to keep in sync.
- No change to `QuestionJourneyItem`. The explanation and correct reasoning stay
  in the linked `TutorReplay.replay_steps` rather than being duplicated onto the
  journey row.

## Post-review amendments

Added after the two-axis review (`/code-review`, Standards + Spec axes).

- **`lib/phase4FromSession.ts`** — the surviving `raw.work_artifact?.page_count`
  inside the `raw.work_artifact ? …` branch was changed to a plain read, and the
  branch gained a comment saying why an absent artifact stays absent. **Why:** the
  optional chain implied a nullability the branch has already ruled out, and the
  only remaining comment described the *empty-artifact* fallback that this change
  deleted, so it read as the opposite of what the code now does.
- **`components/Phase4/TutorStage.tsx`** — added a comment above the destructure
  explaining that `pdfUrl = ''` / `pageCount = 0` deliberately route the
  artifact-free case into the panel's existing missing-work states. **Why:** the
  review flagged the defaults as the empty artifact the adapter had just stopped
  inventing. They are not: they are local render defaults, not data handed on to
  anything else, and the file's convention is that every non-obvious line says so.

No frontend behaviour changed in this pass — `npm test` 1365 passed,
`npm run build` compiled clean.
