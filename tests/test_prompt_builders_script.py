from lib.prompt_builders_script import (
    _format_character_names,
    _format_clue_names,
    build_drama_prompt,
    build_narration_prompt,
)


class TestPromptBuildersScript:
    def test_formatters_emit_bullet_lists(self):
        assert _format_character_names({"A": {}, "B": {}}) == "- A\n- B"
        assert _format_clue_names({"Jade Pendant": {}, "Ancestral Hall": {}}) == "- Jade Pendant\n- Ancestral Hall"

    def test_build_narration_prompt_contains_dynamic_durations(self):
        prompt = build_narration_prompt(
            project_overview={"synopsis": "Story", "genre": "Mystery", "theme": "Truth", "world_setting": "Ancient"},
            style="Ancient court drama",
            style_description="cinematic",
            characters={"Jiang Yuehui": {}},
            clues={"Jade Pendant": {}},
            segments_md="E1S01 | Text",
            supported_durations=[4, 6, 8],
            default_duration=4,
            aspect_ratio="9:16",
        )
        assert "4, 6, 8" in prompt
        assert "default to 4 seconds" in prompt

    def test_build_narration_prompt_auto_duration(self):
        prompt = build_narration_prompt(
            project_overview={"synopsis": "Story", "genre": "Mystery", "theme": "Truth", "world_setting": "Ancient"},
            style="Ancient court drama",
            style_description="cinematic",
            characters={"Jiang Yuehui": {}},
            clues={"Jade Pendant": {}},
            segments_md="E1S01 | Text",
            supported_durations=[5, 10],
            default_duration=None,
            aspect_ratio="9:16",
        )
        assert "5, 10" in prompt
        assert "based on pacing" in prompt

    def test_build_drama_prompt_uses_dynamic_aspect_ratio(self):
        prompt = build_drama_prompt(
            project_overview={"synopsis": "Action", "genre": "Action", "theme": "Growth", "world_setting": "Near future"},
            style="Cyberpunk",
            style_description="high contrast",
            characters={"Lin": {}},
            clues={"Chip": {}},
            scenes_md="E1S01 | Chase",
            supported_durations=[4, 8, 12],
            default_duration=8,
            aspect_ratio="9:16",
        )
        assert "16:9 landscape composition" not in prompt
        assert "portrait composition" in prompt

    def test_build_drama_prompt_landscape(self):
        prompt = build_drama_prompt(
            project_overview={"synopsis": "Action", "genre": "Action", "theme": "Growth", "world_setting": "Near future"},
            style="Cyberpunk",
            style_description="high contrast",
            characters={"Lin": {}},
            clues={"Chip": {}},
            scenes_md="E1S01 | Chase",
            supported_durations=[4, 6, 8],
            default_duration=8,
            aspect_ratio="16:9",
        )
        assert "landscape composition" in prompt
