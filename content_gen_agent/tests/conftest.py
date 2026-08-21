"""Pytest configuration.

Puts the package root on sys.path so tests can `from id_service import ...`
regardless of where pytest is invoked from.

File discovery lives in the package itself (`sources.py`), not here. The
parser needs to find topic documents at runtime, so that logic is part of
the product rather than test scaffolding.
"""

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
