"""Recording which prompt version ran on each call (AIA-103, AC2).

The :class:`PromptTelemetry` port is invoked by the renderer on every render with the
:class:`~app.prompts.types.PromptRef` that was used, so downstream cost/quality work can
attribute completions to an exact prompt version. Two adapters ship: an in-memory one
for tests and a logging one for runtime. Only identifiers are recorded -- never the
rendered text or variable values, which may contain user data.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from app.prompts.types import PromptRef

_LOGGER = logging.getLogger("app.prompts")


@runtime_checkable
class PromptTelemetry(Protocol):
    """A write port: record that a prompt version was used."""

    def record(self, ref: PromptRef) -> None: ...


class InMemoryPromptTelemetry:
    """Collects refs in a list so tests can assert what was recorded."""

    def __init__(self) -> None:
        self.records: list[PromptRef] = []

    def record(self, ref: PromptRef) -> None:
        self.records.append(ref)

    @property
    def versions(self) -> list[str]:
        """The version of each recorded ref, in call order."""
        return [ref.version for ref in self.records]


class LoggingPromptTelemetry:
    """Emits one structured log line per render (id/version/locale only)."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or _LOGGER

    def record(self, ref: PromptRef) -> None:
        self._logger.info(
            "prompt rendered: id=%s version=%s locale=%s",
            ref.id,
            ref.version,
            ref.locale.value,
        )
