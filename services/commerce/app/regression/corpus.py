"""Load the commerce regression corpus for the release gate (HRD-905 follow-up).

The release gate executes this corpus: the golden order / payment / lifecycle scenarios the
commerce service ships with, each carrying the severity it gates release on. The file lives at
``<service>/regression/corpus.json`` next to the application package, mirroring the AI service's
golden corpus location.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.regression.case import CommerceCase

CORPUS_PATH = Path(__file__).resolve().parents[2] / "regression" / "corpus.json"


def load_commerce_cases() -> tuple[CommerceCase, ...]:
    """Load every regression case in the commerce corpus."""
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases") or []
    return tuple(
        CommerceCase(
            name=str(case.get("name") or ""),
            journey=str(case.get("journey") or ""),
            severity=str(case.get("severity") or "P2"),
            tags=tuple(case.get("tags") or ()),
            input=dict(case.get("input") or {}),
            expected=dict(case.get("expected") or {}),
        )
        for case in cases
    )
