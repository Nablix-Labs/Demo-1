# Content Approver — v3 contract reconciliation

What the frontend needs from the `/authoring/*` API, stated as deltas against
**UI Hierarchy Contract v3.0-hierarchical** (`Nablix_Content_Approver_T02_UI_Hierarchy_AllPages_v3.json`
+ `Nablix_Content_Approver_JSON_Usage_Guide.docx`, both dated 8 Aug 2026).

Audited against: the v3 sample responses, the source workbook
`Nablix_Topics_1_to_3_Canvas_AnswerSteps.xlsx` (27 sheets), and the built portal
(`nablix-authoring-ui`, all 15 screens on mock data).

**Verdict: adopt v3 as-is.** It is a better fit for this UI than the bundle the
portal currently consumes, and it is already the shared vocabulary with the
backend. The frontend is being refactored onto it. What follows is the small set
of additions the UI needs before the endpoints are built, and the schema changes
those imply.

---

## 1. Blocking gaps — the UI cannot implement v3's own rules without these

### 1.1 Misconception → Hint / Visual Cue links are the contract's spine but have no schema note

The guide calls this "critical parent/child behaviour" and devotes §9.2 plus a
whole example file to it. The workbook does carry the mapping tables —
`Misconception_Hints (misconception_id, hint_id, sequence_order)` and
`Misconception_VisualCues (misconception_id, visual_cue_id, sequence_order)` —
so this is implementable today. Flagging it because it is the relation most
likely to be dropped when a backend developer reads `Hints` as a standalone
table.

**Correction, 24 Aug 2026:** this section previously said the portal "does not
model" the relation and "renders a flat topic-level hint list". That was true
when it was written on 10 Aug and stopped being true when the Hints page moved
onto the v3 contract. The page now renders `hierarchy.misconception_groups`,
opens on `default_selection`, filters children to the selected parent, shows
`parent_context.sequence_order`, and warns on `shared_by_misconception_count`
before an edit. The ask below is unchanged and is purely about what the **API**
must return — the UI is ready for it.

**Required:** `/authoring/topics/{id}/support-assets` must return hints grouped
under their misconception, ordered by `Misconception_Hints.sequence_order`, and
must return `shared_by_misconception_count` / `_ids` on each hint (not only on
visual cues, as the v3 sample does). A hint shared across misconceptions needs
the same "used by N" warning before save that a cue does.

### 1.2 `Question_Error_Map.micro_skill_id` — confirmed absent, please add

The guide already flags this. Confirmed against the workbook: `Question_Error_Map`
is `(question_id, response_pattern, error_code)` only — 82 rows, no skill column.

The v3 sample papers over it with `micro_skill_context_source` /
`source_schema_has_micro_skill_id` on each error mapping. Those are useful as a
migration signal but the UI should not ship reading them. **Add the column**;
drop the two synthetic fields once it lands.

Corollary, also already in the guide and confirmed present in the workbook:
`Error_Types.related_micro_skill_id` exists and must **not** be exposed.

### 1.3 Misconceptions have no order column

Confirmed: the `Misconceptions` sheet has no `display_order`. v3 returns one
anyway, which is right — but it must be **deterministic across requests**, or
"first misconception" changes between page loads and the default selection moves
under the approver. Either persist the column or derive it from a stable key.

Same class of problem, lower stakes: `Hints` has `hint_level` but a hint's
position is only defined by `Misconception_Hints.sequence_order` — i.e. per
parent. Two misconceptions can order the same hint differently. The API must
send the sequence for the parent being viewed (v3 does this correctly in
`selected_item.parent_context.sequence_order` — keep it).

### 1.4 Orientation has no video parent record

Confirmed: `Orientation_Video_Scenes` carries `video_id`, but there is no
`Orientation_Videos` sheet anywhere in the workbook. So there is no video title,
no duration, no status, and **no `topic_id` on the video** — the topic link only
exists transitively through scenes.

The guide calls this a structural warning. For the UI it is worse than a
warning: the Orientation page's hierarchy is `Topic → Video → Scenes`, and the
middle level currently cannot be rendered from data. Either normalise the table,
or v3 must define the synthetic video object the API will return (id, title,
duration = sum of scenes, status = rolled up) so the frontend isn't inventing it.

**Update, 10 Aug 2026:** storage is now settled — Azure Blob Storage, chosen to
keep as much as possible in one ecosystem. That turns this from a warning into a
blocker, because there is nowhere in the schema *or* in the v3 payload to put the
file's URL. The table needs creating with a `video_url` field, and page 06's
`hierarchy.video` node needs `video_url` added. Written up separately as
*Addendum 1: orientation video storage and schema*.

---

## 2. Fields the workbook has and v3 drops

These exist in the source data, the portal has screens that want them, and the
v3 sample responses omit them. Cheap to add now, expensive after the endpoints
are written.

