"""Offline AI recommendation eval harness (AIA-701).

This package grades the AI recommendation output on a fixed prompt set with known constraints and
reports two quality metrics -- **constraint-respect %** and **mean alignment score** -- entirely
offline (no LLM, no network), so it can run headless in CI and have its results trended over time.

- :data:`~app.eval.dataset.EVAL_SET` -- the fixed prompts with known constraints.
- :class:`~app.eval.harness.EvalHarness` -- grades the set into an
  :class:`~app.eval.report.EvalReport`.
- :func:`~app.eval.history.record` / :func:`~app.eval.history.compare_to_previous` -- trending.

Run it headless with ``python -m app.eval`` (see :mod:`app.eval.__main__`).
"""

from app.eval.case import CaseResult, EvalCase
from app.eval.dataset import EVAL_SET
from app.eval.harness import EvalHarness
from app.eval.history import EvalTrend, compare_to_previous, latest, record
from app.eval.report import EvalReport

__all__ = [
    "EVAL_SET",
    "CaseResult",
    "EvalCase",
    "EvalHarness",
    "EvalReport",
    "EvalTrend",
    "compare_to_previous",
    "latest",
    "record",
]
