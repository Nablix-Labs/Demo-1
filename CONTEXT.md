# Student Model Contract Verification

This context defines the language used when verifying the Student Model against the authoritative end-to-end testcase specification.

## Language

**Testcase**:
One complete numbered scenario from the authoritative 25-testcase specification, including its full input event and expected output JSON.
_Avoid_: Gap, assertion, field check

**Contract assertion**:
One expected field, value, collection, state transition, or routing rule inside a testcase.
_Avoid_: Testcase

**Contract gap**:
A contract assertion that the current implementation does not satisfy.
_Avoid_: Testcase failure reason used as a testcase title

**Expected JSON**:
The complete input or output contract copied from the authoritative testcase specification.
_Avoid_: Recommended JSON, illustrative JSON

**Current implementation evidence**:
Repository source, focused test output, or runtime output used to determine whether a contract assertion is supported.
_Avoid_: Expected behavior

**Strict verdict**:
The result for the complete original testcase: PASS only when every required contract assertion is supported, FAIL when at least one assertion is confirmed different, and NOT VERIFIED when evidence is insufficient.
_Avoid_: A verdict inferred from unrelated passing tests

**Implementation coverage**:
Whether the scenario flow exists independently of strict conformance: FULL, PARTIAL, or NONE.
_Avoid_: Strict verdict
