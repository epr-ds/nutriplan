"""An in-memory LLM provider for tests and offline development.

It records every request and can be scripted with a sequence of responses and/or
exceptions, which lets the retry/backoff client be tested deterministically (e.g.
"fail transiently twice, then succeed") with no network. When the script is empty it
echoes the last user message, so endpoint tests in later slices have a stand-in that
never calls a real provider.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.llm.types import LLMRequest, LLMResponse


class FakeLLMProvider:
    """A scripted, network-free :class:`~app.llm.provider.LLMProvider`."""

    name = "fake"

    def __init__(
        self,
        script: Sequence[LLMResponse | Exception] | None = None,
        *,
        model: str = "fake-model",
    ) -> None:
        self._script: list[LLMResponse | Exception] = list(script or [])
        self._model = model
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self._script:
            item = self._script.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        last = request.messages[-1].content if request.messages else ""
        return LLMResponse(content=f"echo: {last}", model=request.model or self._model)

    @property
    def call_count(self) -> int:
        return len(self.calls)
