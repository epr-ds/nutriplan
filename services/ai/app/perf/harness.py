"""Drive a workload through the cached, budgeted completion stack and measure it (AIA-706).

:class:`BudgetHarness` issues a fixed sequence of requests at the production
:class:`~app.completions.CachedCompletionService` -- the very object the ``/ai/*`` routes call --
and records what happened, so the three guarantees can be asserted on real wiring rather than a
mock: a repeated request is served from cache (AC1), the p95 latency of served calls stays within
budget (AC2), and a request that would breach a token quota is refused, not run (AC3).

Two observability probes keep the harness honest without reaching inside the service: a ``clock``
(read before and after each call) gives an exact latency, and a ``calls`` counter (the provider's
cumulative call count) reveals whether a served request actually reached the provider -- if it did
not, it was a cache hit and cost nothing. A refusal surfaces as a :class:`~app.budget.errors.\
BudgetError`, which the harness catches and tallies separately from served calls.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.budget.errors import BudgetError
from app.budget.policy import BudgetScope
from app.completions import CachedCompletionService
from app.llm.types import LLMRequest
from app.perf.latency import LatencyBudget
from app.perf.report import BudgetReport

Workload = Sequence[tuple[LLMRequest, BudgetScope | None]]


class BudgetHarness:
    """Run a workload through a completion service and report cache / latency / cost metrics."""

    def __init__(
        self,
        service: CachedCompletionService,
        *,
        clock: Callable[[], float],
        calls: Callable[[], int],
        budget: LatencyBudget,
    ) -> None:
        self._service = service
        self._clock = clock
        self._calls = calls
        self._budget = budget

    def run(self, workload: Workload) -> BudgetReport:
        """Issue every request in order, measuring latency, cache hits, refusals, and spend."""
        latencies: list[float] = []
        cache_hits = 0
        refusals = 0
        tokens_spent = 0
        for request, scope in workload:
            calls_before = self._calls()
            started_at = self._clock()
            try:
                response = self._service.complete(request, scope)
            except BudgetError:
                refusals += 1
                continue
            latencies.append(self._clock() - started_at)
            if self._calls() == calls_before:
                cache_hits += 1
            elif response.usage is not None:
                tokens_spent += response.usage.total_tokens
        return BudgetReport(
            latencies=tuple(latencies),
            cache_hits=cache_hits,
            refusals=refusals,
            tokens_spent=tokens_spent,
            budget=self._budget,
        )
