from lib.prompt_builders import (
    build_character_prompt,
    build_clue_prompt,
    build_location_prompt,
    build_prop_prompt,
    build_storyboard_suffix,
    build_style_prompt,
)


class TestPromptBuilders:
    def test_build_character_prompt_includes_style_and_description(self):
        prompt = build_character_prompt(
            "姜月茴",
            "Black hair, calm expression.",
            style="Ancient court drama",
            style_description="Cinematic, low-key lighting",
        )
        assert "Visual style: Cinematic, low-key lighting" in prompt
        assert "Professional character design reference, Ancient court drama." in prompt
        assert "姜月茴" in prompt
        assert "Black hair, calm expression." in prompt

    def test_build_clue_prompt_dispatches_by_type(self):
        prop_prompt = build_clue_prompt("Jade Pendant", "Ancient and weathered", clue_type="prop", style="Realistic")
        location_prompt = build_clue_prompt("Ancestral Hall", "Dim interior", clue_type="location", style="Realistic")

        assert prop_prompt == build_prop_prompt("Jade Pendant", "Ancient and weathered", "Realistic", "")
        assert location_prompt == build_location_prompt("Ancestral Hall", "Dim interior", "Realistic", "")

    def test_build_storyboard_suffix_by_aspect_ratio(self):
        assert build_storyboard_suffix(aspect_ratio="9:16") == "Portrait composition."
        assert build_storyboard_suffix(aspect_ratio="16:9") == "Landscape composition."
        assert build_storyboard_suffix() == "Portrait composition."

    def test_build_style_prompt_combines_available_parts(self):
        project_data = {
            "style": "Anime",
            "style_description": "soft pastel, hand-drawn",
        }
        result = build_style_prompt(project_data)
        assert "Style: Anime" in result
        assert "Visual style: soft pastel, hand-drawn" in result

    def test_build_style_prompt_handles_empty_values(self):
        assert build_style_prompt({}) == ""
        assert build_style_prompt({"style": ""}) == ""
