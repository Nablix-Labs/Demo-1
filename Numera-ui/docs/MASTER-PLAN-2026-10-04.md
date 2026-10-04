# Numera — master plan and backend asks, 4 Oct 2026

**Author:** Manav (frontend) · **For:** Manjusha, to assign and follow up with Sanya, Chiru, Saravanan and Aditya
**Evidence:** a live run on the VM today as ST009 (screenshots in `~/Numera/screens-2026-10-04/`), and the 8080 OpenAPI.

---

## 0. Done today

| What | Status |
|---|---|
| Phase 0: make the question change visible (Manjusha, 22 Sep + 4 Oct) | **Deployed**, build `M56EcXTKUJO5bOVLFGBMH`, commit `eac5bf3`. Counter is now a "Question 2 / 8" chip that flashes amber, the question block rises in, and "Next question coming →" shows while the tutor speaks. |

---

## 1. Phase 1 (orientation): what is left, and who owns each part

Manjusha's ask (22 Sep): "more tutor writing on the canvas with proper explanation and clear presentation (diff ink and simple way) similar to phase 4 review". Spec: `docs/SPEC-MANJUSHA-ASKS-2026-09-22.md` §2.

**What today's live run showed (ALG-ORI-02, "Decoding Compact Algebraic Notation"):**

