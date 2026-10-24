"""The notification copy engine and the catalog it serves (NTF-401).

This module owns the *shipped* copy: one :class:`~app.domain.templates.NotificationTemplate`
per notification intent per supported language, with a shared version string per intent so
telemetry and replays can tell copies from different revisions apart.

The catalog is deliberately static -- it is the content of a deploy, not per-user state --
and it is resolved per user through :class:`~app.domain.templates.Locale` at render time, so
the same process can send Spanish to one user and English to another from the same event.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.adapters.in_memory_notification_template_store import InMemoryNotificationTemplateStore
from app.domain.enums import NotificationType
from app.domain.repositories import NotificationTemplateStore
from app.domain.templates import Locale, NotificationTemplate, RenderedNotification

NOTIFICATION_COPY_VERSION = "2026-10-23"
"""Shared version stamp for every template of the current copy revision (NTF-401)."""

DEFAULT_NOTIFICATION_TEMPLATES: tuple[NotificationTemplate, ...] = (
    # -- order lifecycle (NTF-202) -----------------------------------------------------
    NotificationTemplate(
        id="order_confirmed",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.ES,
        title="Pedido confirmado",
        body="Recibimos tu pedido $orderId. Síguelo aquí: $deepLink",
    ),
    NotificationTemplate(
        id="order_confirmed",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.EN,
        title="Order confirmed",
        body="We received your order, $orderId. Track it at $deepLink",
    ),
    NotificationTemplate(
        id="order_preparing",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.ES,
        title="Preparando tu pedido",
        body="Estamos preparando tu pedido $orderId. Síguelo aquí: $deepLink",
    ),
    NotificationTemplate(
        id="order_preparing",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.EN,
        title="Preparing your order",
        body="Your order $orderId is being prepared. Follow it at $deepLink",
    ),
    NotificationTemplate(
        id="order_in_transit",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.ES,
        title="En camino",
        body="Tu pedido $orderId está en camino. Síguelo aquí: $deepLink",
    ),
    NotificationTemplate(
        id="order_in_transit",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.EN,
        title="On the way",
        body="Your order $orderId is in transit. Track it at $deepLink",
    ),
    NotificationTemplate(
        id="order_delivered",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.ES,
        title="Entregado",
        body="Tu pedido $orderId fue entregado. Síguelo aquí: $deepLink",
    ),
    NotificationTemplate(
        id="order_delivered",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.EN,
        title="Delivered",
        body="Your order $orderId was delivered. Track it at $deepLink",
    ),
    NotificationTemplate(
        id="order_cancelled",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.ES,
        title="Cancelado",
        body="Tu pedido $orderId fue cancelado. Síguelo aquí: $deepLink",
    ),
    NotificationTemplate(
        id="order_cancelled",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.EN,
        title="Cancelled",
        body="Your order $orderId was cancelled. Track it at $deepLink",
    ),
    # -- meal reminders (NTF-401) -------------------------------------------------------
    NotificationTemplate(
        id="meal_reminder",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.ES,
        title="Recordatorio de comida",
        body="Hora de $mealName — abre los detalles de la comida en $deepLink",
    ),
    NotificationTemplate(
        id="meal_reminder",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.EN,
        title="Meal reminder",
        body="$mealName is due — open the meal details at $deepLink",
    ),
    # -- plan endings (NTF-402) ---------------------------------------------------------
    NotificationTemplate(
        id="plan_ending",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.ES,
        title="Tu plan se acaba pronto",
        body="Tu plan $planType termina el $endingDate — gestiona en $deepLink",
    ),
    NotificationTemplate(
        id="plan_ending",
        version=NOTIFICATION_COPY_VERSION,
        locale=Locale.EN,
        title="Your plan ends soon",
        body="Your $planType plan ends on $endingDate — manage it at $deepLink",
    ),
)


def build_default_catalog() -> InMemoryNotificationTemplateStore:
    """Build a catalog pre-loaded with every shipped copy template."""
    return InMemoryNotificationTemplateStore(DEFAULT_NOTIFICATION_TEMPLATES)


class NotificationTemplateService:
    """Resolve a notification type's copy for a locale and render it to title + body."""

    def __init__(self, store: NotificationTemplateStore) -> None:
        self._store = store

    def render(
        self,
        notification_type: NotificationType,
        *,
        locale: Locale | str = Locale.ES,
        variables: Mapping[str, object] | None = None,
    ) -> RenderedNotification:
        """Render ``notification_type``'s copy for ``locale`` and substitute ``variables``.

        ``locale`` may be a :class:`~app.domain.templates.Locale` or any language tag;
        unsupported tags resolve to the default locale rather than failing the send. A type
        with no template on the resolved locale (and none on the default) raises
        :class:`TemplateNotFoundError`, which the delivery path treats as "no template" and
        falls back to the producer-supplied copy.
        """
        resolved = Locale.parse(locale, default=Locale.default())
        template = self._store.get(notification_type, resolved)
        return template.render(variables)
