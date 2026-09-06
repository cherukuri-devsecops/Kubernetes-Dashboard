import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

from app.config import Settings, get_settings
from app.services.redis import client as redis_client

logger = logging.getLogger("kubernetes-dashboard")


class AuthenticatedUser(BaseModel):
    email: EmailStr
    name: str
    role: str


bearer_scheme = HTTPBearer(auto_error=False)

# Verified-token cache. Redis is the shared tier so every replica benefits from
# one verification; the in-process dict below is the fallback when Redis is down.
_verified_tokens: dict[str, tuple[AuthenticatedUser, float]] = {}
_MAX_CACHED_TOKENS = 2048
_REDIS_KEY_PREFIX = "auth:token:"


def _token_key(token: str) -> str:
    """Digest rather than the raw token, so a stray log or dump cannot leak it."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _cache_get(key: str, max_age_seconds: float) -> AuthenticatedUser | None:
    raw = await redis_client.cache_get(f"{_REDIS_KEY_PREFIX}{key}")
    if raw is not None:
        try:
            payload = json.loads(raw)
            if time.time() - float(payload["verifiedAt"]) <= max_age_seconds:
                return AuthenticatedUser(**payload["user"])
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("discarding malformed cached verification: %s", exc)
            await redis_client.cache_delete(f"{_REDIS_KEY_PREFIX}{key}")

    entry = _verified_tokens.get(key)
    if entry is None:
        return None
    user, verified_at = entry
    # Monotonic here: the in-process clock must not be fooled by wall-clock jumps.
    if time.monotonic() - verified_at > max_age_seconds:
        return None
    return user


async def _cache_put(key: str, user: AuthenticatedUser, stale_seconds: int) -> None:
    await redis_client.cache_set(
        f"{_REDIS_KEY_PREFIX}{key}",
        json.dumps({"user": user.model_dump(mode="json"), "verifiedAt": time.time()}),
        # Redis expiry is the hard bound on how long a verification can live.
        max(stale_seconds, 1),
    )

    if len(_verified_tokens) >= _MAX_CACHED_TOKENS:
        # Cheap bound: drop the oldest verification rather than tracking an LRU.
        oldest = min(_verified_tokens, key=lambda item: _verified_tokens[item][1])
        _verified_tokens.pop(oldest, None)
    _verified_tokens[key] = (user, time.monotonic())


async def _cache_evict(key: str) -> None:
    await redis_client.cache_delete(f"{_REDIS_KEY_PREFIX}{key}")
    _verified_tokens.pop(key, None)


def create_access_token(user: AuthenticatedUser, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user.email,
        "name": user.name,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def user_from_payload(payload: Mapping[str, Any], fallback_email: str | None = None) -> AuthenticatedUser:
    raw_roles = payload.get("roles")
    role = payload.get("role")
    if not role and isinstance(raw_roles, list) and raw_roles:
        role = str(raw_roles[0])
    if not role:
        role = "viewer"

    email = (
        payload.get("email")
        or payload.get("sub")
        or payload.get("username")
        or fallback_email
    )
    if not email:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Auth API response did not include a user email",
        )

    name = (
        payload.get("name")
        or payload.get("full_name")
        or payload.get("display_name")
        or payload.get("username")
        or email
    )

    return AuthenticatedUser(email=email, name=str(name), role=str(role))


def decode_access_token(token: str, settings: Settings) -> AuthenticatedUser:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return AuthenticatedUser(
            email=payload["sub"],
            name=payload.get("name", payload["sub"]),
            role=payload.get("role", "viewer"),
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


def decode_external_token(token: str, settings: Settings) -> AuthenticatedUser:
    if not settings.auth_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="External auth requires AUTH_API_ME_PATH or AUTH_JWT_SECRET",
        )

    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.auth_jwt_algorithm],
        )
        return user_from_payload(payload)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


async def fetch_external_user(token: str, settings: Settings) -> AuthenticatedUser:
    if not settings.auth_api_base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AUTH_API_BASE_URL is required when AUTH_PROVIDER=external",
        )

    if not settings.auth_api_me_path:
        return decode_external_token(token, settings)

    key = _token_key(token)
    cached = await _cache_get(key, settings.auth_cache_ttl_seconds)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=settings.auth_api_timeout_seconds) as client:
            response = await client.get(
                settings.auth_api_url(settings.auth_api_me_path),
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        stale = await _cache_get(key, settings.auth_cache_stale_seconds)
        if stale is not None:
            logger.warning("auth API unreachable, using cached verification: %s", exc)
            return stale
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth API is unavailable",
        ) from exc

    if response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
        # An explicit rejection is authoritative: drop the cached verification so
        # revoked tokens stop working immediately.
        await _cache_evict(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if response.status_code >= 400:
        stale = await _cache_get(key, settings.auth_cache_stale_seconds)
        if stale is not None:
            logger.warning(
                "auth API returned %s, using cached verification", response.status_code
            )
            return stale
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Auth API rejected the user lookup",
        )

    data = response.json()
    user_payload = data.get("user") if isinstance(data, dict) else None
    if isinstance(user_payload, dict):
        user = user_from_payload(user_payload)
    elif isinstance(data, dict):
        user = user_from_payload(data)
    else:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Auth API returned an unsupported user response",
        )

    await _cache_put(key, user, settings.auth_cache_stale_seconds)
    return user


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    if settings.use_external_auth:
        return await fetch_external_user(credentials.credentials, settings)
    return decode_access_token(credentials.credentials, settings)
