"""
Core authentication module.

Provides password generation, JWT creation/verification, and credential
validation. Also supports API key authentication via ``arc-`` bearer tokens.
"""

import hashlib
import logging
import os
import secrets
import string
import time
from collections import OrderedDict
from datetime import UTC
from pathlib import Path
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict

from lib import PROJECT_ROOT

logger = logging.getLogger(__name__)


class CurrentUserInfo(BaseModel):
    """Current authenticated user info."""

    id: str
    sub: str
    role: str = "admin"

    model_config = ConfigDict(frozen=True)


# JWT signing-secret cache
_cached_token_secret: str | None = None

# Token lifetime: 7 days
TOKEN_EXPIRY_SECONDS = 7 * 24 * 3600

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

# Password hashing
_password_hash = PasswordHash.recommended()
_cached_password_hash: str | None = None


def generate_password(length: int = 16) -> str:
    """Generate a random alphanumeric password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_token_secret() -> str:
    """Return the JWT signing secret.

    Prefers the ``AUTH_TOKEN_SECRET`` environment variable and otherwise
    auto-generates and caches a secret.
    """
    global _cached_token_secret

    env_secret = os.environ.get("AUTH_TOKEN_SECRET")
    if env_secret:
        return env_secret

    if _cached_token_secret is not None:
        return _cached_token_secret

    _cached_token_secret = secrets.token_hex(32)
    logger.info("Auto-generated JWT signing secret")
    return _cached_token_secret


def create_token(username: str) -> str:
    """Create a JWT token.

    Args:
        username: Username to encode into the token.

    Returns:
        The JWT token string.
    """
    now = time.time()
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, get_token_secret(), algorithm="HS256")


def verify_token(token: str) -> dict | None:
    """Verify a JWT token.

    Args:
        token: JWT token string.

    Returns:
        The decoded payload dict on success, otherwise ``None``.
    """
    try:
        payload = jwt.decode(token, get_token_secret(), algorithms=["HS256"])
        return payload
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        return None


DOWNLOAD_TOKEN_EXPIRY_SECONDS = 300  # 5 minutes


def create_download_token(username: str, project_name: str) -> str:
    """Issue a short-lived download token for browser-native downloads."""
    now = time.time()
    payload = {
        "sub": username,
        "project": project_name,
        "purpose": "download",
        "iat": now,
        "exp": now + DOWNLOAD_TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, get_token_secret(), algorithm="HS256")


def verify_download_token(token: str, project_name: str) -> dict:
    """Verify a download token.

    Returns:
        The decoded payload dict.

    Raises:
        jwt.ExpiredSignatureError: The token has expired.
        jwt.InvalidTokenError: The token is invalid.
        ValueError: The purpose or project does not match.
    """
    payload = jwt.decode(token, get_token_secret(), algorithms=["HS256"])
    if payload.get("purpose") != "download":
        raise ValueError("token purpose does not match")
    if payload.get("project") != project_name:
        raise ValueError("token project does not match")
    return payload


def _get_password_hash() -> str:
    """Return the cached hash of the current password."""
    global _cached_password_hash
    if _cached_password_hash is None:
        raw = os.environ.get("AUTH_PASSWORD", "")
        _cached_password_hash = _password_hash.hash(raw)
    return _cached_password_hash


def check_credentials(username: str, password: str) -> bool:
    """Validate username and password using a hash comparison.

    Reads ``AUTH_USERNAME`` (default ``admin``) and ``AUTH_PASSWORD`` from the
    environment. A hash comparison still runs even when the username does not
    match, which helps reduce timing-attack leakage.
    """
    expected_username = os.environ.get("AUTH_USERNAME", "admin")
    pw_hash = _get_password_hash()
    username_ok = secrets.compare_digest(username, expected_username)
    password_ok = _password_hash.verify(password, pw_hash)
    return username_ok and password_ok


def ensure_auth_password(env_path: str | None = None) -> str:
    """Ensure that ``AUTH_PASSWORD`` is set.

    If the environment variable is empty, a password is generated, written back
    to the environment, persisted to ``.env``, and logged as a warning.

    Args:
        env_path: Optional path to the ``.env`` file. Defaults to the project root.

    Returns:
        The current ``AUTH_PASSWORD`` value.
    """
    password = os.environ.get("AUTH_PASSWORD")
    if password:
        return password

    # Auto-generate password
    password = generate_password()
    os.environ["AUTH_PASSWORD"] = password

    # Persist back to .env
    if env_path is None:
        env_path = str(PROJECT_ROOT / ".env")

    env_file = Path(env_path)
    try:
        if env_file.exists():
            lines = env_file.read_text().splitlines()
            new_lines = []
            found = False
            for line in lines:
                if not found and line.strip().startswith("AUTH_PASSWORD="):
                    new_lines.append(f"AUTH_PASSWORD={password}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"AUTH_PASSWORD={password}")
            new_content = "\n".join(new_lines) + "\n"
            # Write in place (truncate + write) to preserve the inode for Docker bind mounts.
            with open(env_file, "r+") as f:
                f.seek(0)
                f.write(new_content)
                f.truncate()
        else:
            env_file.write_text(f"AUTH_PASSWORD={password}\n")
    except OSError:
        logger.warning("Could not write the .env file: %s", env_path)

    logger.warning("An auth password was generated automatically. Check AUTH_PASSWORD in the .env file")
    return password


# ---------------------------------------------------------------------------
# API key authentication support
# ---------------------------------------------------------------------------

API_KEY_PREFIX = "arc-"
API_KEY_CACHE_TTL = 300  # 5 minutes

# LRU cache: key_hash -> (payload_dict | None, expires_at_timestamp)
# A payload of None means the key is missing or expired (negative cache).
# Uses OrderedDict for LRU: move_to_end on hit, popitem(last=False) on eviction.
_api_key_cache: OrderedDict[str, tuple[dict | None, float]] = OrderedDict()
_API_KEY_CACHE_MAX = 512


def _hash_api_key(key: str) -> str:
    """Compute the SHA-256 hash of an API key."""
    return hashlib.sha256(key.encode()).hexdigest()


def invalidate_api_key_cache(key_hash: str) -> None:
    """Immediately clear the cache entry for ``key_hash``."""
    _api_key_cache.pop(key_hash, None)


def _get_cached_api_key_payload(key_hash: str) -> tuple[bool, dict | None]:
    """Look up a cache entry and return ``(hit, payload_or_none)``."""
    entry = _api_key_cache.get(key_hash)
    if entry is None:
        return False, None
    payload, expiry = entry
    if time.monotonic() > expiry:
        _api_key_cache.pop(key_hash, None)
        return False, None
    _api_key_cache.move_to_end(key_hash)
    return True, payload


def _set_api_key_cache(key_hash: str, payload: dict | None, expires_at_ts: float | None = None) -> None:
    """Write an entry into the cache, including LRU eviction.

    Positive cache entries cap their TTL at the real key expiration time so an
    expired key cannot remain valid due to cache lag.
    """
    if len(_api_key_cache) >= _API_KEY_CACHE_MAX:
        # Evict the least recently used entry (the OrderedDict head).
        _api_key_cache.popitem(last=False)
    ttl = API_KEY_CACHE_TTL
    if payload is not None and expires_at_ts is not None:
        time_to_expiry = expires_at_ts - time.monotonic()
        if time_to_expiry <= 0:
            # The key is expired, so store a negative-cache entry.
            _api_key_cache[key_hash] = (None, time.monotonic() + API_KEY_CACHE_TTL)
            return
        ttl = min(ttl, time_to_expiry)
    _api_key_cache[key_hash] = (payload, time.monotonic() + ttl)


async def _verify_api_key(token: str) -> dict | None:
    """Validate an API key token and return its payload dict or ``None``.

    The cache is checked first. On a miss, the database is queried. A successful
    lookup updates ``last_used_at`` asynchronously so the response is not blocked.
    """
    key_hash = _hash_api_key(token)

    # Cache lookup
    hit, cached_payload = _get_cached_api_key_payload(key_hash)
    if hit:
        return cached_payload

    # Database lookup
    from lib.db import async_session_factory
    from lib.db.repositories.api_key_repository import ApiKeyRepository

    async with async_session_factory() as session:
        async with session.begin():
            repo = ApiKeyRepository(session)
            row = await repo.get_by_hash(key_hash)

    if row is None:
        _set_api_key_cache(key_hash, None)
        return None

    # Check expiration
    expires_at = row.get("expires_at")
    expires_at_monotonic: float | None = None
    if expires_at:
        from datetime import datetime

        try:
            exp_dt = expires_at
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=UTC)
            if datetime.now(UTC) >= exp_dt:
                _set_api_key_cache(key_hash, None)
                return None
            # Convert the expiration time into a monotonic timestamp for TTL capping.
            remaining_secs = (exp_dt - datetime.now(UTC)).total_seconds()
            expires_at_monotonic = time.monotonic() + remaining_secs
        except (ValueError, TypeError):
            logger.warning("API Key expires_at value could not be parsed; skipping expiration check: %r", expires_at)

    payload = {"sub": f"apikey:{row['name']}", "via": "apikey"}
    _set_api_key_cache(key_hash, payload, expires_at_ts=expires_at_monotonic)

    # Update last_used_at asynchronously without blocking, while keeping a reference alive.
    import asyncio

    async def _touch():
        try:
            async with async_session_factory() as s:
                async with s.begin():
                    await ApiKeyRepository(s).touch_last_used(key_hash)
        except Exception:
            logger.exception("Failed to update API Key last_used_at (non-fatal)")

    _touch_task = asyncio.create_task(_touch())
    _touch_task.add_done_callback(lambda _: None)  # suppress "never retrieved" warning

    return payload


def _verify_and_get_payload(token: str) -> dict:
    """Synchronously validate a JWT and raise 401 on failure."""
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def _verify_and_get_payload_async(token: str) -> dict:
    """Asynchronously validate either an API key or a JWT token."""
    if token.startswith(API_KEY_PREFIX):
        payload = await _verify_api_key(token)
        if payload is None:
            raise HTTPException(
                status_code=401,
                detail="API Key is invalid, expired, or does not exist",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    # JWT path
    return _verify_and_get_payload(token)


def _payload_to_user(payload: dict) -> CurrentUserInfo:
    """Convert a verified JWT/API-key payload to CurrentUserInfo."""
    from lib.db.base import DEFAULT_USER_ID

    sub = payload.get("sub", "")
    return CurrentUserInfo(id=DEFAULT_USER_ID, sub=sub, role="admin")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> CurrentUserInfo:
    """Standard auth dependency supporting JWT and API-key bearer tokens."""
    payload = await _verify_and_get_payload_async(token)
    return _payload_to_user(payload)


async def get_current_user_flexible(
    token: Annotated[str | None, Depends(oauth2_scheme_optional)] = None,
    query_token: str | None = Query(None, alias="token"),
) -> CurrentUserInfo:
    """SSE auth dependency supporting Authorization headers and ?token query params."""
    raw = token or query_token
    if not raw:
        raise HTTPException(
            status_code=401,
            detail="Authentication token is missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = await _verify_and_get_payload_async(raw)
    return _payload_to_user(payload)


# Type aliases for FastAPI dependency injection
CurrentUser = Annotated[CurrentUserInfo, Depends(get_current_user)]
CurrentUserFlexible = Annotated[CurrentUserInfo, Depends(get_current_user_flexible)]
