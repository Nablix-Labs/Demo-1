"""
Worked example retrieval service for AD-402.

Core logic for POST /worked-example/retrieve: queries Qdrant, filters by
concept_id/operation_type/difficulty, then applies two safety checks before
returning a result:

1. Different-numbers check: extracts all numbers from the student's current
   question and the worked example's question. If any numbers overlap, the
   example is skipped. This is a hard rule from the module guide -- we can't
   show students a worked example that uses the same numbers because that
   would basically give away their answer.

2. Guardrail check: uses Sanya's contains_answer_reveal() function from
   rag/guardrail.py to make sure the worked example text doesn't accidentally
   contain the student's current answer (e.g., "so x = 4" when the student's
   answer is 4). When running locally (not inside the rag/ package), this
   falls back to a simplified version of the same check.

The response always includes different_numbers_confirmed=True because we
only return examples that passed both checks.
"""

import re
import logging

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("worked_example_service")


# --- Guardrail integration ---
#
# Sanya's guardrail (rag/guardrail.py) has contains_answer_reveal() which
# checks if text reveals an answer. It does three checks:
#   1. Substring match: is the answer string anywhere in the text?
#   2. Reveal phrases: "the answer is", "so x =", etc.
#   3. Regex: does the answer number appear with word boundaries?
#
# Problem: check 1 uses raw substring matching. When the student's answer
# is "5", it matches "5" inside "15" (because "15" contains the character
# "5"). Same with "2" matching inside "2x". This causes false positives
# in worked examples which are full of numbers.
#
# The fix: we keep Sanya's full guardrail logic (all three checks + all
# reveal phrases) but replace check 1 with a proper word-boundary regex.
# This way "5" matches standalone "5" but NOT "15" or "25". And "2"
# matches standalone "2" but NOT the coefficient in "2x".
#
# When deployed to rag/worked_example_retrieval/ inside the repo, this
# should import from Sanya's guardrail.py directly (with the same fix
# applied there). For local development, we use a local implementation.

_guardrail_fn = None

try:
    from ..guardrail import contains_answer_reveal, _load_rules
    # When using the import, we wrap it to load rules automatically
    def _imported_guardrail(message: str, correct_answer: str, example_question: str = "") -> bool:
        rules = _load_rules()
        return contains_answer_reveal(message, correct_answer, rules)
    _guardrail_fn = _imported_guardrail
    logger.info("Imported guardrail from rag package")
