"""Cost / latency budget guarantees, measured on the real completion stack (AIA-706).

These drive a workload through the production :class:`~app.completions.CachedCompletionService` with
a deterministic clock and a latency-injecting provider, then assert the three guarantees on the
resulting :class:`~app.perf.report.BudgetReport`: a repeated request is a cache hit that costs
nothing (AC1), the p95 latency of served calls is checked against a budget -- and a regression is
caught (AC2), and a request that would breach a token quota or trip the global kill-switch is
refused, not run (AC3).
"""

from __future__ import annotations

import pytest

from app.budget.guard import TokenBudgetGuard
from app.budget.policy import BudgetPolicy, BudgetScope
from app.cache.cache import ResponseCache
from app.completions import CachedCompletionService
from app.kv.memory import InMemoryKeyValueStore
from app.llm.types import LLMMessage, LLMRequest, LLMResponse, LLMUsage, Role
from app.perf.clock import ManualClock
from app.perf.harness import BudgetHarness
from app.perf.latency import LatencyBudget


class _LatencyProvider:
    """A network-free provider that advances a clock by a fixed latency on every call."""

    def __init__(self, clock: ManualClock, *, latency: float, tokens: int = 10) -> None:
        self._clock = clock
        self._latency = latency
        self._tokens = tokens
        self.calls = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        self._clock.advance(self._latency)
        return LLMResponse(
            content=f"resp-{self.calls}",
            model="m",
            usage=LLMUsage(0, self._tokens, self._tokens),
        )


def _req(text: str) -> LLMRequest:
    return LLMRequest.of([LLMMessage(Role.USER, text)])


def _harness(
    service: CachedCompletionService,
    clock: ManualClock,
    provider: _LatencyProvider,
    budget: LatencyBudget,
) -> BudgetHarness:
    return BudgetHarness(service, clock=clock, calls=lambda: provider.calls, budget=budget)


def test_repeated_request_is_served_from_cache_for_free() -> None:
    clock = ManualClock()
    store = InMemoryKeyValueStore()
    provider = _LatencyProvider(clock, latency=0.5, tokens=10)
    service = CachedCompletionService(
        provider,
        cache=ResponseCache(store, ttl_seconds=100),
        guard=TokenBudgetGuard(store, BudgetPolicy(global_tokens=1_000)),
    )
    request = _req("plan my week")
    harness = _harness(service, clock, provider, LatencyBudget(1.0))

    report = harness.run(
        [
            (request, BudgetScope(user_id="u1")),
            (request, BudgetScope(user_id="u1")),
        ]
    )

    assert report.served == 2
    assert report.cache_hits == 1
    assert report.cache_hit_rate == 0.5
    assert provider.calls == 1  # the repeat never reached the provider
    assert report.tokens_spent == 10  # and was charged only once


def test_p95_latency_within_budget_passes() -> None:
    clock = ManualClock()
    provider = _LatencyProvider(clock, latency=0.1)
    service = CachedCompletionService(provider)  # no cache: each request is a fresh miss
    harness = _harness(service, clock, provider, LatencyBudget(0.2))

    report = harness.run([(_req(f"q{n}"), None) for n in range(20)])

    assert report.served == 20
    assert report.cache_hits == 0
    assert report.p95_latency == pytest.approx(0.1)
    assert report.within_latency_budget is True


def test_p95_latency_over_budget_is_caught() -> None:
    clock = ManualClock()
    provider = _LatencyProvider(clock, latency=0.3)
    service = CachedCompletionService(provider)
    harness = _harness(service, clock, provider, LatencyBudget(0.2))

    report = harness.run([(_req(f"q{n}"), None) for n in range(10)])

    assert report.p95_latency == pytest.approx(0.3)
    assert report.within_latency_budget is False


def test_cache_keeps_p95_low_despite_a_slow_provider() -> None:
    clock = ManualClock()
    store = InMemoryKeyValueStore()
    provider = _LatencyProvider(clock, latency=0.5, tokens=10)
    service = CachedCompletionService(provider, cache=ResponseCache(store, ttl_seconds=100))
    request = _req("same question")
    harness = _harness(service, clock, provider, LatencyBudget(0.05))

    report = harness.run([(request, None) for _ in range(20)])

    assert provider.calls == 1
    assert report.cache_hits == 19
    assert report.cache_hit_rate == 0.95
    assert report.p95_latency == pytest.approx(0.0)  # only 1 of 20 actually called the provider
    assert report.within_latency_budget is True


def test_per_user_token_quota_refuses_over_budget_requests() -> None:
    clock = ManualClock()
    store = InMemoryKeyValueStore()
    provider = _LatencyProvider(clock, latency=0.1, tokens=10)
    guard = TokenBudgetGuard(store, BudgetPolicy(per_user_tokens=15))
    service = CachedCompletionService(provider, guard=guard)
    user = BudgetScope(user_id="u1")
    harness = _harness(service, clock, provider, LatencyBudget(1.0))

    report = harness.run([(_req("a"), user), (_req("b"), user), (_req("c"), user)])

    # 0 -> charge 10 -> charge 10 (soft quota lets 10 < 15 through, reaching 20) -> 20 >= 15 refused
    assert report.served == 2
    assert report.refusals == 1
    assert report.tokens_spent == 20
    assert provider.calls == 2


def test_global_kill_switch_turns_away_other_users() -> None:
    clock = ManualClock()
    store = InMemoryKeyValueStore()
    provider = _LatencyProvider(clock, latency=0.1, tokens=10)
    guard = TokenBudgetGuard(store, BudgetPolicy(global_tokens=15))
    service = CachedCompletionService(provider, guard=guard)
    harness = _harness(service, clock, provider, LatencyBudget(1.0))

    report = harness.run(
        [
            (_req("a"), BudgetScope(user_id="u1")),
            (_req("b"), BudgetScope(user_id="u1")),  # tips global usage to 20, latching the switch
            (_req("c"), BudgetScope(user_id="u2")),  # a different user is refused
        ]
    )

    assert report.served == 2
    assert report.refusals == 1
    assert provider.calls == 2


def test_report_summary_is_descriptive() -> None:
    clock = ManualClock()
    provider = _LatencyProvider(clock, latency=0.1)
    service = CachedCompletionService(provider)
    harness = _harness(service, clock, provider, LatencyBudget(0.2))

    summary = harness.run([(_req("q"), None)]).summary()

    assert "cache_hit_rate" in summary
    assert "p95" in summary
    assert "refusals" in summary
