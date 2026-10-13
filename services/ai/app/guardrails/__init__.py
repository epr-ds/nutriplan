"""Guardrails for the AI service: it resists abuse (AIA-504) and stays compliant (AIA-505).

Deterministic, pure guards make the AI safe by construction, independent of any single endpoint:

* :mod:`app.guardrails.sanitizer` -- :class:`PromptSanitizer` scrubs injected instructions, role
  delimiters, and control characters out of user free-text *before* it is templated into a prompt,
  so user input stays data rather than instructions (input defense, AIA-504 AC1).
* :mod:`app.guardrails.policy` -- :class:`OutputContentPolicy` blocks hijacked or unsafe model
  output *before* the user sees it, letting the service drop the offending recipe (which hands off
  to the AIA-503 curated fallback) or blank the reasoning (output defense, AIA-504 AC2).
* :mod:`app.guardrails.compliance` -- :class:`ResponsePostProcessor` disclaims every AI response and
  strips diagnostic/medical claims from its generated free-text (AIA-505).

All publish through telemetry ports so attempts are logged and counted, and all back the AIA-506
adversarial guardrail suite. Nothing here imports an LLM or does I/O.
"""

from app.guardrails.compliance import (
    InMemoryMedicalClaimTelemetry,
    LoggingMedicalClaimTelemetry,
    MedicalClaimCategory,
    MedicalClaimEvent,
    MedicalClaimTelemetry,
    ResponsePostProcessor,
)
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
    "InMemoryMedicalClaimTelemetry",
    "InMemoryOutputPolicyTelemetry",
    "InMemorySanitizationTelemetry",
    "InjectionCategory",
    "LoggingMedicalClaimTelemetry",
    "LoggingOutputPolicyTelemetry",
    "LoggingSanitizationTelemetry",
    "MedicalClaimCategory",
    "MedicalClaimEvent",
    "MedicalClaimTelemetry",
    "OutputContentPolicy",
    "OutputPolicyTelemetry",
    "PolicyCategory",
    "PolicyViolation",
    "PromptSanitizer",
    "ResponsePostProcessor",
    "SanitizationEvent",
    "SanitizationTelemetry",
]
