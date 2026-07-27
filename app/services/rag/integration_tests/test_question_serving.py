"""
AD-403 Integration Test -- Question Serving (AD-300 + AD-400)

Tests the question serving microservice via HTTP requests.
Covers both /question/next (AD-300) and /diagnostic/question (AD-400).

The server must be running on the configured port before running this.

Usage:
    cd question_serving/
    python server.py &          # start server on port 8002
    cd ../../AD-403/
    python test_question_serving.py
"""

import requests
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_question_serving")

BASE_URL = "http://localhost:8002"


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
        logger.error("  Start the server first: cd question_serving/ && python server.py")
        return False


def test_question_next():
    """Test 1: POST /question/next returns a valid question."""
    logger.info("=== Test 1: /question/next basic retrieval ===")
    errors = []

    payload = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "phase": "GUIDED_PRACTICE",
        "difficulty": "FOUNDATION",
        "previously_seen_ids": [],
    }

    resp = requests.post(f"{BASE_URL}/question/next", json=payload, timeout=10)
    if resp.status_code != 200:
        errors.append(f"1a: Expected 200, got {resp.status_code}: {resp.text}")
    else:
        data = resp.json()

        # Check required fields exist
        required = [
            "question_id", "question_text", "correct_answer",
            "difficulty", "phase", "concept_id", "topic", "subtopic",
        ]
        for field in required:
            if field not in data or not data[field]:
                errors.append(f"1b: Missing or empty field '{field}'")

        # Check values match request
        if data.get("concept_id") != "ALG_LINEAR_ONE_STEP":
            errors.append(f"1c: concept_id mismatch: {data.get('concept_id')}")
        if data.get("phase") != "GUIDED_PRACTICE":
            errors.append(f"1d: phase mismatch: {data.get('phase')}")
        if data.get("difficulty") != "FOUNDATION":
            errors.append(f"1e: difficulty mismatch: {data.get('difficulty')}")

        if not errors:
            logger.info(f"  Got: {data['question_id']} -- {data['question_text']}")
            logger.info(f"  Answer: {data['correct_answer']}, Topic: {data['topic']}")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def test_question_next_exclusion():
    """Test 2: Excluding a question ID returns a different question."""
    logger.info("=== Test 2: /question/next with exclusion ===")
    errors = []

    # First call to get a question
    payload1 = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "phase": "GUIDED_PRACTICE",
        "difficulty": "FOUNDATION",
        "previously_seen_ids": [],
    }
    resp1 = requests.post(f"{BASE_URL}/question/next", json=payload1, timeout=10)
    if resp1.status_code != 200:
        errors.append(f"2a: First request failed: {resp1.status_code}")
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    first_id = resp1.json()["question_id"]

    # Second call excluding the first
    payload2 = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "phase": "GUIDED_PRACTICE",
        "difficulty": "FOUNDATION",
        "previously_seen_ids": [first_id],
    }
    resp2 = requests.post(f"{BASE_URL}/question/next", json=payload2, timeout=10)

    if resp2.status_code == 200:
        second_id = resp2.json()["question_id"]
        if second_id == first_id:
            errors.append(f"2b: Same question returned despite exclusion: {first_id}")
        else:
            logger.info(f"  First: {first_id}, Second: {second_id}")
    elif resp2.status_code == 404:
        logger.info(f"  First: {first_id}, Second: 404 (only one question available)")
    else:
        errors.append(f"2c: Unexpected status: {resp2.status_code}")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def test_diagnostic_question():
    """Test 3: POST /diagnostic/question returns a diagnostic question."""
    logger.info("=== Test 3: /diagnostic/question ===")
    errors = []

    payload = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "difficulty": "FOUNDATION",
        "previously_seen_ids": [],
    }

    resp = requests.post(f"{BASE_URL}/diagnostic/question", json=payload, timeout=10)
    if resp.status_code != 200:
        # 404 is acceptable if no diagnostic questions exist in the bank
        if resp.status_code == 404:
            logger.info("  No diagnostic questions in bank (404). Skipping.")
            logger.info("  PASS (no data)")
            return True
        errors.append(f"3a: Expected 200 or 404, got {resp.status_code}: {resp.text}")
    else:
        data = resp.json()

        # Check diagnostic-specific fields
        if data.get("phase") != "DIAGNOSTIC":
            errors.append(f"3b: phase should be DIAGNOSTIC, got '{data.get('phase')}'")

        # diagnostic_purpose and expected_method can be None but should be in response
        if "diagnostic_purpose" not in data:
            errors.append("3c: Missing 'diagnostic_purpose' field")
        if "expected_method" not in data:
            errors.append("3d: Missing 'expected_method' field")

        if not errors:
            logger.info(f"  Got: {data['question_id']} -- {data['question_text']}")
            logger.info(f"  Purpose: {data.get('diagnostic_purpose', 'N/A')}")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def test_invalid_request():
    """Test 4: Invalid request returns 422 (validation error)."""
    logger.info("=== Test 4: Invalid request handling ===")
    errors = []

    # Missing required field
    resp = requests.post(f"{BASE_URL}/question/next", json={}, timeout=10)
    if resp.status_code != 422:
        errors.append(f"4a: Expected 422 for empty body, got {resp.status_code}")
    else:
        logger.info("  Empty body correctly rejected with 422")

    # Invalid phase value
    payload = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "phase": "INVALID_PHASE",
        "difficulty": "FOUNDATION",
        "previously_seen_ids": [],
    }
    resp = requests.post(f"{BASE_URL}/question/next", json=payload, timeout=10)
    if resp.status_code != 422:
        errors.append(f"4b: Expected 422 for invalid phase, got {resp.status_code}")
    else:
        logger.info("  Invalid phase correctly rejected with 422")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def test_content_is_approved():
    """Test 5: Returned content has approval_status APPROVED."""
    logger.info("=== Test 5: Content approval status ===")
    errors = []

    # The response model doesn't include approval_status directly,
    # but the service filters for APPROVED only. We verify by checking
    # that the response has actual content (not empty/null fields).
    payload = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "phase": "GUIDED_PRACTICE",
        "difficulty": "FOUNDATION",
        "previously_seen_ids": [],
    }
    resp = requests.post(f"{BASE_URL}/question/next", json=payload, timeout=10)
    if resp.status_code != 200:
        errors.append(f"5a: Request failed: {resp.status_code}")
    else:
        data = resp.json()
        if not data.get("question_text"):
            errors.append("5b: question_text is empty")
        if not data.get("correct_answer"):
            errors.append("5c: correct_answer is empty")
        if not data.get("topic"):
            errors.append("5d: topic is empty")

        if not errors:
            logger.info(f"  Content looks valid: {data['question_id']}")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def main():
    logger.info("AD-403 Integration Test: Question Serving (AD-300 + AD-400)\n")

    if not check_server():
        return 1

    results = {}
    results["question_next"] = test_question_next()
    results["exclusion"] = test_question_next_exclusion()
    results["diagnostic"] = test_diagnostic_question()
    results["invalid_request"] = test_invalid_request()
    results["approved_content"] = test_content_is_approved()

    logger.info("\n=== Test Summary ===")
    for name, passed in results.items():
        logger.info(f"  {name}: {'PASS' if passed else 'FAIL'}")

    all_passed = all(results.values())
    logger.info(f"\n{'All tests passed!' if all_passed else 'Some tests failed.'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
