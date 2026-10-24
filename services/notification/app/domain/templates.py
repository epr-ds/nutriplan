"""The notification-copy templating vocabulary (NTF-401).

A notification does not arrive with copy of its own; it arrives with *intent*, and the copy
the user reads is the translation of that intent into the user's language. NTF-401 owns that
translation, and this module is where the vocabulary lives.

Two value objects do the work.

:class:`Locale` is the supported set of user-facing languages. It is a small closed set --
``es`` and ``en`` -- and carries the rules the rest of the story depends on: the Spanish
catalog is the service's default (the product's base market), the English catalog is the
secondary fallback, and an unsupported tag resolves to the default rather than failing the
send. Resolving per user happens at the preference layer (NTF-104); this module only knows
how to name the languages that exist.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from app.domain.errors import MissingTemplateVariableError, UnknownLocaleError

_PLACEHOLDER = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
"""``$name`` placeholders. Camel-case payload keys (``mealName``) are legal identifiers, which
the ``str.Template`` syntax would not have accepted, so the substitution is done here."""


class Locale(StrEnum):
    """A user-facing language that notification copy is available in."""

    EN = "en"
    ES = "es"

    @classmethod
    def default(cls) -> Locale:
        """The locale used when a user has not chosen one -- and the fallback for missing keys."""
        return cls.ES

    @classmethod
    def parse(cls, value: Locale | str, *, default: Locale | None = None) -> Locale:
        """Map a language tag onto a supported locale.

        Accepts already-typed members and BCP-47-ish strings (``"es"``, ``"es-MX"``, ``"EN_US"``)
        by matching the primary subtag, case-insensitively. An unsupported tag returns
        ``default`` when one is given, otherwise raises :class:`UnknownLocaleError`, so callers
        that want strict behaviour can opt into it.
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
class RenderedNotification:
    """A fully substituted notification: one title and one body, in the user's language."""

    title: str
    body: str


@dataclass(frozen=True, slots=True)
class NotificationTemplate:
    """One versioned, localized piece of notification copy: a title and a body.

    The bodies are written with ``$placeholders`` naming the notification payload fields the
    copy speaks to (``$orderId``, ``$mealName``, ``$deepLink`` ...). The placeholders are the
    contract between catalog and producer: the catalog declares what it needs, the render
    fills it, and a copy that references a field the producer never sent is a bug -- it fails
    loudly through :class:`MissingTemplateVariableError` rather than quietly rendering ``$...``
    text into a push that reads wrong.

    ``version`` is a date-stamp shared by both locales of one template id; bump it whenever the
    wording changes so telemetry and replays can tell templates from different revisions apart.
    """

    id: str
    version: str
    locale: Locale
    title: str
    body: str

    def required_variables(self) -> frozenset[str]:
        """The set of placeholder names ``render`` must be given a value for."""
        names: set[str] = set()
        for text in (self.title, self.body):
            names.update(_PLACEHOLDER.findall(text))
        return frozenset(names)

    def render(self, variables: Mapping[str, object] | None = None) -> RenderedNotification:
        """Substitute the payload fields into this template's ``$placeholders``.

        Every declared placeholder must have a value (extra keys are ignored); a gap is a bug,
        so it raises :class:`MissingTemplateVariableError` listing the missing names rather
        than leaving placeholder text in the copy. Values are stringified so callers can pass
        numbers and booleans straight from a payload.
        """
        values = {str(key): str(value) for key, value in (variables or {}).items()}
        missing = self.required_variables() - values.keys()
        if missing:
            raise MissingTemplateVariableError(
                f"notification template '{self.id}' is missing variable(s): "
                f"{', '.join(sorted(missing))}"
            )

        def substitute(match: re.Match[str]) -> str:
            return values.get(match.group(1), "")

        return RenderedNotification(
            title=_PLACEHOLDER.sub(substitute, self.title),
            body=_PLACEHOLDER.sub(substitute, self.body),
        )
