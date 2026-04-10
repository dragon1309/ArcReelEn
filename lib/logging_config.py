"""Shared logging configuration."""

import logging
import os

_HANDLER_ATTR = "_arcreel_logging"


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger.

    Args:
        level: Log level string such as DEBUG/INFO/WARNING/ERROR.
            When omitted, reads LOG_LEVEL from the environment and defaults to INFO.
    """
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Idempotent: avoid adding duplicate handlers.
    if any(getattr(h, _HANDLER_ATTR, False) for h in root.handlers):
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    setattr(handler, _HANDLER_ATTR, True)
    root.addHandler(handler)

    # Align uvicorn logging with the shared formatter.
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    # Disable uvicorn.access because request logging is handled by app.py middleware.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.disabled = True

    # Suppress noisy aiosqlite DEBUG logs.
    logging.getLogger("aiosqlite").setLevel(max(numeric_level, logging.INFO))
