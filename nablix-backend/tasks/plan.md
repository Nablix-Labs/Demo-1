# Implementation Plan: Recover From Empty Canvas OCR

## Overview

Treat Mathpix `image_no_content` as normal unreadable student work. Return the existing clarification flow instead of exposing it as `ADAPTER_UNAVAILABLE`.

## Architecture Decisions

- Classify only Mathpix's stable `error_info.id` (and legacy top-level error value) `image_no_content`.
- Reuse the existing `VisionOCRResult` and canvas clarification path; add no fallback provider, retry loop, feature flag, or new response type.
- Preserve all other Mathpix failures as `AdapterError` and HTTP 503.

## Task List

### Phase 1: Provider Boundary

- [ ] Task 1: Normalize Mathpix empty-content responses.

### Checkpoint: Provider Boundary

- [ ] The focused Mathpix tests pass.
- [ ] Other provider failures still raise `AdapterError`.

### Phase 2: Endpoint Behavior

- [ ] Task 2: Add canvas regression coverage for clarification and attempt preservation.

### Checkpoint: Complete

- [ ] Focused vision and canvas tests pass.
- [ ] Backend compile check passes.
- [ ] No unrelated files are staged.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| A provider outage is mistaken for empty content | High | Match only the exact stable `image_no_content` identifier. |
| Empty work is graded as an answer | High | Return `needs_clarification=True`; existing canvas service exits before grading. |
| Existing workspace artifacts are accidentally included | Medium | Stage only the two targeted source/test files. |

## Open Questions

- None for the approved scope.
