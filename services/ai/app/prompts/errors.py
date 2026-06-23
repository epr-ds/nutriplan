"""Exception hierarchy for prompt templating (AIA-103).

Kept separate from :mod:`app.llm.errors`: those describe failures *talking to* a
provider, while these describe failures *building* the prompt before any call is made
(an unknown template, a missing template variable, a misconfigured catalog). The
endpoint layer maps both onto its own HTTP responses in later slices.
"""

from __future__ import annotations


class PromptError(Exception):
    """Base class for every prompt-construction failure."""


class PromptNotFoundError(PromptError):
    """No template is registered for the requested id (and locale fallback)."""


class MissingPromptVariableError(PromptError):
    """``render`` was called without a value for one or more template variables."""


class DuplicatePromptError(PromptError):
    """A template was registered twice for the same id + locale."""


class UnknownLocaleError(PromptError):
    """A locale string could not be mapped to a supported :class:`~app.prompts.types.Locale`."""
