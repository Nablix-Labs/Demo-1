"""
Test script for AD-300 — Question Serving.

Tests the full flow:
1. Validate question_bank.json structure
2. Check Qdrant has the ingested data
3. Test get_next_question with different filters + "not previously seen" logic

Usage:
    python ingest.py           # run this first
    python test_question_serving.py

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

# Shared Qdrant client -- created once, used by all tests.
# Local file-based Qdrant only allows one client at a time,
# so we open it once here and pass it around.
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
        logger.error("Run 'python ingest.py' first to populate the question bank.")
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


def test_question_bank_structure():
    """Test 1: Verify question_bank.json has valid structure."""
    logger.info("=== Test 1: Question Bank Structure ===")

    bank_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "question_bank.json")
    with open(bank_path) as f:
        questions = json.load(f)

    required_fields = ["question_id", "concept_id", "phase", "difficulty",
                       "question_text", "correct_answer", "topic", "subtopic"]

    errors = []
    ids_seen = set()
    for i, q in enumerate(questions):
        for field in required_fields:
            if field not in q or not q[field]:
                errors.append(f"Question {i} ({q.get('question_id', '?')}): missing '{field}'")

        qid = q.get("question_id", "")
        if qid in ids_seen:
            errors.append(f"Duplicate question_id: {qid}")
        ids_seen.add(qid)

        valid_phases = {"DIAGNOSTIC", "CONCEPT_ORIENTATION", "GUIDED_PRACTICE",
                        "INDEPENDENT_PRACTICE", "REVIEW"}
        if q.get("phase") not in valid_phases:
            errors.append(f"Question {qid}: invalid phase '{q.get('phase')}'")

        valid_diffs = {"FOUNDATION", "INTERMEDIATE", "ADVANCED"}
        if q.get("difficulty") not in valid_diffs:
            errors.append(f"Question {qid}: invalid difficulty '{q.get('difficulty')}'")

    if errors:
        for err in errors:
            logger.error(f"  FAIL: {err}")
        return False

    phases = {}
    concepts = {}
    for q in questions:
        phases[q["phase"]] = phases.get(q["phase"], 0) + 1
        concepts[q["concept_id"]] = concepts.get(q["concept_id"], 0) + 1

    logger.info(f"  Total questions: {len(questions)}")
    logger.info(f"  Unique IDs: {len(ids_seen)}")
    logger.info(f"  Phases covered: {dict(sorted(phases.items()))}")
    logger.info(f"  Concepts covered: {dict(sorted(concepts.items()))}")
    logger.info("  PASS")
    return True


def test_collection_exists():
    """Test 2: Check that Qdrant collection has questions."""
    logger.info("=== Test 2: Qdrant Collection Check ===")

    import config

    try:
        info = _qdrant_client.get_collection(config.QDRANT_COLLECTION)
        point_count = info.points_count

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


def test_get_next_question():
    """Test 3: Test the get_next_question function."""
    logger.info("=== Test 3: get_next_question ===")

    from question_service import get_next_question, count_available_questions

    errors = []

    # 3a: Get a question for GUIDED_PRACTICE, FOUNDATION, one-step
    result = get_next_question(
        concept_id="ALG_LINEAR_ONE_STEP",
        phase="GUIDED_PRACTICE",
        difficulty="FOUNDATION",
        previously_seen_ids=[],
        qdrant_client=_qdrant_client,
        openai_client=_openai_client,
    )
    if result is None:
        errors.append("3a: No question returned for GP/FOUNDATION/ONE_STEP")
    else:
        logger.info(f"  3a: Got {result['question_id']} - {result['question_text']}")
        if result["phase"] != "GUIDED_PRACTICE":
            errors.append(f"3a: Wrong phase '{result['phase']}', expected GUIDED_PRACTICE")
        if result["concept_id"] != "ALG_LINEAR_ONE_STEP":
            errors.append(f"3a: Wrong concept '{result['concept_id']}'")

    # 3b: Get a question for DIAGNOSTIC phase (different from GP)
    result_diag = get_next_question(
        concept_id="ALG_LINEAR_ONE_STEP",
        phase="DIAGNOSTIC",
        difficulty="FOUNDATION",
        previously_seen_ids=[],
        qdrant_client=_qdrant_client,
        openai_client=_openai_client,
    )
    if result_diag is None:
        errors.append("3b: No question returned for DIAGNOSTIC")
    else:
        logger.info(f"  3b: Got {result_diag['question_id']} - {result_diag['question_text']}")
        if result_diag["phase"] != "DIAGNOSTIC":
            errors.append(f"3b: Wrong phase '{result_diag['phase']}', expected DIAGNOSTIC")

    # 3c: Test "previously seen" -- pass first result's ID, should get a different one
    if result:
        first_id = result["question_id"]
        result2 = get_next_question(
            concept_id="ALG_LINEAR_ONE_STEP",
            phase="GUIDED_PRACTICE",
            difficulty="FOUNDATION",
            previously_seen_ids=[first_id],
            qdrant_client=_qdrant_client,
            openai_client=_openai_client,
        )
        if result2 is None:
            errors.append("3c: No second question returned (expected at least 2 GP/F questions)")
        elif result2["question_id"] == first_id:
            errors.append(f"3c: Got same question back ({first_id}) despite being in previously_seen")
        else:
            logger.info(f"  3c: Previously-seen works. First: {first_id}, Second: {result2['question_id']}")

    # 3d: Test two-step concept
    result_2step = get_next_question(
        concept_id="ALG_LINEAR_TWO_STEP",
        phase="GUIDED_PRACTICE",
        difficulty="FOUNDATION",
        previously_seen_ids=[],
        qdrant_client=_qdrant_client,
        openai_client=_openai_client,
    )
    if result_2step is None:
        errors.append("3d: No question returned for two-step GP/FOUNDATION")
    else:
        logger.info(f"  3d: Two-step: {result_2step['question_id']} - {result_2step['question_text']}")

    # 3e: Test exhausting all questions for a filter
    gp_count = count_available_questions(
        concept_id="ALG_LINEAR_ONE_STEP",
        phase="GUIDED_PRACTICE",
        difficulty="FOUNDATION",
        qdrant_client=_qdrant_client,
    )
    logger.info(f"  3e: Total GP/F/ONE_STEP questions: {gp_count}")

    all_seen = []
    for _ in range(gp_count + 1):
        r = get_next_question(
            concept_id="ALG_LINEAR_ONE_STEP",
            phase="GUIDED_PRACTICE",
            difficulty="FOUNDATION",
            previously_seen_ids=all_seen,
            qdrant_client=_qdrant_client,
            openai_client=_openai_client,
        )
        if r is None:
            break
        all_seen.append(r["question_id"])

    logger.info(f"  3e: Exhausted {len(all_seen)} questions before None: {all_seen}")
    if len(all_seen) != gp_count:
        errors.append(f"3e: Expected {gp_count} questions, got {len(all_seen)}")

    if errors:
        for err in errors:
            logger.error(f"  FAIL: {err}")
        return False

    logger.info("  PASS")
    return True


def main():
    logger.info("Starting AD-300 tests\n")

    results = {}

    # Test 1: Structure (no API calls needed)
    results["structure"] = test_question_bank_structure()

    # Tests 2 & 3 need OpenAI API key + Qdrant data
    if not _has_api_key():
        logger.warning("OPENAI_API_KEY not set. Skipping ingestion/retrieval tests.")
        logger.info("\nTo run full tests, add OPENAI_API_KEY to .env in the AD-300 folder.")
    else:
        if not _setup_clients():
            logger.error("Failed to set up clients. Run 'python ingest.py' first.")
            return 1

        try:
            results["collection"] = test_collection_exists()
            if results["collection"]:
                results["retrieval"] = test_get_next_question()
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
