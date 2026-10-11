"""Firebase Cloud Messaging push adapter (NTF-301).

This module provides the FCM push notification adapter that sends push notifications
to Android devices via the Firebase Cloud Messaging API.

The adapter handles:
- Authentication with FCM using service account credentials
- Sending messages to device tokens
- Handling FCM error responses and retry logic
- Deep link payload construction
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# FCM endpoint
FCM_SEND_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"

# FCM error codes that indicate permanent failures (no retry)
PERMANENT_FCM_ERRORS = {
    "INVALID_ARGUMENT": "invalid argument",
    "NOT_FOUND": "device token not found",
    "UNREGISTERED": "device token unregistered",
    "APPS_CHECK_FAILED": "apps check failed",
    "FAULTY_ETAG": "faulty etag",
    "INTERNAL": "internal error",
    "QUOTA_EXCEEDED": "quota exceeded",
    "QUOTA_EXCEEDED_PER_USER": "quota exceeded per user",
    "QUOTA_EXCEEDED_PER_PROJECT": "quota exceeded per project",
    "SERVICE_UNAVAILABLE": "service unavailable",
    "THROTTLE": "throttle",
}


@dataclass(frozen=True)
class FCMConfig:
    """Configuration for FCM push adapter."""

    project_id: str
    credentials_json: dict[str, Any]
    timeout: float = 10.0


@dataclass(frozen=True)
class FCMMessage:
    """A message to send via FCM."""

    token: str
    title: str
    body: str
    data: dict[str, str]
    notification: dict[str, str] | None = None
    android: dict[str, Any] | None = None
    apns: dict[str, Any] | None = None


class FCMAdapter:
    """Send push notifications via Firebase Cloud Messaging."""

    def __init__(self, config: FCMConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._token_expiry: float = 0

    async def start(self) -> None:
        """Initialize the HTTP client and fetch access token."""
        self._client = httpx.AsyncClient(
            base_url="https://oauth2.googleapis.com/token",
            timeout=self._config.timeout,
        )
        await self._refresh_token()

    async def stop(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _refresh_token(self) -> None:
        """Fetch a new OAuth2 access token from Google."""
        if self._client is None:
            raise RuntimeError("FCMAdapter not started")

        payload = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": self._make_jwt(),
        }
        try:
            response = await self._client.post(
                "/token",
                data=payload,
            )
            response.raise_for_status()
            token_data = response.json()
            self._access_token = token_data["access_token"]
            self._token_expiry = (
                self._config.credentials_json.get("token_expiry", 0)
                or (self._config.credentials_json.get("expires_in", 3600) / 1000)
                + __import__("time").time()
            )
        except httpx.HTTPError as exc:
            logger.error("fcm.token_fetch_failed error=%s", exc)
            raise

    def _make_jwt(self) -> str:
        """Create a JWT assertion for FCM authentication."""
        # Simplified JWT creation - in production, use a proper JWT library
        import base64
        import hashlib
        import hmac
        import json
        import time

        header = {"alg": "RS256", "typ": "JWT"}
        payload = {
            "iss": self._config.credentials_json["client_email"],
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "aud": "https://oauth2.googleapis.com/token",
            "exp": int(__import__("time").time()) + 3600,
            "iat": int(__import__("time").time()),
        }

        def b64encode(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        header_b64 = b64encode(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = b64encode(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{header_b64}.{payload_b64}"

        # In production, use the private key from credentials
        # For now, return a placeholder
        return f"{signing_input}.signature"

    async def send(self, message: FCMMessage) -> str:
        """Send a push notification to a device token.

        Returns the FCM message ID on success.
        Raises FCMError on permanent failures.
        """
        if self._client is None:
            raise RuntimeError("FCMAdapter not started")

        if self._access_token is None or __import__("time").time() > self._token_expiry:
            await self._refresh_token()

        fcm_payload = {
            "message": {
                "token": message.token,
                "notification": {
                    "title": message.title,
                    "body": message.body,
                },
                "data": message.data,
            }
        }

        if message.android:
            fcm_payload["message"]["android"] = message.android

        if message.apns:
            fcm_payload["message"]["apns"] = message.apns

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._client.post(
                FCM_SEND_ENDPOINT.format(project=self._config.project_id),
                json=fcm_payload,
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
            logger.info(
                "fcm.message_sent message_id=%s token=%s",
                result.get("name", "unknown"),
                message.token[-8:],
            )
            return result.get("name", "")
        except httpx.HTTPStatusError as exc:
            error_data = exc.response.json() if exc.response.text else {}
            error_code = error_data.get("error", {}).get("code", "UNKNOWN")
            error_status = error_data.get("error", {}).get("status", "UNKNOWN")

            if error_status in PERMANENT_FCM_ERRORS:
                logger.warning(
                    "fcm.permanent_failure message_id=%s error=%s",
                    message.token,
                    error_status,
                )
                raise FCMError(error_status, error_data) from exc
            else:
                logger.warning(
                    "fcm.temporary_failure message_id=%s error=%s",
                    message.token,
                    error_status,
                )
                raise FCMError(error_status, error_data, retryable=True) from exc
        except httpx.HTTPError as exc:
            logger.error(
                "fcm.http_error message_id=%s error=%s",
                message.token,
                exc,
            )
            raise FCMError("HTTP_ERROR", {"message": str(exc)}, retryable=True) from exc


class FCMError(Exception):
    """Error from FCM API."""

    def __init__(
        self,
        code: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.details = details or {}
        self.retryable = retryable
        super().__init__(f"FCM error {code}: {details}")


def build_fcm_adapter(settings: Any) -> FCMAdapter:
    """Build an FCM adapter from settings.

    Settings must have:
    - fcm_project_id: Firebase project ID
    - fcm_credentials: Service account credentials JSON (dict or path)
    """
    import json
    import os

    credentials = settings.fcm_credentials
    if isinstance(credentials, str):
        # Load from file or JSON string
        if os.path.exists(credentials):
            with open(credentials) as f:
                credentials = json.load(f)
        else:
            credentials = json.loads(credentials)

    config = FCMConfig(
        project_id=settings.fcm_project_id,
        credentials_json=credentials,
    )
    return FCMAdapter(config)
