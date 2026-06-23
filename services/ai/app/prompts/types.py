"""Immutable value objects for prompt templating (AIA-103).

These sit one layer above :mod:`app.llm.types`: a rendered prompt is ultimately turned
into an :class:`~app.llm.types.LLMRequest`, but the prompt layer also tracks *which*
template (id + version + locale) produced it so that information can be recorded as
telemetry on every call.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.llm.types import LLMMessage, LLMRequest
from app.prompts.errors import UnknownLocaleError


class Locale(StrEnum):
    """A supported user language. Prompts ship in every member (es/en for AIA-103)."""

    EN = "en"
    ES = "es"

    @classmethod
    def default(cls) -> Locale:
        """The locale used as the fallback when a requested one is unavailable."""
        return cls.EN

    @classmethod
    def parse(cls, value: Locale | str, *, default: Locale | None = None) -> Locale:
        """Map an arbitrary language tag to a supported locale.

        Accepts already-typed members and BCP-47-ish strings (``"es"``, ``"es-MX"``,
        ``"en_US"``) by matching the primary subtag, case-insensitively. Unsupported
        tags return ``default`` when one is given, otherwise raise
        :class:`~app.prompts.errors.UnknownLocaleError` so a caller that wants strict
        behaviour can opt into it.
        """
        if isinstance(value, cls):
            return value
        primary = str(value).strip().lower().replace("_", "-").split("-", 1)[0]
        for member in cls:
            if member.value == primary:
                return member
        if default is not None:
            return default
        raise UnknownLocaleError(f"unsupported locale: {value!r}")


@dataclass(frozen=True, slots=True)
class PromptRef:
    """Identifies the exact template that produced a prompt, for telemetry/audit."""

    id: str
    version: str
    locale: Locale

    def __str__(self) -> str:
        return f"{self.id}@{self.version} ({self.locale.value})"


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """A fully substituted prompt plus the reference to the template behind it."""

    ref: PromptRef
    messages: tuple[LLMMessage, ...]

    def to_request(
        self,
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMRequest:
        """Bridge to the LLM layer: wrap the rendered messages in an ``LLMRequest``."""
        return LLMRequest.of(
            self.messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
