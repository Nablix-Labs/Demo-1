# Part 17 — Pull Request Evidence

## Implementation evidence

- Prompt artifacts are stored under `prompts/ai_tutor/` with a versioned manifest.
- Layer 1 is validated against the approved SHA-256 checksum during registry loading and application startup.
- The prompt registry is loaded once per process and returned from an in-memory cache.
- The prompt builder creates three ordered system messages: immutable Layer 1, selected Phase plus canonical Conditional Protocols, and dynamic Session Context.
- Conditional Protocols use the fixed `TRIGGER_ORDER`; duplicates are removed and unknown triggers raise `ValueError`.
- Session Context uses deterministic JSON serialization and remains after the two stable system-message boundaries.
- OpenAI usage logs expose cache reads, token counts, prompt version, phase, canonical triggers, and diagnostic hashes without logging prompt text or student content.

## Validation results

- Backend `tests/` suite: `131 passed, 2 warnings in 0.61s`.
- The warnings are FastAPI `on_event` deprecation warnings and are unrelated to prompt integrity or caching.
- Approved Layer 1 SHA-256: `bd08e7a10ea9067cbf793a63822a0fc61b880ff0cbdfeb56e40b1f54da2c216d`.
- No files under `prompts/ai_tutor/` were changed by this implementation.
- The phase-transition and trigger-transition diagnostic hashes are recorded in `prompt_transition_hashes.jsonl`.

## Controlled OpenAI integration result

The integration used the normal backend endpoint and the approved Nablix prompt with `gpt-4o-mini`.

- First sequence: `cached_tokens=0`, showing the prefix was not read from cache on those requests.
- Repeated sequence with the same Phase and trigger set: cache reads were reported as `4608`, `4096`, and `4096` cached input tokens.
- Layer 1 and semi-static diagnostic hashes stayed identical across both sequences.
- OpenAI uses automatic exact-prefix caching. The system-message boundaries establish stable prefixes; they are not explicit cache-breakpoint markers.
- The API reports cache reads through `cached_tokens`. It does not report an explicit cache-write count for these requests, so `cache_write_tokens` remains `0`.

The sanitized usage records are in `openai_prompt_cache_usage.jsonl`. They contain no prompt wording, student name, session ID, question, OCR text, RAG text, or API key.

## Remaining integration limitation

The prompt builder supports `HANDWRITING_AMBIGUITY`, and its prefix-hash transition is covered by tests and diagnostic evidence. The current public endpoint does not yet derive or accept that trigger, so the OCR-trigger transition is not claimed as a completed public-endpoint integration test.

Running unscoped `pytest` also collects `app/services/rag/sanya_guardrail/test_classifier.py`, which currently imports the nonexistent `app.classifier` module and fails during collection. This pre-existing RAG test issue is outside the OpenAI prompt-cache change; the configured backend `tests/` suite passes.
