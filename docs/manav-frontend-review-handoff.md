# Frontend Review Handoff & Phase 4 Transition Specification

**For:** Manav  
**Date:** 2026-09-02  
**Scope:** `Numera-ui` only. Backend (`nablix-backend`) PR #242 is already deployed and live on port 8001. No backend or Student Model changes are needed from frontend engineering.

---

## 1. What Is Breaking in the User Flow (Live Evidence)

During live testing on the Azure VM (2026-09-02 19:03–19:06 UTC, student `ST010`), three critical issues prevented the Phase 4 Review UI from functioning and trapped the user in an infinite review loop:

### Bug 1: Stalled Practice Screen (`reviewIsNext` ignores `current_phase`)
* **File:** [`Numera-ui/lib/phase3.ts:181-185`](file:///Users/tacticalcamel/Desktop/Nablix/Numera-ui/lib/phase3.ts#L181-L185)
* **What happens:** In `app/practice/page.tsx:411`, the auto-exit condition evaluates:
  ```ts
  if (reviewIsNext(res) && !servedNextQuestion(res, answeredQuestionId)) {
    void reviewWithTutor();
  }
  ```
  `reviewIsNext(res)` only checks `res.recommended_entry_phase === 'REVIEW'`. When `/canvas/submit` returns `current_phase: "REVIEW"` with a null recommendation, `reviewIsNext` returns `false`. The practice canvas locks with *"Answer recorded."* and stalls.

### Bug 2: Race Condition Flashes Mock Fallback Worksheets Instead of Phase 4
* **Files:** [`Numera-ui/lib/usePhaseRouting.ts:97-99`](file:///Users/tacticalcamel/Desktop/Nablix/Numera-ui/lib/usePhaseRouting.ts#L97-L99) and [`Numera-ui/app/review/page.tsx:261-264, 299`](file:///Users/tacticalcamel/Desktop/Nablix/Numera-ui/app/review/page.tsx#L261-L264)
* **What happens:**
  1. `/canvas/submit` completes, and `applyBackendPhase` sets `store.currentPhase = "REVIEW"`.
  2. `usePhaseRouting.ts` immediately triggers `router.push('/review')` **before** `reviewWithTutor()` has fetched `getSession()` and populated `store.backendSession`.
  3. `/review` mounts with `backendSession` empty or holding stale Phase 3 data.
  4. `phase4FromSession(backendSession)` evaluates to `null`.
  5. Because `reviewBlocked` is initially `false`, the component falls through past `if (phase4)`, rendering the **legacy mock worksheet UI** ("You worked through 0 questions") instead of the Phase 4 Review.

### Bug 3: Infinite Review Loop (`next_topic_handoff` discarded)
* **Files:** [`Numera-ui/app/review/page.tsx:188-194`](file:///Users/tacticalcamel/Desktop/Nablix/Numera-ui/app/review/page.tsx#L188-L194) and [`Numera-ui/lib/useFlowNav.ts:63-73`](file:///Users/tacticalcamel/Desktop/Nablix/Numera-ui/lib/useFlowNav.ts#L63-L73)
* **What happened live:**
  1. `SESSION6582...` completed review. Backend returned HTTP 200 with:
     ```json
     {
       "next_topic_handoff": {
         "topic_id": "ALG-ORI-02",
         "entry_phase": "PHASE_0_DIAGNOSTIC",
         "source_session_id": "SESSION658267fd03b4446c86bb221adb7094b2"
       }
     }
     ```
  2. `reportReviewFinished()` in `app/review/page.tsx` threw away the response.
  3. `finishReview` called `end()`, which cleared `sessionId` and called `decideReview('pass')`.
  4. `decideReview` called `nextTopicId()` from a local hardcoded table.
  5. The mounting screen saw `sessionId === null` and triggered `tutor.start(DEMO_CONCEPT_ID, 'TEXT')`, where `DEMO_CONCEPT_ID` is hardcoded to `'ALG_LINEAR_ONE_STEP'` (`ALG-KS3-01`).
  6. Student Model saw `ALG-KS3-01` was already completed and reopened it in `REVIEW` (`SESSIONd007...`), creating an infinite loop of reviewing `ALG-KS3-01`.

### Bug 4: Empty Review Rail on Flawless Runs
* **File:** [`Numera-ui/lib/phase4FromSession.ts:157-164`](file:///Users/tacticalcamel/Desktop/Nablix/Numera-ui/lib/phase4FromSession.ts#L157-L164)
* **What happens:** When the student gets every question right (`tutor_replays: []`), `phase4FromSession` derives `question_journey` solely from `tutor_replays.map(...)`, leaving `question_journey: []` and rendering an empty left column instead of showing the student's successful questions.

---

## 2. Server Contract the Frontend Must Consume

Backend PR #242 exposes the following fields on `SessionRecord` and API responses:

```ts
export type NextTopicHandoff = {
  source_session_id: string;
  student_model_request_id: string;
  topic_id: string;
  entry_phase: string;
};

export type ReviewMaterializationState = 'PENDING' | 'READY';
```

* `review_materialization_state`:
  - `PENDING`: The student's final answer is accepted and Student Model has transitioned to `REVIEW`. Phase 4 review payload is still being prepared by OpenAI.
  - `READY`: `phase4_review` is fully populated and safe to render.
* `next_topic_handoff`:
  - Returned by `POST /session/{id}/review/complete` on `SessionRecord`.
  - The Student Model is the sole authority for `topic_id` (e.g. `'ALG-ORI-02'`) and `entry_phase` (e.g. `'PHASE_0_DIAGNOSTIC'`).

---

## 3. Required Frontend Changes (Action Items for Manav)

### Action 1: Fix `reviewIsNext()` in `lib/phase3.ts`
Update `reviewIsNext` to check both `current_phase` and `recommended_entry_phase`:
```ts
export function reviewIsNext(
  res: { current_phase?: string | null; recommended_entry_phase?: string | null } | null | undefined,
): boolean {
  const current = res?.current_phase?.trim().toUpperCase();
  const recommended = res?.recommended_entry_phase?.trim().toUpperCase();
  return current === 'REVIEW' || recommended === 'REVIEW';
}
```

### Action 2: Add Types to `lib/api.ts`
1. Export `NextTopicHandoff` and `ReviewMaterializationState`.
2. Add them to `SessionRecord`:
   ```ts
   export interface SessionRecord {
     ...
     review_materialization_state?: ReviewMaterializationState | null;
     phase4_review?: unknown;
     next_topic_handoff?: NextTopicHandoff | null;
   }
   ```
3. Update `completeReview()` so it returns `SessionRecord` or throws/reports explicit failure. Do not return `null` on successful HTTP 200.

### Action 3: Handle Pending Review & Eliminate Flash of Fallbacks on `/review`
In `app/review/page.tsx`:
1. While `apiEnabled` and `!phase4`:
   - If `backendSession` is still being fetched or `backendSession.review_materialization_state === 'PENDING'`, **do NOT fall through to `<FallbackWorksheets />`**.
   - Render a clean loading/skeleton state (`<GateSkeleton />` or *"Preparing your review..."*).
2. Update `retryReview()` / mount effect to poll or retry `getSession()` with a bounded backoff if `review_materialization_state === 'PENDING'`.

### Action 4: Consume `next_topic_handoff` & Break the Review Loop
In `app/review/page.tsx` and `lib/useFlowNav.ts`:
1. Modify `reportReviewFinished()`:
   ```ts
   const reportReviewFinished = useCallback(async (): Promise<NextTopicHandoff | null> => {
     if (!apiEnabled) return null;
     const plan = planReviewCompletion(reviewSessionId.current, () => `REVIEW-COMPLETE-${Date.now()}`);
     const res = await completeReview(reviewSessionId.current!, studentId(), plan.turnId);
     return res?.next_topic_handoff ?? null;
   }, [apiEnabled]);
   ```
2. In `finishReview(outcome)`:
   - When `handoff` is present:
     - Clear active `sessionId`.
     - Immediately invoke the session start flow with `handoff.topic_id` and `handoff.entry_phase`.
     - Replace active `sessionId`, `currentTopicId`, and route to the new topic's entry stage.
     - **Do NOT call `decideReview()` or restart `DEMO_CONCEPT_ID` in live API mode.**
   - If `handoff` is missing or in mock mode (`!apiEnabled`), fall back to existing `decideReview(outcome)`.

### Action 5: Support Flawless Phase 3 Runs in `lib/phase4FromSession.ts`
When `tutor_replays` is empty, populate `question_journey` from `raw.question_journey`:
```ts
const question_journey = tutor_replays.length > 0
  ? tutor_replays.map((replay) => ({
      question_id: replay.question_id,
      question_text: replay.question_text,
      evaluation: 'WRONG' as const,
      replay_item_id: replay.review_item_id,
    }))
  : (raw.question_journey ?? []).map((item: any) => ({
      question_id: item.question_id,
      question_text: item.question_text || item.question_id,
      evaluation: item.evaluation || 'CORRECT',
      replay_item_id: null,
    }));
```

---

## 4. Acceptance Verification for Manav

1. **Auto-Exit Practice:** Submitting the final correct Phase 3 question automatically triggers navigation to Review without getting stuck on "Answer recorded."
2. **No Fallback Flash:** Arriving on `/review` never renders the mock worksheet screen ("You worked through 0 questions") while live API is enabled.
3. **Flawless Runs Render Cleanly:** Sessions where the student made 0 mistakes display the Learning Summary directly, with completed Phase 3 questions shown in the left rail.
4. **Handoff Advances to Topic 2:** Clicking "Complete Review" / "Continue" reads `next_topic_handoff` and opens `ALG-ORI-02` (Orientation / Diagnostic). It never restarts `ALG-KS3-01`.
5. **No Regressions:** All existing 107 test files in `Numera-ui` continue to pass (`npm test`).
