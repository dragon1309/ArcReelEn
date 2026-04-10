"""
Shared Ark helper utilities.

Reused by text backends, image backends, video backends, and provider adapters.

Includes:
- ``ARK_BASE_URL``: the Ark API base URL
- ``resolve_ark_api_key``: API key resolution with environment fallback
- ``create_ark_client``: Ark client factory
"""

from __future__ import annotations

import os

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def resolve_ark_api_key(api_key: str | None = None) -> str:
    """Resolve the Ark API key, with environment fallback support."""
    resolved = api_key or os.environ.get("ARK_API_KEY")
    if not resolved:
        raise ValueError("Ark API key is missing. Configure it in Settings > Providers.")
    return resolved


def create_ark_client(*, api_key: str | None = None):
    """Create an Ark client after validating the API key."""
    from volcenginesdkarkruntime import Ark

    return Ark(base_url=ARK_BASE_URL, api_key=resolve_ark_api_key(api_key))
