"""Apple Push Notification service adapter (NTF-301).

Sends one message to one iOS device token through APNs' HTTP/2 API. Like the FCM adapter this
is **synchronous**: delivery runs inside the service's plain event loop, and an async client
would add lifecycle and event-loop bridging without making any send faster.

The signing step is still a placeholder -- NTF-705 supplies the provider key -- but the JWT
shape, the sandbox/production switch, and the error classification are real, because those are
what NTF-303's receipt tracking depends on.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

APNS_PRODUCTION_URL = "https://api.push.apple.com"
APNS_SANDBOX_URL = "https://api.sandbox.push.apple.com"

INVALID_TOKEN_APNS_ERRORS = frozenset({"BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"})
"""Codes that mean the *address* is gone, so the registration should be pruned."""

PERMANENT_APNS_ERRORS = frozenset(
    {
        "BadCollapseId",
        "BadExpirationDate",
        "BadMessageId",
        "BadPriority",
        "BadTopic",
        "DeviceTokenNotForTopic",
        "DuplicateHeaders",
        "MissingDeviceToken",
        "MissingTopic",
        "PayloadEmpty",
        "PayloadTooLarge",
        "TopicDisallowed",
        "BadCertificate",
        "BadCertificateEnvironment",
        "Forbidden",
        "InvalidProviderToken",
        "MissingProviderToken",
        "BadPath",
        "MethodNotAllowed",
        *INVALID_TOKEN_APNS_ERRORS,
    }
)
"""Refusals a retry cannot change. Transient codes (``ServiceUnavailable``, ``InternalServerError``,
``TooManyRequests``) are left out and retried by NTF-303."""

REFRESH_TOKEN_ERRORS = frozenset({"ExpiredProviderToken", "InvalidProviderToken"})
"""A stale provider JWT; drop it so the next attempt signs a fresh one."""


@dataclass(frozen=True)
class APNsConfig:
    """Configuration for APNs push adapter."""

    key_id: str
    team_id: str
    auth_key: bytes  # PEM-encoded private key
    bundle_id: str
    use_sandbox: bool = False
    timeout: float = 10.0


@dataclass(frozen=True)
class APNsMessage:
    """A message to send via APNs."""

    token: str
    payload: dict[str, Any]
    sound: str | dict[str, Any] = "default"
    badge: int | None = None
    category: str | None = None
    thread_id: str | None = None


class APNsAdapter:
    """Send push notifications via Apple Push Notification service."""

    def __init__(self, config: APNsConfig) -> None:
        self._config = config
        self._client: httpx.Client | None = None
        self._access_token: str | None = None
        self._token_expiry: float = 0

    def start(self) -> None:
        """Initialize the HTTP client and fetch a provider JWT (idempotent)."""
        if self._client is not None:
            return
        base_url = APNS_SANDBOX_URL if self._config.use_sandbox else APNS_PRODUCTION_URL
        self._client = httpx.Client(
            base_url=base_url,
            timeout=self._config.timeout,
            headers={"apns-topic": self._config.bundle_id},
        )
        self._refresh_token()

    def stop(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _refresh_token(self) -> None:
        """Create the short-lived JWT APNs accepts as a bearer token."""
        issued_at = int(time.time())
        header = {"alg": "ES256", "kid": self._config.key_id}
        payload = {
            "iss": self._config.team_id,
            "iat": issued_at,
            "exp": issued_at + 1800,
        }

        def b64encode(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        header_b64 = b64encode(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = b64encode(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{header_b64}.{payload_b64}"
        signature = self._sign(signing_input.encode())

        self._access_token = f"{signing_input}.{signature}"
        self._token_expiry = issued_at + 1800

    def _sign(self, data: bytes) -> str:
        """Sign data with the APNs private key.

        The real implementation loads ``self._config.auth_key`` with ``cryptography`` and signs
        with ECDSA/P-256; NTF-705 owns landing the key, so this returns a placeholder until then.
        """
        return base64.urlsafe_b64encode(b"placeholder_signature").rstrip(b"=").decode("ascii")

    def send(self, message: APNsMessage) -> str:
        """Send a push notification to a device token.

        Returns the APNs message ID on success and raises :class:`APNsError` on refusal.
        """
        if self._client is None:
            self.start()

        if self._access_token is None or time.time() > self._token_expiry:
            self._refresh_token()

        apns_payload: dict[str, Any] = {
            "aps": {
                "alert": {
                    "title": message.payload.get("title", ""),
                    "body": message.payload.get("body", ""),
                },
            }
        }

        if message.sound:
            apns_payload["aps"]["sound"] = message.sound

        if message.badge is not None:
            apns_payload["aps"]["badge"] = message.badge

        if message.category:
            apns_payload["aps"]["category"] = message.category

        if message.thread_id:
            apns_payload["aps"]["thread-id"] = message.thread_id

        for key, value in message.payload.items():
            if key not in {"title", "body"}:
                apns_payload[key] = value

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "apns-topic": self._config.bundle_id,
            "apns-id": str(message.payload.get("id") or uuid.uuid4().hex),
        }

        assert self._client is not None
        try:
            response = self._client.post(
                f"/3/{message.token}",
                json=apns_payload,
                headers=headers,
            )
            response.raise_for_status()
            logger.info(
                "apns.message_sent token=%s status=%s",
                message.token[-8:],
                response.status_code,
            )
            return response.headers.get("apns-id", "")
        except httpx.HTTPStatusError as exc:
            error_data = _json_or_empty(exc.response)
            error_code = str(error_data.get("reason", "UNKNOWN"))

            if error_code in REFRESH_TOKEN_ERRORS:
                self._access_token = None
                self._token_expiry = 0

            if error_code in PERMANENT_APNS_ERRORS:
                logger.warning(
                    "apns.permanent_failure token=%s error=%s",
                    message.token[-8:],
                    error_code,
                )
                raise APNsError(
                    error_code,
                    error_data,
                    dead_token=error_code in INVALID_TOKEN_APNS_ERRORS,
                ) from exc

            logger.warning(
                "apns.temporary_failure token=%s error=%s",
                message.token[-8:],
                error_code,
            )
            raise APNsError(error_code, error_data, retryable=True) from exc
        except httpx.HTTPError as exc:
            logger.error("apns.http_error token=%s error=%s", message.token[-8:], exc)
            raise APNsError("HTTP_ERROR", {"message": str(exc)}, retryable=True) from exc


def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
    """The provider's error body, which is sometimes not JSON at all (a gateway page)."""
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


class APNsError(Exception):
    """Error from APNs API."""

    def __init__(
        self,
        code: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        dead_token: bool = False,
    ) -> None:
        self.code = code
        self.details = details or {}
        self.dead_token = dead_token
        self.retryable = retryable and not dead_token
        super().__init__(f"APNs error {code}: {details}")


def build_apns_adapter(settings: Any) -> APNsAdapter:
    """Build an APNs adapter from settings.

    ``apns_private_key`` is a SecretStr holding either the PEM content or a path to it.
    """
    raw = settings.apns_private_key
    auth_key = raw.get_secret_value() if hasattr(raw, "get_secret_value") else raw
    if isinstance(auth_key, str):
        if os.path.exists(auth_key):
            with open(auth_key, "rb") as handle:
                auth_key = handle.read()
        else:
            auth_key = auth_key.encode()

    config = APNsConfig(
        key_id=settings.apns_key_id,
        team_id=settings.apns_team_id,
        auth_key=auth_key,
        bundle_id=settings.apns_bundle_id,
        use_sandbox=settings.apns_use_sandbox,
    )
    return APNsAdapter(config)
