"""Compute runtime status and aggregate statistics for projects and scripts.

These fields are derived at read time to avoid storing redundant data on disk.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class StatusCalculator:
    """Calculate project and script status fields on demand."""

    def __init__(self, project_manager):
        """Initialize the calculator with a ``ProjectManager`` instance."""
        self.pm = project_manager

    @classmethod
    def _select_content_mode_and_items(cls, script: dict) -> tuple[str, list[dict]]:
        content_mode = script.get("content_mode")
        if content_mode in {"narration", "drama"}:
            if content_mode == "narration" and isinstance(script.get("segments"), list):
                return "narration", script.get("segments", [])
            if content_mode == "drama" and isinstance(script.get("scenes"), list):
                return "drama", script.get("scenes", [])

        if isinstance(script.get("segments"), list):
            return "narration", script.get("segments", [])
        if isinstance(script.get("scenes"), list):
            return "drama", script.get("scenes", [])

        return ("narration" if content_mode not in {"narration", "drama"} else content_mode), []

    def calculate_episode_stats(self, project_name: str, script: dict) -> dict:
        """Calculate summary statistics for a single episode script."""
        content_mode, items = self._select_content_mode_and_items(script)
        default_duration = 4 if content_mode == "narration" else 8

        # Aggregate generated asset counts.
        storyboard_done = sum(1 for i in items if i.get("generated_assets", {}).get("storyboard_image"))
        video_done = sum(1 for i in items if i.get("generated_assets", {}).get("video_clip"))
        total = len(items)

        # Derive the episode status from completed assets.
        if video_done == total and total > 0:
            status = "completed"
        elif storyboard_done > 0 or video_done > 0:
            status = "in_production"
        else:
            status = "draft"

        return {
            "scenes_count": total,
            "status": status,
            "duration_seconds": sum(i.get("duration_seconds", default_duration) for i in items),
            "storyboards": {"total": total, "completed": storyboard_done},
            "videos": {"total": total, "completed": video_done},
        }

    @staticmethod
    def _safe_exists(base: Path, rel_path: str) -> bool:
        """Return whether ``rel_path`` safely resolves inside ``base`` and exists."""
        if not rel_path:
            return False
        try:
            full = (base / rel_path).resolve()
            return full.is_relative_to(base.resolve()) and full.exists()
        except (OSError, ValueError):
            return False

    def _load_episode_script(
        self, project_name: str, episode_num: int, script_file: str, *, content_mode: str = "narration"
    ) -> tuple:
        """Load one episode script and return ``(script_status, script|None)``.

        ``script_status`` is one of ``generated``, ``segmented``, or ``none``.
        """
        try:
            script = self.pm.load_script(project_name, script_file)
            return "generated", script
        except FileNotFoundError:
            project_dir = self.pm.get_project_path(project_name)
            try:
                safe_num = int(episode_num)
            except (ValueError, TypeError):
                return "none", None
            draft_filename = "step1_segments.md" if content_mode == "narration" else "step1_normalized_script.md"
            draft_file = project_dir / f"drafts/episode_{safe_num}/{draft_filename}"
            return ("segmented" if draft_file.exists() else "none"), None
        except ValueError as e:
            logger.warning(
                "Skipping status calculation because script JSON is invalid or the path is unsafe "
                "project=%s file=%s: %s",
                project_name,
                script_file,
                e,
            )
            return "generated", None

    def calculate_current_phase(self, project: dict, episodes_stats: list[dict]) -> str:
        """Infer the current project phase from project and episode status."""
        if not project.get("overview"):
            return "setup"
        if not episodes_stats:
            return "worldbuilding"
        any_generated = any(s["script_status"] == "generated" for s in episodes_stats)
        all_generated = all(s["script_status"] == "generated" for s in episodes_stats)
        if not any_generated:
            return "worldbuilding"
        if not all_generated:
            return "scripting"
        all_completed = all(s["status"] == "completed" for s in episodes_stats)
        return "completed" if all_completed else "production"

    def _calculate_phase_progress(self, project: dict, phase: str, episodes_stats: list[dict]) -> float:
        """Calculate completion progress for the current phase on a 0.0-1.0 scale."""
        if phase == "setup":
            return 0.0
        if phase == "worldbuilding":
            return 0.0
        if phase == "scripting":
            total = len(episodes_stats)
            if total == 0:
                return 0.0
            done = sum(1 for s in episodes_stats if s["script_status"] == "generated")
            return done / total
        if phase == "production":
            total_videos = sum(s.get("videos", {}).get("total", 0) for s in episodes_stats)
            done_videos = sum(s.get("videos", {}).get("completed", 0) for s in episodes_stats)
            return done_videos / total_videos if total_videos > 0 else 0.0
        return 1.0  # completed

    @staticmethod
    def _make_fallback_ep_stats(script_status: str) -> dict:
        """Build default stats for episodes without a generated script."""
        return {
            "script_status": script_status,
            "status": "draft",
            "storyboards": {"total": 0, "completed": 0},
            "videos": {"total": 0, "completed": 0},
            "scenes_count": 0,
            "duration_seconds": 0,
        }

    def _build_episodes_stats(self, project_name: str, project: dict) -> list[dict]:
        """Iterate through all episodes and compute per-episode statistics."""
        content_mode = project.get("content_mode", "narration")
        episodes_stats = []
        for ep in project.get("episodes", []):
            script_file = ep.get("script_file", "")
            episode_num = ep.get("episode", 0)

            if script_file:
                script_status, script = self._load_episode_script(
                    project_name, episode_num, script_file, content_mode=content_mode
                )
            else:
                script_status, script = "none", None

            if script_status == "generated" and script is not None:
                ep_stats = self.calculate_episode_stats(project_name, script)
                if ep_stats["status"] == "draft":
                    ep_stats["status"] = "scripted"
                ep_stats["script_status"] = "generated"
            else:
                ep_stats = self._make_fallback_ep_stats(script_status)
            episodes_stats.append(ep_stats)
        return episodes_stats

    def calculate_project_status(
        self, project_name: str, project: dict, *, _preloaded_episodes_stats: list[dict] | None = None
    ) -> dict:
        """Calculate overall project status for list/detail API responses."""
        project_dir = self.pm.get_project_path(project_name)

        # Character asset stats.
        chars = project.get("characters", {})
        chars_total = len(chars)
        chars_done = sum(1 for c in chars.values() if self._safe_exists(project_dir, c.get("character_sheet", "")))

        # Clue asset stats across all clues.
        clues = project.get("clues", {})
        clues_total = len(clues)
        clues_done = sum(1 for c in clues.values() if self._safe_exists(project_dir, c.get("clue_sheet", "")))

        # Reuse preloaded episode stats when available to avoid duplicate I/O.
        if _preloaded_episodes_stats is not None:
            episodes_stats = _preloaded_episodes_stats
        else:
            episodes_stats = self._build_episodes_stats(project_name, project)

        phase = self.calculate_current_phase(project, episodes_stats)
        phase_progress = self._calculate_phase_progress(project, phase, episodes_stats)
        if phase == "worldbuilding":
            total_assets = chars_total + clues_total
            phase_progress = (chars_done + clues_done) / total_assets if total_assets > 0 else 0.0

        return {
            "current_phase": phase,
            "phase_progress": phase_progress,
            "characters": {"total": chars_total, "completed": chars_done},
            "clues": {"total": clues_total, "completed": clues_done},
            "episodes_summary": {
                "total": len(episodes_stats),
                "scripted": sum(1 for s in episodes_stats if s["script_status"] == "generated"),
                "in_production": sum(1 for s in episodes_stats if s["status"] == "in_production"),
                "completed": sum(1 for s in episodes_stats if s["status"] == "completed"),
            },
        }

    def enrich_project(self, project_name: str, project: dict) -> dict:
        """Inject computed fields into project data for detail API responses."""
        # Compute per-episode detail and collect summary stats.
        episodes_stats = self._build_episodes_stats(project_name, project)

        for ep, ep_stats in zip(project.get("episodes", []), episodes_stats):
            ep.update(ep_stats)

        # Reuse the preloaded episode stats to avoid loading scripts twice.
        project["status"] = self.calculate_project_status(
            project_name, project, _preloaded_episodes_stats=episodes_stats
        )
        return project

    def enrich_script(self, script: dict) -> dict:
        """Inject computed fields into script data for API responses."""
        content_mode, items = self._select_content_mode_and_items(script)
        default_duration = 4 if content_mode == "narration" else 8

        total_duration = sum(i.get("duration_seconds", default_duration) for i in items)

        # Populate computed metadata fields.
        if "metadata" not in script:
            script["metadata"] = {}

        script["metadata"]["total_scenes"] = len(items)
        script["metadata"]["estimated_duration_seconds"] = total_duration
        script["duration_seconds"] = total_duration  # Injected at read time to mirror metadata.

        # Aggregate episode-level character and clue references for API responses only.
        chars_set = set()
        clues_set = set()

        char_field = "characters_in_segment" if content_mode == "narration" else "characters_in_scene"
        clue_field = "clues_in_segment" if content_mode == "narration" else "clues_in_scene"

        for item in items:
            chars_set.update(item.get(char_field, []))
            clues_set.update(item.get(clue_field, []))

        script["characters_in_episode"] = sorted(chars_set)
        script["clues_in_episode"] = sorted(clues_set)

        return script
