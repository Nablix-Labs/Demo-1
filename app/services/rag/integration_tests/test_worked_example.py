"""
AD-403 Integration Test -- Worked Example Engine (AD-402)

Tests the worked example retrieval microservice via HTTP requests.

The server must be running on the configured port before running this.

Usage:
    cd worked_ex_engine/   (or AD-402/)
    python server.py &     # start server on port 8005
    cd ../../AD-403/       (or ../AD-403/)
    python test_worked_example.py
"""

import requests
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_worked_example")

BASE_URL = "http://localhost:8005"


def check_server():
    """Test 0: Is the server reachable?"""
    logger.info("=== Test 0: Server Health Check ===")
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        data = resp.json()
        logger.info(f"  Status: {data.get('status')}")
        logger.info(f"  Collection exists: {data.get('collection_exists')}")
        if data.get("status") != "ok":
            logger.error("  Server returned non-ok status.")
            return False
        if not data.get("collection_exists"):
            logger.error("  Qdrant collection missing. Run ingest.py first.")
            return False
        logger.info("  PASS")
        return True
    except requests.ConnectionError:
        logger.error(f"  Cannot connect to {BASE_URL}.")
        logger.error("  Start the server first: cd worked_ex_engine/ && python server.py")
        return False


def test_retrieve_worked_example():
    """Test 1: POST /worked-example/retrieve returns a valid example."""
    logger.info("=== Test 1: /worked-example/retrieve basic retrieval ===")
    errors = []

    payload = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "operation_type": "ADDITION",
        "current_question": "x + 3 = 7",
        "current_answer": "4",
        "difficulty": "FOUNDATION",
        "exclude_content_ids": [],
    }

    resp = requests.post(f"{BASE_URL}/worked-example/retrieve", json=payload, timeout=10)
    if resp.status_code != 200:
        if resp.status_code == 404:
            errors.append("1a: No worked example returned (404)")
        else:
            errors.append(f"1a: Expected 200, got {resp.status_code}: {resp.text}")
    else:
        data = resp.json()

        # Check required fields
        required = [
            "content_id", "content_type", "concept_id", "operation_type",
            "example_question", "example_answer", "text", "difficulty",
            "topic", "subtopic", "relevance_score", "approval_status",
        ]
        for field in required:
            if field not in data:
                errors.append(f"1b: Missing field '{field}'")
            elif data[field] is None or data[field] == "":
                errors.append(f"1c: Empty field '{field}'")

        # Check values match request
        if data.get("concept_id") != "ALG_LINEAR_ONE_STEP":
            errors.append(f"1d: concept_id mismatch: {data.get('concept_id')}")
        if data.get("operation_type") != "ADDITION":
            errors.append(f"1e: operation_type mismatch: {data.get('operation_type')}")
        if data.get("difficulty") != "FOUNDATION":
            errors.append(f"1f: difficulty mismatch: {data.get('difficulty')}")
        if data.get("content_type") != "WORKED_EXAMPLE":
            errors.append(f"1g: content_type should be WORKED_EXAMPLE, got '{data.get('content_type')}'")

        # Check safety fields
        if data.get("different_numbers_confirmed") is not True:
            errors.append("1h: different_numbers_confirmed should be True")
        if data.get("approval_status") != "APPROVED":
            errors.append(f"1i: approval_status should be APPROVED, got '{data.get('approval_status')}'")

        # The returned example should NOT use the same numbers as the request
        # (x + 3 = 7 has numbers 3 and 7)
        eq = data.get("example_question", "")
        if "3" in eq and "7" in eq:
            errors.append(f"1j: Example uses same numbers as current question: {eq}")

        if not errors:
            logger.info(f"  Got: {data['content_id']}")
            logger.info(f"  Question: {data['example_question']}, Answer: {data['example_answer']}")
            logger.info(f"  Score: {data['relevance_score']}")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def test_different_operation_types():
    """Test 2: Different operation types return relevant examples."""
    logger.info("=== Test 2: Different operation types ===")
    errors = []

    test_cases = [
        ("ADDITION", "x + 3 = 7", "4"),
        ("SUBTRACTION", "x - 2 = 6", "8"),
        ("MULTIPLICATION", "2x = 10", "5"),
    ]

    for op_type, question, answer in test_cases:
        payload = {
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "operation_type": op_type,
            "current_question": question,
            "current_answer": answer,
            "difficulty": "FOUNDATION",
            "exclude_content_ids": [],
        }
        resp = requests.post(f"{BASE_URL}/worked-example/retrieve", json=payload, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            if data.get("operation_type") != op_type:
                errors.append(f"2: {op_type}: response mismatch: {data.get('operation_type')}")
            else:
                logger.info(f"  {op_type}: {data['content_id']} ({data['example_question']})")
        elif resp.status_code == 404:
            logger.info(f"  {op_type}: no example available (404)")
        else:
            errors.append(f"2: {op_type}: unexpected status {resp.status_code}")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def test_guardrail_blocks_answer_reveal():
    """Test 3: Guardrail prevents returning example that reveals student's answer."""
    logger.info("=== Test 3: Guardrail blocks answer reveal ===")
    errors = []

    # Student answer is "5". WORKED_005 (3x=15, answer=5) should be blocked
    # because its answer is the same as the student's.
    # WORKED_006 (4x=28, answer=7) should be returned instead.
    payload = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "operation_type": "MULTIPLICATION",
        "current_question": "2x = 10",
        "current_answer": "5",
        "difficulty": "FOUNDATION",
        "exclude_content_ids": [],
    }
    resp = requests.post(f"{BASE_URL}/worked-example/retrieve", json=payload, timeout=10)

    if resp.status_code == 200:
        data = resp.json()
        # The returned example's answer should NOT be "5"
        if data.get("example_answer") == "5":
            errors.append(
                f"3a: Guardrail failed -- returned example with answer '5' "
                f"(same as student): {data['content_id']}"
            )
        else:
            logger.info(
                f"  Guardrail working: skipped answer='5' examples, "
                f"got {data['content_id']} (answer={data['example_answer']})"
            )
    elif resp.status_code == 404:
        logger.info("  No example available after guardrail filtering (404)")
    else:
        errors.append(f"3b: Unexpected status: {resp.status_code}")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def test_exclusion():
    """Test 4: Excluding a content_id returns a different example."""
    logger.info("=== Test 4: Exclusion ===")
    errors = []

    payload1 = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "operation_type": "ADDITION",
        "current_question": "x + 3 = 7",
        "current_answer": "4",
        "difficulty": "FOUNDATION",
        "exclude_content_ids": [],
    }
    resp1 = requests.post(f"{BASE_URL}/worked-example/retrieve", json=payload1, timeout=10)
    if resp1.status_code != 200:
        logger.info("  No example returned for first request. Skipping exclusion test.")
        logger.info("  PASS (no data)")
        return True

    first_id = resp1.json()["content_id"]

    payload2 = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "operation_type": "ADDITION",
        "current_question": "x + 3 = 7",
        "current_answer": "4",
        "difficulty": "FOUNDATION",
        "exclude_content_ids": [first_id],
    }
    resp2 = requests.post(f"{BASE_URL}/worked-example/retrieve", json=payload2, timeout=10)

    if resp2.status_code == 200:
        second_id = resp2.json()["content_id"]
        if second_id == first_id:
            errors.append(f"4a: Same example returned despite exclusion: {first_id}")
        else:
            logger.info(f"  First: {first_id}, Second: {second_id}")
    elif resp2.status_code == 404:
        logger.info(f"  First: {first_id}, Second: 404 (only one example available)")
    else:
        errors.append(f"4b: Unexpected status: {resp2.status_code}")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def test_invalid_request():
    """Test 5: Invalid request returns 422."""
    logger.info("=== Test 5: Invalid request handling ===")
    errors = []

    # Missing required fields
    resp = requests.post(f"{BASE_URL}/worked-example/retrieve", json={}, timeout=10)
    if resp.status_code != 422:
        errors.append(f"5a: Expected 422 for empty body, got {resp.status_code}")
    else:
        logger.info("  Empty body correctly rejected with 422")

    # Invalid difficulty
    payload = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "operation_type": "ADDITION",
        "current_question": "x + 3 = 7",
        "current_answer": "4",
        "difficulty": "INVALID",
        "exclude_content_ids": [],
    }
    resp = requests.post(f"{BASE_URL}/worked-example/retrieve", json=payload, timeout=10)
    if resp.status_code != 422:
        errors.append(f"5b: Expected 422 for invalid difficulty, got {resp.status_code}")
    else:
        logger.info("  Invalid difficulty correctly rejected with 422")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def main():
    logger.info("AD-403 Integration Test: Worked Example Engine (AD-402)\n")

    if not check_server():
        return 1

    results = {}
    results["retrieve"] = test_retrieve_worked_example()
    results["operation_types"] = test_different_operation_types()
    results["guardrail"] = test_guardrail_blocks_answer_reveal()
    results["exclusion"] = test_exclusion()
    results["invalid_request"] = test_invalid_request()

    logger.info("\n=== Test Summary ===")
    for name, passed in results.items():
        logger.info(f"  {name}: {'PASS' if passed else 'FAIL'}")

    all_passed = all(results.values())
    logger.info(f"\n{'All tests passed!' if all_passed else 'Some tests failed.'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
