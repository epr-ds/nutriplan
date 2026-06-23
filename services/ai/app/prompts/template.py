"""The prompt template itself: text with named variables, rendered to chat messages.

A template carries an id + version + locale (so the output is attributable) and a
system and user body written with ``string.Template`` ``$variable`` placeholders. The
``$`` syntax is used over ``str.format`` because prompts routinely contain literal
braces (JSON examples, code), which ``str.format`` would choke on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from string import Template

from app.llm.types import LLMMessage, Role
from app.prompts.errors import MissingPromptVariableError
from app.prompts.types import Locale, PromptRef, RenderedPrompt


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """A versioned, localized system/user prompt pair.

    ``system`` is optional: when blank it is omitted from the rendered messages, so the
    same type covers both persona-led prompts and bare user instructions.
    """

    id: str
    version: str
    locale: Locale
    user: str
    system: str = ""

    @property
    def ref(self) -> PromptRef:
        """The telemetry reference for this template (id + version + locale)."""
        return PromptRef(id=self.id, version=self.version, locale=self.locale)

    def required_variables(self) -> frozenset[str]:
        """The set of ``$variable`` names that ``render`` must be given a value for."""
        names: set[str] = set()
        for text in (self.system, self.user):
            if text:
                names.update(Template(text).get_identifiers())
        return frozenset(names)

    def render(self, variables: Mapping[str, object] | None = None) -> RenderedPrompt:
        """Substitute ``variables`` into the template and return chat messages.

        Every declared placeholder must have a value (extra keys are ignored); a gap is
        a programming error, so it raises :class:`MissingPromptVariableError` listing the
        missing names rather than silently leaving ``$placeholder`` text in the prompt.
        Values are stringified so callers can pass numbers and the like directly.
        """
        values = {key: str(value) for key, value in (variables or {}).items()}
        missing = self.required_variables() - values.keys()
        if missing:
            raise MissingPromptVariableError(
                f"prompt '{self.id}' is missing variable(s): {', '.join(sorted(missing))}"
            )

        messages: list[LLMMessage] = []
        if self.system:
            system_text = Template(self.system).substitute(values).strip()
            if system_text:
                messages.append(LLMMessage(Role.SYSTEM, system_text))
        messages.append(LLMMessage(Role.USER, Template(self.user).substitute(values)))
        return RenderedPrompt(ref=self.ref, messages=tuple(messages))
