import json
from pathlib import Path

import pytest

from lib.data_validator import DataValidator
from lib.project_translation import ProjectTranslationError, ProjectTranslator, TranslationCollisionError
from lib.text_backends.base import TextGenerationResult


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class _FakeTranslationGenerator:
    def __init__(self, translations: dict[str, str]) -> None:
        self._translations = translations

    async def generate(self, request):
        payload = json.loads(request.prompt.split("Items:\n", 1)[1])
        items = []
        for item in payload:
            items.append(
                {
                    "id": item["id"],
                    "text": self._translations.get(item["text"], item["text"]),
                }
            )
        return TextGenerationResult(
            text=json.dumps({"items": items}, ensure_ascii=False),
            provider="fake",
            model="fake-model",
        )


def _create_demo_project(project_dir: Path) -> None:
    project = {
        "title": "宫墙秘事",
        "content_mode": "drama",
        "style": "古风悬疑",
        "style_description": "冷色调",
        "characters": {
            "姜月茴": {
                "description": "女主",
                "character_sheet": "characters/jiang.png",
                "reference_image": "characters/refs/jiang-ref.png",
            }
        },
        "clues": {
            "玉佩": {
                "type": "prop",
                "description": "关键线索",
                "importance": "major",
                "clue_sheet": "clues/jade.png",
            }
        },
        "episodes": [
            {
                "episode": 1,
                "title": "第一集",
                "script_file": "scripts/episode_1.json",
            }
        ],
    }
    script = {
        "episode": 1,
        "title": "初入宫门",
        "summary": "玉佩现身",
        "content_mode": "drama",
        "scenes": [
            {
                "scene_id": "E1S01",
                "scene_type": "剧情",
                "duration_seconds": 8,
                "title": "庭院相遇",
                "characters_in_scene": ["姜月茴"],
                "clues_in_scene": ["玉佩"],
                "note": "她察觉异样",
                "image_prompt": "月下庭院，紧张对峙",
                "video_prompt": "镜头缓慢推进，衣袂翻飞",
                "generated_assets": {
                    "storyboard_image": "storyboards/E1S01.png",
                    "video_clip": "videos/E1S01.mp4",
                    "status": "completed",
                },
            }
        ],
    }

    _write_json(project_dir / "project.json", project)
    _write_json(project_dir / "scripts" / "episode_1.json", script)
    (project_dir / "drafts").mkdir(parents=True, exist_ok=True)
    (project_dir / "drafts" / "outline.md").write_text("草稿：玉佩第一次出现。", encoding="utf-8")
    (project_dir / "source").mkdir(parents=True, exist_ok=True)
    (project_dir / "source" / "chapter1.txt").write_text("第一章：她拾起玉佩。", encoding="utf-8")

    for relative_path in (
        "characters/jiang.png",
        "characters/refs/jiang-ref.png",
        "clues/jade.png",
        "storyboards/E1S01.png",
        "videos/E1S01.mp4",
    ):
        path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"asset")