- The worked example arrives as **one step** ("Step 1 of 1") holding every case (3y, ab, a², a³, ½x). The frontend already lays out one row per step and leaves earlier rows up (fix for #303). With a single step there is only one row, so each case replaces the last and the board never shows more than one line.
- The pen hand sits on top of the line it has just written.
- "Skip the walkthrough" goes straight to guided practice, so the teach-back step is skipped too.

| # | Task | Owner | Needs |
|---|---|---|---|
| 1.1 | **Board builds up.** One row per case, earlier rows stay up, Phase 4 board spacing. Split an authored multi-case step into rows on the frontend, so this works even before content is re-authored. | Manav | Nothing |
| 1.2 | Move the hand off the ink it has just written. | Manav | Nothing |
| 1.3 | **Different ink by role:** amber for what changes, teal for what stays fixed, navy with a box for the conclusion. One colour map shared with Phase 2. | Manav | Palette confirmed by Manjusha |
| 1.4 | Decide whether "Skip the walkthrough" should still offer teach-back. | Manjusha decides, Manav builds | A decision |
| 1.5 | **Re-author worked examples as one case per step**, using the existing `steps[]`. | **Sanya** (content) | — |
| 1.6 | Optional per-step fields `emphasis` (`CHANGE` / `FIXED` / `CONCLUSION`) and `box`, plus a per-example `presentation` (`accumulate` / `sheet`). Without them, everything renders in navy as it does today. | **Sanya** (content contract) | — |

Order: 1.1 and 1.2 first (frontend only, visible on the next deploy), then 1.3. Sanya's 1.5 and 1.6 can run in parallel, and nothing on the frontend waits for them.

---

## 2. Backend bugs found in today's run

| # | Bug | Owner | Evidence |
|---|---|---|---|
| B1 | **A plain wrong answer in guided practice sometimes returns 503 instead of a hint.** The classifier marked "2pq" INCORRECT but credited every required concept. The consistency check then raises, and nothing falls back. The student sees "The tutor service hit an error". Flaky: the same answer worked on retry. | **Sanya** | `nablix-backend/app/ai_engine/classifier.py:6551`, request `REQ39B30E58`, 4 Oct 11:05 UTC, session `SESSIONef248668…`, Q-T02-003, `ADAPTER_UNAVAILABLE`. Suggested fix: when the attempt is INCORRECT and nothing is missing, treat the question's target concepts as missing rather than raising. |

---

## 3. Saravanan's work

| Item | Finding | Ask |
|---|---|---|
| **Content-generation endpoints** | **I could not find any.** The 8080 service has 55 routes today, the same set as on 2 Oct, and none of them generate content. The only content-generation code in the repo is `content_gen_agent/`, an offline DOCX → LLM → Excel pipeline by **Aditya** (PR #379, 29 Sep). It has no HTTP API. | **Saravanan:** which host or port, repo and branch? Once I have a URL and an approver token, I will test every route and report back. |
| **Onboarding** (in progress) | The frontend is ready behind `NEXT_PUBLIC_REGISTRATION_LIVE`: registration, guardian consent, the student-code step and error states. The contract is in `docs/ONBOARDING-API.md`. The `/auth/register/*` and `/consent/*` routes exist on 8080. | Tell me when it is done. I will switch the flag on and run it end to end. |
| **Postgres migration** | — | Tell me before the cutover. Login, `student_code` and journey state all depend on it. |
| **Psychometric tests** | Blocked on the migration and on a spec. | **Manjusha:** the test content, when it runs (during onboarding or before the first topic), who scores it, and where results are shown. Then I can build the test runner screen. |

---

## 4. The other menus: what the backend needs to provide

**Today every menu screen except the lesson is mock data.** Workbook, Key Notes, History, Files, Flagged, Notifications, People and Group Challenge are hardcoded in the frontend, and Profile is only partly real (from login). None of them call the backend, because the endpoints they need do not exist. There are no list or "me" endpoints in either API.

Ownership follows where the data lives: per-student records → **Saravanan** (Student Model, Postgres), session content → **Sanya** (Tutor Backend), account and profile → **Chiru**.

| Menu | Endpoint needed | Fields the screen shows | Suggested owner | Priority |
|---|---|---|---|---|
| **Profile** | `GET` / `PATCH /students/me/profile`, `POST` / `DELETE /students/me/avatar`, `PUT /students/me/consents/{purpose}` | display_name, avatar_url, age/grade band, preferred_mode, guardian {name, relationship, email, phone, verified}, preferences {input_mode, panel_side}, consents[] | **Chiru** (already specced in `docs/PROFILE-BACKEND.md` #2–#5) | High |
| **Workbook** (curriculum + progress) | `GET /curriculum` (topics → subtopics → lessons with real codes such as `ALG-ORI-02`, key stage, blurb), `GET /students/me/progress` | per lesson: status `mastered \| in_progress \| not_started`; per topic: % mastered; phases_done[] | **Saravanan** (`/student/{id}/progress/summary` already exists; extend it) | High |
| **History** (previous work) | `GET /students/me/sessions?limit=&cursor=` | session_id, started_at, duration, topic code and title, questions total and correct, phase reached; totals (sessions, minutes, correct of total) | **Sanya**. Needs sessions persisted; today they live only in memory and are lost on restart. | High |
| **Key Notes** | `GET /students/me/key-notes?session_id=` | per note: topic, meaning, how_to_start, steps[], be_careful[], tips[], formula, example[], exam_tip, flagged (from a mistake made this session) | **Sanya** (generate from session evidence; Phase 4's `first_error` and pattern summary can seed it). Aditya if it comes from RAG. | Medium |
| **Flagged** | `POST` / `DELETE /students/me/flags` {question_id, reason}, `GET /students/me/flags` | question text, topic and module code + title, reason, flagged_at, session_id | **Saravanan**. The frontend also adds a "flag this question" button in the lesson. | Medium |
| **Files** | `GET /students/me/work-artifacts` | artifact_id, kind (worksheet / canvas / notes), title, created_at, size, mime, session_id, topic | **Saravanan** (artifacts and `/work-artifacts/{id}/pdf` already exist; only the list is missing) | Medium |
| **Notifications** | `GET /students/me/notifications`, `POST …/{id}/read` | id, type (reminder / message / mastery / worksheet), title, body, created_at, read_at | **Saravanan** | Low |
| **People** | Guardian comes from Profile. Tutors and classmates need a class model (`/teacher/class/{id}/overview` exists). | name, role, detail, online | **Chiru** (guardian) / **Saravanan** (class) | Low |
| **Group Challenge** | A realtime group-session service: presence, shared strokes, invite codes, AI commentary stream | — | **Manjusha to decide**: park it, or scope it as its own project | Park |
| **Help / Nablix Assist** | `POST /support/instruction`, `/support/action-result`, `/support/escalate`, `/support/screenshot`, `WS /support/remote-assist` (contract in `lib/support/assistApi.ts`) | — | **Owner to be decided** | Low |

**Frontend commitment:** as each endpoint lands, I wire that screen to it, keep the mock as a fallback when the API is off, and show an honest empty state when a real student has no data yet.

**Recommended order:** Profile → Workbook progress → History → Flagged + Files → Key Notes → Notifications.

---

## 5. Plan for this week (frontend)

| When | Work |
|---|---|
| Now | Phase 1 tasks 1.1 and 1.2 (board builds up, hand off the ink) and deploy |
| Next | 1.3 ink roles, shared with Phase 2 |
| As backends land | Onboarding end to end; content-gen endpoint testing; menu screens in the order above |
| Small fixes queued | Profile shows "Name not set" though login now returns the name; the Profile phase strip is local and shows 6 of 6 for every student |

## 6. Agenda for Monday's call (8 pm)

1. Phase 1 palette and the skip / teach-back decision.
2. Owners and dates for the menu endpoints in §4.
3. Where Saravanan's content-gen endpoints live; onboarding ETA; Postgres cutover date.
4. Psychometric test spec.
5. Group Challenge: park or scope.
