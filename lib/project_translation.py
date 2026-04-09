"""Project language migration helpers."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from lib.data_validator import DataValidator
from lib.text_backends.base import TextGenerationRequest, TextTaskType
from lib.text_backends.prompts import (
    PROJECT_TRANSLATION_SYSTEM_PROMPT,
    build_project_translation_prompt,
)
from lib.text_generator import TextGenerator

_HAN_RE = re.compile(r"[\u3400-\u9fff]")
_MARKDOWN_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.DOTALL)
_SCENE_TYPE_MAP = {
    "剧情": "story",
    "动作": "story",
    "对话": "story",
    "story": "story",
    "空镜": "establishing",
    "establishing": "establishing",
}
_UNSUPPORTED_SOURCE_SUFFIXES = {".doc", ".docx"}
_TEXT_FILE_SUFFIXES = {".txt", ".md"}


class _TranslatedItem(BaseModel):
    id: str
    text: str


class _TranslationBatchResponse(BaseModel):
    items: list[_TranslatedItem]


@dataclass
class _PendingTextUpdate:
    item_id: str
    text: str
    apply: Callable[[str], None]


@dataclass
class ProjectMigrationReport:
    project_name: str
    backup_path: Path
    changed_files: list[str]


class ProjectTranslationError(RuntimeError):
    """Raised when project migration cannot be completed safely."""


class TranslationCollisionError(ProjectTranslationError):
    """Raised when translated keys would collide."""


def _contains_han(value: str) -> bool:
    return bool(_HAN_RE.search(value))


def _strip_fences(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        text = _MARKDOWN_FENCE_RE.sub("", text).strip()
    return text


def _chunk_text(text: str, *, max_chars: int = 4500) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""
    tokens = re.split(r"(\n\s*\n)", text)
    for token in tokens:
        if not token:
            continue
        if len(token) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(token):
                chunks.append(token[start : start + max_chars])
                start += max_chars
            continue
        if current and len(current) + len(token) > max_chars:
            chunks.append(current)
            current = token
        else:
            current += token
    if current:
        chunks.append(current)
    return chunks


def _normalize_scene_type(value: str | None) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return "story"
    return _SCENE_TYPE_MAP.get(normalized, "story")


def _build_glossary(char_map: dict[str, str], clue_map: dict[str, str]) -> str:
    lines: list[str] = []
    if char_map:
        lines.append("Character glossary:")
        lines.extend(f"- {source} => {target}" for source, target in char_map.items())
    if clue_map:
        lines.append("Clue glossary:")
        lines.extend(f"- {source} => {target}" for source, target in clue_map.items())
    return "\n".join(lines)


class ProjectTranslator:
    """Translate a Chinese-first project into the English-only schema."""

    def __init__(self, generator: TextGenerator, *, target_language: str = "en") -> None:
        self.generator = generator
        self.target_language = target_language

    @classmethod
    async def create(cls, *, target_language: str = "en") -> "ProjectTranslator":
        generator = await TextGenerator.create(TextTaskType.OVERVIEW)
        return cls(generator, target_language=target_language)

    async def migrate_project(
        self,
        project_dir: Path,
        *,
        include_source: bool = False,
        write: bool = True,
    ) -> ProjectMigrationReport:
        if self.target_language != "en":
            raise ProjectTranslationError("Only target_language='en' is supported.")

        project_dir = Path(project_dir).resolve()
        if not (project_dir / "project.json").exists():
            raise ProjectTranslationError(f"Missing project.json in {project_dir}")

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_root = project_dir.parent / ".language-migration-backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_dir = backup_root / f"{project_dir.name}-{timestamp}"
        temp_dir = project_dir.parent / f".{project_dir.name}.lang-migration-{timestamp}"

        shutil.copytree(project_dir, backup_dir, symlinks=True)
        shutil.copytree(project_dir, temp_dir, symlinks=True)

        try:
            changed_files = await self._translate_project_tree(temp_dir, include_source=include_source)

            validator = DataValidator(projects_root=str(temp_dir.parent))
            result = validator.validate_project_tree(temp_dir)
            if not result.valid:
                raise ProjectTranslationError(str(result))

            if write:
                self._swap_project_dir(project_dir, temp_dir, timestamp)
            else:
                shutil.rmtree(temp_dir)

            return ProjectMigrationReport(
                project_name=project_dir.name,
                backup_path=backup_dir,
                changed_files=sorted(changed_files),
            )
        except Exception:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def _swap_project_dir(self, project_dir: Path, temp_dir: Path, timestamp: str) -> None:
        archived_dir = project_dir.parent / f".{project_dir.name}.pre-language-{timestamp}"
        project_dir.rename(archived_dir)
        try:
            temp_dir.rename(project_dir)
        except Exception:
            if archived_dir.exists():
                archived_dir.rename(project_dir)
            raise
        else:
            shutil.rmtree(archived_dir, ignore_errors=True)

    async def _translate_project_tree(self, project_dir: Path, *, include_source: bool) -> set[str]:
        changed_files: set[str] = set()
        project_path = project_dir / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))

        project, char_map, clue_map = await self._translate_project_payload(project)
        glossary = _build_glossary(char_map, clue_map)
        project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        changed_files.add("project.json")

        scripts_dir = project_dir / "scripts"
        if scripts_dir.exists():
            for script_path in sorted(scripts_dir.glob("*.json")):
                script = json.loads(script_path.read_text(encoding="utf-8"))
                translated = await self._translate_script_payload(script, char_map=char_map, clue_map=clue_map, glossary=glossary)
                script_path.write_text(json.dumps(translated, ensure_ascii=False, indent=2), encoding="utf-8")
                changed_files.add(script_path.relative_to(project_dir).as_posix())

        drafts_dir = project_dir / "drafts"
        if drafts_dir.exists():
            for draft_path in sorted(drafts_dir.rglob("*")):
                if draft_path.is_file() and draft_path.suffix.lower() in _TEXT_FILE_SUFFIXES:
                    translated = await self._translate_document(
                        draft_path.read_text(encoding="utf-8"),
                        context=f"project draft document\n{glossary}".strip(),
                    )
                    draft_path.write_text(translated, encoding="utf-8")
                    changed_files.add(draft_path.relative_to(project_dir).as_posix())

        source_dir = project_dir / "source"
        if include_source and source_dir.exists():
            for source_path in sorted(source_dir.rglob("*")):
                if not source_path.is_file():
                    continue
                suffix = source_path.suffix.lower()
                if suffix in _UNSUPPORTED_SOURCE_SUFFIXES:
                    raise ProjectTranslationError(
                        f"Unsupported source file for in-place translation: {source_path.relative_to(project_dir).as_posix()}"
                    )
                if suffix in _TEXT_FILE_SUFFIXES:
                    translated = await self._translate_document(
                        source_path.read_text(encoding="utf-8"),
                        context=f"source novel text\n{glossary}".strip(),
                    )
                    source_path.write_text(translated, encoding="utf-8")
                    changed_files.add(source_path.relative_to(project_dir).as_posix())

        return changed_files

    async def _translate_project_payload(self, project: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
        project = json.loads(json.dumps(project))
        characters = project.get("characters", {})
        clues = project.get("clues", {})

        char_map = await self._translate_name_map(list(characters.keys()), label="character")
        clue_map = await self._translate_name_map(list(clues.keys()), label="clue")
        glossary = _build_glossary(char_map, clue_map)

        translated_characters: dict[str, Any] = {}
        for name, data in characters.items():
            new_name = char_map.get(name, name)
            translated_characters[new_name] = json.loads(json.dumps(data))
        project["characters"] = translated_characters

        translated_clues: dict[str, Any] = {}
        for name, data in clues.items():
            new_name = clue_map.get(name, name)
            translated_clues[new_name] = json.loads(json.dumps(data))
        project["clues"] = translated_clues

        pending: list[_PendingTextUpdate] = []
        self._queue_text_update(pending, project, "title")
        self._queue_text_update(pending, project, "style")
        self._queue_text_update(pending, project, "style_description")

        overview = project.get("overview")
        if isinstance(overview, dict):
            for key in ("synopsis", "genre", "theme", "world_setting"):
                self._queue_text_update(pending, overview, key)

        for episode in project.get("episodes", []):
            if isinstance(episode, dict):
                self._queue_text_update(pending, episode, "title")

        for data in project["characters"].values():
            if isinstance(data, dict):
                self._queue_text_update(pending, data, "description")
                self._queue_text_update(pending, data, "voice_style")

        for data in project["clues"].values():
            if isinstance(data, dict):
                self._queue_text_update(pending, data, "description")

        await self._apply_pending_updates(pending, context=f"project metadata\n{glossary}".strip())
        project["language"] = "en"
        return project, char_map, clue_map

    async def _translate_script_payload(
        self,
        script: dict[str, Any],
        *,
        char_map: dict[str, str],
        clue_map: dict[str, str],
        glossary: str,
    ) -> dict[str, Any]:
        script = json.loads(json.dumps(script))
        pending: list[_PendingTextUpdate] = []

        self._queue_text_update(pending, script, "title")
        self._queue_text_update(pending, script, "summary")

        novel = script.get("novel")
        if isinstance(novel, dict):
            self._queue_text_update(pending, novel, "title")
            self._queue_text_update(pending, novel, "chapter")

        if isinstance(script.get("characters"), dict):
            script["characters"] = {char_map.get(name, name): data for name, data in script["characters"].items()}
        if isinstance(script.get("clues"), dict):
            script["clues"] = {clue_map.get(name, name): data for name, data in script["clues"].items()}

        content_mode = script.get("content_mode", "narration")
        if content_mode == "narration":
            for index, segment in enumerate(script.get("segments", [])):
                self._rewrite_segment(segment, index=index, pending=pending, char_map=char_map, clue_map=clue_map)
        else:
            for index, scene in enumerate(script.get("scenes", [])):
                self._rewrite_scene(scene, index=index, pending=pending, char_map=char_map, clue_map=clue_map)

        await self._apply_pending_updates(pending, context=f"episode script\n{glossary}".strip())
        return script

    def _rewrite_segment(
        self,
        segment: dict[str, Any],
        *,
        index: int,
        pending: list[_PendingTextUpdate],
        char_map: dict[str, str],
        clue_map: dict[str, str],
    ) -> None:
        segment["characters_in_segment"] = [char_map.get(name, name) for name in segment.get("characters_in_segment", [])]
        segment["clues_in_segment"] = [clue_map.get(name, name) for name in segment.get("clues_in_segment", [])]
        self._queue_text_update(pending, segment, "novel_text")
        self._queue_text_update(pending, segment, "note")
        self._rewrite_prompt_fields(segment, pending, prefix=f"segments[{index}]", char_map=char_map)
        self._rewrite_legacy_scene_fields(segment, pending)

    def _rewrite_scene(
        self,
        scene: dict[str, Any],
        *,
        index: int,
        pending: list[_PendingTextUpdate],
        char_map: dict[str, str],
        clue_map: dict[str, str],
    ) -> None:
        scene["scene_type"] = _normalize_scene_type(scene.get("scene_type"))
        scene["characters_in_scene"] = [char_map.get(name, name) for name in scene.get("characters_in_scene", [])]
        scene["clues_in_scene"] = [clue_map.get(name, name) for name in scene.get("clues_in_scene", [])]
        self._queue_text_update(pending, scene, "title")
        self._queue_text_update(pending, scene, "note")
        self._rewrite_prompt_fields(scene, pending, prefix=f"scenes[{index}]", char_map=char_map)
        self._rewrite_legacy_scene_fields(scene, pending)

    def _rewrite_prompt_fields(
        self,
        item: dict[str, Any],
        pending: list[_PendingTextUpdate],
        *,
        prefix: str,
        char_map: dict[str, str],
    ) -> None:
        image_prompt = item.get("image_prompt")
        if isinstance(image_prompt, str):
            self._queue_text_update(pending, item, "image_prompt")
        elif isinstance(image_prompt, dict):
            self._queue_text_update(pending, image_prompt, "scene")
            composition = image_prompt.get("composition")
            if isinstance(composition, dict):
                self._queue_text_update(pending, composition, "lighting")
                self._queue_text_update(pending, composition, "ambiance")

        video_prompt = item.get("video_prompt")
        if isinstance(video_prompt, str):
            self._queue_text_update(pending, item, "video_prompt")
        elif isinstance(video_prompt, dict):
            self._queue_text_update(pending, video_prompt, "action")
            self._queue_text_update(pending, video_prompt, "ambiance_audio")
            for dialogue_index, dialogue in enumerate(video_prompt.get("dialogue", [])):
                if not isinstance(dialogue, dict):
                    continue
                speaker = dialogue.get("speaker")
                if isinstance(speaker, str) and speaker in char_map:
                    dialogue["speaker"] = char_map[speaker]
                else:
                    self._queue_text_update(pending, dialogue, "speaker")
                self._queue_text_update(pending, dialogue, "line")

    def _rewrite_legacy_scene_fields(self, item: dict[str, Any], pending: list[_PendingTextUpdate]) -> None:
        visual = item.get("visual")
        if isinstance(visual, dict):
            for key in ("description", "lighting", "mood"):
                self._queue_text_update(pending, visual, key)

        audio = item.get("audio")
        if isinstance(audio, dict):
            self._queue_text_update(pending, audio, "narration")
            sound_effects = audio.get("sound_effects")
            if isinstance(sound_effects, list):
                for idx, effect in enumerate(sound_effects):
                    if isinstance(effect, str) and _contains_han(effect):
                        item_id = f"pending-{len(pending)}"

                        def _apply(translated: str, *, target=sound_effects, target_index=idx) -> None:
                            target[target_index] = translated

                        pending.append(_PendingTextUpdate(item_id=item_id, text=effect, apply=_apply))

        dialogue = item.get("dialogue")
        if isinstance(dialogue, dict):
            self._queue_text_update(pending, dialogue, "speaker")
            self._queue_text_update(pending, dialogue, "text")
            self._queue_text_update(pending, dialogue, "emotion")

        self._queue_text_update(pending, item, "action")

    def _queue_text_update(self, pending: list[_PendingTextUpdate], container: dict[str, Any], key: str) -> None:
        value = container.get(key)
        if not isinstance(value, str):
            return
        stripped = value.strip()
        if not stripped or not _contains_han(stripped):
            return

        item_id = f"pending-{len(pending)}"

        def _apply(translated: str, *, target=container, target_key=key) -> None:
            target[target_key] = translated

        pending.append(_PendingTextUpdate(item_id=item_id, text=value, apply=_apply))

    async def _translate_name_map(self, names: list[str], *, label: str) -> dict[str, str]:
        translatable = [name for name in names if _contains_han(name)]
        if not translatable:
            return {name: name for name in names}

        items = [{"id": f"{label}-{index}", "text": name} for index, name in enumerate(translatable)]
        translations = await self._translate_items(
            items,
            context=f"{label} names. Return natural English names that can be used as canonical references.",
        )

        name_map = {name: name for name in names}
        translated_names: list[str] = []
        for index, original in enumerate(translatable):
            translated = translations[f"{label}-{index}"].strip()
            if not translated:
                raise ProjectTranslationError(f"Translated {label} name is empty for {original!r}")
            if _contains_han(translated):
                raise ProjectTranslationError(f"Translated {label} name is not English for {original!r}: {translated!r}")
            name_map[original] = translated
            translated_names.append(translated)

        normalized = [name.strip().casefold() for name in translated_names]
        if len(set(normalized)) != len(normalized):
            raise TranslationCollisionError(f"Translated {label} names would collide: {translated_names}")
        return name_map

    async def _apply_pending_updates(self, pending: list[_PendingTextUpdate], *, context: str) -> None:
        if not pending:
            return
        translations = await self._translate_items(
            [{"id": item.item_id, "text": item.text} for item in pending],
            context=context,
        )
        for item in pending:
            translated = translations[item.item_id]
            if _contains_han(translated):
                raise ProjectTranslationError(f"Translation output still contains Chinese text for item {item.item_id}")
            item.apply(translated)

    async def _translate_document(self, text: str, *, context: str) -> str:
        if not _contains_han(text):
            return text
        chunks = _chunk_text(text)
        translated_chunks: list[str] = []
        for index, chunk in enumerate(chunks):
            translations = await self._translate_items(
                [{"id": f"chunk-{index}", "text": chunk}],
                context=f"{context}\nChunk {index + 1} of {len(chunks)}",
            )
            translated = translations[f"chunk-{index}"]
            if _contains_han(translated):
                raise ProjectTranslationError(f"Translated document chunk {index} still contains Chinese text.")
            translated_chunks.append(translated)
        return "".join(translated_chunks)

    async def _translate_items(self, items: list[dict[str, str]], *, context: str) -> dict[str, str]:
        if not items:
            return {}

        translated: dict[str, str] = {}
        current_batch: list[dict[str, str]] = []
        current_chars = 0

        async def _flush_batch() -> None:
            nonlocal current_batch, current_chars
            if not current_batch:
                return
            prompt = build_project_translation_prompt(
                context=context,
                items=current_batch,
                target_language="English",
            )
            result = await self.generator.generate(
                TextGenerationRequest(
                    prompt=prompt,
                    response_schema=_TranslationBatchResponse,
                    system_prompt=PROJECT_TRANSLATION_SYSTEM_PROMPT,
                )
            )
            payload = _TranslationBatchResponse.model_validate_json(_strip_fences(result.text))
            batch_map = {item.id: item.text for item in payload.items}
            expected_ids = {item["id"] for item in current_batch}
            if set(batch_map) != expected_ids:
                raise ProjectTranslationError(
                    f"Translation response ids did not match request. Expected {expected_ids}, got {set(batch_map)}."
                )
            translated.update(batch_map)
            current_batch = []
            current_chars = 0

        for item in items:
            text = item["text"]
            if current_batch and (current_chars + len(text) > 6000 or len(current_batch) >= 20):
                await _flush_batch()
            current_batch.append(item)
            current_chars += len(text)
        await _flush_batch()
        return translated
