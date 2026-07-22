"""Read-only question fetch from Aditya's Qdrant question bank.

Reads the `math_tutor_questions` collection seeded by
app/services/rag/question_serving (Aditya's code, untouched). Selection is a
pure filter lookup — no embedding call, no HTTP hop to his standalone
/question/next server — so it works on Vercel where that server does not run.
"""

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings
from app.models.fields import Phase

_client: AsyncQdrantClient | None = None


def _get_client() -> AsyncQdrantClient:
    # ponytail: module-level singleton, fine for one event loop per serverless worker.
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=settings.adapter_request_timeout_seconds,
        )
    return _client


async def fetch_question(
    concept_id: str,
    phase: Phase,
    exclude_question_ids: list[str] | None = None,
    difficulty: str = "FOUNDATION",
) -> tuple[str, str, str] | None:
    """Return (question_text, correct_answer, question_id) or None when exhausted.

    Only questions with a non-empty correct_answer are served — a question the
    backend cannot grade is treated as absent.
    """

    settings = get_settings()
    must_not: list[models.Condition] = []
    if exclude_question_ids:
        must_not.append(
            models.FieldCondition(
                key="question_id", match=models.MatchAny(any=exclude_question_ids)
            )
        )
    points, _ = await _get_client().scroll(
        collection_name=settings.qdrant_questions_collection,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="concept_id", match=models.MatchValue(value=concept_id)
                ),
                models.FieldCondition(
                    key="phase", match=models.MatchValue(value=phase)
                ),
                models.FieldCondition(
                    key="difficulty", match=models.MatchValue(value=difficulty)
                ),
            ],
            must_not=must_not,
        ),
        limit=10,
        with_payload=["question_text", "correct_answer", "question_id"],
    )
    served = set(exclude_question_ids or [])
    for point in points:
        payload = point.payload or {}
        text = payload.get("question_text")
        answer = payload.get("correct_answer")
        question_id = payload.get("question_id")
        if text and answer and question_id and question_id not in served:
            return (text, str(answer), question_id)
    return None
