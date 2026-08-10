# Tasks: Recover From Empty Canvas OCR

- [ ] Task 1: Normalize Mathpix empty-content responses
  - Acceptance: `image_no_content` returns `VisionOCRResult(needs_clarification=True, confidence=0.0)`.
  - Verify: `pytest -q tests/test_vision_provider.py`.
  - Files: `app/adapters/mathpix_vision.py`, `tests/test_vision_provider.py`.

- [ ] Task 2: Verify endpoint clarification behavior
  - Acceptance: Empty OCR returns `CLARIFICATION_REQUIRED`, does not invoke grading, and does not increment attempts.
  - Verify: `pytest -q tests/test_canvas.py`.
  - Files: `tests/test_canvas.py`.
