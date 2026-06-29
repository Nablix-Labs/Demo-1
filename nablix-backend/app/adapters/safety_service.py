"""Mock safety adapter for pre-tutor checks.

The safety service is intentionally adapter-shaped even while it is mock-only,
so `InteractionService` can keep a separate preflight step before RAG and tutor
generation. A future live safety provider should keep the same `check` result
contract.
"""

from app.models.adapters import AdapterContext, SafetyCheckResult


class MockSafetyServiceAdapter:
    """Mock safety gate for the interaction pipeline.

    The mock fails only on an explicit test token so normal tests avoid storing
    or asserting against sensitive phrases.
    """

    async def check(self, context: AdapterContext) -> SafetyCheckResult:
        """Return a blocking result only for the explicit test trigger."""

        if "SAFETY_BLOCK" in context.message:
            return SafetyCheckResult(
                passed=False,
                flag_type="MOCK_BLOCK",
                action_taken="SAFE_FALLBACK",
                safe_fallback_message="Let's pause for a moment and come back to the maths when you're ready.",
            )
        return SafetyCheckResult(passed=True)