| Sheet | Field(s) dropped by v3 | Why the UI wants it |
|---|---|---|
| `Visual_Cues` | `asset_url`, `image_generation_prompt`, `negative_prompt`, `tutor_explanation_template`, `retrieval_text`, `retrieval_keywords`, `embedding_status` | The whole cue editor, essentially. `asset_url` matters most: it is the subject of v3's own `VISUAL_CUE_ASSET_PENDING` warning, so the contract raises a warning about a field it never sends. v3 returns cues as `{id, sequence_order, label, preview, active, shared_by…}` only. |
| `Parallel_Examples` | `worked_steps` | A parallel example is a worked solution; without steps it's just a statement and an answer. |
| `Micro_Skills` | `prerequisite_micro_skill_id` | Micro-skill detail shows the prerequisite chain. |
| coverage cells (page 14) | `add_action` | The guide says clicking a red or amber cell should open the creation flow with `topic_id` and `micro_skill_id` prefilled, but no coverage cell carries an `add_action`. Without it a cell click can only reach the owning section, not a prefilled form. Same applies to the `+ Add` affordances the guide requires at every hierarchy level. |

Everything else I initially suspected was missing turned out to be present on
inspection — `Scaffold_Steps.partial_content`, the `Question_Scaffolds` link
(as `question_links`, with `priority` and micro-skill context),
`Misconception_Errors.confidence_weight`, `Source_Provenance.source_item_id` /
`license_url`, scene `direction`, and `version` on questions are all in the
sample responses. v3 is more complete than a first read suggests.

## 3. Naming to settle before implementation

v3 and the portal disagree on a handful of names. v3 wins on all of them — the
frontend is changing — but they need to be fixed in writing so nobody re-litigates:

| Concept | v3 (adopt) | Portal today (changing) |
|---|---|---|
| Topic title | `title` | `topic_title` |
| Completion | `completion_percent` | `completion_pct` |
| Lifecycle | `workflow_status` | `status` |
| Health state | `COMPLETE` / `WARNING` / `MISSING` | `ok` / `warn` / `missing` |
| Validation severity | `blocking: bool` + `severity` | `severity: 'blocking'\|'warning'` |

### Inconsistencies inside v3 itself

Found by building against it, not by reading it. None are blocking — the
frontend handles all four — but each is a trap for whoever writes the endpoints,
because the sample teaches the wrong lesson if you only read one page.

1. **`title` vs `topic_title`.** Every workspace page sends `topic.title`;
   page 03 alone sends `topic.topic_title`. Pick one.
2. **Tab ids are plural, support types are singular.** Page 12 sends
   `tabs[].tab_id = "HINTS" | "VISUAL_CUES"` but
   `default_selection.support_type = "HINT"` and
   `selected_item.entity_type = "HINT"`. They look interchangeable and are not —
   comparing them directly leaves no tab highlighted on load, which is exactly
   the bug I hit.
3. **`answer_steps` is an array of objects**, `{step_no, text}` — not the array
   of strings that `accepted_answers` and `common_wrong_answers` are, right
   beside it in the same object.
4. **A fourth phase exists.** `PHASE_1_ORIENTATION` appears on worked examples,
   though only three phases carry questions. Anything typed as "the phase enum"
   needs all four.

One genuine ambiguity, not just naming: v3 uses `status` for **activity**
(`ACTIVE`/`INACTIVE`) on micro-skills, hints and misconceptions, and
`workflow_status` for **lifecycle** (`DRAFT`…`ARCHIVED`) on topics — but
`Worked_Examples.status` and `Orientation_Video_Scenes.status` in the workbook
look like lifecycle values. Please confirm which vocabulary each entity's
`status` draws from; the UI renders a different pill for each.

## 4. Confirmed correct — no change requested

Recording these so they don't get "fixed" later:

- **Page-wise responses in production.** Agreed. The portal is being refactored
  from one topic-wide bundle to the 15 page endpoints.
- **`{ success, _meta, data }` envelope.** Fine. The frontend unwraps `.data`;
  `_meta` is treated as non-editable.
- **Explicit `default_selection` per page.** Yes — this is the right call and
  the frontend will stop guessing. Keep `reason` on it; it's genuinely useful
  when debugging why a page opened where it did.
- **`content_health` on the node, not in a side list.** Yes.
- **Parent roll-up of child health.** Yes — the left tree is unusable without it.
- **`navigate_to` / `add_action` metadata on issues.** Yes. The UI will stop
  hard-coding record routes.
- **Content edit vs relationship edit separation.** Yes, and worth stating
  loudly to whoever writes the PUT handlers.

## 5. Requests the contract does not cover yet

Approver-role items the built portal has screens for, with no v3 endpoint behind
them. v3 covers *reading and validating* content thoroughly; the *approval
workflow* itself is only represented as `workflow.available_actions` and
`publish_allowed` on page 15.

- **Approve / Return actions.** No endpoint. Needed:
  `POST /authoring/topics/{id}/approve`, `POST /authoring/topics/{id}/return`
  (with a comment body — a reviewer returning work without a reason is useless).
- **Review comments.** No schema anywhere. The spec's role table says the
  reviewer "adds comments"; nothing carries them.
- **Audit log.** Spec §2 requires all admin actions be audit logged. No table,
  no endpoint.
- **Who is the current user, and what may they do?** The guide correctly says
  "available actions come from workflow/permission state, not hard-coded
  buttons" — but no response carries the caller's role. The portal currently
  shows every action to everyone. Needs a session/permissions payload.

---

## Suggested next step

Items **1.1–1.4** and **§5** need a decision from Saravanan / Manjusha before
the endpoints are built. **§2** is additive and safe to fold in now. **§3** is
mine to absorb — no backend impact.

The frontend is not blocked on any of it: the portal is being moved onto v3
using the sample JSON as its mock, so the moment the real endpoints return the
same shapes, it switches over with an env flag.
