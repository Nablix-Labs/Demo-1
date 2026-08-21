"""Locating the input files.

The topic documents and the reference workbook are inputs, not code. They
are not in the repository -- they are large binaries authored elsewhere --
so anything that needs them has to find them wherever this package happens
to be checked out.

Used by the parser (CG-005 onward) to find topic DOCX files, and by the
tests to find the reference workbook.

Resolution order:

  1. NABLIX_CONTENT_SOURCES, if set. Use this when the sources live
     somewhere unusual, or in CI.
  2. A "Content Gen- Agent" directory at any level above this package.
     Covers both the working copy and a checkout inside the repo, which
     sit at different depths.

Returning None rather than raising is deliberate: the tests skip when the
reference is absent, and skipping is the correct behaviour on a machine
that only has the code. The risk is that a missing workbook turns the
reference tests into silent skips and the suite still reports green, so
`describe_sources()` exists to make the situation visible when needed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

SOURCES_DIR_NAME = "Content Gen- Agent"
REFERENCE_WORKBOOK_NAME = "Nablix_Topics_1_to_3_Canvas_AnswerSteps.xlsx"
TOPIC_DOC_PATTERN = "Topic_*_Formatted.docx"

ENV_VAR = "NABLIX_CONTENT_SOURCES"


def find_sources_dir() -> Optional[Path]:
    """Directory holding the topic documents and the reference workbook."""
    override = os.environ.get(ENV_VAR)
    if override:
        candidate = Path(override).expanduser()
        return candidate if candidate.is_dir() else None

    for parent in Path(__file__).resolve().parents:
        candidate = parent / SOURCES_DIR_NAME
        if candidate.is_dir():
            return candidate
    return None


def find_reference_workbook() -> Optional[Path]:
    """The approved reference workbook, or None if it is not present."""
    sources = find_sources_dir()
    if sources is None:
        return None
    workbook = sources / REFERENCE_WORKBOOK_NAME
    return workbook if workbook.is_file() else None


def find_topic_documents() -> list[Path]:
    """Every formatted topic document, sorted by name.

    Empty list when the sources directory is missing, so callers can
    report that clearly rather than crashing on a path.
    """
    sources = find_sources_dir()
    if sources is None:
        return []
    return sorted(sources.glob(TOPIC_DOC_PATTERN))


def describe_sources() -> str:
    """Human-readable summary, for when something is not being found."""
    sources = find_sources_dir()
    if sources is None:
        return (
            f"No sources directory found. Looked for {SOURCES_DIR_NAME!r} "
            f"above {Path(__file__).resolve().parent}, and ${ENV_VAR} is "
            f"{'set to ' + os.environ[ENV_VAR] if ENV_VAR in os.environ else 'unset'}."
        )
    workbook = find_reference_workbook()
    topics = find_topic_documents()
    return (
        f"sources: {sources}\n"
        f"reference workbook: {workbook or 'MISSING'}\n"
        f"topic documents: {len(topics)} found"
        + ("".join(f"\n  - {p.name}" for p in topics) if topics else "")
    )


REFERENCE_WORKBOOK = find_reference_workbook()


if __name__ == "__main__":
    print(describe_sources())
