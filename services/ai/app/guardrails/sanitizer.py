"""Prompt-injection input defense: neutralize hijack attempts in user free-text (AIA-504).

Every recommendation and analysis prompt is built by substituting user-supplied free-text
(allergies, excluded ingredients, constraints, a meal description...) into a templated system/user
prompt. That substitution is the classic prompt-injection surface: a user can try to smuggle
*instructions* ("ignore the previous instructions and...", a fake ``system:`` turn, a
``<|im_start|>`` token) into a field that is meant to carry *data*. :class:`PromptSanitizer` is the
deterministic pre-prompt scrub that keeps user input as data: it redacts injected role delimiters /
model control tokens, known instruction-override phrases, and system-prompt-exfiltration phrases,
strips raw control characters, collapses runaway whitespace, and caps length. Benign food text
passes through untouched -- "peanuts", "no cilantro", "Oatmeal with banana" are not instructions --
so the safety/bounds guards downstream see exactly what the user meant. Every redaction is recorded
through a :class:`SanitizationTelemetry` port so injection attempts are logged and counted.
Everything here is pure -- no LLM, no I/O -- so it is fully unit-testable and reproducible, and it
backs the AIA-506 adversarial guardrail suite.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

_LOGGER = logging.getLogger("app.guardrails.sanitizer")

# What an injected span is replaced with: a visible, inert marker (never a real instruction).
REDACTION = "[removed]"
# Defense against prompt-stuffing: no single user field is allowed to dominate the prompt.
DEFAULT_MAX_LENGTH = 2000


class InjectionCategory(StrEnum):
    """Why a span was redacted (or the input was scrubbed)."""

    INSTRUCTION_OVERRIDE = "instruction_override"
    ROLE_HIJACK = "role_hijack"
    SYSTEM_LEAK = "system_leak"
    CONTROL = "control"


@dataclass(frozen=True, slots=True)
class SanitizationEvent:
    """A single scrub: the field it came from and the category that fired."""

    source: str
    category: InjectionCategory


@runtime_checkable
class SanitizationTelemetry(Protocol):
    """A write port: record that the sanitizer neutralized something in user input."""

    def record(self, event: SanitizationEvent) -> None: ...


class InMemorySanitizationTelemetry:
    """Collects events in a list so tests can assert what was scrubbed and counted."""

    def __init__(self) -> None:
        self.events: list[SanitizationEvent] = []

    def record(self, event: SanitizationEvent) -> None:
        self.events.append(event)

    @property
    def count(self) -> int:
        """Total number of recorded scrub events."""
        return len(self.events)

    def count_for(self, category: InjectionCategory) -> int:
        """How many recorded events were of ``category``."""
        return sum(1 for event in self.events if event.category is category)

    @property
    def categories(self) -> list[InjectionCategory]:
        """The category of each recorded event, in record order."""
        return [event.category for event in self.events]


class LoggingSanitizationTelemetry:
    """Emits one WARNING per scrub -- a sanitized input is an attempted abuse worth noting."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or _LOGGER

    def record(self, event: SanitizationEvent) -> None:
        self._logger.warning(
            "prompt input sanitized: category=%s source=%s",
            event.category.value,
            event.source or "?",
        )


# --- Detection patterns --------------------------------------------------------------------------
# Each is intentionally narrow: it must catch instruction-shaped injections without touching the
# food vocabulary users legitimately type. Matched spans are replaced with the inert REDACTION text.

# Raw control characters (excluding tab/newline/carriage-return, which whitespace-collapse handles).
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Chat/model structural tokens and role delimiters used to forge a new turn.
_ROLE_TOKENS = re.compile(
    r"<\|[^|>]*\|>"  # <|im_start|>, <|im_end|>, <|system|> ...
    r"|\[/?INST\]"  # [INST] / [/INST]
    r"|<</?SYS>>"  # <<SYS>> / <</SYS>>
    r"|</?s>",  # <s> / </s>
    re.IGNORECASE,
)
# A line that opens a forged system/assistant/developer turn.
_ROLE_LABELS = re.compile(r"^\s*(?:system|assistant|developer)\s*:", re.IGNORECASE | re.MULTILINE)

