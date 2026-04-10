"""Shared OpenAI utilities reused by text, image, video, and provider layers."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

OPENAI_RETRYABLE_ERRORS: tuple[type[Exception], ...] = ()

try:
    from openai import (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )

    OPENAI_RETRYABLE_ERRORS = (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )
except ImportError:
    pass  # Defensive fallback even though openai is a required dependency.


def create_openai_client(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    max_retries: int | None = None,
) -> AsyncOpenAI:
    """Create an ``AsyncOpenAI`` client with normalized auth and base URL inputs."""
    kwargs: dict = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    return AsyncOpenAI(**kwargs)