except (ImportError, SystemError):
    logger.info("Running outside rag package -- using local guardrail check")

    # Reveal phrases from Sanya's classifier_rules.yaml.
    #
    # Split into two groups:
    #
    # "Always" phrases flag no matter what. If the text says "the answer
    # is ..." that's a reveal regardless of context.
    #
    # "With-answer" phrases like "so x =" only matter when the number
    # AFTER them matches the student's answer. Every worked example ends
    # with "So x = [answer]" -- that's the whole point. We only care if
    # that answer happens to be the STUDENT's answer, not the example's.
    _REVEAL_PHRASES_ALWAYS = [
        "the answer is",
        "final answer is",
        "solution is",
    ]

    _REVEAL_PHRASES_WITH_ANSWER = [
        "so x =",
        "therefore x =",
    ]

    def _normalize(text: str) -> str:
        return " ".join(text.strip().lower().split())

    def _local_contains_answer_reveal(
        message: str,
        correct_answer: str,
        example_question: str = "",
    ) -> bool:
        """Check if a worked example message reveals the student's answer.

        Based on Sanya's contains_answer_reveal() from rag/guardrail.py,
        adapted for worked examples with two key changes:

        1. Word-boundary regex instead of raw substring matching.
           Sanya's check 1 does "answer in message" which causes "5" to
           match inside "15". We use (?<!\\w)...(?!\\w) so "5" only
           matches as a standalone token.

        2. Context-aware checks for worked examples.
           Sanya's guardrail was built for HINT and SCAFFOLD_STEP content.
           Worked examples are different -- they show a full solution with
           all the steps, so numbers from the example's equation naturally
           appear throughout the text ("divide by 2" when the equation is
           "2x + 3 = 11"). We exempt those numbers from standalone checks.

           Similarly, reveal phrases like "so x =" appear in every worked
           example ("So x = 7."). We only flag them when the number that
           follows matches the student's answer.

        Args:
            message: The text to check (worked example text)
            correct_answer: The student's current answer (e.g., "4")
            example_question: The worked example's equation (e.g., "2x + 3 = 11").
                Numbers from this equation are exempt from standalone checks
                because they appear naturally in the solution steps.

        Returns:
            True if the message reveals the student's answer (skip this example)
        """
        normalized_msg = _normalize(message)
        normalized_ans = _normalize(correct_answer)

        # Numbers from the example's own equation. These appear naturally
        # in worked example text as part of showing the solution steps
        # (e.g., "divide both sides by 2" when the equation is "2x + 3 = 11").
        # We don't flag these even if they match the student's answer --
        # they're part of the example, not a reveal.
        exempt_numbers = set()
        if example_question:
            exempt_numbers = _extract_numbers(example_question)

        # Check 1: does the answer appear as a standalone token?
        # Uses word boundaries so "5" matches "x = 5" but not "15" or "2x".
        if normalized_ans:
            pattern = rf"(?<!\w){re.escape(normalized_ans)}(?!\w)"
            if re.search(pattern, normalized_msg):
                # Skip if this number is from the example's equation
                try:
                    if float(normalized_ans) not in exempt_numbers:
                        return True
                except ValueError:
                    return True

        # Check 2a: unconditional reveal phrases
        for phrase in _REVEAL_PHRASES_ALWAYS:
            if phrase in normalized_msg:
                return True

        # Check 2b: context-aware reveal phrases ("so x =", "therefore x =")
        # Only flag if the number right after the phrase matches the
        # student's answer. "so x = 7" is fine when student's answer is 5.
        # "so x = 5" when student's answer is 5 is a reveal.
        answer_nums = re.findall(r"-?\d+(?:\.\d+)?", normalized_ans)
        if answer_nums:
            answer_float = float(answer_nums[-1])
            for phrase in _REVEAL_PHRASES_WITH_ANSWER:
                start = 0
                while True:
                    pos = normalized_msg.find(phrase, start)
                    if pos < 0:
                        break
                    remainder = normalized_msg[pos + len(phrase):].strip()
                    num_match = re.match(r"-?\d+(?:\.\d+)?", remainder)
                    if num_match and float(num_match.group()) == answer_float:
                        return True
                    start = pos + 1

        # Check 3: does the answer number appear as a standalone number?
        number_matches = re.findall(r"-?\d+(?:\.\d+)?", correct_answer)
        if not number_matches:
            return False

        answer_number = float(number_matches[-1])
        if answer_number == int(answer_number):
            answer_str = str(int(answer_number))
        else:
            answer_str = str(answer_number)

        # Word-boundary regex: "5" matches standalone but not in "15" or "5x".
        number_pattern = rf"(?<!\w)-?{re.escape(answer_str)}(?!\w)"
        if re.search(number_pattern, normalized_msg):
            # Exempt numbers from the example's equation
            if answer_number not in exempt_numbers:
                return True

        return False

    _guardrail_fn = _local_contains_answer_reveal


# --- Different-numbers check ---

def _extract_numbers(text: str) -> set[float]:
    """Pull all numbers out of a string.

    For "2x + 3 = 11" this returns {2.0, 3.0, 11.0}.
    For "x + 5 = 12" this returns {5.0, 12.0}.

    We use floats so that "3" and "3.0" are treated as the same number.
    """
    matches = re.findall(r"-?\d+(?:\.\d+)?", text)
    return {float(m) for m in matches}


def _has_same_numbers(current_question: str, example_question: str) -> bool:
    """Check if the worked example uses any of the same numbers as the
    student's current question.

    This is the "hard rule" from the module guide: a worked example
    must use completely different numbers so it doesn't give the student
    a shortcut to their answer.

    Args:
        current_question: e.g., "x + 3 = 7"
        example_question: e.g., "x + 5 = 12"

    Returns:
        True if there are shared numbers (meaning we should SKIP this example)
    """
    current_nums = _extract_numbers(current_question)
    example_nums = _extract_numbers(example_question)

    overlap = current_nums & example_nums
    if overlap:
        logger.debug(f"Number overlap: {overlap} between '{current_question}' and '{example_question}'")
        return True
    return False


# --- Main retrieval function ---

