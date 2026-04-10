"""Shared retry decorator with exponential backoff and jitter.

This module is provider-agnostic and can be reused by all backends. Individual
providers can pass their own retryable exception types through retryable_errors.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random

logger = logging.getLogger(__name__)

# Base retryable errors that do not depend on any SDK.
BASE_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
)

# Fallback string matching for transient errors whose exception types are not listed.
RETRYABLE_STATUS_PATTERNS = (
    "429",
    "resource_exhausted",
    "500",
    "502",
    "503",
    "504",
    "internalservererror",
    "internal server error",
    "serviceunavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "timed out",
    "timeout",
)

# Default retry settings so magic numbers are not duplicated across backends.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS: tuple[int, ...] = (2, 4, 8)


def _should_retry(exc: Exception, retryable_errors: tuple[type[Exception], ...]) -> bool:
    """Return whether an exception should be retried."""
    if isinstance(exc, retryable_errors):
        return True
    error_lower = str(exc).lower()
    return any(pattern in error_lower for pattern in RETRYABLE_STATUS_PATTERNS)


def with_retry_async(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: tuple[int, ...] = DEFAULT_BACKOFF_SECONDS,
    retryable_errors: tuple[type[Exception], ...] = BASE_RETRYABLE_ERRORS,
):
    """Retry decorator for async functions with exponential backoff and jitter."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if not _should_retry(e, retryable_errors):
                        raise

                    if attempt < max_attempts - 1:
                        backoff_idx = min(attempt, len(backoff_seconds) - 1)
                        base_wait = backoff_seconds[backoff_idx]
                        jitter = random.uniform(0, 2)
                        wait_time = base_wait + jitter
                        logger.warning(
                            "API call error: %s - %s",
                            type(e).__name__,
                            str(e)[:200],
                        )
                        logger.warning(
                            "Retry %d/%d in %.1f seconds...",
                            attempt + 1,
                            max_attempts - 1,
                            wait_time,
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        raise

            raise RuntimeError(f"with_retry_async: max_attempts={max_attempts}, no attempts were executed")

        return wrapper

    return decorator
