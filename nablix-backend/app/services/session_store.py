import json

import asyncpg

from app.models.session import SessionRecord


_pool: asyncpg.Pool | None = None


async def open_session_store(database_url: str) -> dict[str, SessionRecord]:
    """Connect to PostgreSQL and load every persisted Nablix session."""

    if not database_url:
        raise RuntimeError("NABLIX_DATABASE_URL is required for session persistence.")

    global _pool
    _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    rows = await _pool.fetch("SELECT session_id, state FROM sessions")
    return {
        row["session_id"]: SessionRecord.model_validate(
            json.loads(row["state"]) if isinstance(row["state"], str) else row["state"]
        )
        for row in rows
    }


async def close_session_store() -> None:
    """Close the PostgreSQL connection pool."""

    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def save_session(session: SessionRecord) -> None:
    """Insert or replace one complete session record."""

    if _pool is None:
        raise RuntimeError("Session store is not open.")

    await _pool.execute(
        """
        INSERT INTO sessions (session_id, student_id, status, state, created_at, updated_at)
        VALUES ($1, $2, $3, $4::jsonb, $5, NOW())
        ON CONFLICT (session_id) DO UPDATE SET
            student_id = EXCLUDED.student_id,
            status = EXCLUDED.status,
            state = EXCLUDED.state,
            updated_at = NOW()
        """,
        session.session_id,
        session.student_id,
        session.status,
        json.dumps(session.model_dump(mode="json")),
        session.started_at,
    )
