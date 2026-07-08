# Numera — Tutor Writing to the Canvas
### Implementation plan & backend requirements

**Audience:** Backend / AI team
**Status:** Frontend rendering built; backend "draw command" producer to be implemented
**Owner:** Frontend (Manav) · **Version:** Draft v1.0

---

## 1. What this is

The canvas carries **two** independent streams of data. This document is about the
**second** one (tutor → student); the first is already specified and live.

| Direction | Trigger | Endpoint / channel | Purpose | Status |
|---|---|---|---|---|
| **Student → backend** | Student taps **Check** | `POST /canvas/submit` (PNG snapshot → OCR → tutor eval) | Read the student's handwriting | ✅ Specified & wired |
| **Backend/Tutor → student** | Tutor decides to demonstrate | **`canvas_draw` command** (this doc) | Numera *writes/draws* on the canvas while teaching | 🟡 Frontend ready, backend TODO |

The tutor never sends an image. It sends **structured, resolution-independent
draw commands**, and the frontend renders them. This keeps the backend
device-agnostic and keeps the marks crisp, animatable, and separate from the
student's own ink.

---

## 2. How the frontend already handles it

Already implemented (no backend dependency to render):

- A dedicated, **non-interactive "tutor layer"** sits *above* the student's drawing
  (`components/Canvas/TutorLayer.tsx`). Tutor marks are visually distinct and the
  student's eraser never touches them.
- A store action **`applyCanvasDraw(payload)`** ingests a draw command; **`clearTutorMarks()`** wipes the tutor layer.
- All geometry is expressed in **normalised 0–1 coordinates** and scaled to the
  live canvas size at render time. The backend therefore never needs to know the
  pixel dimensions of any device.
- Supported primitives today: `text`, `math`, `line`, `arrow`, `rect`, `ellipse`,
  `freehand`, `highlight`.

So the backend's job is **not** rendering — it is *producing valid draw commands*.

---

## 3. The draw-command contract

This is the exact shape the frontend consumes. (Source of truth:
`store/useNumeraStore.ts` → `CanvasDrawPayload` / `TutorElement`.)

### 3.1 Envelope — `CanvasDrawPayload`

```jsonc
{
  "author": "tutor",          // optional, always "tutor" for these
  "actionId": "step-3-circle", // optional; unique id for idempotency / de-dupe
  "mode": "append",            // "append" (add to layer) | "replace" (clear then set)
  "elements": [ /* TutorElement[] */ ]
}
```

- **`mode: "append"`** — adds these elements to whatever is already on the tutor
  layer (use while building up an explanation step by step).
- **`mode: "replace"`** — clears the tutor layer, then draws these (use to reset
  for a new question). `mode:"replace"` with `elements: []` = clear the layer.
- **`actionId`** — lets the frontend ignore duplicates if a command is re-delivered
  (e.g. on WebSocket reconnect). Please send one per logical draw action.

### 3.2 Element — `TutorElement`

```jsonc
{
  "id": "e1",              // optional; frontend generates if omitted
  "kind": "arrow",         // one of the kinds below
  "x": 0.5, "y": 0.4,      // normalised 0–1 position (meaning depends on kind)
  "w": 0.2, "h": 0.1,      // normalised size (rect/ellipse)
  "from": [0.1, 0.2],      // normalised start point (line/arrow)
  "to":   [0.6, 0.2],      // normalised end point   (line/arrow)
  "points": [0.1,0.2, 0.15,0.25, 0.2,0.22], // normalised x,y pairs (freehand/highlight)
  "text": "2x = 8",        // text content (kind:"text")
  "tex":  "2x = 8",        // LaTeX content (kind:"math")
  "color": "#1B2A4A",      // stroke/fill colour (optional; sensible defaults applied)
  "strokeWidth": 2,         // optional
  "size": 24                // font size in px @ native scale (text/math)
}
```

### 3.3 Which fields each `kind` uses

| kind | Uses | Meaning |
|---|---|---|
| `text` | `x,y` (anchor centre), `text`, `size`, `color` | Plain text (labels, notes) |
| `math` | `x,y` (anchor centre), `tex` (or `text`), `size`, `color` | An equation/step (rendered in a math font today — see §7) |
| `line` | `from`, `to`, `color`, `strokeWidth` | Straight line (e.g. underline, fraction bar) |
| `arrow` | `from`, `to`, `color`, `strokeWidth` | Arrow with a head at `to` (point at a term/step) |
| `rect` | `x,y` (top-left), `w,h`, `color`, `strokeWidth` | Rectangle (box a region) |
| `ellipse` | `x,y` (**centre**), `w,h` (**full diameters**), `color`, `strokeWidth` | Circle/ellipse (circle an error) |
| `freehand` | `points`, `color`, `strokeWidth` | Smooth polyline (hand-drawn strokes) |
| `highlight` | `points`, `strokeWidth`, `color` | Translucent highlighter stroke (defaults to amber, ~35% opacity) |

> Coordinate frame: **`(0,0)` = top-left, `(1,1)` = bottom-right** of the canvas
> working area. Numbers are fractions of the canvas width (x) and height (y).

---

## 4. Transport — how the backend delivers commands

### 4.1 Primary: WebSocket (recommended, already wired)

The frontend listens on the voice socket (`wss://{host}/voice?session={id}`,
`hooks/useWebSocket.ts`). To draw, the backend pushes a message:

```jsonc
{ "type": "canvas_draw", "mode": "append", "actionId": "step-3",
  "elements": [ /* TutorElement[] */ ] }
```

The frontend already routes `type: "canvas_draw"` → `applyCanvasDraw(...)`. This is
the right channel for **"write while talking"**: send each mark as the tutor speaks
that part of the explanation, interleaved with `transcript_*` messages.

