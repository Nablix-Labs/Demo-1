"""
Test script for AD-401 -- Visual Cue Retrieval.

Tests the full flow:
1. Validate visual_cue_bank.json structure
2. Check Qdrant has the ingested data
3. Test get_visual_cue with different filters + exclusion logic

Usage:
    python ingest.py                    # run this first
    python test_visual_cue_retrieval.py

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
        logger.error("Run 'python ingest.py' first to populate the visual cue bank.")
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


def test_visual_cue_bank_structure():
    """Test 1: Verify visual_cue_bank.json has valid structure."""
    logger.info("=== Test 1: Visual Cue Bank Structure ===")

    bank_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "visual_cue_bank.json")
    with open(bank_path) as f:
        cues = json.load(f)

    required_fields = ["content_id", "concept_id", "error_type", "visual_cue_type",
                       "difficulty", "text", "topic", "subtopic"]

    errors = []
    ids_seen = set()
    for i, c in enumerate(cues):
        for field in required_fields:
            if field not in c or not c[field]:
                errors.append(f"Cue {i} ({c.get('content_id', '?')}): missing '{field}'")

        cid = c.get("content_id", "")
        if cid in ids_seen:
            errors.append(f"Duplicate content_id: {cid}")
        ids_seen.add(cid)

        valid_diffs = {"FOUNDATION", "INTERMEDIATE", "ADVANCED"}
        if c.get("difficulty") not in valid_diffs:
            errors.append(f"Cue {cid}: invalid difficulty '{c.get('difficulty')}'")

    if errors:
        for err in errors:
            logger.error(f"  FAIL: {err}")
        return False

    error_types = {}
    cue_types = {}
    concepts = {}
    for c in cues:
        error_types[c["error_type"]] = error_types.get(c["error_type"], 0) + 1
        cue_types[c["visual_cue_type"]] = cue_types.get(c["visual_cue_type"], 0) + 1
        concepts[c["concept_id"]] = concepts.get(c["concept_id"], 0) + 1

    logger.info(f"  Total cues: {len(cues)}")
    logger.info(f"  Unique IDs: {len(ids_seen)}")
    logger.info(f"  Error types: {dict(sorted(error_types.items()))}")
    logger.info(f"  Visual cue types: {dict(sorted(cue_types.items()))}")
    logger.info(f"  Concepts: {dict(sorted(concepts.items()))}")
    logger.info("  PASS")
    return True


def test_collection_exists():
    """Test 2: Check that Qdrant collection has visual cues."""
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


def test_get_visual_cue():
    """Test 3: Test the get_visual_cue function."""
    logger.info("=== Test 3: get_visual_cue ===")

    from visual_cue_service import get_visual_cue, count_available_cues

    errors = []

    # 3a: Get a visual cue for OPPOSITE_OPERATION_ERROR, one-step, foundation
    result = get_visual_cue(
        concept_id="ALG_LINEAR_ONE_STEP",
        error_type="OPPOSITE_OPERATION_ERROR",
        difficulty="FOUNDATION",
        exclude_content_ids=[],
        qdrant_client=_qdrant_client,
        openai_client=_openai_client,
    )
    if result is None:
        errors.append("3a: No cue returned for OPPOSITE_OPERATION_ERROR/ONE_STEP/FOUNDATION")
    else:
        logger.info(f"  3a: Got {result['content_id']} (type={result['visual_cue_type']}, score={result['relevance_score']})")
        if result["error_type"] != "OPPOSITE_OPERATION_ERROR":
            errors.append(f"3a: Wrong error_type '{result['error_type']}'")
        if result["concept_id"] != "ALG_LINEAR_ONE_STEP":
            errors.append(f"3a: Wrong concept '{result['concept_id']}'")
        if not result.get("text"):
            errors.append("3a: text field is empty")
        if not result.get("visual_cue_type"):
            errors.append("3a: visual_cue_type field is empty")

    # 3b: Get a cue for ARITHMETIC_ERROR
    result_arith = get_visual_cue(
        concept_id="ALG_LINEAR_ONE_STEP",
        error_type="ARITHMETIC_ERROR",
        difficulty="FOUNDATION",
        exclude_content_ids=[],
        qdrant_client=_qdrant_client,
        openai_client=_openai_client,
    )
    if result_arith is None:
        errors.append("3b: No cue returned for ARITHMETIC_ERROR")
    else:
        logger.info(f"  3b: Got {result_arith['content_id']} (type={result_arith['visual_cue_type']})")
        if result_arith["error_type"] != "ARITHMETIC_ERROR":
            errors.append(f"3b: Wrong error_type '{result_arith['error_type']}'")

    # 3c: Get a cue for two-step concept
    result_2step = get_visual_cue(
        concept_id="ALG_LINEAR_TWO_STEP",
        error_type="MISSING_STEP_ERROR",
        difficulty="FOUNDATION",
        exclude_content_ids=[],
        qdrant_client=_qdrant_client,
        openai_client=_openai_client,
    )
    if result_2step is None:
        errors.append("3c: No cue returned for MISSING_STEP_ERROR/TWO_STEP")
    else:
        logger.info(f"  3c: Got {result_2step['content_id']} (type={result_2step['visual_cue_type']})")

    # 3d: Test exclusion -- exclude first result, should get a different one
    if result:
        first_id = result["content_id"]
        result2 = get_visual_cue(
            concept_id="ALG_LINEAR_ONE_STEP",
            error_type="OPPOSITE_OPERATION_ERROR",
            difficulty="FOUNDATION",
            exclude_content_ids=[first_id],
            qdrant_client=_qdrant_client,
            openai_client=_openai_client,
        )
        if result2 is not None and result2["content_id"] == first_id:
            errors.append(f"3d: Got same cue back ({first_id}) despite being excluded")
        else:
            second_id = result2["content_id"] if result2 else "None (all excluded)"
            logger.info(f"  3d: Exclusion works. First: {first_id}, Second: {second_id}")

    # 3e: Count cues for a specific filter
    count = count_available_cues(
        concept_id="ALG_LINEAR_ONE_STEP",
        error_type="SIGN_ERROR",
        difficulty="FOUNDATION",
        qdrant_client=_qdrant_client,
    )
    logger.info(f"  3e: SIGN_ERROR/ONE_STEP/FOUNDATION count: {count}")
    if count == 0:
        errors.append("3e: Expected at least 1 SIGN_ERROR cue for ONE_STEP/FOUNDATION")

    if errors:
        for err in errors:
            logger.error(f"  FAIL: {err}")
        return False

    logger.info("  PASS")
    return True


def main():
    logger.info("Starting AD-401 tests\n")

    results = {}

    # Test 1: Structure (no API calls needed)
    results["structure"] = test_visual_cue_bank_structure()

    # Tests 2 & 3 need OpenAI API key + Qdrant data
    if not _has_api_key():
        logger.warning("OPENAI_API_KEY not set. Skipping ingestion/retrieval tests.")
        logger.info("\nTo run full tests, add OPENAI_API_KEY to .env in the AD-401 folder.")
    else:
        if not _setup_clients():
            logger.error("Failed to set up clients. Run 'python ingest.py' first.")
            return 1

        try:
            results["collection"] = test_collection_exists()
            if results["collection"]:
                results["retrieval"] = test_get_visual_cue()
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
