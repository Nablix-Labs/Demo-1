"""
Test script for AD-402 -- Worked Example Retrieval.

Tests the full flow:
1. Validate worked_example_bank.json structure
2. Check Qdrant has the ingested data
3. Test get_worked_example with different filters
4. Test the different-numbers check (should skip examples with overlapping numbers)
5. Test the guardrail check (should skip examples that reveal the answer)

Usage:
    python ingest.py                          # run this first
    python test_worked_example_retrieval.py

Note: Requires OPENAI_API_KEY in .env (for embeddings).
"""

import json
import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test")

# Shared clients -- created once, used by all tests.
_qdrant_client = None
_openai_client = None


def _setup_clients():
    """Create shared Qdrant and OpenAI clients."""
    global _qdrant_client, _openai_client

    import config
    from openai import OpenAI
    from qdrant_client import QdrantClient

    qdrant_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qdrant_data")

    if not os.path.exists(qdrant_path):
        logger.error(f"qdrant_data not found at {qdrant_path}")
        logger.error("Run 'python ingest.py' first to populate the worked example bank.")
        return False

    _qdrant_client = QdrantClient(path=qdrant_path)
    _openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
    return True


def _cleanup_clients():
    """Close clients."""
    global _qdrant_client
    if _qdrant_client:
        _qdrant_client.close()
        _qdrant_client = None


def test_worked_example_bank_structure():
    """Test 1: Verify worked_example_bank.json has valid structure."""
    logger.info("=== Test 1: Worked Example Bank Structure ===")

    bank_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worked_example_bank.json")
    with open(bank_path) as f:
        examples = json.load(f)

    required_fields = [
        "content_id", "concept_id", "operation_type", "difficulty",
        "example_question", "example_answer", "text", "topic", "subtopic",
    ]

    errors = []
    ids_seen = set()
    for i, ex in enumerate(examples):
        for field in required_fields:
            if field not in ex or not ex[field]:
                errors.append(f"Example {i} ({ex.get('content_id', '?')}): missing '{field}'")

        cid = ex.get("content_id", "")
        if cid in ids_seen:
            errors.append(f"Duplicate content_id: {cid}")
        ids_seen.add(cid)

        valid_diffs = {"FOUNDATION", "INTERMEDIATE", "ADVANCED"}
        if ex.get("difficulty") not in valid_diffs:
            errors.append(f"Example {cid}: invalid difficulty '{ex.get('difficulty')}'")

        valid_ops = {"ADDITION", "SUBTRACTION", "MULTIPLICATION", "DIVISION"}
        if ex.get("operation_type") not in valid_ops:
            errors.append(f"Example {cid}: invalid operation_type '{ex.get('operation_type')}'")

    if errors:
        for err in errors:
            logger.error(f"  FAIL: {err}")
        return False

    operation_types = {}
    concepts = {}
    for ex in examples:
        operation_types[ex["operation_type"]] = operation_types.get(ex["operation_type"], 0) + 1
        concepts[ex["concept_id"]] = concepts.get(ex["concept_id"], 0) + 1

    logger.info(f"  Total examples: {len(examples)}")
    logger.info(f"  Unique IDs: {len(ids_seen)}")
    logger.info(f"  Operation types: {dict(sorted(operation_types.items()))}")
    logger.info(f"  Concepts: {dict(sorted(concepts.items()))}")
    logger.info("  PASS")
    return True


def test_collection_exists():
    """Test 2: Check that Qdrant collection has worked examples."""
    logger.info("=== Test 2: Qdrant Collection Check ===")

    import config

    try:
        info = _qdrant_client.get_collection(config.QDRANT_COLLECTION)
        point_count = info.points_count

        logger.info(f"  Collection: {config.QDRANT_COLLECTION}")
        logger.info(f"  Points in collection: {point_count}")
        if point_count == 0:
            logger.error("  FAIL: No points stored")
            return False

        logger.info("  PASS")
        return True
    except ValueError as e:
        logger.error(f"  FAIL: {e}")
        logger.error("  Run 'python ingest.py' first, then re-run tests.")
        return False


