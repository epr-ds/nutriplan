"""Authentication use-cases: registration, login (with lockout), and refresh rotation."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.oauth import OAuthError, provider_supported, verify_oauth_token
from app.db.models import Credential, OAuthIdentity, RefreshToken, User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    OAuthRequest,
    RefreshRequest,
    RegisterRequest,
)
from app.schemas.user import UserProfileResponse


def _aware(dt: datetime | None) -> datetime | None:
    """Treat naive datetimes (e.g. from SQLite) as UTC for safe comparison."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _mint_refresh_token(db: Session, user_id: uuid.UUID, family_id: uuid.UUID) -> str:
    raw = secrets.token_urlsafe(48)
    db.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=_hash_token(raw),
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds),
        )
    )
    return raw


def _auth_response(db: Session, user: User, family_id: uuid.UUID) -> AuthResponse:
    access_token, expires_in = security.create_access_token(str(user.id), user.email)
    refresh_token = _mint_refresh_token(db, user.id, family_id)
    db.commit()
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=UserProfileResponse.model_validate(user),
    )


def register(db: Session, payload: RegisterRequest) -> AuthResponse:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(email=email, name=payload.name)
    db.add(user)
    db.flush()
    db.add(Credential(user_id=user.id, password_hash=security.hash_password(payload.password)))
    db.flush()
    return _auth_response(db, user, uuid.uuid4())


def login(db: Session, payload: LoginRequest) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    cred = user.credential
    now = datetime.now(UTC)

    locked_until = _aware(cred.locked_until)
    if locked_until is not None and locked_until > now:
        retry_after = max(int((locked_until - now).total_seconds()), 1)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Account temporarily locked due to repeated failed logins",
            headers={"Retry-After": str(retry_after)},
        )

    if not security.verify_password(cred.password_hash, payload.password):
        cred.failed_attempts += 1
        if cred.failed_attempts >= settings.login_max_failed_attempts:
            cred.locked_until = now + timedelta(seconds=settings.login_lockout_seconds)
            cred.failed_attempts = 0
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    cred.failed_attempts = 0
    cred.locked_until = None
    db.flush()
    return _auth_response(db, user, uuid.uuid4())


def refresh(db: Session, payload: RefreshRequest) -> AuthResponse:
    token_hash = _hash_token(payload.refresh_token)
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    now = datetime.now(UTC)

    # Reuse detection: presenting a revoked or already-rotated token compromises the
    # whole family, so revoke every token issued in that lineage.
    if token.revoked or token.used_at is not None:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == token.family_id)
            .values(revoked=True)
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token reuse detected")

    if _aware(token.expires_at) < now:
        token.revoked = True
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")

    token.used_at = now
    user = db.get(User, token.user_id)
    db.flush()
    return _auth_response(db, user, token.family_id)


def oauth_login(db: Session, provider: str, payload: OAuthRequest) -> AuthResponse:
    """Verify a provider id-token, then provision or look up the matching user (IDN-201/202)."""
    if not provider_supported(provider):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported OAuth provider: {provider}")

    try:
        claims = verify_oauth_token(provider, payload.id_token, payload.nonce)
    except OAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    identity = db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider, OAuthIdentity.subject == claims.subject
        )
    )
    if identity is not None:
        user = db.get(User, identity.user_id)
        return _auth_response(db, user, uuid.uuid4())

    # First login for this provider identity: link to an existing account by email,
    # otherwise auto-provision. (Cross-provider dedupe nuances are IDN-204, Sprint 5.)
    user = None
    if claims.email:
        user = db.scalar(select(User).where(User.email == claims.email.lower()))
    if user is None:
        if not claims.email:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Identity token did not include an email address"
            )
        user = User(email=claims.email.lower(), name=claims.name or claims.email.split("@")[0])
        db.add(user)
        db.flush()

    db.add(OAuthIdentity(user_id=user.id, provider=provider, subject=claims.subject))
    db.flush()
    return _auth_response(db, user, uuid.uuid4())