# "Forget what you were told, do this instead" -- the instruction-override family.
_OVERRIDE = re.compile(
    r"("
    r"ignore(?:\s+all|\s+any|\s+the)?\s+(?:previous|prior|preceding|above|earlier)\s+"
    r"(?:instruction|prompt|message|rule|direction|context)s?"
    r"|disregard(?:\s+all|\s+the)?\s+(?:previous|prior|preceding|above|earlier)\s+"
    r"(?:instruction|prompt|message|rule|context)s?"
    r"|forget\s+(?:all\s+|everything\s+|your\s+|the\s+)?(?:previous\s+|prior\s+|above\s+)?"
    r"(?:instruction|prompt|rule|context|everything)s?"
    r"|override\s+(?:the\s+|your\s+)?(?:previous\s+|system\s+|above\s+)?(?:instruction|prompt|rule)s?"
    r"|new\s+instructions?\s*:"
    r"|you\s+are\s+now\b"
    r"|from\s+now\s+on,?\s+you\s+(?:are|will|must|should)\b"
    r"|act\s+as\s+(?:an?\s+)?"
    r"(?:dietitian|nutritionist|assistant|ai|chatbot|model|developer|system|dan|jailbreak)\b"
    r"|pretend\s+(?:to\s+be|you\s+are|that\s+you\s+are)\b"
    r")",
    re.IGNORECASE,
)

# "Tell me your hidden instructions" -- the system-prompt-exfiltration family.
_SYSTEM_LEAK = re.compile(
    r"("
    r"(?:reveal|repeat|print|show|display|output|share|reproduce|give\s+me|tell\s+me)\s+"
    r"(?:me\s+)?(?:your\s+|the\s+)?(?:system\s+)?"
    r"(?:prompt|instructions|rules|configuration|guidelines|directives)"
    r"|repeat\s+(?:the\s+|everything\s+)?(?:text|words|content|instruction|message)s?\s+"
    r"(?:above|before|preceding|earlier)"
    r"|what\s+(?:are|were|is)\s+your\s+(?:system\s+)?(?:prompt|instructions|rules|guidelines)"
    r")",
    re.IGNORECASE,
)

_WHITESPACE = re.compile(r"\s+")

# Stable order in which fired categories are recorded, regardless of detection order.
_RECORD_ORDER: tuple[InjectionCategory, ...] = (
    InjectionCategory.INSTRUCTION_OVERRIDE,
    InjectionCategory.ROLE_HIJACK,
    InjectionCategory.SYSTEM_LEAK,
    InjectionCategory.CONTROL,
)


def _has_content(value: str) -> bool:
    """Whether a sanitized value still carries real text once redaction markers are removed."""
    return bool(value.replace(REDACTION, "").strip())


class PromptSanitizer:
    """Scrub injection attempts out of user free-text, keeping it as data, not instructions."""

    def __init__(
        self,
        telemetry: SanitizationTelemetry | None = None,
        *,
        max_length: int = DEFAULT_MAX_LENGTH,
    ) -> None:
        self._telemetry = telemetry or LoggingSanitizationTelemetry()
        self._max_length = max_length

    def sanitize(self, text: str, *, source: str = "") -> str:
        """Return ``text`` with injected instructions redacted, recording each category fired."""
        fired: set[InjectionCategory] = set()

        cleaned, control_hits = _CONTROL_CHARS.subn(" ", text)
        if control_hits:
            fired.add(InjectionCategory.CONTROL)

        cleaned, token_hits = _ROLE_TOKENS.subn(REDACTION, cleaned)
        cleaned, label_hits = _ROLE_LABELS.subn(REDACTION, cleaned)
        if token_hits or label_hits:
            fired.add(InjectionCategory.ROLE_HIJACK)

        cleaned, override_hits = _OVERRIDE.subn(REDACTION, cleaned)
        if override_hits:
            fired.add(InjectionCategory.INSTRUCTION_OVERRIDE)

        cleaned, leak_hits = _SYSTEM_LEAK.subn(REDACTION, cleaned)
        if leak_hits:
            fired.add(InjectionCategory.SYSTEM_LEAK)

        cleaned = _WHITESPACE.sub(" ", cleaned).strip()
        if len(cleaned) > self._max_length:
            cleaned = cleaned[: self._max_length].rstrip()

        for category in _RECORD_ORDER:
            if category in fired:
                self._telemetry.record(SanitizationEvent(source=source, category=category))
        return cleaned

    def sanitize_all(self, values: Iterable[str], *, source: str = "") -> tuple[str, ...]:
        """Sanitize each value, dropping any that held nothing but an injection attempt."""
        sanitized = (self.sanitize(value, source=source) for value in values)
        return tuple(value for value in sanitized if _has_content(value))
