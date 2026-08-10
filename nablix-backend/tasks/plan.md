# Implementation Plan: Unify Canvas and Interaction Responses (Option 1)

## Overview
We are modifying the `/canvas/submit` endpoint to return the exact same `InteractionResponse` JSON payload as `/interaction`, while keeping the endpoints separate. This ensures the frontend receives the full session state (messages, hints, attempts) regardless of whether the input was text/voice or canvas strokes.

## Architecture Decisions
- **Keep endpoints separate**: Canvas payload (strokes/images) and OCR logic remain isolated in `/canvas/submit`.
- **Unify response builder**: Refactor the central `_response_from` function in `interaction_service.py` to accept explicit data arguments instead of an `InteractionRequest` object, so it can be safely called by `canvas_service.py`.
- **Extend InteractionResponse**: Add `canvas_draw`, `ocr`, and `latency` directly to `InteractionResponse`.

## Task List

### Phase 1: Foundation (Models)
- [ ] Task 1: Extend `InteractionResponse` with canvas fields
- [ ] Task 2: Remove `CanvasSubmitResponse`

### Checkpoint: Foundation
- [ ] Models build cleanly
- [ ] No immediate syntax errors in models

### Phase 2: Core Refactor (Services)
- [ ] Task 3: Refactor `_response_from` signature to use explicit arguments
- [ ] Task 4: Update `_process_interaction` to use the new `_response_from` signature
- [ ] Task 5: Update `submit_canvas` to build its response using `_response_from`

### Checkpoint: Core Features
- [ ] Server starts without dependency injection or import errors
- [ ] Both `/interaction` and `/canvas/submit` endpoints can be hit without 500 errors

### Phase 3: API & Tests
- [ ] Task 6: Update `app/api/canvas.py` signature
- [ ] Task 7: Fix unit tests in `tests/test_canvas.py` and `tests/test_interaction.py`

### Checkpoint: Complete
- [ ] `pytest tests/test_canvas.py tests/test_interaction.py -v` passes
- [ ] Ready for review

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Circular Imports | High | `app/models/interaction.py` importing from `app/models/canvas.py` might cause issues. We will carefully sequence imports or use local imports if needed. |
| Missing State in Canvas | Med | Ensure `submit_canvas` passes all updated session state correctly into `_response_from`. |

## Open Questions
- None.
