"""Mock-grade store for raw canvas snapshots, kept out of session state.

Holding the ~2 MB image here (keyed by reference) rather than inside
SessionRecord keeps the session object small and makes the snapshot an
intentional, retrievable artifact instead of dead weight. Swap this module for
disk/blob storage later without touching callers.
"""

_snapshots: dict[str, str] = {}


def build_reference(submission_id: str) -> str:
    """Derive the stable reference string for a submission's snapshot."""

    return f"canvas/{submission_id}.png"


def store_snapshot(reference: str, snapshot_data_url: str) -> None:
    _snapshots[reference] = snapshot_data_url


def get_snapshot(reference: str) -> str | None:
    return _snapshots.get(reference)