To clear: send `{ "type": "canvas_draw", "mode": "replace", "elements": [] }`.

### 4.2 Alternative: on the `/interaction` response

If a turn is fully request/response (no socket), the backend can attach draw
commands to the `/interaction` (or `/canvas/submit`) JSON response, e.g. add an
optional field:

```jsonc
// InteractionResponse (proposed addition)
{ ...existing fields..., "canvas_draw": { "mode": "append", "elements": [ ... ] } }
```

The frontend would call `applyCanvasDraw(response.canvas_draw)` when present. Useful
for step-by-step "worked solution" replies. **Recommendation:** support the WS path
for live guided learning; the response-attached path is a fine fallback / for
non-voice turns.

---

## 5. What the backend actually needs to build

The one genuinely new capability: **turn the tutor's intended visual explanation
into valid `TutorElement[]` in normalised coordinates.** Two viable approaches
(can be combined):

1. **LLM emits structured draw ops** (recommended). Use JSON-mode / function-calling
   so the tutoring model outputs draw commands against a *constrained schema* (the
   contract in §3). Validate every element server-side before relaying (drop/repair
   out-of-range coords, unknown kinds, missing required fields).

2. **Deterministic templates.** For common, well-understood moves — underline a
   line, cross out a term, write "the next step", put a tick/cross — map the
   semantic intent to templated geometry in code. More reliable than free-form LLM
   geometry for those cases.

Backend deliverables:

- A **producer** that emits `CanvasDrawPayload` (over WS `canvas_draw`, and/or on
  `/interaction`).
- A **schema + validator** enforcing the §3 contract (coords in [0,1], valid kind,
  required fields per kind, size/colour sanity).
- **Sequencing with voice** — order elements and (optionally) pace them so the
  writing tracks the spoken words (e.g. an optional `stepDelayMs`, or one message
  per spoken step).
- **`actionId`** on every logical action for idempotency across reconnects.

---

## 6. Coordinate anchoring — the key open question

Normalised coords are simple, but the tutor often wants to draw **relative to
something** — e.g. "circle the `5` in `2x + 5 = 13`" or "write the next line under
the student's last step." That requires knowing *where those things are* on the
canvas. Options to decide together:

- **A. Fixed regions (simplest).** Define a stable layout (question band at top,
  free working area below). The tutor places marks in the working area by fraction.
  Good enough for "write the worked solution" demos.
- **B. Frontend sends anchors.** The frontend reports the bounding boxes of the
  question / key regions (and canvas aspect ratio) to the backend, so the tutor can
  target them. Small addition on both sides.
- **C. Annotate student work.** To mark a *specific thing the student wrote*, use the
  OCR output from `/canvas/submit` — `OcrResult` already returns `detected_steps`,
  `detected_shapes`, `latex`. If the backend also returns **bounding boxes** per
  detected step, the tutor can circle/underline the student's own writing precisely.
  (This is the richest option and worth scoping if "correct the student's specific
  mistake on the canvas" is a goal.)

---

## 7. Rendering fidelity & roadmap

- **Math (`kind:"math"`)**: v1 renders `tex`/`text` as text in a math font (italic).
  True **KaTeX** typesetting (HTML overlay or rasterised image) is a planned frontend
  upgrade — the `tex` field is already there so the backend contract won't change.
- **Handwriting feel**: `freehand`/`highlight` support a natural hand-drawn look.
- **Progressive/animated strokes** (draw a stroke over ~300ms rather than instantly)
  is an optional enhancement; the current contract can carry it later via per-element
  timing without breaking changes.

---

## 8. End-to-end example

Tutor spots that the student wrote `2x = 13 − 5` correctly but then miscalculated.
It circles the wrong result, writes the correction, and points to it — while
speaking. Sent as three `canvas_draw` messages (or one with three elements):

```jsonc
{ "type": "canvas_draw", "mode": "append", "actionId": "t1-circle",
  "elements": [
    { "kind": "ellipse", "x": 0.42, "y": 0.55, "w": 0.14, "h": 0.09,
      "color": "#F77F00", "strokeWidth": 3 }
  ]
}
{ "type": "canvas_draw", "mode": "append", "actionId": "t1-fix",
  "elements": [
    { "kind": "math", "x": 0.65, "y": 0.55, "tex": "2x = 8", "size": 26,
      "color": "#1B2A4A" }
  ]
}
{ "type": "canvas_draw", "mode": "append", "actionId": "t1-arrow",
  "elements": [
    { "kind": "arrow", "from": [0.50, 0.55], "to": [0.60, 0.55],
      "color": "#00B4D8", "strokeWidth": 2 }
  ]
}
```

Frontend result: an orange circle around the wrong value, `2x = 8` written to its
right in navy, and a cyan arrow connecting them — all rendered on the tutor layer,
untouched by the student's eraser.

---

## 9. Backend checklist (summary)

- [ ] Produce `CanvasDrawPayload` conforming to §3 (normalised coords, valid kinds).
- [ ] Deliver via WS `{ type: "canvas_draw", ... }` (primary) and/or on `/interaction`.
- [ ] Validate/repair LLM-generated geometry before sending.
- [ ] Decide coordinate anchoring (§6: A fixed regions / B anchors / C OCR boxes).
- [ ] Sequence draw with the spoken explanation; send `actionId` per action.
- [ ] (If annotating student work) return per-step bounding boxes from `/canvas/submit` OCR.
- [ ] Decide persistence: are tutor marks replayable per session, or ephemeral?

**Bottom line:** the frontend can already *render* anything in the §3 contract. The
backend work is (1) generating valid draw commands from the tutor's intent, (2)
delivering them over the WebSocket, and (3) deciding how precisely the tutor needs to
anchor marks to the question and to the student's own writing.
