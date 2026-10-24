"""An in-process notification copy template store (NTF-401).

The dev/CI twin of the real catalog. Records are held as :class:`NotificationTemplate`
instances rather than encoded JSON -- there is nothing to serialize a *copy* to, the catalog
is an in-process fact about the intents the service understands, not per-user state. That
also means an in-memory stand-in can be populated directly in tests, which is how the
"untranslated" and "missing" lint paths get exercised without standing up a file format.

Like the other in-memory adapters it is not safe across processes; production resolves copy
from a deployment that shares one process (the catalog is static per deploy, the locale is
per user and comes from the preferences store, which *is* shared).
"""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.enums import NotificationType
from app.domain.errors import DuplicateNotificationTemplateError, TemplateNotFoundError
from app.domain.repositories import NotificationTemplateStore
from app.domain.templates import Locale, NotificationTemplate


class InMemoryNotificationTemplateStore(NotificationTemplateStore):
    """A dict-backed :class:`~app.domain.repositories.NotificationTemplateStore`."""

    def __init__(self, templates: Iterable[NotificationTemplate] | None = None) -> None:
        self._templates: dict[tuple[str, Locale], NotificationTemplate] = {}
        for template in templates or ():
            self.register(template)

    def register(self, template: NotificationTemplate) -> None:
        """Add a template, rejecting a second one for the same notification type + locale."""
        key = (template.id, template.locale)
        if key in self._templates:
            raise DuplicateNotificationTemplateError(
                f"notification template '{template.id}' already registered for locale "
                f"'{template.locale.value}'"
            )
        self._templates[key] = template

    def get(self, notification_type: NotificationType, locale: Locale) -> NotificationTemplate:
        """Return the template for ``notification_type``, falling back to the default locale.

        The returned template's ``locale`` reflects what was *actually* selected (the fallback
        when the requested one is absent), so callers that log which catalog served a copy know
        what they are talking about.
        """
        exact = self._templates.get((notification_type.value, locale))
        if exact is not None:
            return exact
        fallback = self._templates.get((notification_type.value, Locale.default()))
        if fallback is not None:
            return fallback
        raise TemplateNotFoundError(
            f"no copy template for notification '{notification_type.value}' and locale "
            f"'{locale.value}'"
        )

    def ids(self) -> frozenset[str]:
        """Every notification type that has at least one registered copy template."""
        return frozenset(
            notification_type_value for notification_type_value, _locale in self._templates
        )

    def available_locales(self, notification_type: NotificationType) -> frozenset[Locale]:
        """The locales a given notification type has a copy template for."""
        return frozenset(
            locale
            for notification_type_value, locale in self._templates
            if notification_type_value == notification_type.value
        )
