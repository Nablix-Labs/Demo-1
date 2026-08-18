"""Select which Phase 3 attempts the tutor replays in Phase 4.

The spec states the rule once: a wrong Phase 3 submission is replayed, a
correct one is evidence only. Its four worked cases all fall out of that
single rule rather than needing branches of their own:

  A  first attempt correct                        -> nothing wrong, no replay
  B  wrong, then a fresh question correct         -> the one wrong attempt
  C  wrong, fresh wrong, repaired, then correct   -> both wrong attempts
  D  hint used, then correct                      -> nothing wrong, no replay

So hints never cause a replay, and a later correct attempt never suppresses
the earlier wrong one it replaced. The cases are covered as tests, not code.
"""

from __future__ import annotations

from app.models.topic_event_history import TopicAttemptRecord


PHASE_3 = "PHASE_3_INDEPENDENT_PRACTICE"


def filter_replay_attempts(
    attempts: list[TopicAttemptRecord],
) -> list[TopicAttemptRecord]:
    """Return the wrong Phase 3 attempts, in the order they were made."""

    return [
        attempt
        for attempt in attempts
        if attempt.phase == PHASE_3 and attempt.is_wrong
    ]
