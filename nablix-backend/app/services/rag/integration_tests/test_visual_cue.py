"""
AD-403 Integration Test -- Visual Cue Retrieval (AD-401)

Tests the visual cue retrieval microservice via HTTP requests.

The server must be running on the configured port before running this.

Usage:
    cd visual_cue_retrieval/
    python server.py &          # start server on port 8003
    cd ../../AD-403/
    python test_visual_cue.py
"""

import requests
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_visual_cue")

BASE_URL = "http://localhost:8003"


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
        logger.error("  Start the server first: cd visual_cue_retrieval/ && python server.py")
        return False


def test_retrieve_visual_cue():
    """Test 1: POST /visual-cue/retrieve returns a valid cue."""
    logger.info("=== Test 1: /visual-cue/retrieve basic retrieval ===")
    errors = []

    payload = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "error_type": "OPPOSITE_OPERATION_ERROR",
        "difficulty": "FOUNDATION",
        "exclude_content_ids": [],
    }

    resp = requests.post(f"{BASE_URL}/visual-cue/retrieve", json=payload, timeout=10)
    if resp.status_code != 200:
        if resp.status_code == 404:
            logger.info("  No cues found for this filter (404). Check data.")
            errors.append("1a: No visual cue returned (404)")
        else:
            errors.append(f"1a: Expected 200, got {resp.status_code}: {resp.text}")
    else:
        data = resp.json()

        # Check required fields
        required = [
            "content_id", "concept_id", "visual_cue_type", "text",
            "error_type", "difficulty", "topic", "subtopic",
            "relevance_score", "approval_status",
        ]
        for field in required:
            if field not in data:
                errors.append(f"1b: Missing field '{field}'")
            elif data[field] is None or data[field] == "":
                errors.append(f"1c: Empty field '{field}'")

        # Check values match request
        if data.get("concept_id") != "ALG_LINEAR_ONE_STEP":
            errors.append(f"1d: concept_id mismatch: {data.get('concept_id')}")
        if data.get("error_type") != "OPPOSITE_OPERATION_ERROR":
            errors.append(f"1e: error_type mismatch: {data.get('error_type')}")
        if data.get("difficulty") != "FOUNDATION":
            errors.append(f"1f: difficulty mismatch: {data.get('difficulty')}")

        # Check approval status
        if data.get("approval_status") != "APPROVED":
            errors.append(f"1g: approval_status should be APPROVED, got '{data.get('approval_status')}'")

        # Check visual_cue_type is a known value
        known_types = {"BALANCE_SCALE", "NUMBER_LINE", "EQUATION_BLOCK", "STEP_HIGHLIGHT"}
        if data.get("visual_cue_type") not in known_types:
            errors.append(
                f"1h: visual_cue_type '{data.get('visual_cue_type')}' not in known types: {known_types}"
            )

        if not errors:
            logger.info(f"  Got: {data['content_id']}")
            logger.info(f"  Type: {data['visual_cue_type']}, Score: {data['relevance_score']}")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def test_different_error_types():
    """Test 2: Different error types return relevant cues."""
    logger.info("=== Test 2: Different error types ===")
    errors = []

    error_types = [
        "OPPOSITE_OPERATION_ERROR",
        "ARITHMETIC_ERROR",
        "SIGN_ERROR",
    ]

    for error_type in error_types:
        payload = {
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "error_type": error_type,
            "difficulty": "FOUNDATION",
            "exclude_content_ids": [],
        }
        resp = requests.post(f"{BASE_URL}/visual-cue/retrieve", json=payload, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            if data.get("error_type") != error_type:
                errors.append(f"2: {error_type}: response error_type mismatch: {data.get('error_type')}")
            else:
                logger.info(f"  {error_type}: {data['content_id']} ({data['visual_cue_type']})")
        elif resp.status_code == 404:
            logger.info(f"  {error_type}: no cue available (404)")
        else:
            errors.append(f"2: {error_type}: unexpected status {resp.status_code}")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def test_exclusion():
    """Test 3: Excluding a content_id returns a different cue."""
    logger.info("=== Test 3: Exclusion ===")
    errors = []

    payload1 = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "error_type": "OPPOSITE_OPERATION_ERROR",
        "difficulty": "FOUNDATION",
        "exclude_content_ids": [],
    }
    resp1 = requests.post(f"{BASE_URL}/visual-cue/retrieve", json=payload1, timeout=10)
    if resp1.status_code != 200:
        logger.info("  No cue returned for first request. Skipping exclusion test.")
        logger.info("  PASS (no data)")
        return True

    first_id = resp1.json()["content_id"]

    payload2 = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "error_type": "OPPOSITE_OPERATION_ERROR",
        "difficulty": "FOUNDATION",
        "exclude_content_ids": [first_id],
    }
    resp2 = requests.post(f"{BASE_URL}/visual-cue/retrieve", json=payload2, timeout=10)

    if resp2.status_code == 200:
        second_id = resp2.json()["content_id"]
        if second_id == first_id:
            errors.append(f"3a: Same cue returned despite exclusion: {first_id}")
        else:
            logger.info(f"  First: {first_id}, Second: {second_id}")
    elif resp2.status_code == 404:
        logger.info(f"  First: {first_id}, Second: 404 (only one cue available)")
    else:
        errors.append(f"3b: Unexpected status: {resp2.status_code}")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def test_invalid_request():
    """Test 4: Invalid request returns 422."""
    logger.info("=== Test 4: Invalid request handling ===")
    errors = []

    # Missing required field
    resp = requests.post(f"{BASE_URL}/visual-cue/retrieve", json={}, timeout=10)
    if resp.status_code != 422:
        errors.append(f"4a: Expected 422 for empty body, got {resp.status_code}")
    else:
        logger.info("  Empty body correctly rejected with 422")

    # Invalid difficulty
    payload = {
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "error_type": "OPPOSITE_OPERATION_ERROR",
        "difficulty": "INVALID",
        "exclude_content_ids": [],
    }
    resp = requests.post(f"{BASE_URL}/visual-cue/retrieve", json=payload, timeout=10)
    if resp.status_code != 422:
        errors.append(f"4b: Expected 422 for invalid difficulty, got {resp.status_code}")
    else:
        logger.info("  Invalid difficulty correctly rejected with 422")

    if errors:
        for e in errors:
            logger.error(f"  FAIL: {e}")
        return False

    logger.info("  PASS")
    return True


def main():
    logger.info("AD-403 Integration Test: Visual Cue Retrieval (AD-401)\n")

    if not check_server():
        return 1

    results = {}
    results["retrieve"] = test_retrieve_visual_cue()
    results["error_types"] = test_different_error_types()
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
