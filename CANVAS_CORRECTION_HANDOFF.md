# Canvas Correction Backend Handoff

## Purpose

This document explains the current canvas correction flow and clearly separates the work completed by Sanya and Chirudeva.

The goal of this flow is:

1. The student writes math work on the canvas.
2. The canvas work is submitted to the backend.
3. OCR reads the written work.
4. The AI Engine checks the math steps.
5. The backend returns structured correction data that the frontend can display on the canvas.

## Completed By Chirudeva

Chirudeva completed the canvas submission and OCR pipeline.

### Step 1: Canvas Submission Endpoint

The backend has a canvas submit endpoint:

```text
POST /canvas/submit
```

This endpoint receives the student's canvas snapshot from the frontend.

Relevant files:

```text
nablix-backend/app/api/canvas.py
nablix-backend/app/models/canvas.py
```

### Step 2: Canvas Snapshot Processing

After the canvas image is submitted, the backend stores the snapshot reference and sends the image to the vision/OCR adapter.

Relevant file:

```text
nablix-backend/app/services/canvas_service.py
```

### Step 3: OCR Result Generation

The OCR result includes:

- raw OCR text
- detected equation
- detected steps
- detected text regions
- confidence values
- final answer when OCR can identify it

The detected text regions include normalized canvas coordinates. These coordinates are needed later so the frontend knows where to draw correction marks.

### Step 4: Step ID Assignment

The backend assigns stable step IDs to OCR text regions.

Example:

```text
step-1
step-2
step-3
```

These step IDs allow the AI Engine to say which exact canvas step contains the mistake.

Relevant file:

```text
nablix-backend/app/services/canvas_annotations.py
```

### Step 5: Canvas Draw Payload Planning

The backend already has logic to convert AI Engine correction output into drawable canvas instructions.

These instructions can include:

- circle target
- correction text
- arrow

Relevant file:

```text
nablix-backend/app/services/canvas_annotations.py
```

The final `/canvas/submit` response can include:

```text
canvas_draw
```

This is the backend payload that the frontend can use to draw tutor marks on the canvas.

## Completed By Sanya

Sanya completed the AI Engine correction logic that decides whether the student's canvas work contains a supported mistake.

### Step 1: Canvas Regions Added To AI Engine Input

The AI Engine can now receive canvas text regions.

Each region includes:

- step ID
- OCR text
- normalized bounding box
- OCR confidence

This lets the AI Engine reason about the student's written steps, not only the final typed answer.

Relevant files:

```text
nablix-backend/app/ai_engine/schemas.py
nablix-backend/app/ai_engine/classifier.py
nablix-backend/app/api/ai_engine.py
```

### Step 2: Mistake Classification Added

The AI Engine now returns structured mistake information using:

```text
mistake_classification
```

This tells the backend:

- whether a mistake was found
- which step has the mistake
- which text is wrong
- the character span of the wrong text
- the replacement/correction text
- confidence

Example:

```text
status: mistake_found
mistake_step_id: step-2
target_text: 6
replacement_text: 5
```

### Step 3: Annotation Intents Added

The AI Engine now returns:

```text
annotation_intents
```

These are high-level instructions for what should be drawn.

Supported annotation intents:

```text
circle_target
write_correction
draw_arrow
```

Example:

```text
circle the wrong value
write the corrected step
draw an arrow to the correction
```

### Step 4: Supported Canvas Correction Case 1

The backend can detect a wrong inverse-operation operand.

Example student work:

```text
x + 4 = 9
x = 9 - 5
```

Expected correction:

```text
x = 9 - 4
```

In this case, the AI Engine identifies `5` as the wrong value and returns correction text using `4`.

### Step 5: Supported Canvas Correction Case 2

The backend can detect a wrong intermediate solved value, even if the final answer is later correct.

Example student work:

```text
x + 4 - 4 = 9 - 4
x = 6
x = 5
```

Expected correction:

```text
x = 5
```

In this case, the AI Engine identifies `x = 6` as the incorrect intermediate step and returns correction text `x = 5`.

### Step 6: Backend Tests Added

Tests were added for the supported correction behavior.

Relevant file:

```text
nablix-backend/tests/test_ai_engine.py
```

The tests check that the backend returns:

- `mistake_found`
- the correct mistaken step ID
- the wrong target text
- the correct replacement text
- annotation intents for drawing the correction

## Full Backend Flow

The current backend logic works like this:

1. Frontend submits the canvas snapshot to:

```text
POST /canvas/submit
```

2. Chirudeva's canvas flow sends the snapshot to OCR.

3. OCR returns text, steps, and text regions.

4. The backend assigns stable step IDs to text regions.

5. The canvas text regions are passed into Sanya's AI Engine classifier.

6. The AI Engine checks whether the written work contains a supported mistake.

7. If a supported mistake is found, the AI Engine returns:

```text
mistake_classification
annotation_intents
```

8. The backend canvas annotation planner converts the AI Engine output into:

```text
canvas_draw
```

9. `/canvas/submit` returns the tutor response and the canvas draw payload.

## Current Limitations

The current backend correction logic is not a full general math solver.

It currently supports targeted demo-ready linear equation correction cases.

It does not fully support:

- multiplication equations such as `4x = 20`
- division equations such as `x / 3 = 5`
- sign errors such as `-x = 6`
- fractions
- geometry work
- multiple mistakes in the same canvas submission
- heavily unclear OCR output
- complex multi-step algebra

## What Is Left To Do

The backend can now produce correction information, but the frontend still needs to display it after a canvas check.

The remaining frontend step is:

```text
Read canvas_draw from /canvas/submit
Pass it into the existing canvas drawing layer
Render the tutor correction marks
```

In simple flow form:

```text
Student clicks Check
-> frontend calls /canvas/submit
-> backend returns canvas_draw
-> frontend applies canvas_draw
-> tutor marks appear on the canvas
```

Expected frontend behavior:

1. Student writes canvas work.
2. Student clicks the orange `Check` button.
3. Backend returns correction payload.
4. Frontend draws the correction mark on the canvas.
5. Student sees the wrong part highlighted and the correction shown nearby.

Suggested test case for frontend integration:

```text
x + 4 - 4 = 9 - 4
x = 6
x = 5
```

Expected visible result:

```text
circle/highlight 6
show correction x = 5
draw an arrow from the mistake to the correction
```

## Summary

Chirudeva completed the canvas submission, OCR, step-region, and backend canvas draw planning flow.

Sanya completed the AI Engine logic that identifies supported canvas mistakes and returns structured correction instructions.

The remaining work is to connect the `/canvas/submit` response to the existing frontend canvas annotation layer so the returned correction appears visually to the student.
