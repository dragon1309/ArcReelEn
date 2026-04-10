"""Helpers for custom provider identifiers."""

CUSTOM_PROVIDER_PREFIX = "custom-"


def make_provider_id(db_id: int) -> str:
    """Build a custom-provider identifier such as ``custom-3``."""
    return f"{CUSTOM_PROVIDER_PREFIX}{db_id}"


def parse_provider_id(provider_id: str) -> int:
    """Extract the database ID from a ``custom-3`` style provider identifier.

    Raises:
        ValueError: if the format is invalid
    """
    return int(provider_id.removeprefix(CUSTOM_PROVIDER_PREFIX))


def is_custom_provider(provider_id: str) -> bool:
    """Return whether ``provider_id`` refers to a custom provider."""
    return provider_id.startswith(CUSTOM_PROVIDER_PREFIX)