def test_get_worked_example():
    """Test 3: Test basic retrieval with different filters."""
    logger.info("=== Test 3: get_worked_example basic retrieval ===")

    from worked_example_service import get_worked_example, count_available_examples

    errors = []

    # 3a: Get a worked example for ADDITION, one-step
    # Using a question with numbers that DON'T overlap with our bank examples
    result = get_worked_example(
        concept_id="ALG_LINEAR_ONE_STEP",
        operation_type="ADDITION",
        current_question="x + 3 = 7",
        current_answer="4",
        difficulty="FOUNDATION",
        exclude_content_ids=[],
        qdrant_client=_qdrant_client,
        openai_client=_openai_client,
    )
    if result is None:
        errors.append("3a: No example returned for ADDITION/ONE_STEP (question: x + 3 = 7)")
    else:
        logger.info(f"  3a: Got {result['content_id']} (question={result['example_question']}, score={result['relevance_score']})")
        if result["operation_type"] != "ADDITION":
            errors.append(f"3a: Wrong operation_type '{result['operation_type']}'")
        if not result.get("different_numbers_confirmed"):
            errors.append("3a: different_numbers_confirmed should be True")
        if not result.get("text"):
            errors.append("3a: text field is empty")

    # 3b: Get example for MULTIPLICATION, one-step
    result_mult = get_worked_example(
        concept_id="ALG_LINEAR_ONE_STEP",
        operation_type="MULTIPLICATION",
        current_question="2x = 10",
        current_answer="5",
        difficulty="FOUNDATION",
        exclude_content_ids=[],
        qdrant_client=_qdrant_client,
        openai_client=_openai_client,
    )
    if result_mult is None:
        errors.append("3b: No example returned for MULTIPLICATION/ONE_STEP")
    else:
        logger.info(f"  3b: Got {result_mult['content_id']} (question={result_mult['example_question']})")

    # 3c: Get example for two-step concept
    result_2step = get_worked_example(
        concept_id="ALG_LINEAR_TWO_STEP",
        operation_type="ADDITION",
        current_question="4x + 1 = 9",
        current_answer="2",
        difficulty="FOUNDATION",
        exclude_content_ids=[],
        qdrant_client=_qdrant_client,
        openai_client=_openai_client,
    )
    if result_2step is None:
        errors.append("3c: No example returned for ADDITION/TWO_STEP")
    else:
        logger.info(f"  3c: Got {result_2step['content_id']} (question={result_2step['example_question']})")

    # 3d: Test exclusion -- exclude first result, should get a different one
    if result:
        first_id = result["content_id"]
        result2 = get_worked_example(
            concept_id="ALG_LINEAR_ONE_STEP",
            operation_type="ADDITION",
            current_question="x + 3 = 7",
            current_answer="4",
            difficulty="FOUNDATION",
            exclude_content_ids=[first_id],
            qdrant_client=_qdrant_client,
            openai_client=_openai_client,
        )
        if result2 is not None and result2["content_id"] == first_id:
            errors.append(f"3d: Got same example back ({first_id}) despite being excluded")
        else:
            second_id = result2["content_id"] if result2 else "None (all excluded)"
            logger.info(f"  3d: Exclusion works. First: {first_id}, Second: {second_id}")

    # 3e: Count examples for a filter
    count = count_available_examples(
        concept_id="ALG_LINEAR_ONE_STEP",
        operation_type="SUBTRACTION",
        difficulty="FOUNDATION",
        qdrant_client=_qdrant_client,
    )
    logger.info(f"  3e: SUBTRACTION/ONE_STEP/FOUNDATION count: {count}")
    if count == 0:
        errors.append("3e: Expected at least 1 SUBTRACTION example for ONE_STEP/FOUNDATION")

    if errors:
        for err in errors:
            logger.error(f"  FAIL: {err}")
        return False

    logger.info("  PASS")
    return True


def test_different_numbers_check():
    """Test 4: Verify the different-numbers filter works.

    The module guide says worked examples MUST use different numbers
    from the student's current question. This test uses a question
    whose numbers overlap with a known example to verify it gets skipped.
    """
    logger.info("=== Test 4: Different-Numbers Check ===")

    from worked_example_service import _has_same_numbers

    errors = []

    # 4a: "x + 5 = 12" should overlap with example ALG_EQ_WORKED_001 (which uses x + 5 = 12)
    if not _has_same_numbers("x + 5 = 12", "x + 5 = 12"):
        errors.append("4a: Same question should have overlapping numbers")
    else:
        logger.info("  4a: Correctly detected same numbers (identical questions)")

    # 4b: "x + 3 = 7" should NOT overlap with "x + 5 = 12"
    if _has_same_numbers("x + 3 = 7", "x + 5 = 12"):
        errors.append("4b: Different numbers should not overlap")
    else:
        logger.info("  4b: Correctly found no overlap (x + 3 = 7 vs x + 5 = 12)")

    # 4c: "x + 9 = 15" shares 9 with "x + 9 = 20" -- should detect overlap
    if not _has_same_numbers("x + 9 = 15", "x + 9 = 20"):
        errors.append("4c: Should detect shared number 9")
    else:
        logger.info("  4c: Correctly detected shared number 9")

    # 4d: "3x = 12" shares 3 with "2x + 3 = 11" -- should detect overlap
    if not _has_same_numbers("3x = 12", "2x + 3 = 11"):
        errors.append("4d: Should detect shared number 3")
    else:
        logger.info("  4d: Correctly detected shared number 3")

    if errors:
        for err in errors:
            logger.error(f"  FAIL: {err}")
        return False

    logger.info("  PASS")
    return True


