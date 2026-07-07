# Nablix Tutor Canvas Context

This context captures the language for tutor-led canvas correction. It defines the domain terms used when the backend, tutor engine, OCR layer, and frontend tutor layer cooperate to mark student work.

## Language

**Student Work**:
The math or geometry content written by the student on the canvas.
_Avoid_: Canvas image, user drawing

**Canvas Snapshot**:
A PNG data URL exported from the frontend canvas and submitted to the backend for OCR and tutor evaluation.
_Avoid_: Screenshot, snapshot blob

**OCR Result**:
The provider-neutral transcription of the canvas snapshot, including detected steps, text regions, confidence, and visible shapes.
_Avoid_: Tutor result, math result

**Detected Step**:
One visible line or step of student work, transcribed exactly as written by OCR.
_Avoid_: Correct step, solution step

**Text Region**:
A normalized bounding box for a detected line or text fragment in the canvas snapshot.
_Avoid_: Character box, pixel box

**Math Diagnosis**:
The backend's structured explanation of whether a detected step transition is valid and, if not, what the mathematical error is.
_Avoid_: OCR correction, RAG answer

**Annotation Intent**:
The tutor-facing semantic instruction for what should be marked, such as "circle the wrong subexpression" or "write the corrected next step".
_Avoid_: Draw command, raw coordinates

**Annotation Planner**:
The backend component that converts annotation intent plus OCR anchors into validated canvas draw payloads.
_Avoid_: Renderer, tutor engine

**Canvas Draw Payload**:
The normalized, resolution-independent command sent to the frontend tutor layer to draw tutor marks.
_Avoid_: Image, rendered mark

**Tutor Layer**:
The non-interactive frontend canvas layer that renders tutor marks separately from student work.
_Avoid_: Student canvas, overlay image
