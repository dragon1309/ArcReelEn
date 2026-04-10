"""Asset fingerprint computation based on mtime for cache-busting support."""

from pathlib import Path

# Media subdirectories to scan.
_MEDIA_SUBDIRS = ("storyboards", "videos", "thumbnails", "characters", "clues")

# Known media files that may live at the project root (for example style references).
_ROOT_MEDIA_SUFFIXES = frozenset((".png", ".jpg", ".jpeg", ".webp", ".mp4"))


def _scan_subdir(prefix: str, dir_path: Path, fingerprints: dict[str, int]) -> None:
    """Scan one media subdirectory and its first-level children, skipping ``versions/``."""
    for entry in dir_path.iterdir():
        if entry.is_file():
            fingerprints[f"{prefix}/{entry.name}"] = entry.stat().st_mtime_ns
        elif entry.is_dir() and entry.name != "versions":
            sub_prefix = f"{prefix}/{entry.name}"
            for sub_entry in entry.iterdir():
                if sub_entry.is_file():
                    fingerprints[f"{sub_prefix}/{sub_entry.name}"] = sub_entry.stat().st_mtime_ns


def compute_asset_fingerprints(project_path: Path) -> dict[str, int]:
    """Scan project media files and return ``{relative_path: mtime_ns}``.

    ``mtime_ns`` is used as a high-precision cache-busting token for asset URLs.
    The scan reads only filesystem metadata and is typically very fast.
    """
    fingerprints: dict[str, int] = {}

    for subdir in _MEDIA_SUBDIRS:
        dir_path = project_path / subdir
        if dir_path.is_dir():
            _scan_subdir(subdir, dir_path, fingerprints)

    # Root-level media files such as ``style_reference.png``.
    for f in project_path.iterdir():
        if f.is_file() and f.suffix.lower() in _ROOT_MEDIA_SUFFIXES:
            fingerprints[f.name] = f.stat().st_mtime_ns

    return fingerprints
