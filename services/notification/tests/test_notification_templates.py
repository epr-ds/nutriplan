"""NTF-401: notification copy templating, localization, and catalog lint.

The copy engine answers one question: what should this notification say, in the user's
language? The engine takes a notification type + locale + payload variables and renders the
title/body the user will actually read; the catalog is what ships those words.

These tests pin the behaviours the story exists for.

1. **Render** -- a type's copy for a locale, placeholders filled from the payload, missing
   variables rejected rather than guessed at, unsupported locales falling back to the default.
2. **Catalog** -- every type the delivery can render is shipped in the default language and the
   secondary one, with a shared version per type, and the secondary locale really is a
   translation rather than the default copy wearing a different hat.
3. **Lint** -- the shipped catalog covers the delivery's vocabulary at all, which is the gate
   that turns "we forgot a notification type" into a failing test instead of a push that reads
   the type token.
"""

from __future__ import annotations

import re

import pytest

from app.adapters.in_memory_notification_template_store import InMemoryNotificationTemplateStore
from app.application.templates import (
    DEFAULT_NOTIFICATION_TEMPLATES,
    NOTIFICATION_COPY_VERSION,
    NotificationTemplateService,
)
from app.domain.enums import NotificationType
from app.domain.errors import (
    DuplicateNotificationTemplateError,
    MissingTemplateVariableError,
    TemplateNotFoundError,
)
from app.domain.templates import Locale, NotificationTemplate

_PLACEHOLDER = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
_COPY_VERSION = NOTIFICATION_COPY_VERSION


def _bare(text: str) -> str:
    """A copy's text with its placeholders emptied, so two copies can be compared by wording."""
    return _PLACEHOLDER.sub("", text).strip()


def _service() -> NotificationTemplateService:
    return NotificationTemplateService(
        InMemoryNotificationTemplateStore(DEFAULT_NOTIFICATION_TEMPLATES)
    )


def _render(
    notification_type: NotificationType, *, locale: Locale | str, variables: dict[str, str]
) -> str:
    return _service().render(notification_type, locale=locale, variables=variables).title


class TestRender:
    def test_the_default_locale_is_the_spanish_catalog(self) -> None:
        """The service ships Spanish as its default (NTF-401); English is the secondary."""
        rendered = _service().render(
            NotificationType.MEAL_REMINDER,
            variables={"mealName": "Oatmeal", "deepLink": "nutriplan://meal/meal-1"},
        )

        assert rendered.title == "Recordatorio de comida"
        assert "Oatmeal" in rendered.body

    def test_the_users_locale_selects_the_copy(self) -> None:
        rendered = _service().render(
            NotificationType.ORDER_IN_TRANSIT,
            locale=Locale.EN,
            variables={"orderId": "o-1", "deepLink": "nutriplan://order/o-1"},
        )

        assert rendered.title == "On the way"
        assert "o-1" in rendered.body

    def test_a_missing_placeholder_is_a_bug_rather_than_a_guess(self) -> None:
        with pytest.raises(MissingTemplateVariableError) as exc:
            _service().render(NotificationType.ORDER_IN_TRANSIT, variables={"orderId": "o-1"})

        assert "deepLink" in str(exc.value)

    def test_an_unsupported_locale_falls_back_to_the_default(self) -> None:
        rendered = _service().render(
            NotificationType.ORDER_CONFIRMED,
            locale="fr",
            variables={"orderId": "o-1", "deepLink": "nutriplan://order/o-1"},
        )

        assert rendered.title == "Pedido confirmado"

    def test_a_type_without_a_template_for_the_locale_is_not_found(self) -> None:
        service = NotificationTemplateService(
            InMemoryNotificationTemplateStore(
                [
                    NotificationTemplate(
                        id="only_es",
                        version="v1",
                        locale=Locale.ES,
                        title="Solo",
                        body="Solo para $who",
                    )
                ]
            )
        )

        with pytest.raises(TemplateNotFoundError):
            service.render(NotificationType.MEAL_REMINDER, locale=Locale.EN, variables={"who": "x"})


class TestTheCatalog:
    def test_every_type_the_delivery_can_render_is_shipped_in_both_locales(self) -> None:
        catalog = InMemoryNotificationTemplateStore(DEFAULT_NOTIFICATION_TEMPLATES)

        for notification_type in NotificationType:
            assert catalog.available_locales(notification_type) == frozenset({Locale.ES, Locale.EN})

    def test_the_locales_of_a_type_share_a_version(self) -> None:
        catalog = InMemoryNotificationTemplateStore(DEFAULT_NOTIFICATION_TEMPLATES)

        en = catalog.get(NotificationType.ORDER_IN_TRANSIT, Locale.EN)
        es = catalog.get(NotificationType.ORDER_IN_TRANSIT, Locale.ES)

        assert en.version == es.version == _COPY_VERSION

    def test_the_secondary_locale_is_a_translation_and_not_the_default_copy(self) -> None:
        """Lint: a secondary catalog repeating the default wording is untranslated copy."""
        by_id: dict[str, dict[Locale, NotificationTemplate]] = {}
        for template in DEFAULT_NOTIFICATION_TEMPLATES:
            by_id.setdefault(template.id, {})[template.locale] = template

        for notification_type in NotificationType:
            pair = by_id[notification_type.value]
            assert _bare(pair[Locale.EN].body) != _bare(pair[Locale.ES].body)
            assert _bare(pair[Locale.EN].title) != _bare(pair[Locale.ES].title)

    def test_a_second_template_for_the_same_type_and_locale_is_refused(self) -> None:
        template = NotificationTemplate(
            id="order_in_transit",
            version=_COPY_VERSION,
            locale=Locale.EN,
            title="Dup",
            body="Dup $orderId",
        )
        store = InMemoryNotificationTemplateStore()
        store.register(template)

        with pytest.raises(DuplicateNotificationTemplateError):
            store.register(template)
