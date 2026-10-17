"""Chaos tests for LLM retry resilience (AI service).

Verify retry policy and backoff behavior when LLM providers fail.
"""

from __future__ import annotations

import random

import pytest
from app.llm.retry import RetryPolicy, compute_backoff


class TestLLMRetryPolicy:
    """Verify retry policy parameters."""

    def test_default_max_retries(self) -> None:
        """Default policy retries 2 times (3 total attempts)."""
        policy = RetryPolicy()
        assert policy.max_retries == 2

    def test_default_base_delay(self) -> None:
        """Default base delay is 0.5 seconds."""
        policy = RetryPolicy()
        assert policy.base_delay == 0.5

    def test_default_max_delay(self) -> None:
        """Default max delay is 8.0 seconds."""
        policy = RetryPolicy()
        assert policy.max_delay == 8.0

    def test_default_multiplier(self) -> None:
        """Default multiplier is 2.0 (exponential)."""
        policy = RetryPolicy()
        assert policy.multiplier == 2.0


class TestLLMBackoff:
    """Verify exponential backoff computation."""

    def test_first_retry_no_delay(self) -> None:
        """First retry (attempt=0) with rand=0.0 gives 0 delay."""
        policy = RetryPolicy(base_delay=0.5)
        delay = compute_backoff(0, policy, rand=lambda: 0.0)
        assert delay == 0.0

    def test_first_retry_full_jitter(self) -> None:
        """First retry (attempt=0) with rand=1.0 gives base_delay."""
        policy = RetryPolicy(base_delay=0.5)
        delay = compute_backoff(0, policy, rand=lambda: 1.0)
        assert delay == 0.5

    def test_second_retry_doubled(self) -> None:
        """Second retry (attempt=1) with rand=1.0 gives 2x base_delay."""
        policy = RetryPolicy(base_delay=0.5, multiplier=2.0)
        delay = compute_backoff(1, policy, rand=lambda: 1.0)
        assert delay == 1.0

    def test_third_retry_quadrupled(self) -> None:
        """Third retry (attempt=2) with rand=1.0 gives 4x base_delay."""
        policy = RetryPolicy(base_delay=0.5, multiplier=2.0)
        delay = compute_backoff(2, policy, rand=lambda: 1.0)
        assert delay == 2.0

    def test_capped_at_max_delay(self) -> None:
        """Delay is capped at max_delay regardless of attempt count."""
        policy = RetryPolicy(base_delay=0.5, max_delay=2.0, multiplier=2.0)

        # Even at high attempt counts, delay should be capped
        delay = compute_backoff(10, policy, rand=lambda: 1.0)
        assert delay == 2.0

    def test_full_jitter_provides_spread(self) -> None:
        """Full jitter produces different delays for the same attempt."""
        policy = RetryPolicy(base_delay=1.0, multiplier=2.0)

        delays = [compute_backoff(2, policy, rand=random.random) for _ in range(100)]

        # All delays should be in [0, max_delay]
        for d in delays:
            assert 0.0 <= d <= policy.max_delay

        # Should have some variance (not all the same)
        assert len(set(delays)) > 1

    def test_deterministic_with_fixed_rand(self) -> None:
        """With fixed rand, backoff is deterministic."""
        policy = RetryPolicy(base_delay=1.0, multiplier=2.0)

        delays = [compute_backoff(i, policy, rand=lambda: 0.5) for i in range(5)]

        # Ceiling is min(8.0, 2**i); scaled by rand=0.5: 0.5, 1.0, 2.0, 4.0, 4.0
        assert delays[0] == 0.5
        assert delays[1] == 1.0
        assert delays[2] == 2.0
        assert delays[3] == 4.0
        assert delays[4] == 4.0


class TestLLMChaosScenario:
    """Simulate LLM provider failure scenarios."""

    def test_provider_fails_then_recovers(self) -> None:
        """A provider that fails 2 times then recovers."""
        call_count = [0]

        def failing_call():
            call_count[0] += 1
            if call_count[0] <= 2:
                raise Exception("LLM timeout")
            return {"content": "recovered"}

        policy = RetryPolicy(max_retries=3, base_delay=0.1, max_delay=0.5)
        max_delay = policy.max_delay

        # Simulate retry loop
        result = None
        for attempt in range(policy.max_retries + 1):
            try:
                result = failing_call()
                break
            except Exception:
                if attempt < policy.max_retries:
                    delay = compute_backoff(attempt, policy, rand=lambda: 1.0)
                    # In real code: time.sleep(min(delay, max_delay))
                    delay = min(delay, max_delay)
                else:
                    raise

        assert result is not None
        assert call_count[0] == 3  # 2 failures + 1 success

    def test_provider_fails_all_retries(self) -> None:
        """When all retries fail, the exception propagates."""
        call_count = [0]

        def always_fails():
            call_count[0] += 1
            raise Exception("LLM timeout")

        policy = RetryPolicy(max_retries=2, base_delay=0.1, max_delay=0.5)
        max_delay = policy.max_delay

        with pytest.raises(Exception, match="LLM timeout"):
            for attempt in range(policy.max_retries + 1):
                try:
                    always_fails()
                except Exception:
                    if attempt < policy.max_retries:
                        delay = compute_backoff(attempt, policy, rand=lambda: 1.0)
                        delay = min(delay, max_delay)
                    else:
                        raise

        assert call_count[0] == 3  # 1 initial + 2 retries

    def test_jitter_prevents_thundering_herd(self) -> None:
        """Different clients with jitter should have different delays."""
        policy = RetryPolicy(base_delay=1.0, multiplier=2.0)

        # Simulate 10 clients retrying at attempt=2
        client_delays = []
        for client_id in range(10):
            # Each client gets a different random seed
            rand_val = (client_id + 1) / 11.0  # Different values per client
            delay = compute_backoff(2, policy, rand=lambda: rand_val)
            client_delays.append(delay)

        # Should have spread (not all the same)
        unique_delays = len(set(client_delays))
        assert unique_delays > 1  # Jitter provides spread
