"""Where templates live and how the right one is chosen for a locale (AIA-103).

The :class:`PromptCatalog` port lets callers look a template up by id + locale without
caring how the set is stored or built. :class:`InMemoryPromptCatalog` is the adapter
used in-process; it falls back to the default locale when a requested one is missing so
an unexpected language degrades to a working prompt instead of an error.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from app.prompts.errors import DuplicatePromptError, PromptNotFoundError
from app.prompts.template import PromptTemplate
from app.prompts.types import Locale


@runtime_checkable
class PromptCatalog(Protocol):
    """A read port: resolve a template for an id and locale."""

    def get(self, prompt_id: str, locale: Locale) -> PromptTemplate: ...


class InMemoryPromptCatalog:
    """A dictionary-backed :class:`PromptCatalog`, populated at startup."""

    def __init__(self, templates: Iterable[PromptTemplate] | None = None) -> None:
        self._templates: dict[tuple[str, Locale], PromptTemplate] = {}
        for template in templates or ():
            self.register(template)

    def register(self, template: PromptTemplate) -> None:
        """Add a template, rejecting a second one for the same id + locale."""
        key = (template.id, template.locale)
        if key in self._templates:
            raise DuplicatePromptError(
                f"prompt '{template.id}' already registered for locale '{template.locale.value}'"
            )
        self._templates[key] = template

    def get(self, prompt_id: str, locale: Locale) -> PromptTemplate:
        """Return the template for ``locale``, falling back to the default locale.

        The returned template's ``locale`` reflects what was *actually* selected (the
        fallback when the requested one is absent), so telemetry records the prompt that
        truly ran.
        """
        exact = self._templates.get((prompt_id, locale))
        if exact is not None:
            return exact
        fallback = self._templates.get((prompt_id, Locale.default()))
        if fallback is not None:
            return fallback
        raise PromptNotFoundError(f"no prompt '{prompt_id}' for locale '{locale.value}'")

    @property
    def ids(self) -> frozenset[str]:
        """Every registered prompt id."""
        return frozenset(prompt_id for prompt_id, _ in self._templates)

    def available_locales(self, prompt_id: str) -> frozenset[Locale]:
        """The locales a given prompt id is registered for."""
        return frozenset(loc for pid, loc in self._templates if pid == prompt_id)