def test_guardrail_check():
    """Test 5: Verify the guardrail catches answer reveals.

    Uses Sanya's guardrail logic (contains_answer_reveal) with a fix:
    the original does a raw substring check ("5" in "15" = True).
    Our version uses word-boundary regex so "5" only matches as a
    standalone number, not inside "15" or as a coefficient in "5x".

    This is important because worked example text is full of numbers
    (coefficients like "2x", intermediate results like "2x = 8").
    """
    logger.info("=== Test 5: Guardrail Check ===")

    from worked_example_service import _guardrail_fn

    errors = []

    # 5a: Text that says "x = 4" should be flagged when current answer is "4"
    if not _guardrail_fn("We get x = 4.", "4"):
        errors.append("5a: Should flag 'x = 4' when answer is 4")
    else:
        logger.info("  5a: Correctly flagged text containing standalone answer '4'")

    # 5b: Text with different answer should NOT be flagged
    if _guardrail_fn("We get x = 7.", "4"):
        errors.append("5b: Should not flag 'x = 7' when answer is 4")
    else:
        logger.info("  5b: Correctly allowed text with different number (7 vs answer 4)")

    # 5c: "5" inside "15" should NOT be flagged (the word-boundary fix)
    if _guardrail_fn("We have 15 apples and 3 baskets.", "5"):
        errors.append("5c: Should NOT flag '5' inside '15' (word boundary fix)")
    else:
        logger.info("  5c: Correctly allowed '5' inside '15' (word boundary works)")

    # 5d: "2" should NOT match coefficient in "2x"
    if _guardrail_fn("Start with 2x + 3 = 11. Subtract 3.", "2"):
        errors.append("5d: Should NOT flag '2' in '2x' (coefficient, not answer)")
    else:
        logger.info("  5d: Correctly allowed '2' as coefficient in '2x'")

    # 5e: Reveal phrase should still be flagged
    if not _guardrail_fn("the answer is to subtract both sides", "99"):
        errors.append("5e: Should flag reveal phrase 'the answer is'")
    else:
        logger.info("  5e: Correctly flagged reveal phrase 'the answer is'")

    # 5f: Normal instructional text should be fine
    if _guardrail_fn("Subtract from both sides to isolate x.", "99"):
        errors.append("5f: Should not flag normal instructional text")
    else:
        logger.info("  5f: Correctly allowed normal instructional text")

    # 5g: "so x = 7" should NOT flag when student answer is "5"
    # Context-aware: the number after "so x =" is 7, not the student's 5.
    if _guardrail_fn("So x = 7.", "5"):
        errors.append("5g: 'so x = 7' should NOT flag when answer is 5")
    else:
        logger.info("  5g: Correctly allowed 'so x = 7' when answer is 5 (context-aware)")

    # 5h: "so x = 5" SHOULD flag when student answer is "5"
    if not _guardrail_fn("So x = 5.", "5"):
        errors.append("5h: 'so x = 5' SHOULD flag when answer is 5")
    else:
        logger.info("  5h: Correctly flagged 'so x = 5' when answer is 5")

    # 5i: standalone "2" in "divide by 2" should NOT flag when "2" is
    # from the example's equation. The third argument (example_question)
    # tells the guardrail which numbers belong to the example.
    text_008 = "Divide both sides by 2: 2x / 2 = 8 / 2. That gives us x = 4."
    if _guardrail_fn(text_008, "2", "2x + 3 = 11"):
        errors.append("5i: 'by 2' should NOT flag when 2 is in example equation")
    else:
        logger.info("  5i: Correctly exempted '2' from example equation '2x + 3 = 11'")

    if errors:
        for err in errors:
            logger.error(f"  FAIL: {err}")
        return False

    logger.info("  PASS")
    return True


def main():
    logger.info("Starting AD-402 tests\n")

    results = {}

    # Test 1: Structure (no API calls needed)
    results["structure"] = test_worked_example_bank_structure()

    # Test 4 & 5: Unit tests for the safety checks (no API calls needed)
    results["different_numbers"] = test_different_numbers_check()
    results["guardrail"] = test_guardrail_check()

    # Tests 2 & 3 need OpenAI API key + Qdrant data
    if not _has_api_key():
        logger.warning("OPENAI_API_KEY not set. Skipping ingestion/retrieval tests.")
        logger.info("\nTo run full tests, add OPENAI_API_KEY to .env in the AD-402 folder.")
    else:
        if not _setup_clients():
            logger.error("Failed to set up clients. Run 'python ingest.py' first.")
            return 1

        try:
            results["collection"] = test_collection_exists()
            if results["collection"]:
                results["retrieval"] = test_get_worked_example()
            else:
                logger.warning("Skipping retrieval tests since collection check failed.")
        finally:
            _cleanup_clients()

    # Summary
    logger.info("\n=== Test Summary ===")
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        logger.info(f"  {name}: {status}")

    all_passed = all(results.values())
    logger.info(f"\n{'All tests passed!' if all_passed else 'Some tests failed.'}")
    return 0 if all_passed else 1


def _has_api_key():
    """Check if API key is available."""
    if os.getenv("OPENAI_API_KEY"):
        return True
    try:
        import config
        return bool(config.OPENAI_API_KEY)
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(main())
