"""Shared validation helpers reused by multiple routers."""

from __future__ import annotations

from fastapi import HTTPException

from lib.config.registry import PROVIDER_REGISTRY

# Legacy provider name -> canonical registry provider_id.
# Keep this aligned with generation_worker._normalize_provider_id().
_LEGACY_PROVIDER_NAMES: dict[str, str] = {
    "gemini": "gemini-aistudio",
    "vertex": "gemini-vertex",
    "seedance": "ark",
}


def validate_backend_value(value: str, field_name: str) -> None:
    """Validate a backend value that should use ``provider/model`` format.

    Legacy single-provider values such as ``"gemini"`` are still accepted so
    older projects can be normalized downstream.

    Raises:
        HTTPException(400): The format is invalid or the provider is unknown.
    """
    if "/" not in value:
        if value in _LEGACY_PROVIDER_NAMES or value in PROVIDER_REGISTRY:
            return  # Legacy format or bare registry id; normalized downstream.
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must use provider/model format",
        )
    provider_id = value.split("/", 1)[0]
    if provider_id not in PROVIDER_REGISTRY and not provider_id.startswith("custom-"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {provider_id}",
        )
