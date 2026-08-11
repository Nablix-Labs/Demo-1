- [ ] Task 1: Extend `InteractionResponse` with canvas fields
  - Acceptance: `app/models/interaction.py` has `canvas_draw`, `ocr`, and `latency` added to `InteractionResponse`.
  - Verify: Syntax check `app/models/interaction.py`
  - Files: `app/models/interaction.py`

- [ ] Task 2: Remove `CanvasSubmitResponse`
  - Acceptance: `CanvasSubmitResponse` is deleted from `app/models/canvas.py`.
  - Verify: Syntax check `app/models/canvas.py`
  - Files: `app/models/canvas.py`

- [ ] Task 3: Refactor `_response_from` signature to use explicit arguments
  - Acceptance: `_response_from` takes explicit arguments (like `session_id`, `student_id`, `turn_id`, `interaction_type`, `nudge_id`, `canvas_draw`, etc.) instead of `InteractionRequest`.
  - Verify: Syntax check `app/services/interaction_service.py`
  - Files: `app/services/interaction_service.py`

- [ ] Task 4: Update `_process_interaction` to use the new `_response_from` signature
  - Acceptance: `_process_interaction` successfully calls the updated `_response_from`. The `_cache_response` function is also updated to take `session_id` and `turn_id` explicitly.
  - Verify: Syntax check `app/services/interaction_service.py`
  - Files: `app/services/interaction_service.py`

- [ ] Task 5: Update `submit_canvas` to build its response using `_response_from`
  - Acceptance: `submit_canvas` calls `_response_from` and returns an `InteractionResponse`.
  - Verify: Syntax check `app/services/canvas_service.py`
  - Files: `app/services/canvas_service.py`

- [ ] Task 6: Update `app/api/canvas.py` signature
  - Acceptance: Endpoint returns `InteractionResponse`.
  - Verify: Syntax check `app/api/canvas.py`
  - Files: `app/api/canvas.py`

- [ ] Task 7: Fix unit tests
  - Acceptance: All test files referencing `CanvasSubmitResponse` are updated.
  - Verify: `pytest tests/test_canvas.py tests/test_interaction.py -v` passes.
  - Files: `tests/test_canvas.py`, `tests/test_interaction.py`
