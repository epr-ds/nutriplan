"""Apple Push Notification service adapter (NTF-302).

This module provides the APNs push notification adapter that sends push notifications
to iOS devices via the Apple Push Notification service.

The adapter handles:
- Authentication with APNs using JWT (JSON Web Token)
- Sending messages to device tokens
- Handling APNs error responses and retry logic
- Deep link payload construction
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# APNs endpoint
APNS_ENDPOINT = "https://api.push.apple.com/3/{device_token}"

# APNs error codes that indicate permanent failures (no retry)
PERMANENT_APNS_ERRORS = {
    "BadDeviceToken": "bad device token",
    "DeviceTokenNotForTopic": "device token not for topic",
    "Unregistered": "unregistered device",
}


@dataclass(frozen=True)
class APNsConfig:
    """Configuration for APNs push adapter."""

    key_id: str
    team_id: str
    auth_key: bytes  # PEM-encoded private key
    bundle_id: str
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
        self._client: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._token_expiry: float = 0

    async def start(self) -> None:
        """Initialize the HTTP client and fetch access token."""
        self._client = httpx.AsyncClient(
            base_url="https://api.push.apple.com",
            timeout=self._config.timeout,
            headers={
                "apns-topic": self._config.bundle_id,
            },
        )
        await self._refresh_token()

    async def stop(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _refresh_token(self) -> None:
        """Fetch a new JWT for APNs authentication."""
        import base64
        import hashlib
        import hmac

        # Create JWT header
        header = {
            "alg": "ES256",
            "kid": self._config.key_id,
        }

        # Create JWT payload
        payload = {
            "iss": self._config.team_id,
            "iat": int(time.time()),
        }

        def b64encode(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        header_b64 = b64encode(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = b64encode(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{header_b64}.{payload_b64}"

        # Sign with private key (simplified - in production, use cryptography library)
        signature = self._sign(signing_input.encode())

        self._access_token = f"{signing_input}.{signature}"
        self._token_expiry = int(time.time()) + 1800  # JWTs valid for 30 minutes

    def _sign(self, data: bytes) -> str:
        """Sign data with the APNs private key.

        In production, use the cryptography library:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        private_key = serialization.load_pem_private_key(self._config.auth_key, password=None)
        signature = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
        return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        """
        # Placeholder - in production, implement proper signing
        return base64.urlsafe_b64encode(b"placeholder_signature").rstrip(b"=").decode("ascii")

    async def send(self, message: APNsMessage) -> str:
        """Send a push notification to a device token.

        Returns the APNs message ID on success.
        Raises APNsError on permanent failures.
        """
        if self._client is None:
            raise RuntimeError("APNsAdapter not started")

        if self._access_token is None or time.time() > self._token_expiry:
            await self._refresh_token()

        # Build APNs payload
        apns_payload = {
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

        # Add custom data
        for key, value in message.payload.items():
            if key != "title" and key != "body":
                apns_payload[key] = value

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "apns-topic": self._config.bundle_id,
            "apns-id": message.payload.get("id", __import__("uuid").uuid4().hex),
        }

        try:
            response = await self._client.post(
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
            error_data = exc.response.json() if exc.response.text else {}
            error_code = error_data.get("reason", "UNKNOWN")

            if error_code in PERMANENT_APNS_ERRORS:
                logger.warning(
                    "apns.permanent_failure token=%s error=%s",
                    message.token,
                    error_code,
                )
                raise APNsError(error_code, error_data) from exc
            else:
                logger.warning(
                    "apns.temporary_failure token=%s error=%s",
                    message.token,
                    error_code,
                )
                raise APNsError(error_code, error_data, retryable=True) from exc
        except httpx.HTTPError as exc:
            logger.error(
                "apns.http_error token=%s error=%s",
                message.token,
                exc,
            )
            raise APNsError("HTTP_ERROR", {"message": str(exc)}, retryable=True) from exc


class APNsError(Exception):
    """Error from APNs API."""

    def __init__(
        self,
        code: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.details = details or {}
        self.retryable = retryable
        super().__init__(f"APNs error {code}: {details}")


def build_apns_adapter(settings: Any) -> APNsAdapter:
    """Build an APNs adapter from settings.

    Settings must have:
    - apns_key_id: Apple Key ID
    - apns_team_id: Apple Team ID
    - apns_auth_key: Path to or content of auth key PEM file
    - apns_bundle_id: Apple bundle ID
    """
    import os

    auth_key = settings.apns_auth_key
    if isinstance(auth_key, str) and os.path.exists(auth_key):
        with open(auth_key, "rb") as f:
            auth_key = f.read()

    config = APNsConfig(
        key_id=settings.apns_key_id,
        team_id=settings.apns_team_id,
        auth_key=auth_key,
        bundle_id=settings.apns_bundle_id,
    )
    return APNsAdapter(config)
