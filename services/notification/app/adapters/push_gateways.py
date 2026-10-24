"""Provider adapters for the application's :class:`~app.domain.push.PushGateway` port.

The concrete FCM/APNs clients speak their own message types and raise their own error classes.
These wrappers translate both, so the delivery service can be written once and tested against
a fake without either SDK in the room. They are intentionally thin: anything that is not a
translation belongs in the adapter below them or in the use case above them.
"""

from __future__ import annotations

from typing import Any

from app.adapters.apns_adapter import APNsAdapter, APNsError, APNsMessage
from app.adapters.fcm_adapter import FCMAdapter, FCMError, FCMMessage
from app.domain.enums import DevicePlatform
from app.domain.push import PushError, PushMessage


class FcmPushGateway:
    """Deliver to Android through :class:`~app.adapters.fcm_adapter.FCMAdapter`."""

    platform = DevicePlatform.ANDROID

    def __init__(self, adapter: FCMAdapter) -> None:
        self._adapter = adapter

    def send(self, message: PushMessage) -> str:
        try:
            return self._adapter.send(
                FCMMessage(
                    token=message.token,
                    title=message.title,
                    body=message.body,
                    data=dict(message.data),
                    android=self._android(message),
                )
            )
        except FCMError as exc:
            raise PushError(
                exc.code,
                retryable=exc.retryable,
                dead_token=exc.dead_token,
                details=exc.details,
            ) from exc

    @staticmethod
    def _android(message: PushMessage) -> dict[str, Any] | None:
        """The FCM rich-notification block, or ``None`` for a plain push (NTF-405).

        ``None`` means *no block at all*: the provider's own default rendering handles the copy,
        which is the graceful fallback made structural rather than a message without the fields a
        rich notification would have needed.
        """
        if message.image_url is None and not message.actions:
            return None
        notification: dict[str, Any] = {"title": message.title, "body": message.body}
        if message.image_url is not None:
            notification["image"] = message.image_url
        if message.actions:
            notification["click_action"] = message.actions[0].deep_link
        return {"notification": notification}


class ApnsPushGateway:
    """Deliver to iOS through :class:`~app.adapters.apns_adapter.APNsAdapter`."""

    platform = DevicePlatform.IOS

    def __init__(self, adapter: APNsAdapter) -> None:
        self._adapter = adapter

    def send(self, message: PushMessage) -> str:
        payload = {"title": message.title, "body": message.body, **message.data}
        try:
            return self._adapter.send(
                APNsMessage(
                    token=message.token,
                    payload=payload,
                    badge=message.badge,
                    image_url=message.image_url,
                )
            )
        except APNsError as exc:
            raise PushError(
                exc.code,
                retryable=exc.retryable,
                dead_token=exc.dead_token,
                details=exc.details,
            ) from exc
