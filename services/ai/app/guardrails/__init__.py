"""Prompt-injection / unsafe-content defense for the AI service (AIA-504).

Two deterministic, pure guards make the AI "resist abuse" by construction, independent of any single
endpoint:

* :mod:`app.guardrails.sanitizer` -- :class:`PromptSanitizer` scrubs injected instructions, role
  delimiters, and control characters out of user free-text *before* it is templated into a prompt,
  so user input stays data rather than instructions (input defense, AC1).
* :mod:`app.guardrails.policy` -- :class:`OutputContentPolicy` blocks hijacked or unsafe model
  output *before* the user sees it, letting the service drop the offending recipe (which hands off
  to the AIA-503 curated fallback) or blank the reasoning (output defense, AC2).

Both publish through telemetry ports so attempts are logged and counted, and both back the AIA-506
adversarial guardrail suite. Nothing here imports an LLM or does I/O.
"""

from app.guardrails.policy import (
    InMemoryOutputPolicyTelemetry,
    LoggingOutputPolicyTelemetry,
    OutputContentPolicy,
    OutputPolicyTelemetry,
    PolicyCategory,
    PolicyViolation,
)
from app.guardrails.sanitizer import (
    InjectionCategory,
    InMemorySanitizationTelemetry,
    LoggingSanitizationTelemetry,
    PromptSanitizer,
    SanitizationEvent,
    SanitizationTelemetry,
)

__all__ = [
    "InMemoryOutputPolicyTelemetry",
    "InMemorySanitizationTelemetry",
    "InjectionCategory",
    "LoggingOutputPolicyTelemetry",
    "LoggingSanitizationTelemetry",
    "OutputContentPolicy",
    "OutputPolicyTelemetry",
    "PolicyCategory",
    "PolicyViolation",
    "PromptSanitizer",
    "SanitizationEvent",
    "SanitizationTelemetry",
]
