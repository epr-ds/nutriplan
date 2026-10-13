"""The measured outcome of a budget-harness run: latency, cache, and cost (AIA-706).

:class:`BudgetReport` gathers what one workload produced -- the per-request latencies of served
calls, how many were cache hits, how many were refused on budget grounds, and the tokens actually
spent -- and derives the three headline figures the story cares about: the cache-hit rate (AC1), the
p95 latency and whether it is within budget (AC2), and the token spend the guard kept bounded (AC3).
Refused requests are counted but carry no latency sample, so the p95 reflects only calls that ran.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.perf.latency import LatencyBudget, percentile

_P95 = 95.0


@dataclass(frozen=True, slots=True)
class BudgetReport:
    """Derived cache / latency / cost metrics for a single harness run."""

    latencies: tuple[float, ...]
    cache_hits: int
    refusals: int
    tokens_spent: int
    budget: LatencyBudget

    @property
    def served(self) -> int:
        """Requests that ran to a response (cache hits plus provider misses)."""
        return len(self.latencies)

    @property
    def misses(self) -> int:
        """Served requests that reached the provider."""
        return self.served - self.cache_hits

    @property
    def total_requests(self) -> int:
        """Every request the workload issued, served or refused."""
        return self.served + self.refusals

    @property
    def cache_hit_rate(self) -> float:
        """Fraction of served requests answered from cache (``0.0`` when none ran)."""
        return self.cache_hits / self.served if self.served else 0.0

    @property
    def p95_latency(self) -> float:
        """The 95th-percentile latency of served requests, in seconds."""
        return percentile(self.latencies, _P95)

    @property
    def within_latency_budget(self) -> bool:
        """Whether the measured p95 latency is within budget."""
        return self.budget.allows(self.p95_latency)

    def summary(self) -> str:
        """A one-line, human-readable digest of the run."""
        return (
            f"requests={self.total_requests} served={self.served} "
            f"cache_hit_rate={self.cache_hit_rate:.2%} "
            f"p95={self.p95_latency:.4f}s budget={self.budget.p95_seconds:.4f}s "
            f"within_budget={self.within_latency_budget} "
            f"tokens_spent={self.tokens_spent} refusals={self.refusals}"
        )
