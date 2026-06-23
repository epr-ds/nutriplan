"""The application service that ties templating, localization, and telemetry together.

Callers hand it a prompt id, a locale, and variables; it resolves the right localized
template from the catalog, renders it, and records the version that ran. The catalog and
telemetry are injected (constructor DI) so tests use in-memory doubles and production
wires the shipped catalog plus a logging recorder.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.prompts.catalog import PromptCatalog
from app.prompts.telemetry import PromptTelemetry
from app.prompts.types import Locale, RenderedPrompt


class PromptRenderer:
    """Resolve + render a versioned, localized prompt, recording the version used."""

    def __init__(
        self,
        catalog: PromptCatalog,
        *,
        telemetry: PromptTelemetry | None = None,
    ) -> None:
        self._catalog = catalog
        self._telemetry = telemetry

    def render(
        self,
        prompt_id: str,
        *,
        locale: Locale | str = Locale.EN,
        variables: Mapping[str, object] | None = None,
    ) -> RenderedPrompt:
        """Render ``prompt_id`` for ``locale`` and record the prompt version (AC2).

        ``locale`` may be a :class:`Locale` or any language tag; unsupported tags fall
        back to the default locale rather than failing, matching the catalog's own
        locale fallback.
        """
        resolved = Locale.parse(locale, default=Locale.default())
        template = self._catalog.get(prompt_id, resolved)
        rendered = template.render(variables)
        if self._telemetry is not None:
            self._telemetry.record(rendered.ref)
        return rendered
