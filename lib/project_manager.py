"""Project file manager and metadata utilities."""

import fcntl
import json
import logging
import os
import re
import secrets
import tempfile
import unicodedata
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from lib.project_change_hints import emit_project_change_hint

logger = logging.getLogger(__name__)

PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")
PROJECT_SLUG_SANITIZER = re.compile(r"[^a-zA-Z0-9]+")

# ==================== Data Models ====================


class ProjectOverview(BaseModel):
    """Project overview schema for structured outputs."""

    synopsis: str = Field(description="Story synopsis, roughly 200-300 words summarizing the main plot")
    genre: str = Field(description="Genre label")
    theme: str = Field(description="Core theme")
    world_setting: str = Field(description="World setting and background")


class ProjectManager:
    """Video project manager."""

    # Project subdirectory layout.
    SUBDIRS = [
        "source",
        "scripts",
        "drafts",
        "characters",
        "clues",
        "storyboards",
        "videos",
        "thumbnails",
        "output",
    ]

    # Project metadata filename.
    PROJECT_FILE = "project.json"

    @staticmethod
    def normalize_project_name(name: str) -> str:
        """Validate and normalize a project identifier."""
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("Project identifier cannot be empty")
        if not PROJECT_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("Project identifier may contain only letters, numbers, and hyphens")
        return normalized

    @staticmethod
    def _slugify_project_title(title: str) -> str:
        """Build a filesystem-safe slug prefix from the project title."""
        ascii_text = unicodedata.normalize("NFKD", str(title).strip()).encode("ascii", "ignore").decode("ascii")
        slug = PROJECT_SLUG_SANITIZER.sub("-", ascii_text).strip("-_").lower()
        return slug[:24] or "project"

    def generate_project_name(self, title: str | None = None) -> str:
        """Generate a unique internal project identifier."""
        prefix = self._slugify_project_title(title or "")
        while True:
            candidate = f"{prefix}-{secrets.token_hex(4)}"
            if not (self.projects_root / candidate).exists():
                return candidate

    @classmethod
    def from_cwd(cls) -> tuple["ProjectManager", str]:
        """Infer ``ProjectManager`` and the project name from the current directory."""
        cwd = Path.cwd().resolve()
        project_name = cwd.name
        projects_root = cwd.parent
        pm = cls(projects_root)
        if not (projects_root / project_name / cls.PROJECT_FILE).exists():
            raise FileNotFoundError(f"Current directory is not a valid project directory: {cwd}")
        return pm, project_name

    def __init__(self, projects_root: str | None = None):
        """Initialize the project manager."""
        if projects_root is None:
            # Try the environment variable first, then fall back to the default path.
            projects_root = os.environ.get("AI_ANIME_PROJECTS", "projects")

        self.projects_root = Path(projects_root)
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def list_projects(self) -> list[str]:
        """List all projects."""
        return [d.name for d in self.projects_root.iterdir() if d.is_dir() and not d.name.startswith(".")]

    def create_project(self, name: str) -> Path:
        """Create a new project and return its directory path."""
        name = self.normalize_project_name(name)
        project_dir = self.projects_root / name

        if project_dir.exists():
            raise FileExistsError(f"Project '{name}' already exists")

        # Create all project subdirectories.
        for subdir in self.SUBDIRS:
            (project_dir / subdir).mkdir(parents=True, exist_ok=True)

        self.repair_claude_symlink(project_dir)

        return project_dir

    def repair_claude_symlink(self, project_dir: Path) -> dict:
        """Repair the ``.claude`` and ``CLAUDE.md`` symlinks in a project directory."""
        project_root = self.projects_root.parent
        profile_dir = project_root / "agent_runtime_profile"

        SYMLINKS = {
            ".claude": profile_dir / ".claude",
            "CLAUDE.md": profile_dir / "CLAUDE.md",
        }
        REL_TARGETS = {
            ".claude": Path("../../agent_runtime_profile/.claude"),
            "CLAUDE.md": Path("../../agent_runtime_profile/CLAUDE.md"),
        }

        stats = {"created": 0, "repaired": 0, "skipped": 0, "errors": 0}
        for name, target_source in SYMLINKS.items():
            if not target_source.exists():
                continue
            symlink_path = project_dir / name
            if symlink_path.is_symlink() and not symlink_path.exists():
                # Broken symlink.
                try:
                    symlink_path.unlink()
                    symlink_path.symlink_to(REL_TARGETS[name])
                    stats["repaired"] += 1
                except OSError as e:
                    logger.warning("Unable to repair %s symlink %s: %s", project_dir.name, name, e)
                    stats["errors"] += 1
            elif not symlink_path.exists() and not symlink_path.is_symlink():
                # Missing link.
                try:
                    symlink_path.symlink_to(REL_TARGETS[name])
                    stats["created"] += 1
                except OSError as e:
                    logger.warning("Unable to create symlink %s for project %s: %s", name, project_dir.name, e)
                    stats["errors"] += 1
            else:
                stats["skipped"] += 1
        return stats

    def repair_all_symlinks(self) -> dict:
        """Scan all project directories and repair their symlinks."""
        totals = {"created": 0, "repaired": 0, "skipped": 0, "errors": 0}
        if not self.projects_root.exists():
            return totals
        for project_dir in sorted(self.projects_root.iterdir()):
            if not project_dir.is_dir() or project_dir.name.startswith("."):
                continue
            try:
                result = self.repair_claude_symlink(project_dir)
                for key in ("created", "repaired", "skipped", "errors"):
                    totals[key] += result.get(key, 0)
            except Exception as e:
                logger.warning("Error while repairing symlinks for project %s: %s", project_dir.name, e)
                totals["errors"] += 1
        return totals

    def get_project_path(self, name: str) -> Path:
        """Return the project path with path-traversal protection."""
        name = self.normalize_project_name(name)
        real = os.path.realpath(self.projects_root / name)
        base = os.path.realpath(self.projects_root) + os.sep
        if not real.startswith(base):
            raise ValueError(f"Invalid project name: '{name}'")
        project_dir = Path(real)
        if not project_dir.exists():
            raise FileNotFoundError(f"Project '{name}' does not exist")
        return project_dir

    @staticmethod
    def _safe_subpath(base_dir: Path, filename: str) -> str:
        """Validate that ``filename`` stays inside ``base_dir`` and return its real path."""
        real = os.path.realpath(base_dir / filename)
        bound = os.path.realpath(base_dir) + os.sep
        if not real.startswith(bound):
            raise ValueError(f"Invalid filename: '{filename}'")
        return real

    def get_project_status(self, name: str) -> dict[str, Any]:
        """Return the current project status snapshot."""
        project_dir = self.get_project_path(name)

        status = {
            "name": name,
            "path": str(project_dir),
            "source_files": [],
            "scripts": [],
            "characters": [],
            "clues": [],
            "storyboards": [],
            "videos": [],
            "outputs": [],
            "current_stage": "empty",
        }

        # Inspect the contents of each project directory.
        for subdir in self.SUBDIRS:
            subdir_path = project_dir / subdir
            if subdir_path.exists():
                files = list(subdir_path.glob("*"))
                if subdir == "source":
                    status["source_files"] = [f.name for f in files if f.is_file()]
                elif subdir == "scripts":
                    status["scripts"] = [f.name for f in files if f.suffix == ".json"]
                elif subdir == "characters":
                    status["characters"] = [f.name for f in files if f.suffix in [".png", ".jpg", ".jpeg"]]
                elif subdir == "clues":
                    status["clues"] = [f.name for f in files if f.suffix in [".png", ".jpg", ".jpeg"]]
                elif subdir == "storyboards":
                    status["storyboards"] = [f.name for f in files if f.suffix in [".png", ".jpg", ".jpeg"]]
                elif subdir == "videos":
                    status["videos"] = [f.name for f in files if f.suffix in [".mp4", ".webm"]]
                elif subdir == "output":
                    status["outputs"] = [f.name for f in files if f.suffix in [".mp4", ".webm"]]

        # Determine the current stage.
        if status["outputs"]:
            status["current_stage"] = "completed"
        elif status["videos"]:
            status["current_stage"] = "videos_generated"
        elif status["storyboards"]:
            status["current_stage"] = "storyboards_generated"
        elif status["characters"]:
            status["current_stage"] = "characters_generated"
        elif status["scripts"]:
            status["current_stage"] = "script_created"
        elif status["source_files"]:
            status["current_stage"] = "source_ready"
        else:
            status["current_stage"] = "empty"

        return status

    # ==================== Script Operations ====================

    def create_script(self, project_name: str, title: str, chapter: str) -> dict:
        """Create a new storyboard-script template."""
        script = {
            "novel": {"title": title, "chapter": chapter},
            "scenes": [],
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "total_scenes": 0,
                "estimated_duration_seconds": 0,
                "status": "draft",
            },
        }

        return script

    def save_script(self, project_name: str, script: dict, filename: str | None = None) -> Path:
        """Save a script and return the output path."""
        project_dir = self.get_project_path(project_name)
        scripts_dir = project_dir / "scripts"

        if filename is not None and filename.startswith("scripts/"):
            filename = filename[len("scripts/") :]

        if filename is None:
            chapter = script["novel"].get("chapter", "chapter_01")
            filename = f"{chapter.replace(' ', '_')}_script.json"

        # Update metadata, including compatibility with older script shapes.
        now = datetime.now().isoformat()
        metadata = script.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            script["metadata"] = metadata
        metadata.setdefault("created_at", now)
        metadata.setdefault("status", "draft")
        metadata["updated_at"] = now

        scenes = script.get("scenes", [])
        if not isinstance(scenes, list):
            scenes = []
        segments = script.get("segments", [])
        if not isinstance(segments, list):
            segments = []

        content_mode = script.get("content_mode", "narration")
        if content_mode == "narration" and segments:
            items = segments
            items_type = "segments"
        elif scenes:
            items = scenes
            items_type = "scenes"
        else:
            items = segments
            items_type = "segments"

        metadata["total_scenes"] = len(items)

        # Compute total duration based on the active data shape.
        default_duration = 4 if items_type == "segments" else 8
        total_duration = sum(item.get("duration_seconds", default_duration) for item in items)
        metadata["estimated_duration_seconds"] = total_duration

        # Save the file with path traversal protection.
        real = self._safe_subpath(scripts_dir, filename)
        with open(real, "w", encoding="utf-8") as f:  # noqa: PTH123
            json.dump(script, f, ensure_ascii=False, indent=2)
        output_path = Path(real)

        emit_project_change_hint(
            project_name,
            changed_paths=[f"scripts/{output_path.name}"],
        )

        # Automatically sync episode metadata back into project.json.
        if self.project_exists(project_name) and isinstance(script.get("episode"), int):
            self.sync_episode_from_script(project_name, filename)

        return output_path

    def sync_episode_from_script(self, project_name: str, script_filename: str) -> dict:
        """Sync episode metadata from a script file back into ``project.json``."""
        script = self.load_script(project_name, script_filename)
        project = self.load_project(project_name)

        episode_num = script.get("episode", 1)
        episode_title = script.get("title", "")
        script_file = f"scripts/{script_filename}"

        # Find or create the episode entry.
        episodes = project.setdefault("episodes", [])
        episode_entry = next((ep for ep in episodes if ep["episode"] == episode_num), None)

        if episode_entry is None:
            episode_entry = {"episode": episode_num}
            episodes.append(episode_entry)

        # Sync core metadata only. Status fields are calculated at read time.
        episode_entry["title"] = episode_title
        episode_entry["script_file"] = script_file

        # Sort and save.
        episodes.sort(key=lambda x: x["episode"])
        self.save_project(project_name, project)

        logger.info("Synchronized episode metadata: Episode %d - %s", episode_num, episode_title)
        return project

    def load_script(self, project_name: str, filename: str) -> dict:
        """Load a storyboard script file."""
        project_dir = self.get_project_path(project_name)
        if filename.startswith("scripts/"):
            filename = filename[len("scripts/") :]
        real = self._safe_subpath(project_dir / "scripts", filename)

        if not os.path.exists(real):
            raise FileNotFoundError(f"Script file does not exist: {real}")

        with open(real, encoding="utf-8") as f:  # noqa: PTH123
            return json.load(f)

    def list_scripts(self, project_name: str) -> list[str]:
        """List all scripts in a project."""
        project_dir = self.get_project_path(project_name)
        scripts_dir = project_dir / "scripts"
        return [f.name for f in scripts_dir.glob("*.json")]

    # ==================== Character Management ====================

    def update_character_sheet(self, project_name: str, script_filename: str, name: str, sheet_path: str) -> dict:
        """Update the path to a character sheet image."""
        script = self.load_script(project_name, script_filename)

        if name not in script["characters"]:
            raise KeyError(f"Character '{name}' does not exist")

        script["characters"][name]["character_sheet"] = sheet_path
        self.save_script(project_name, script, script_filename)
        return script

    # ==================== Data Normalization ====================

    @staticmethod
    def create_generated_assets(content_mode: str = "narration") -> dict:
        """Create the standard ``generated_assets`` structure."""
        return {
            "storyboard_image": None,
            "video_clip": None,
            "video_thumbnail": None,
            "video_uri": None,
            "status": "pending",
        }

    @staticmethod
    def create_scene_template(scene_id: str, episode: int = 1, duration_seconds: int = 8) -> dict:
        """Create the standard scene object template."""
        return {
            "scene_id": scene_id,
            "episode": episode,
            "title": "",
            "scene_type": "story",
            "duration_seconds": duration_seconds,
            "segment_break": False,
            "characters_in_scene": [],
            "clues_in_scene": [],
            "visual": {
                "description": "",
                "shot_type": "medium shot",
                "camera_movement": "static",
                "lighting": "",
                "mood": "",
            },
            "action": "",
            "dialogue": {"speaker": "", "text": "", "emotion": "neutral"},
            "audio": {"dialogue": [], "narration": "", "sound_effects": []},
            "transition_to_next": "cut",
            "generated_assets": ProjectManager.create_generated_assets(),
        }

    def normalize_scene(self, scene: dict, episode: int = 1) -> dict:
        """Fill in any missing fields in a single scene dict."""
        template = self.create_scene_template(
            scene_id=scene.get("scene_id", "000"),
            episode=episode,
            duration_seconds=scene.get("duration_seconds", 8),
        )

        # Merge the visual field.
        if "visual" not in scene:
            scene["visual"] = template["visual"]
        else:
            for key in template["visual"]:
                if key not in scene["visual"]:
                    scene["visual"][key] = template["visual"][key]

        # Merge the audio field.
        if "audio" not in scene:
            scene["audio"] = template["audio"]
        else:
            for key in template["audio"]:
                if key not in scene["audio"]:
                    scene["audio"][key] = template["audio"][key]

        # Fill in generated_assets.
        if "generated_assets" not in scene:
            scene["generated_assets"] = self.create_generated_assets()
        else:
            assets_template = self.create_generated_assets()
            for key in assets_template:
                if key not in scene["generated_assets"]:
                    scene["generated_assets"][key] = assets_template[key]

        # Fill in other top-level fields.
        top_level_defaults = {
            "episode": episode,
            "title": "",
            "scene_type": "story",
            "segment_break": False,
            "characters_in_scene": [],
            "clues_in_scene": [],
            "action": "",
            "dialogue": template["dialogue"],
            "transition_to_next": "cut",
        }

        for key, default_value in top_level_defaults.items():
            if key not in scene:
                scene[key] = default_value

        # Update status.
        self.update_scene_status(scene)

        return scene

    def update_scene_status(self, scene: dict) -> str:
        """Update and return scene status based on ``generated_assets`` content."""
        assets = scene.get("generated_assets", {})

        has_image = bool(assets.get("storyboard_image"))
        has_video = bool(assets.get("video_clip"))

        if has_video:
            status = "completed"
        elif has_image:
            status = "storyboard_ready"
        else:
            status = "pending"

        assets["status"] = status
        return status

    def normalize_script(self, project_name: str, script_filename: str, save: bool = True) -> dict:
        """Fill in missing fields inside an existing ``script.json`` payload."""
        import re

        script = self.load_script(project_name, script_filename)

        # Infer the episode number from the filename or existing data.
        episode = script.get("episode", 1)
        if not episode:
            match = re.search(r"episode[_\s]*(\d+)", script_filename, re.IGNORECASE)
            if match:
                episode = int(match.group(1))
            else:
                episode = 1

        # Fill in missing top-level fields.
        script_defaults = {
            "episode": episode,
            "title": script.get("novel", {}).get("chapter", ""),
            "duration_seconds": 0,
            "summary": "",
        }

        for key, default_value in script_defaults.items():
            if key not in script:
                script[key] = default_value

        # Ensure required top-level structures exist.
        if "novel" not in script:
            script["novel"] = {"title": "", "chapter": ""}
        # Strip deprecated ``source_file`` fields.
        if isinstance(script.get("novel"), dict):
            script["novel"].pop("source_file", None)

        # Handle legacy format: sync characters into project.json.
        if "characters" in script and isinstance(script["characters"], dict) and script["characters"]:
            logger.warning("Detected legacy characters object; automatically syncing to project.json")
            self.sync_characters_from_script(project_name, script_filename)
            # ``sync_characters_from_script`` reloads and saves the script, so reload it here too.
            script = self.load_script(project_name, script_filename)

        # Handle legacy format: sync clues into project.json.
        if "clues" in script and isinstance(script["clues"], dict) and script["clues"]:
            logger.warning("Detected legacy clues object; automatically syncing to project.json")
            self.sync_clues_from_script(project_name, script_filename)
            script = self.load_script(project_name, script_filename)

        # characters_in_episode and clues_in_episode are now computed at read time.

        if "scenes" not in script:
            script["scenes"] = []

        if "metadata" not in script:
            script["metadata"] = {
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "total_scenes": 0,
                "estimated_duration_seconds": 0,
                "status": "draft",
            }

        # Normalize every scene.
        for scene in script["scenes"]:
            self.normalize_scene(scene, episode)

        # Update summary metadata.
        script["metadata"]["total_scenes"] = len(script["scenes"])
        script["metadata"]["estimated_duration_seconds"] = sum(s.get("duration_seconds", 8) for s in script["scenes"])
        script["duration_seconds"] = script["metadata"]["estimated_duration_seconds"]

        if save:
            self.save_script(project_name, script, script_filename)
            logger.info("Normalized and saved script: %s", script_filename)

        return script

    # ==================== Scene Management ====================

    def add_scene(self, project_name: str, script_filename: str, scene: dict) -> dict:
        """Add a scene to a script and return the updated script."""
        script = self.load_script(project_name, script_filename)

        # Generate a scene ID automatically.
        existing_ids = [s["scene_id"] for s in script["scenes"]]
        next_id = f"{len(existing_ids) + 1:03d}"
        scene["scene_id"] = next_id

        # Ensure a ``generated_assets`` field exists.
        if "generated_assets" not in scene:
            scene["generated_assets"] = {
                "storyboard_image": None,
                "video_clip": None,
                "status": "pending",
            }

        script["scenes"].append(scene)
        self.save_script(project_name, script, script_filename)
        return script

    def update_scene_asset(
        self,
        project_name: str,
        script_filename: str,
        scene_id: str,
        asset_type: str,
        asset_path: str,
    ) -> dict:
        """Update the generated asset path for a scene or segment."""
        script = self.load_script(project_name, script_filename)

        # Select the correct data structure based on content mode.
        content_mode = script.get("content_mode", "narration")
        if content_mode == "narration" and "segments" in script:
            items = script["segments"]
            id_field = "segment_id"
        else:
            items = script.get("scenes", [])
            id_field = "scene_id"

        for item in items:
            if str(item.get(id_field)) == str(scene_id):
                assets = item.get("generated_assets")
                if not isinstance(assets, dict):
                    assets = {}
                    item["generated_assets"] = assets

                assets_template = self.create_generated_assets(content_mode)
                for key, default_value in assets_template.items():
                    if key not in assets:
                        assets[key] = default_value

                assets[asset_type] = asset_path

                # Recalculate status after the asset update.
                self.update_scene_status(item)

                self.save_script(project_name, script, script_filename)
                return script

        raise KeyError(f"Scene '{scene_id}' does not exist")

    def get_pending_scenes(self, project_name: str, script_filename: str, asset_type: str) -> list[dict]:
        """Return the list of scenes or segments still missing a given asset type."""
        script = self.load_script(project_name, script_filename)

        # Select the correct data structure based on content mode.
        content_mode = script.get("content_mode", "narration")
        if content_mode == "narration" and "segments" in script:
            items = script["segments"]
        else:
            items = script.get("scenes", [])

        return [item for item in items if not item["generated_assets"].get(asset_type)]

    # ==================== File Path Helpers ====================

    def get_source_path(self, project_name: str, filename: str) -> Path:
        """Return the path for a source file."""
        return self.get_project_path(project_name) / "source" / filename

    def get_character_path(self, project_name: str, filename: str) -> Path:
        """Return the path for a character sheet file."""
        return self.get_project_path(project_name) / "characters" / filename

    def get_storyboard_path(self, project_name: str, filename: str) -> Path:
        """Return the path for a storyboard image."""
        return self.get_project_path(project_name) / "storyboards" / filename

    def get_video_path(self, project_name: str, filename: str) -> Path:
        """Return the path for a video file."""
        return self.get_project_path(project_name) / "videos" / filename

    def get_output_path(self, project_name: str, filename: str) -> Path:
        """Return the path for an output file."""
        return self.get_project_path(project_name) / "output" / filename

    def get_scenes_needing_storyboard(self, project_name: str, script_filename: str) -> list[dict]:
        """Return scenes or segments that still need storyboard images."""
        script = self.load_script(project_name, script_filename)

        content_mode = script.get("content_mode", "narration")
        if content_mode == "narration" and "segments" in script:
            items = script["segments"]
        else:
            items = script.get("scenes", [])

        return [item for item in items if not item.get("generated_assets", {}).get("storyboard_image")]

    # ==================== Project Metadata ====================

    def _get_project_file_path(self, project_name: str) -> Path:
        """Return the metadata file path for a project."""
        return self.get_project_path(project_name) / self.PROJECT_FILE

    def project_exists(self, project_name: str) -> bool:
        """Return whether a project's metadata file exists."""
        try:
            return self._get_project_file_path(project_name).exists()
        except FileNotFoundError:
            return False

    def load_project_raw(self, project_name: str) -> dict:
        """
        Load project metadata without enforcing the language cutover.
        """
        project_file = self._get_project_file_path(project_name)

        if not project_file.exists():
            raise FileNotFoundError(f"Project metadata file does not exist: {project_file}")

        with open(project_file, encoding="utf-8") as f:
            return json.load(f)

    def load_project(self, project_name: str) -> dict:
        """Load project metadata and enforce the English-only language contract."""
        project = self.load_project_raw(project_name)
        language = project.get("language")
        if language != "en":
            raise ValueError(
                f"Project '{project_name}' must be migrated before use. Expected project.json language 'en', got {language!r}."
            )
        return project

    @contextmanager
    def _project_lock(self, project_name: str):
        """Acquire an exclusive lock for project metadata using a dedicated lock file."""
        lock_path = self._get_project_file_path(project_name).with_suffix(".lock")
        lock_path.touch(exist_ok=True)
        fd = open(lock_path)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()

    @staticmethod
    def _atomic_write_json(path: Path, data: dict) -> None:
        """Atomically write JSON using a temp file plus ``os.replace``."""
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(path.parent),
                prefix=".project.",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                json.dump(data, tmp, ensure_ascii=False, indent=2)
                tmp_path = Path(tmp.name)
            os.replace(tmp_path, path)
            tmp_path = None
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def save_project(self, project_name: str, project: dict) -> Path:
        """Save project metadata and return the path to ``project.json``."""
        project_file = self._get_project_file_path(project_name)

        self._touch_metadata(project)

        with self._project_lock(project_name):
            self._atomic_write_json(project_file, project)

        emit_project_change_hint(
            project_name,
            changed_paths=[self.PROJECT_FILE],
        )

        return project_file

    def update_project(
        self,
        project_name: str,
        mutate_fn: Callable[[dict], None],
    ) -> Path:
        """Atomically update ``project.json`` under a file lock."""
        project_file = self._get_project_file_path(project_name)

        with self._project_lock(project_name):
            with open(project_file, encoding="utf-8") as f:
                project = json.load(f)
            mutate_fn(project)
            self._touch_metadata(project)
            self._atomic_write_json(project_file, project)

        emit_project_change_hint(
            project_name,
            changed_paths=[self.PROJECT_FILE],
        )

        return project_file

    @staticmethod
    def _touch_metadata(project: dict) -> None:
        now = datetime.now().isoformat()
        project.setdefault("language", "en")
        if "metadata" not in project:
            project["metadata"] = {"created_at": now, "updated_at": now}
        else:
            project["metadata"]["updated_at"] = now

    def create_project_metadata(
        self,
        project_name: str,
        title: str | None = None,
        style: str | None = None,
        content_mode: str = "narration",
        aspect_ratio: str = "9:16",
        default_duration: int | None = None,
    ) -> dict:
        """Create and persist a new ``project.json`` metadata payload."""
        project_name = self.normalize_project_name(project_name)
        project_title = str(title).strip() if title is not None else ""

        project = {
            "language": "en",
            "title": project_title or project_name,
            "content_mode": content_mode,
            "aspect_ratio": aspect_ratio,
            "style": style or "",
            "episodes": [],
            "characters": {},
            "clues": {},
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
        }
        if default_duration is not None:
            project["default_duration"] = default_duration

        self.save_project(project_name, project)
        return project

    def add_episode(self, project_name: str, episode: int, title: str, script_file: str) -> dict:
        """Add or update an episode entry in project metadata."""
        project = self.load_project(project_name)

        # Update the existing episode entry if present.
        for ep in project["episodes"]:
            if ep["episode"] == episode:
                ep["title"] = title
                ep["script_file"] = script_file
                self.save_project(project_name, project)
                return project

        # Add a new episode entry without persisted computed stats.
        project["episodes"].append({"episode": episode, "title": title, "script_file": script_file})

        # Keep episodes sorted by episode number.
        project["episodes"].sort(key=lambda x: x["episode"])

        self.save_project(project_name, project)
        return project

    def sync_project_status(self, project_name: str) -> dict:
        """Deprecated compatibility shim returning project data without writing status."""
        import warnings

        warnings.warn(
            "sync_project_status() is deprecated. Status fields are now computed by StatusCalculator at read time.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Return project data only; do not write anything.
        return self.load_project(project_name)

    # ==================== Project-Level Characters ====================

    def add_project_character(
        self,
        project_name: str,
        name: str,
        description: str,
        voice_style: str | None = None,
        character_sheet: str | None = None,
    ) -> dict:
        """Add a project-level character definition."""
        project = self.load_project(project_name)

        project["characters"][name] = {
            "description": description,
            "voice_style": voice_style or "",
            "character_sheet": character_sheet or "",
        }

        self.save_project(project_name, project)
        return project

    def update_project_character_sheet(self, project_name: str, name: str, sheet_path: str) -> dict:
        """Update the project-level character sheet path."""
        project = self.load_project(project_name)

        if name not in project["characters"]:
            raise KeyError(f"Character '{name}' does not exist")

        project["characters"][name]["character_sheet"] = sheet_path
        self.save_project(project_name, project)
        return project

    def update_character_reference_image(self, project_name: str, char_name: str, ref_path: str) -> dict:
        """Update the reference-image path for a character."""
        project = self.load_project(project_name)

        if "characters" not in project or char_name not in project["characters"]:
            raise KeyError(f"Character '{char_name}' does not exist")

        project["characters"][char_name]["reference_image"] = ref_path
        self.save_project(project_name, project)
        return project

    def get_project_character(self, project_name: str, name: str) -> dict:
        """Return the project-level definition for a character."""
        project = self.load_project(project_name)

        if name not in project["characters"]:
            raise KeyError(f"Character '{name}' does not exist")

        return project["characters"][name]

    # ==================== Clue Management ====================

    def update_clue_sheet(self, project_name: str, name: str, sheet_path: str) -> dict:
        """Update the sheet path for a clue."""
        project = self.load_project(project_name)

        if name not in project["clues"]:
            raise KeyError(f"Clue '{name}' does not exist")

        project["clues"][name]["clue_sheet"] = sheet_path
        self.save_project(project_name, project)
        return project

    def get_clue(self, project_name: str, name: str) -> dict:
        """
        Return a clue definition from project metadata.

        Args:
            project_name: project identifier
            name: clue name

        Returns:
            Clue definition dictionary
        """
        project = self.load_project(project_name)

        if name not in project["clues"]:
            raise KeyError(f"Clue '{name}' does not exist")

        return project["clues"][name]

    def get_pending_characters(self, project_name: str) -> list[dict]:
        """Return characters still missing generated or existing sheets."""
        project = self.load_project(project_name)
        project_dir = self.get_project_path(project_name)

        pending = []
        for name, char in project.get("characters", {}).items():
            sheet = char.get("character_sheet")
            if not sheet or not (project_dir / sheet).exists():
                pending.append({"name": name, **char})

        return pending

    def get_pending_clues(self, project_name: str) -> list[dict]:
        """Return major clues still missing generated or existing sheets."""
        project = self.load_project(project_name)
        project_dir = self.get_project_path(project_name)

        pending = []
        for name, clue in project["clues"].items():
            if clue.get("importance") == "major":
                sheet = clue.get("clue_sheet")
                if not sheet or not (project_dir / sheet).exists():
                    pending.append({"name": name, **clue})

        return pending

    def get_clue_path(self, project_name: str, filename: str) -> Path:
        """Return the path for a clue sheet file."""
        return self.get_project_path(project_name) / "clues" / filename

    # ==================== Direct Character/Clue Writes ====================

    def add_character(self, project_name: str, name: str, description: str, voice_style: str = "") -> bool:
        """Add a character directly to ``project.json`` if it does not already exist."""
        project = self.load_project(project_name)

        if name in project.get("characters", {}):
            logger.debug("Character '%s' already exists in project.json; skipping", name)
            return False

        if "characters" not in project:
            project["characters"] = {}

        project["characters"][name] = {
            "description": description,
            "character_sheet": "",
            "voice_style": voice_style,
        }

        self.save_project(project_name, project)
        logger.info("Added character: %s", name)
        return True

    def add_clue(
        self,
        project_name: str,
        name: str,
        clue_type: str,
        description: str,
        importance: str = "minor",
    ) -> bool:
        """Add a clue directly to ``project.json`` if it does not already exist."""
        project = self.load_project(project_name)

        if name in project.get("clues", {}):
            logger.debug("Clue '%s' already exists in project.json; skipping", name)
            return False

        if "clues" not in project:
            project["clues"] = {}

        project["clues"][name] = {
            "type": clue_type,
            "description": description,
            "importance": importance,
            "clue_sheet": "",
        }

        self.save_project(project_name, project)
        logger.info("Added clue: %s", name)
        return True

    def add_characters_batch(self, project_name: str, characters: dict[str, dict]) -> int:
        """Add multiple characters to ``project.json`` and return the number added."""
        project = self.load_project(project_name)

        if "characters" not in project:
            project["characters"] = {}

        added = 0
        for name, data in characters.items():
            if name not in project["characters"]:
                project["characters"][name] = {
                    "description": data.get("description", ""),
                    "character_sheet": data.get("character_sheet", ""),
                    "voice_style": data.get("voice_style", ""),
                }
                added += 1
                logger.info("Added character: %s", name)
            else:
                logger.debug("Character '%s' already exists; skipping", name)

        if added > 0:
            self.save_project(project_name, project)

        return added

    def add_clues_batch(self, project_name: str, clues: dict[str, dict]) -> int:
        """Add multiple clues to ``project.json`` and return the number added."""
        project = self.load_project(project_name)

        if "clues" not in project:
            project["clues"] = {}

        added = 0
        for name, data in clues.items():
            if name not in project["clues"]:
                project["clues"][name] = {
                    "type": data.get("type", "prop"),
                    "description": data.get("description", ""),
                    "importance": data.get("importance", "minor"),
                    "clue_sheet": data.get("clue_sheet", ""),
                }
                added += 1
                logger.info("Added clue: %s", name)
            else:
                logger.debug("Clue '%s' already exists; skipping", name)

        if added > 0:
            self.save_project(project_name, project)

        return added

    # ==================== Reference Image Collection ====================

    def collect_reference_images(self, project_name: str, scene: dict) -> list[Path]:
        """Collect all reference images required by a scene."""
        project = self.load_project(project_name)
        project_dir = self.get_project_path(project_name)
        refs = []

        # Character reference images.
        for char in scene.get("characters_in_scene", []):
            char_data = project["characters"].get(char, {})
            sheet = char_data.get("character_sheet")
            if sheet:
                sheet_path = project_dir / sheet
                if sheet_path.exists():
                    refs.append(sheet_path)

        # Clue reference images.
        for clue in scene.get("clues_in_scene", []):
            clue_data = project["clues"].get(clue, {})
            sheet = clue_data.get("clue_sheet")
            if sheet:
                sheet_path = project_dir / sheet
                if sheet_path.exists():
                    refs.append(sheet_path)

        return refs

    # ==================== Overview Generation ====================

    def _read_source_files(self, project_name: str, max_chars: int = 50000) -> str:
        """Read text files from the project's ``source`` directory up to ``max_chars``."""
        project_dir = self.get_project_path(project_name)
        source_dir = project_dir / "source"

        if not source_dir.exists():
            return ""

        contents = []
        total_chars = 0

        # Sort by filename to keep ordering stable.
        for file_path in sorted(source_dir.glob("*")):
            if file_path.is_file() and file_path.suffix.lower() in [".txt", ".md"]:
                try:
                    with open(file_path, encoding="utf-8") as f:
                        content = f.read()
                        remaining = max_chars - total_chars
                        if remaining <= 0:
                            break
                        if len(content) > remaining:
                            content = content[:remaining]
                        contents.append(f"--- {file_path.name} ---\n{content}")
                        total_chars += len(content)
                except Exception as e:
                    logger.error("Failed to read file %s: %s", file_path.name, e)

        return "\n\n".join(contents)

    async def generate_overview(self, project_name: str) -> dict:
        """
        Generate a project overview with the configured text backend.

        Args:
            project_name: project identifier

        Returns:
            Generated overview dict with synopsis, genre, theme, world_setting, and generated_at
        """
        from .text_backends.base import TextGenerationRequest, TextTaskType
        from .text_generator import TextGenerator

        source_content = self._read_source_files(project_name)
        if not source_content:
            raise ValueError("The source directory is empty, so an overview cannot be generated")

        generator = await TextGenerator.create(TextTaskType.OVERVIEW, project_name)

        prompt = (
            "Analyze the following source material and produce a concise project overview in English. "
            "Summarize the main plot, genre, theme, and world setting.\n\n"
            f"{source_content}"
        )

        result = await generator.generate(
            TextGenerationRequest(
                prompt=prompt,
                response_schema=ProjectOverview,
            ),
            project_name=project_name,
        )
        response_text = result.text

        overview = ProjectOverview.model_validate_json(response_text)
        overview_dict = overview.model_dump()
        overview_dict["generated_at"] = datetime.now().isoformat()

        project = self.load_project(project_name)
        project["overview"] = overview_dict
        self.save_project(project_name, project)

        logger.info("Project overview generated and saved")
        return overview_dict
