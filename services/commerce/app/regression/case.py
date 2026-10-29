"""Value objects for the commerce regression corpus (HRD-905 release-gate follow-up).

A :class:`CommerceCase` is one release-gate scenario: a journey (order-creation, payment,
order-lifecycle, slot-booking, grocery, pricing, webhook), the severity it gates release on, the
tags it runs under, and the expected outcome. ``input`` carries the scenario's request payload and
``expected`` the outcome the production use cases must reach.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CommerceCase:
    """One golden scenario the commerce release gate must satisfy on every run."""

    name: str
    journey: str
    severity: str = "P2"
    tags: tuple[str, ...] = ()
    input: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CommerceCaseOutcome:
    """The verifier's verdict for one :class:`CommerceCase`."""

    name: str
    failures: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Whether the case passed with no failures."""
        return not self.failures
