# End-to-End Session Transition, VM Audit, and Phase 4 Review Diagnosis

**Date:** 2026-09-02 (UTC)  
**Host:** Azure VM `74.162.34.219` (`Nablix-Dev-Ubu`)  
**Auditors:** Agent 1 (VM Log Monitor) & Agent 2 (Session & JSON Payload Auditor)  
**Methodology:** Direct live journalctl tracing, runtime process auditing, PostgreSQL DB inspection, OpenAPI schema verification, and `Numera-ui` source-contract analysis per `debugging-and-error-recovery` and `grill-with-docs`.

---

## 1. Executive Summary & Live Verification Status

| Surface | Service / Port | Commit / Runtime Version | Live Operational Status |
|---|---|---|---|
| **Backend API** | `nablix-backend.service`<br>Port `8001` (FastAPI/Uvicorn) | Commit `ecd221b` (Merged PR #242 / `2a774b3`)<br>PID `1545` (started 18:55 UTC) | **ACTIVE & FUNCTIONAL (PR #242 Verified)**<br>Prompt registry v1.1.0 validated. Review materialization state machine (`PENDING` -> `READY`), `next_topic_handoff` persistence, and final turn receipts are actively running. Zero 500 errors. |
| **Student Model** | `mathtutor-student.service`<br>Port `8080` (nginx proxy -> `127.0.0.1:8002`) | Pre-PR #14 build<br>PID `547` (started 18:33 UTC) | **STALE / PENDING SERVICE RESTART**<br>Gunicorn workers were booted at 18:33 UTC (17 mins prior to PR #14 merge at 18:50 UTC). Calling `SESSION_RESUMED` still triggers 500 in `continuity.py` instead of returning 422 `UNSUPPORTED_EVENT_TYPE`. |
| **Frontend UI** | `Numera-ui`<br>Static SPA at `/var/www/numera/app/` | Deployed 17:49 UTC | **BLOCKING BUGS IDENTIFIED**<br>Missing integration with PR #242 `next_topic_handoff` and `review_materialization_state`. Trapped in review loop and suppressing Phase 4 UI. |

---

## 2. Root Cause Analysis: Phase 4 Review UI Failure & Session Transition Gaps

Our end-to-end investigation traced why the Phase 4 Review UI is not being displayed and why session transitions stall or loop. The failure is caused by **three compounding client-side contract violations** in `Numera-ui`, plus **one pending service restart** on the VM:

### Gap 1: `reviewIsNext()` Only Checks `recommended_entry_phase`
* **File:** `Numera-ui/lib/phase3.ts:181-185`
* **Code:**
  ```ts
  export function reviewIsNext(
    res: { recommended_entry_phase?: string | null } | null | undefined,
  ): boolean {
    return res?.recommended_entry_phase?.trim().toUpperCase() === 'REVIEW';
  }
  ```
* **Failure Mechanism:** In `Numera-ui/app/practice/page.tsx:411`, after the student answers the final independent question, the UI evaluates `if (reviewIsNext(res) && !servedNextQuestion(res, answeredQuestionId))`. Whenever `res.recommended_entry_phase` is null or not provided on the interaction response (even though `res.current_phase === "REVIEW"`), `reviewIsNext` evaluates to `false`. The UI locks the attempt, displays "Answer recorded.", and stalls on the practice screen without invoking `reviewWithTutor()`.

### Gap 2: Race Condition Between `usePhaseRouting` and Session Fetching
* **Files:** `Numera-ui/lib/usePhaseRouting.ts:85-100` vs `Numera-ui/app/practice/page.tsx:88-109`
* **Failure Mechanism:**
  1. When `/canvas/submit` returns, `applyBackendPhase` in `useDemoTutor.ts` immediately updates Zustand store `currentPhase = "REVIEW"`.
  2. `usePhaseRouting` is an active hook watching `currentPhase`. The moment `currentPhase` becomes `"REVIEW"`, `usePhaseRouting` calls `router.push('/review')`.
  3. This client-side navigation happens **before** `reviewWithTutor()` has completed `getSession(tutor.sessionId)` and updated `store.backendSession`.
  4. When `/review` (`app/review/page.tsx`) mounts, `backendSession` in the store is either null or a stale Phase 3 record.
  5. In `app/review/page.tsx:261-264`, `phase4FromSession(backendSession)` evaluates to `null`.
  6. In `app/review/page.tsx:299`, `if (phase4)` fails. And because `reviewBlocked` is initially `false`, the page immediately falls through to line 400+, rendering the **mock fallback worksheets** ("You worked through 0 questions") instead of the Phase 4 Review!

### Gap 3: Review Completion Discards `next_topic_handoff` and Traps Student in Loop
* **Files:** `Numera-ui/app/review/page.tsx:188-194` and `Numera-ui/lib/useFlowNav.ts:63-73`
* **Observed Live in VM Run:**
  1. At 19:04:06 UTC, `SESSION6582...` completed review. Backend returned 200 with:
     ```json
     {
       "next_topic_handoff": {
         "topic_id": "ALG-ORI-02",
         "entry_phase": "PHASE_0_DIAGNOSTIC",
         "source_session_id": "SESSION658267fd03b4446c86bb221adb7094b2"
       }
     }
     ```
  2. `reportReviewFinished()` discarded the response.
  3. `finishReview` called `end()`, which cleared `sessionId` and called `decideReview('pass')`.
  4. `decideReview` computed `nextTopicId()` from a local hardcoded table and reset flow stage.
  5. The mounting screen saw `sessionId === null` and triggered `tutor.start(DEMO_CONCEPT_ID, 'TEXT')`, where `DEMO_CONCEPT_ID` is hardcoded to `'ALG_LINEAR_ONE_STEP'` (`ALG-KS3-01`)!
  6. Backend forwarded `SESSION_OPENED` for `ALG-KS3-01` to Student Model. Because `ALG-KS3-01` was already marked `MASTERED` and `COMPLETED`, Student Model immediately returned `current_phase: "REVIEW"`, creating session `SESSIONd007...` in Review.
  7. When `SESSIONd007...` completed review at 19:05:30 UTC, the exact same cycle spawned `SESSIONf3b3...` in Review. The student was trapped in an infinite loop of reviewing `ALG-KS3-01`.

### Gap 4: Zero Tutor Replays on Flawless Runs
* **File:** `Numera-ui/lib/phase4FromSession.ts:157-164`
* **Failure Mechanism:** In session `SESSION6582...`, student `ST010` answered every question correctly (`replay_count: 0`, `tutor_replays: []`). `phase4FromSession` derives `question_journey` solely from `tutor_replays.map(...)`. When `tutor_replays` is empty, `question_journey` is also set to `[]`, omitting the student's successful Phase 3 question history from the review rail.

---

## 3. Required Changes Across System Layers

### 3.1 Student Model Layer (`mathtutor-student`)
1. **VM Deployment:** Restart `mathtutor-student.service` (and `fastapi.service`) with PR #14 merged code:
   ```bash
   sudo systemctl restart mathtutor-student
   ```
2. **Contract Enforced:** Ensure `SESSION_RESUMED` returns 422 `UNSUPPORTED_EVENT_TYPE` and `REVIEW_COMPLETED` reliably yields `START_NEXT_TOPIC` with `next_topic_id` and `next_topic_entry_phase`.

### 3.2 Backend Wiring Layer (`nablix-backend`)
1. **Already Deployed (PR #242):** Commit `ecd221b` is running on PID 1545.
2. **Interaction Response Optimization:** Consider including `review_materialization_state` and passing through `recommended_entry_phase: "REVIEW"` whenever `current_phase == "REVIEW"` so naive clients don't drop the transition.

### 3.3 Frontend Layer (`Numera-ui`)
1. **Fix `reviewIsNext`:** Update `isPhase3Exit` / `reviewIsNext` to check:
   ```ts
   export function reviewIsNext(res: Phase3ResponseFields | null | undefined): boolean {
     const phase = (res as any)?.current_phase?.trim().toUpperCase();
     const recPhase = res?.recommended_entry_phase?.trim().toUpperCase();
     return phase === 'REVIEW' || recPhase === 'REVIEW';
   }
   ```
2. **Prevent Flash of Fallback on `/review`:**
   In `app/review/page.tsx`, if `!phase4` and `apiEnabled`, do NOT render fallback worksheets while the session is loading or in `PENDING` materialization. Render a spinner / loading state (`<GateSkeleton />` or "Preparing your review...").
3. **Consume `next_topic_handoff` in Review Completion:**
   In `app/review/page.tsx`:
   - Capture `const res = await completeReview(...)`.
   - Extract `res.data.next_topic_handoff`.
   - Call `tutor.start(handoff.topic_id, 'TEXT', handoff.entry_phase)`.
   - Update active topic and replace `sessionId`. Do NOT call `decideReview()` or restart `DEMO_CONCEPT_ID`.
