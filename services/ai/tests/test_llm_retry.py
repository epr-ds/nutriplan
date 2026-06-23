"""Pure tests for the retry policy and the backoff-wrapping client (AIA-102).

No network and no real sleeping: a scripted FakeLLMProvider drives the provider side
and an injected recording ``sleep`` drives the backoff side, so the retry semantics
are asserted deterministically.
"""

from app.llm.client import LLMClient
from app.llm.errors import LLMAuthError, LLMTimeoutError, LLMTransientError
from app.llm.fake import FakeLLMProvider
from app.llm.retry import RetryPolicy, compute_backoff
from app.llm.types import LLMMessage, LLMRequest, LLMResponse, Role

_REQUEST = LLMRequest.of([LLMMessage(Role.USER, "hello")])


def _ok(content: str = "hi") -> LLMResponse:
    return LLMResponse(content=content, model="fake-model")


class _Recorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def test_backoff_is_monotonic_and_capped() -> None:
    policy = RetryPolicy(base_delay=1.0, max_delay=10.0, multiplier=2.0)
    no_jitter = lambda: 1.0  # noqa: E731

    delays = [compute_backoff(attempt, policy, no_jitter) for attempt in range(6)]

    assert delays[:4] == [1.0, 2.0, 4.0, 8.0]
    assert delays[4] == 10.0 and delays[5] == 10.0  # capped at max_delay
    assert delays == sorted(delays)


def test_backoff_applies_full_jitter() -> None:
    policy = RetryPolicy(base_delay=2.0, max_delay=10.0, multiplier=2.0)

    # Jitter scales the ceiling: attempt 1 ceiling is 4.0, halved by rand()==0.5.
    assert compute_backoff(1, policy, lambda: 0.5) == 2.0


def test_succeeds_after_transient_failures() -> None:
    provider = FakeLLMProvider([LLMTransientError("429"), LLMTimeoutError("slow"), _ok("done")])
    sleep = _Recorder()
    client = LLMClient(provider, RetryPolicy(max_retries=2), sleep=sleep, rand=lambda: 1.0)

    result = client.complete(_REQUEST)

    assert result.content == "done"
    assert provider.call_count == 3  # 1 attempt + 2 retries
    assert len(sleep.delays) == 2  # slept before each retry, not after the success


def test_raises_after_exhausting_retries() -> None:
    provider = FakeLLMProvider(
        [LLMTransientError("a"), LLMTransientError("b"), LLMTransientError("c")]
    )
    sleep = _Recorder()
    client = LLMClient(provider, RetryPolicy(max_retries=2), sleep=sleep, rand=lambda: 1.0)

    try:
        client.complete(_REQUEST)
    except LLMTransientError as exc:
        assert str(exc) == "c"  # the last failure propagates
    else:  # pragma: no cover - the call must raise
        raise AssertionError("expected LLMTransientError")

    assert provider.call_count == 3
    assert len(sleep.delays) == 2


def test_does_not_retry_terminal_errors() -> None:
    provider = FakeLLMProvider([LLMAuthError("401"), _ok("unreached")])
    sleep = _Recorder()
    client = LLMClient(provider, RetryPolicy(max_retries=5), sleep=sleep, rand=lambda: 1.0)

    try:
        client.complete(_REQUEST)
    except LLMAuthError:
        pass
    else:  # pragma: no cover - the call must raise
        raise AssertionError("expected LLMAuthError")

    assert provider.call_count == 1  # terminal failure -> no retry
    assert sleep.delays == []


def test_zero_retries_attempts_once() -> None:
    provider = FakeLLMProvider([LLMTransientError("boom")])
    sleep = _Recorder()
    client = LLMClient(provider, RetryPolicy(max_retries=0), sleep=sleep, rand=lambda: 1.0)

    try:
        client.complete(_REQUEST)
    except LLMTransientError:
        pass
    else:  # pragma: no cover - the call must raise
        raise AssertionError("expected LLMTransientError")

    assert provider.call_count == 1
    assert sleep.delays == []
