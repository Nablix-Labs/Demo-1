import json

import asyncpg

from app.models.session import SessionRecord
from app.services.snapshot_store import get_snapshot, store_snapshot


_pool: asyncpg.Pool | None = None


def _decode_state(value: object) -> dict[str, object]:
    decoded: object = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, dict):
        raise RuntimeError("Persisted session state must be a JSON object.")
    return decoded


def _restore_session(row: asyncpg.Record) -> SessionRecord:
    state = _decode_state(row["state"])
    snapshots = state.pop("_canvas_snapshots", {})
    if not isinstance(snapshots, dict):
        raise RuntimeError("Persisted canvas snapshots must be a JSON object.")
    for reference, snapshot_data_url in snapshots.items():
        if not isinstance(reference, str) or not isinstance(snapshot_data_url, str):
            raise RuntimeError("Persisted canvas snapshot entries must be strings.")
        store_snapshot(reference, snapshot_data_url)
    return SessionRecord.model_validate(state)


async def open_session_store(database_url: str) -> dict[str, SessionRecord]:
    """Connect to PostgreSQL and load every persisted Nablix session."""

    if not database_url:
        raise RuntimeError("NABLIX_DATABASE_URL is required for session persistence.")

    global _pool
    _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    rows = await _pool.fetch("SELECT session_id, state FROM sessions")
    return {row["session_id"]: _restore_session(row) for row in rows}


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

    state = session.model_dump(mode="json")
    snapshots = {
        submission.snapshot_reference: snapshot_data_url
        for submission in session.canvas_submissions
        if (snapshot_data_url := get_snapshot(submission.snapshot_reference)) is not None
    }
    if snapshots:
        state["_canvas_snapshots"] = snapshots

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
        json.dumps(state),
        session.started_at,
    )
