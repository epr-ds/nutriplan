"""Output content policy: block unsafe or hijacked model output before the user sees it (AIA-504).

Sanitizing the input (:mod:`app.guardrails.sanitizer`) is the first half of injection defense; the
second half is not trusting what comes back. A model that was successfully steered -- or that simply
went off the rails -- can echo the system prompt, parrot injected role tokens, or emit content that
has no place in a nutrition assistant. :class:`OutputContentPolicy` is the deterministic gate on
generated free-text (a recipe's name/steps, the recommendation's reasoning): :meth:`allow` returns
``False`` and records a :class:`PolicyViolation` when the text trips one of three checks --

* **injection echo** -- the output carries chat/model structural tokens or a forged role line, a
  sign the model is reproducing an injection rather than answering;
* **system leak** -- the output reads like the model disclosing its own hidden prompt/instructions;
* **unsafe content** -- a deliberately tight, false-positive-safe denylist of material that can
  never belong in a recipe (weapon/explosive construction, self-harm encouragement, poisoning a
  person, illicit-drug synthesis).

The policy only *decides*; the calling service applies the consequence (drop the recipe -- which
lets the AIA-503 curated fallback take over -- or blank the reasoning). Benign recipe text passes
untouched. Everything here is pure -- no LLM, no I/O -- and it backs the AIA-506 adversarial suite.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

_LOGGER = logging.getLogger("app.guardrails.policy")


class PolicyCategory(StrEnum):
    """Why a piece of model output was blocked."""

    INJECTION_ECHO = "injection_echo"
    SYSTEM_LEAK = "system_leak"
    UNSAFE_CONTENT = "unsafe_content"


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    """A single blocked output: the field it came from and the category that fired."""

    source: str
    category: PolicyCategory


@runtime_checkable
class OutputPolicyTelemetry(Protocol):
    """A write port: record that the output policy blocked a piece of model output."""

    def record(self, violation: PolicyViolation) -> None: ...


class InMemoryOutputPolicyTelemetry:
    """Collects violations in a list so tests can assert what was blocked and counted."""

    def __init__(self) -> None:
        self.violations: list[PolicyViolation] = []

    def record(self, violation: PolicyViolation) -> None:
        self.violations.append(violation)

    @property
    def count(self) -> int:
        """Total number of recorded violations."""
        return len(self.violations)

    def count_for(self, category: PolicyCategory) -> int:
        """How many recorded violations were of ``category``."""
        return sum(1 for violation in self.violations if violation.category is category)

    @property
    def categories(self) -> list[PolicyCategory]:
        """The category of each recorded violation, in record order."""
        return [violation.category for violation in self.violations]


class LoggingOutputPolicyTelemetry:
    """Emits one WARNING per block -- unsafe model output is operationally noteworthy."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or _LOGGER

    def record(self, violation: PolicyViolation) -> None:
        self._logger.warning(
            "output policy blocked content: category=%s source=%s",
            violation.category.value,
            violation.source or "?",
        )


# --- Detection patterns --------------------------------------------------------------------------
# Tight by design: a benign recipe or reasoning string must never trip these, so the only result
# of a match is unsafe/hijacked output, which is dropped.

# Chat/model structural tokens echoed back by a steered model.
_MARKER_TOKENS = re.compile(r"<\|[^|>]*\|>|\[/?INST\]|<</?SYS>>", re.IGNORECASE)
# A forged role line reproduced in the output.
_ROLE_LABEL = re.compile(r"^\s*(?:system|assistant|developer)\s*:", re.IGNORECASE | re.MULTILINE)

# The model disclosing its own hidden prompt/instructions.
_LEAK = re.compile(
    r"("
    r"(?:my|the)\s+(?:system\s+)?(?:prompt|instructions)\s+(?:are|is|say|says|state|states)\b"
    r"|here\s+(?:is|are)\s+(?:my|the)\s+(?:system\s+)?(?:prompt|instructions)"
    r"|i\s+(?:was|am)\s+(?:told|instructed|programmed)\s+to\b"
    r"|as\s+an?\s+ai\s+(?:language\s+)?model\b"
    r")",
    re.IGNORECASE,
)

# Clearly-harmful content that cannot appear in a legitimate recipe or its reasoning.
_UNSAFE = re.compile(
    r"("
    r"how\s+to\s+(?:make|build|create|construct)\s+(?:an?\s+)?"
    r"(?:bomb|explosive|weapon|gun|firearm)"
    r"|(?:commit\s+)?suicide|self[-\s]?harm|kill\s+yourself|harm\s+yourself|end\s+your\s+life"
    r"|poison(?:ing)?\s+(?:an?\s+|the\s+|your\s+|someone|somebody|him|her|them|people|family)"
    r"|how\s+to\s+(?:make|synthesize|cook|produce)\s+"
    r"(?:meth|methamphetamine|cocaine|heroin|fentanyl)"
    r")",
    re.IGNORECASE,
)


class OutputContentPolicy:
    """Decide whether a piece of generated text is safe to surface, recording every block."""

    def __init__(self, telemetry: OutputPolicyTelemetry | None = None) -> None:
        self._telemetry = telemetry or LoggingOutputPolicyTelemetry()

    def allow(self, text: str, *, source: str = "") -> bool:
        """Return ``True`` if ``text`` is clean; else record each violation and return ``False``."""
        categories = self._violations(text)
        for category in categories:
            self._telemetry.record(PolicyViolation(source=source, category=category))
        return not categories

    @staticmethod
    def _violations(text: str) -> tuple[PolicyCategory, ...]:
        """The policy categories ``text`` trips, in a stable order (empty means clean)."""
        found: list[PolicyCategory] = []
        if _MARKER_TOKENS.search(text) or _ROLE_LABEL.search(text):
            found.append(PolicyCategory.INJECTION_ECHO)
        if _LEAK.search(text):
            found.append(PolicyCategory.SYSTEM_LEAK)
        if _UNSAFE.search(text):
            found.append(PolicyCategory.UNSAFE_CONTENT)
        return tuple(found)
