"""Trend eval metrics over time by appending each run to a JSONL history (AIA-701).

AC3 asks that "results [are] trended over time". Each run's compact
:meth:`~app.eval.report.EvalReport.metrics` is appended as one JSON line to a history file, and
:func:`compare_to_previous` reads the last recorded run to report the deltas in the two headline
metrics. This is a small, dependency-free store: append-only JSONL is trivially diffable, greppable,
and safe to commit or publish as a CI artifact, so a regression in constraint-respect or alignment
shows up as a negative delta between runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.eval.report import EvalReport


@dataclass(frozen=True, slots=True)
class EvalTrend:
    """The change in the two headline metrics versus the previous recorded run."""

    previous_at: str
    delta_constraint_respect: float
    delta_mean_alignment: float

    def describe(self) -> str:
        return (
            f"vs {self.previous_at}: constraint-respect {self.delta_constraint_respect:+.4f}, "
            f"mean alignment {self.delta_mean_alignment:+.4f}"
        )


def record(report: EvalReport, path: Path) -> None:
    """Append the run's metrics to the JSONL history at ``path`` (creating parents)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report.metrics()) + "\n")


def latest(path: Path) -> dict[str, object] | None:
    """Return the most recent recorded run, or ``None`` if the history is empty/absent."""
    if not path.exists():
        return None
    last: dict[str, object] | None = None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                last = json.loads(stripped)
    return last


def compare_to_previous(report: EvalReport, path: Path) -> EvalTrend | None:
    """Compare ``report`` to the last recorded run, or ``None`` when there is no history."""
    previous = latest(path)
    if previous is None:
        return None
    prev_respect = float(previous.get("constraint_respect", 0.0))  # type: ignore[arg-type]
    prev_alignment = float(previous.get("mean_alignment", 0.0))  # type: ignore[arg-type]
    return EvalTrend(
        previous_at=str(previous.get("generated_at", "unknown")),
        delta_constraint_respect=round(report.constraint_respect - prev_respect, 4),
        delta_mean_alignment=round(report.mean_alignment - prev_alignment, 4),
    )
