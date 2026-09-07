# Phase 3 TC-26+ contract questions

1. Is Phase 3 rescue removed? TC-18/19 show no rescue, but removal would delete the existing rescue acknowledgement and advance lifecycle.
2. Must `question_usage_id` be present on `return_checkpoint`? The examples omit it, while the locked rules require the same question ID and usage ID throughout the repair chain.
3. Are TC-31/33/34/35 journey states abbreviated? They omit fields required by the Schema 3.0 response contract.
4. What is the difficulty reduction for authored levels 4 and 5?
5. Does `is_rescue_retry` now mean any checkpoint re-attempt?
6. Should `attempt_sequence` increment for every attempt of the frozen checkpoint?
7. Should `phase_visit_no` increment on every return to Phase 3?
8. Does `repair_cycle_no` name the next cycle while `phase_2_repair_count` counts completed cycles?
9. Is the curriculum endpoint `/api/v1/curriculum/prerequisite-remediation-route` or `/curriculum/prerequisite-remediation-route`?
10. Please correct the TC-20 trailing comma and the missing comma before TC-36 `submitted_at`.
