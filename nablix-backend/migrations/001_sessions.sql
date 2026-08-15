CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('started', 'ended')),
    state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS sessions_student_id_idx ON sessions (student_id);
