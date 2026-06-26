"""Cost / latency budget harness for the AI completion stack (AIA-706).

A small measurement harness that drives a workload through the production cached, budgeted
completion service and reports the guarantees the QA story cares about: cache hits on repeated
requests (AC1), a p95 latency within budget (AC2), and token spend the guard keeps bounded by
refusing over-quota requests (AC3). :class:`~app.perf.harness.BudgetHarness` produces a
:class:`~app.perf.report.BudgetReport`; :class:`~app.perf.clock.ManualClock` and
:func:`~app.perf.latency.percentile` make the measurements deterministic.
"""

from app.perf.clock import ManualClock
from app.perf.harness import BudgetHarness, Workload
from app.perf.latency import LatencyBudget, percentile
from app.perf.report import BudgetReport

__all__ = [
    "BudgetHarness",
    "BudgetReport",
    "LatencyBudget",
    "ManualClock",
    "Workload",
    "percentile",
]