def get_worked_example(
    concept_id: str,
    operation_type: str,
    current_question: str,
    current_answer: str,
    difficulty: str,
    exclude_content_ids: list[str],
    qdrant_client: QdrantClient,
    openai_client: OpenAI,
) -> dict | None:
    """
    Find the best worked example for the student's current situation.

    How it works:
    1. Build Qdrant filter for concept_id + operation_type + difficulty
       + approval_status=APPROVED
    2. Generate a query embedding
    3. Run vector search to get candidates
    4. For each candidate, apply three filters:
       a. Skip if content_id is in exclude_content_ids (already shown)
       b. Skip if the example uses same numbers as current question
       c. Skip if Sanya's guardrail says example text reveals the answer
          (uses word-boundary matching so "5" doesn't match inside "15")
    5. Return first candidate that passes all filters, or None

    The order matters -- cheapest check first (string compare, number
    extraction), then the guardrail.
    """

    # 1. Build filter
    must_conditions = [
        FieldCondition(key="concept_id", match=MatchValue(value=concept_id)),
        FieldCondition(key="operation_type", match=MatchValue(value=operation_type)),
        FieldCondition(key="difficulty", match=MatchValue(value=difficulty)),
        FieldCondition(key="approval_status", match=MatchValue(value="APPROVED")),
    ]
    query_filter = Filter(must=must_conditions)

    # 2. Build query text for embedding
    query_text = (
        f"worked example for {operation_type} "
        f"in {concept_id} at {difficulty} difficulty"
    )

    query_embedding = openai_client.embeddings.create(
        input=query_text,
        model=config.EMBEDDING_MODEL,
    ).data[0].embedding

    # 3. Search Qdrant
    # Get extra results in case some fail the safety checks
    search_limit = len(exclude_content_ids) + 10

    search_response = qdrant_client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=query_embedding,
        using="text",
        query_filter=query_filter,
        limit=search_limit,
        with_payload=True,
    )

    # 4. Filter candidates
    for hit in search_response.points:
        payload = hit.payload
        content_id = payload.get("content_id", "")
        example_question = payload.get("example_question", "")
        example_text = payload.get("text", "")

        # 4a. Already shown?
        if content_id in exclude_content_ids:
            logger.debug(f"Skipping {content_id}: already excluded")
            continue

        # 4b. Same numbers as current question?
        if _has_same_numbers(current_question, example_question):
            logger.info(
                f"SKIP_SAME_NUMBERS: {content_id} -- "
                f"example '{example_question}' shares numbers with '{current_question}'"
            )
            continue

        # 4c. Does the example text reveal the student's current answer?
        # Uses Sanya's guardrail logic with two adaptations for worked examples:
        #   - Reveal phrases ("so x =") only flag if the number after them
        #     matches the student's answer
        #   - Numbers from the example's equation are exempt from standalone
        #     matching (they appear naturally in solution steps)
        if _guardrail_fn(example_text, current_answer, example_question):
            logger.info(
                f"SKIP_GUARDRAIL: {content_id} -- "
                f"text reveals answer '{current_answer}'"
            )
            continue

        # Also check voice_text if it exists
        voice_text = payload.get("voice_text")
        if voice_text and _guardrail_fn(voice_text, current_answer, example_question):
            logger.info(
                f"SKIP_GUARDRAIL: {content_id} -- "
                f"voice_text reveals answer '{current_answer}'"
            )
            continue

        # 5. This candidate passed all checks
        relevance_score = hit.score if hit.score is not None else 0.0

        result = {
            "content_id": content_id,
            "content_type": "WORKED_EXAMPLE",
            "concept_id": payload.get("concept_id", ""),
            "operation_type": payload.get("operation_type", ""),
            "example_question": example_question,
            "example_answer": payload.get("example_answer", ""),
            "text": example_text,
            "voice_text": voice_text,
            "difficulty": payload.get("difficulty", ""),
            "topic": payload.get("topic", ""),
            "subtopic": payload.get("subtopic", ""),
            "different_numbers_confirmed": True,
            "relevance_score": round(relevance_score, 4),
            "approval_status": payload.get("approval_status", ""),
        }

        logger.info(
            f"WORKED_EXAMPLE_SERVED: content_id={content_id}, "
            f"concept={concept_id}, operation={operation_type}, "
            f"difficulty={difficulty}, score={relevance_score:.4f}"
        )
        return result

    # No matching example found after all filters
    logger.info(
        f"NO_WORKED_EXAMPLE: concept={concept_id}, operation={operation_type}, "
        f"difficulty={difficulty}, question='{current_question}'"
    )
    return None


def count_available_examples(
    concept_id: str,
    operation_type: str,
    difficulty: str,
    qdrant_client: QdrantClient,
) -> int:
    """Count how many worked examples exist for a given filter combination.

    Note: this count is BEFORE the different-numbers and guardrail checks.
    The actual number of usable examples for a specific question might be lower.
    """
    query_filter = Filter(must=[
        FieldCondition(key="concept_id", match=MatchValue(value=concept_id)),
        FieldCondition(key="operation_type", match=MatchValue(value=operation_type)),
        FieldCondition(key="difficulty", match=MatchValue(value=difficulty)),
        FieldCondition(key="approval_status", match=MatchValue(value="APPROVED")),
    ])

    result = qdrant_client.count(
        collection_name=config.QDRANT_COLLECTION,
        count_filter=query_filter,
        exact=True,
    )
    return result.count
