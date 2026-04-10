"""Utility helpers for normalizing provider base URLs."""

from __future__ import annotations

import re


def ensure_openai_base_url(url: str | None) -> str | None:
    """Append the ``/v1`` suffix for OpenAI-compatible APIs when missing."""
    if not url:
        return url
    stripped = url.strip().rstrip("/")
    if not re.search(r"/v\d+$", stripped):
        stripped += "/v1"
    return stripped


def normalize_base_url(url: str | None) -> str | None:
    """Ensure ``base_url`` ends with ``/``.

    Google GenAI SDK ``http_options.base_url`` expects a trailing slash, or URL
    path joining can fail.
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not url.endswith("/"):
        url += "/"
    return url


def ensure_google_base_url(url: str | None) -> str | None:
    """Normalize a Google GenAI SDK ``base_url`` value.

    The SDK appends ``api_version`` (``v1beta`` by default) automatically. If a
    user enters ``https://example.com/v1beta`` directly, the SDK may build an
    invalid URL like ``https://example.com/v1beta/v1beta/models``.

    This helper strips any trailing version segment such as ``/v1beta`` or
    ``/v1`` and then ensures the result ends with ``/``.
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    url = url.rstrip("/")
    # Strip trailing version segments such as /v1, /v1beta, or /v1alpha.
    url = re.sub(r"/v\d+\w*$", "", url)
    if not url.endswith("/"):
        url += "/"
    return url
