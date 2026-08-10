# Spec: Recover Gracefully From Empty Canvas OCR

## Assumptions

1. `image_no_content` means Mathpix received a valid image but found no recognizable math, text, or supported diagram.
2. A blank or unreadable canvas is a normal student input condition, not a backend outage.
3. `/canvas/submit` and `/interaction` with `canvas_state` should return the existing clarification contract rather than HTTP 503.
4. Real provider failures, authentication failures, malformed images, and timeouts must remain errors.
5. The fix stays in the backend OCR adapter and its regression tests; no Student Model schema or dependency change is needed.

## Objective

Prevent Mathpix's `image_no_content` response from becoming `ADAPTER_UNAVAILABLE`. Return a normal OCR result with `needs_clarification=true` so the existing canvas clarification flow can tell the student to write recognizable work and resubmit.

## Current Failure

Mathpix returns HTTP 200 with `error_info.id=image_no_content`. `MathpixVisionOCRAdapter.recognize()` currently raises `AdapterError` for every provider error payload. Nablix maps that exception to HTTP 503 with `ADAPTER_UNAVAILABLE`, making valid but empty student input look like infrastructure failure.

## Intended Contract

For `image_no_content`, the vision adapter returns:

```python
VisionOCRResult(
    raw_ocr_text="",
    detected_equation="",
    detected_steps=[],
    final_answer=None,
    confidence=0.0,
    needs_clarification=True,
    confidence_source="ocr_native",
    provider="mathpix",
)
```

The existing service then returns its normal clarification response. No Student Model event is emitted for an unreadable/empty canvas, and no attempt is incremented.

## Commands

Run from `nablix-backend/`:

```bash
pytest -q tests/test_vision_provider.py
pytest -q tests/test_canvas.py
python -m compileall -q app
```

## Project Structure

- `app/adapters/mathpix_vision.py` — provider error classification and normalized OCR result.
- `app/models/adapters.py` — existing provider-neutral `VisionOCRResult` contract.
- `app/services/canvas_service.py` — existing clarification behavior; no new fallback path.
- `tests/test_vision_provider.py` — Mathpix response mapping regression test.
- `tests/test_canvas.py` — endpoint-level clarification and no-attempt regression test.

## Code Style

Use a small pure classifier for the provider error ID and keep infrastructure errors explicit:

```python
if payload.error_info_id == "image_no_content":
    return _empty_content_result()
raise AdapterError("mathpix_vision", detail)
```

Do not catch all provider errors or silently substitute mock OCR.

## Testing Strategy

- Unit-level adapter test: `image_no_content` maps to `VisionOCRResult` with clarification enabled.
- Existing provider tests: HTTP failures and malformed provider responses still raise `AdapterError`.
- Endpoint-level canvas test: empty-content OCR returns `CLARIFICATION_REQUIRED`, does not call grading/Student Model event processing, and does not increment attempts.
- Compile check: backend imports and type syntax remain valid.

## Boundaries

- Always: preserve provider error details in logs; keep real failures as 503; do not grade empty work.
- Ask first: changing Mathpix credentials/provider, changing the Student Model contract, adding dependencies, or changing deployment configuration.
- Never: treat `image_no_content` as a correct/incorrect answer, call the Student Model for an unreadable canvas, expose API keys, or silently fall back to mock OCR.

## Success Criteria

1. The reported Mathpix response no longer produces `ADAPTER_UNAVAILABLE`.
2. `/canvas/submit` returns the existing clarification response with HTTP 200 and `status="CLARIFICATION_REQUIRED"` for empty OCR content.
3. `/interaction` with a canvas snapshot receives the same clarification behavior.
4. No Student Model answer event is emitted and the attempt count remains unchanged.
5. Non-`image_no_content` Mathpix errors retain their existing failure behavior.
6. The focused provider and canvas tests plus compile check pass.

## Open Questions

- Assumption to confirm: should an empty canvas be surfaced to the student as a clarification response (the existing behavior), rather than as a hard 4xx validation error?
