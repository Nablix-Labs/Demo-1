# Numera Frontend — Status & Future Scope

_Snapshot of what's done on the frontend, what's mock-wired, and what's still
pending (frontend future work vs. backend dependencies). Generated 2026-07-02._

Legend: ✅ done · 🟡 frontend done, waiting on backend · 🔜 frontend future work · 🧹 cleanup

---

## 1. Done on the frontend (shipped to `main`)

| Area | Status | Notes |
|---|---|---|
| Brand design system | ✅ | All ~45 screens on brand tokens; full-bleed layout; primitives (buttons/cards) |
| Registration → Guardian consent → Login | ✅ 🟡 | Full UX + RBAC gate; **mock-wired** (no real auth provider — see §3) |
| Student RBAC gate | ✅ | `AuthGate` enforces role/account_status/consent client-side (§13 of proposal) |
| Adaptive learning loop UI | ✅ 🟡 | Diagnostic → orientation → guided → practice → review; **routing driven by the Demo Director**, not real scoring |
| Canvas drawing tools | ✅ | Pen/pencil/highlighter/eraser/shapes/ruler, colours, undo/redo, draggable toolbar |
| Canvas paper styles | ✅ | Plain / lines / dots / small / grid / large — persisted |
| **Tutor writes to canvas** | ✅ 🟡 | Renders any draw command (shapes + **real KaTeX maths**); both transports wired; **backend must produce the commands** (see §3) |
| Voice input bar | ✅ 🟡 | Live mic-level bar, sensitivity boost, live caption, autoscroll; real STT via Web Speech; **backend voice session pending** |
| 3D tutor avatar + lip-sync | ✅ | Loads, blinks, sways; mouth moves with Numera's TTS |
| Group Challenge UI | ✅ 🟡 | Shared board, private canvas, AI commentary — **mock/timer-based**; real multiplayer pending |
| Route pages | ✅ | Workbook, Practice, Keynotes, People, Files, Flagged, History, Notifications, Help, Complete |

---

## 2. Frontend future work (our side — not yet built / to improve) 🔜

| Item | Priority | Notes |
|---|---|---|
| **Mobile / responsive layout** | High | App is currently fixed-desktop only (demo on laptop). No tablet/phone layout. |
| **Student camera tile** | Med | Referenced as a "placeholder in this build" (Help page); not implemented. |
| Learning-funnel modelling | Med | Frontend funnel is still largely linear; the true loop / mastery / dynamic entry-topic aren't fully modelled in the UI state (bridged by the Demo Director today). |
| Progressive / animated tutor strokes | Low | Tutor marks appear instantly; "draw-along" animation is an enhancement (contract can carry timing later). |
| Tutor handwriting style | Low | Freehand tutor strokes are supported but not styled as handwriting. |
| Accessibility & keyboard nav pass | Med | Broad ARIA is in place; a dedicated a11y audit (focus order, screen-reader flows) is worth doing before launch. |
| Error / empty / offline states polish | Low | Most exist; a consistent pass (network loss, backend down) would harden the demo→prod transition. |
| Session/transcript persistence UI | Med | History page is mock; wire to real session records once the backend exposes them. |

---

## 3. Backend dependencies (frontend is ready; backend to deliver) 🟡

The frontend already renders/handles all of these — they light up as soon as the
backend provides the data.

| Capability | Frontend readiness | What the backend owns |
|---|---|---|
| **Real auth** (SSO/OTP/password, sessions) | Screens + RBAC gate ready | Identity provider, OTP, JWT/session, the 8 identity/consent/RBAC tables + endpoints (see `Nablix_Student_Registration_Login_Consent_RBAC_Proposal`) |
| **Tutor draws on canvas** | Rendering + both transports done | Produce `canvas_draw` commands from tutor intent; deliver over WS or on `/interaction` (see `docs/TUTOR-CANVAS-WRITE-SPEC.md`) |
| **Canvas OCR** (`/canvas/submit`) | Submit + result handling wired | Real OCR of student handwriting → structured result |
| **Adaptive scoring & routing** | Loop UI + decision points ready | Real diagnostic placement, mastery decisions, loop-termination floor (today: Demo Director) |
| **Voice session** (`wss://…/voice`) | WS client mounted (no-op until URL set) | Streaming STT/TTS, turn-taking, `canvas_draw`/`transcript` messages |
| **Group Session** | UI ready | Real multiplayer board, presence, shared strokes |
| **Personalised Key Notes** | UI ready | Per-student note generation (mocked today) |

---

## 4. Cleanup / tech debt 🧹

| Item | Action |
|---|---|
| `components/Canvas/BarModel.tsx` | **Dead code** (not rendered) + contains inline Comic Sans — delete when convenient. |
| `TutorLayer.tsx` header comment | Stale: says math/KaTeX is a "later upgrade"; KaTeX now ships via `TutorMathOverlay`. Update comment. |
| Demo Director (`FlowControls`) | Demo-only; hide behind a flag or remove for production. |
| `window.numeraTutor` dev bridge | Non-prod only (guarded by `NODE_ENV`); fine to keep. |
| Old linear gates (`lib/phases.ts`) | Still underneath the adaptive loop; retire once backend routing lands. |

---

## 5. One-line summary

**The frontend is demo-complete and render-complete for every planned feature.**
What remains is (a) our own polish — chiefly **mobile responsiveness** and a few
placeholder surfaces (camera, history) — and (b) **backend data**: real auth,
tutoring/scoring, OCR, voice, and the tutor's `canvas_draw` production. Each of
those has a frontend seam already in place, so integration is wiring, not rebuilding.
