"""Firebase Cloud Messaging push adapter (NTF-301).

Sends one message to one Android device token through FCM's HTTP v1 API. The adapter is
**synchronous**, like the rest of this service: the event consumer that drives delivery is a
plain loop, not an event loop, and bridging to an async client per message would buy nothing
but an OAuth round trip and a client lifecycle to manage.

Two parts are deliberately still scaffolds, because they belong to later stories rather than
this one: the service-account assertion is a placeholder until NTF-705 injects real
credentials, and successful sends are only *accepted* by the provider -- there is no
on-device delivery receipt to record (NTF-303 owns the status mapping).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FCM_SEND_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"

INVALID_TOKEN_FCM_ERRORS = frozenset({"UNREGISTERED", "NOT_FOUND"})
"""Codes that mean the *address* is gone, so the registration should be pruned."""

PERMANENT_FCM_ERRORS = frozenset(
    {
        "INVALID_ARGUMENT",
        "APPS_CHECK_FAILED",
        "FAULTY_ETAG",
        "SENDER_ID_MISMATCH",
        "THIRD_PARTY_AUTH_ERROR",
        "UNAUTHENTICATED",
        "PERMISSION_DENIED",
        *INVALID_TOKEN_FCM_ERRORS,
    }
)
"""Refusals a retry cannot change. Everything else (UNAVAILABLE, INTERNAL, quotas, throttling)
is transient by FCM's own classification and is retried by NTF-303."""


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
        self._client: httpx.Client | None = None
        self._access_token: str | None = None
        self._token_expiry: float = 0

    def start(self) -> None:
        """Initialize the HTTP client and fetch an access token (idempotent)."""
        if self._client is not None:
            return
        self._client = httpx.Client(
            base_url="https://oauth2.googleapis.com/token",
            timeout=self._config.timeout,
        )
        self._refresh_token()

    def stop(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _refresh_token(self) -> None:
        """Fetch a new OAuth2 access token from Google."""
        if self._client is None:
            raise RuntimeError("FCMAdapter not started")

        payload = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": self._make_jwt(),
        }
        try:
            response = self._client.post("/token", data=payload)
            response.raise_for_status()
            token_data = response.json()
            self._access_token = token_data["access_token"]
            self._token_expiry = time.time() + float(token_data.get("expires_in", 3600))
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.error("fcm.token_fetch_failed error=%s", exc)
            raise FCMError("TOKEN_FETCH_FAILED", {"message": str(exc)}, retryable=True) from exc

    def _make_jwt(self) -> str:
        """Create a JWT assertion for FCM authentication.

        The signature is a placeholder until NTF-705 supplies the service-account key; the
        claims are real so the shape is already correct when signing lands.
        """
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {
            "iss": self._config.credentials_json["client_email"],
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "aud": "https://oauth2.googleapis.com/token",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }

        def b64encode(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        header_b64 = b64encode(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = b64encode(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{header_b64}.{payload_b64}"
        return f"{signing_input}.signature"

    def send(self, message: FCMMessage) -> str:
        """Send a push notification to a device token.

        Returns the FCM message ID on success and raises :class:`FCMError` on refusal.
        """
        if self._client is None:
            self.start()

        if self._access_token is None or time.time() > self._token_expiry:
            self._refresh_token()

        fcm_payload: dict[str, Any] = {
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

        assert self._client is not None
        try:
            response = self._client.post(
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
            error_data = _json_or_empty(exc.response)
            error_status = error_data.get("error", {}).get("status", "UNKNOWN")

            if error_status in PERMANENT_FCM_ERRORS:
                logger.warning(
                    "fcm.permanent_failure token=%s error=%s",
                    message.token[-8:],
                    error_status,
                )
                raise FCMError(
                    error_status,
                    error_data,
                    dead_token=error_status in INVALID_TOKEN_FCM_ERRORS,
                ) from exc

            logger.warning(
                "fcm.temporary_failure token=%s error=%s",
                message.token[-8:],
                error_status,
            )
            raise FCMError(error_status, error_data, retryable=True) from exc
        except httpx.HTTPError as exc:
            logger.error("fcm.http_error token=%s error=%s", message.token[-8:], exc)
            raise FCMError("HTTP_ERROR", {"message": str(exc)}, retryable=True) from exc


def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
    """The provider's error body, which is sometimes not JSON at all (a gateway page)."""
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


class FCMError(Exception):
    """Error from FCM API."""

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
        super().__init__(f"FCM error {code}: {details}")


def build_fcm_adapter(settings: Any) -> FCMAdapter:
    """Build an FCM adapter from settings.

    ``fcm_credentials_json`` is a SecretStr holding the service-account JSON (or a path to
    it); both are accepted so credentials can be mounted as a file or injected as a secret.
    """
    raw = settings.fcm_credentials_json
    credentials = raw.get_secret_value() if hasattr(raw, "get_secret_value") else raw
    if isinstance(credentials, str):
        if os.path.exists(credentials):
            with open(credentials, encoding="utf-8") as handle:
                credentials = json.load(handle)
        else:
            credentials = json.loads(credentials)

    config = FCMConfig(
        project_id=settings.fcm_project_id,
        credentials_json=credentials,
    )
    return FCMAdapter(config)