class TestProjectTranslator:
    @pytest.mark.asyncio
    async def test_migrate_project_rewrites_content_and_preserves_paths(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "projects" / "demo"
        _create_demo_project(project_dir)

        translator = ProjectTranslator(
            _FakeTranslationGenerator(
                {
                    "姜月茴": "Jiang Yuehui",
                    "玉佩": "Jade Pendant",
                    "宫墙秘事": "Palace Wall Secrets",
                    "古风悬疑": "Ancient court mystery",
                    "冷色调": "Cool-toned cinematic style",
                    "第一集": "Episode 1",
                    "女主": "Lead protagonist",
                    "关键线索": "Key story clue",
                    "初入宫门": "Entering the Palace",
                    "玉佩现身": "The jade pendant appears",
                    "庭院相遇": "Courtyard encounter",
                    "她察觉异样": "She senses something is wrong",
                    "月下庭院，紧张对峙": "Moonlit courtyard, tense standoff",
                    "镜头缓慢推进，衣袂翻飞": "Slow push-in as robes flutter",
                    "草稿：玉佩第一次出现。": "Draft: the jade pendant appears for the first time.",
                    "第一章：她拾起玉佩。": "Chapter 1: she picks up the jade pendant.",
                }
            )
        )

        report = await translator.migrate_project(project_dir, include_source=True, write=True)

        migrated_project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
        migrated_script = json.loads((project_dir / "scripts" / "episode_1.json").read_text(encoding="utf-8"))

        assert report.project_name == "demo"
        assert report.backup_path.exists()
        assert "project.json" in report.changed_files
        assert "scripts/episode_1.json" in report.changed_files
        assert "drafts/outline.md" in report.changed_files
        assert "source/chapter1.txt" in report.changed_files

        assert migrated_project["language"] == "en"
        assert migrated_project["title"] == "Palace Wall Secrets"
        assert migrated_project["style"] == "Ancient court mystery"
        assert migrated_project["characters"] == {
            "Jiang Yuehui": {
                "description": "Lead protagonist",
                "character_sheet": "characters/jiang.png",
                "reference_image": "characters/refs/jiang-ref.png",
            }
        }
        assert migrated_project["clues"] == {
            "Jade Pendant": {
                "type": "prop",
                "description": "Key story clue",
                "importance": "major",
                "clue_sheet": "clues/jade.png",
            }
        }
        assert migrated_project["episodes"][0]["title"] == "Episode 1"

        scene = migrated_script["scenes"][0]
        assert migrated_script["title"] == "Entering the Palace"
        assert migrated_script["summary"] == "The jade pendant appears"
        assert scene["scene_type"] == "story"
        assert scene["title"] == "Courtyard encounter"
        assert scene["characters_in_scene"] == ["Jiang Yuehui"]
        assert scene["clues_in_scene"] == ["Jade Pendant"]
        assert scene["note"] == "She senses something is wrong"
        assert scene["image_prompt"] == "Moonlit courtyard, tense standoff"
        assert scene["video_prompt"] == "Slow push-in as robes flutter"
        assert scene["generated_assets"]["storyboard_image"] == "storyboards/E1S01.png"
        assert scene["generated_assets"]["video_clip"] == "videos/E1S01.mp4"

        assert (project_dir / "drafts" / "outline.md").read_text(encoding="utf-8") == (
            "Draft: the jade pendant appears for the first time."
        )
        assert (project_dir / "source" / "chapter1.txt").read_text(encoding="utf-8") == (
            "Chapter 1: she picks up the jade pendant."
        )

        validation = DataValidator(projects_root=str(tmp_path / "projects")).validate_project_tree(project_dir)
        assert validation.valid, str(validation)

    @pytest.mark.asyncio
    async def test_migrate_project_fails_on_name_collision(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "projects" / "demo"
        _write_json(
            project_dir / "project.json",
            {
                "title": "Demo",
                "content_mode": "narration",
                "style": "Anime",
                "characters": {
                    "阿丽丝": {"description": "hero"},
                    "爱丽丝": {"description": "heroine"},
                },
                "clues": {},
            },
        )

        translator = ProjectTranslator(
            _FakeTranslationGenerator(
                {
                    "阿丽丝": "Alice",
                    "爱丽丝": "Alice",
                }
            )
        )

        with pytest.raises(TranslationCollisionError):
            await translator.migrate_project(project_dir, write=True)

        project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
        assert set(project["characters"]) == {"阿丽丝", "爱丽丝"}

    @pytest.mark.asyncio
    async def test_migrate_project_rejects_unsupported_source_files(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "projects" / "demo"
        _write_json(
            project_dir / "project.json",
            {
                "title": "Demo",
                "content_mode": "narration",
                "style": "Anime",
                "characters": {},
                "clues": {},
            },
        )
        (project_dir / "source").mkdir(parents=True, exist_ok=True)
        (project_dir / "source" / "chapter1.docx").write_bytes(b"docx")

        translator = ProjectTranslator(_FakeTranslationGenerator({}))

        with pytest.raises(ProjectTranslationError, match="Unsupported source file"):
            await translator.migrate_project(project_dir, include_source=True, write=True)

        assert (project_dir / "project.json").exists()
