"""AIA-805: LLM usage/cost metrics for cost & usage dashboards."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.llm.client import LLMClient
from app.llm.fake import FakeLLMProvider
from app.llm.types import LLMMessage, LLMRequest, LLMResponse, LLMUsage, Role
from app.main import app

client = TestClient(app)

MODEL = "fake-model"


def _scrape(client: TestClient) -> dict[str, float]:
    """Parse the Prometheus text exposition into ``{series: value}``."""
    values: dict[str, float] = {}
    for line in client.get("/metrics").text.splitlines():
        if not line or line.startswith("#"):
            continue
        series, _, raw = line.rpartition(" ")
        try:
            values[series] = float(raw)
        except ValueError:
            continue
    return values


def _series(name: str, **labels: str) -> str:
    if not labels:
        return name
    inner = ",".join(f'{key}="{value}"' for key, value in labels.items())
    return f"{name}{{{inner}}}"


def _value(client: TestClient, name: str, **labels: str) -> float:
    return _scrape(client).get(_series(name, **labels), 0.0)


def test_llm_usage_metric_is_exposed_on_metrics_endpoint() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "ai_llm_usage_total" in response.text


def test_llm_usage_is_counted_per_completion() -> None:
    provider = FakeLLMProvider(
        script=[
            LLMResponse(
                content="ok",
                model=MODEL,
                usage=LLMUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
            ),
            LLMResponse(
                content="ok",
                model=MODEL,
                usage=LLMUsage(prompt_tokens=4, completion_tokens=1, total_tokens=5),
            ),
        ]
    )
    llm = LLMClient(provider)
    before = _value(client, "ai_llm_usage_total", model=MODEL)
    first = llm.complete(LLMRequest.of([LLMMessage(Role.USER, "hello")]))
    second = llm.complete(LLMRequest.of([LLMMessage(Role.USER, "world")]))
    assert first.content == "ok"
    assert second.content == "ok"
    assert _value(client, "ai_llm_usage_total", model=MODEL) == before + 10


def test_llm_usage_without_token_counts_is_not_recorded() -> None:
    llm = LLMClient(FakeLLMProvider(script=[LLMResponse(content="ok", model=MODEL)]))
    before = _value(client, "ai_llm_usage_total", model=MODEL)
    llm.complete(LLMRequest.of([LLMMessage(Role.USER, "hello")]))
    assert _value(client, "ai_llm_usage_total", model=MODEL) == before
