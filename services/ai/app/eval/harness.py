"""The offline eval harness: grade a fixed prompt set, headless and deterministic (AIA-701).

:class:`EvalHarness` runs each :class:`~app.eval.case.EvalCase` through the production
:class:`~app.recommendations.alignment.RecommendationAligner` -- the same component that computes
``nutritionalAlignment`` for the live ``/ai/*`` response -- and gathers the per-case results into an
:class:`~app.eval.report.EvalReport`. It does no I/O and no LLM call: the model output is recorded
on the cases, so a run is fully offline and reproducible (AC: "runs headless").

The :class:`~app.recommendations.alignment.RecommendationAligner` (and the
:class:`~app.scoring.scorer.AlignmentScorer` inside it) and the ``clock`` are injected, so the
scoring policy is explicit and timestamps are deterministic under test.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from app.eval.case import CaseResult, EvalCase
from app.eval.report import EvalReport
from app.recommendations.alignment import RecommendationAligner


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EvalHarness:
    """Score a fixed eval set into a report of constraint-respect % and mean alignment."""

    def __init__(
        self,
        aligner: RecommendationAligner | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._aligner = aligner or RecommendationAligner()
        self._clock = clock or _utc_now

    def run(self, cases: Sequence[EvalCase]) -> EvalReport:
        """Grade every case and return the aggregated report, stamped with the run time."""
        results = tuple(self._evaluate(case) for case in cases)
        generated_at = self._clock().isoformat(timespec="seconds")
        return EvalReport(generated_at=generated_at, cases=results)

    def _evaluate(self, case: EvalCase) -> CaseResult:
        alignment = self._aligner.align(case.recipes, case.command)
        if alignment is None:
            raise ValueError(
                f"eval case {case.name!r} has no constraints or recipes to score against"
            )
        return CaseResult(name=case.name, prompt=case.prompt, alignment=alignment)
