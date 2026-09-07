# Open questions

Things I need an answer on eventually. None of them are blocking, so I am
building past them with the assumption written down next to each one. If an
assumption turns out wrong, the fix is listed so the cost is visible.

Last updated: 3 September 2026

---

## 1. There is no `topics` sheet in the new export

`nablix_content_export.xlsx` has 26 sheets and none of them is `topics`. Six
tables reference `topic_id`, and `topic_scope` has rows for topics 2 and 3, but
nothing in the export carries the topic itself: title, learning goal, core
message, KS stage, sequence number.

We generate that table today and it holds real content, most of it drawn
straight from the topic documents.

**Assumption:** the export just does not cover it, and the topic record lives
somewhere the export does not reach. We keep generating `topics`.

**If wrong:** we stop writing one sheet. Cheap either way, which is why I am
not waiting. But dropping it without asking would silently lose the learning
goal and core message, so keeping it is the safer default.

---

## 2. Orientation is per topic, but the rule is per micro-skill

The review says every active micro-skill needs at least one teaching exposure.
The new tables key orientation to `topic_id`: 3 videos for 22 micro-skills, and
one support card in total.

So either a topic's video scenes are meant to cover all of its skills between
them, or something links a skill to its exposure and is missing.

**Assumption:** exposure is satisfied at topic level for now. We do not
generate orientation content, because `orientation_videos.asset_url` points at
produced video files in blob storage, which are clearly authored rather than
generated.

**If wrong:** we would need a per-skill orientation generator, and a way to
check every skill is covered. That is new work, not a tweak.

---

## 3. Do we generate video scenes and support cards?

`orientation_video_scenes` holds narration, visual action, on-screen text and
direction. That is writable content. `orientation_support_cards` likewise.
Neither is in the CG-015 to CG-019 roadmap.

Relevant: the review flagged `Q-T02-015` for referencing a support card that
did not exist. The card does exist, in this export, as
`CARD-T02-FRACTIONAL-COEFFICIENT`. So the real problem was that our workbook
had nowhere to put it, not that the card was invented.

**Assumption:** not ours for now. We write the three orientation sheets empty
so the gap is visible in the file rather than absent from it.

---

## 4. `visual_cues.actions` is a new column and is empty in all 14 rows

No example of what belongs in it.

**Assumption:** written empty. If it turns out to hold something the tutor
needs, CG-017 has to fill it and we would want an example first.

---

## 5. The topic id split is still in the export

`ALG-KS3-01` in `micro_skills`, `questions`, `worked_examples`,
`parallel_examples` and `orientation_videos`, against `ALG-ORI-02` and
`ALG-ORI-03` for the other two topics. `topic_scope` has no Topic 1 rows at
all.

This is the same defect recorded during M2 in the original reference workbook,
now carried into the new export. All six topic documents use the `ALG-ORI-nn`
form.

**Assumption:** `ALG-ORI-nn` is correct and Topic 1 is the odd one out. We
generate `ALG-ORI-01`. Flagging because if `ALG-KS3-01` is what the platform
actually holds for Topic 1, our foreign keys will not match on import.

---

## 6. The template's data contradicts the review

Worth stating plainly since it is the thing most likely to cause confusion
later. `nablix_content_export.xlsx` still contains:

- up to 5 micro-skill mappings on one question, where the review requires 1
- weights from 0.1 to 1.0, where the review requires 1.0
- 46 secondary mappings, where the review requires none
- difficulty 1 and 2 only, no difficulty 3
- all 63 questions marked `APPROVED`

**Assumption:** the export is a schema update, not an example of the rules. We
take table shape from it and content rules from the review document. Confirmed
in part by her own note: "i thought it would make it simpler to have only one
PRIMARY with weight 1".

---

## 7. Phase 0 difficulty is unspecified

The review gives difficulty targets "for Phase 2 and Phase 3" and none for the
diagnostic.

**Assumption:** difficulty 2. A question nearly every student answers
correctly separates nobody, and a diagnostic exists to separate. Held in
`coverage_plan.DIAGNOSTIC_DIFFICULTY` and marked as inferred, so changing it is
one line.

---

## 8. The completeness rule in the original document conflicts with the revision

The original asks for at least 2 questions per micro-skill per phase per
difficulty, and says generation is incomplete below that. The revised note asks
for 1 each, 7 per skill in total.

**Assumption:** the revision supersedes. A check written to the original would
mark every topic incomplete.
