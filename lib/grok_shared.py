"""Shared Grok (xAI) client helpers."""

from __future__ import annotations


def create_grok_client(*, api_key: str | None = None):
    """Create an xAI ``AsyncClient`` with normalized validation."""
    import xai_sdk

    if not api_key:
        raise ValueError("XAI_API_KEY is not configured. Add it in the system settings page.")
    return xai_sdk.AsyncClient(api_key=api_key)
