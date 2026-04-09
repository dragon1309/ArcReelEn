"""Prompt builders for narration and drama script generation."""

from __future__ import annotations


def _format_character_names(characters: dict) -> str:
    """Format character names as a bullet list."""
    return "\n".join(f"- {name}" for name in characters.keys())


def _format_clue_names(clues: dict) -> str:
    """Format clue names as a bullet list."""
    return "\n".join(f"- {name}" for name in clues.keys())


def _format_duration_constraint(supported_durations: list[int], default_duration: int | None) -> str:
    """Render the duration-selection rule."""
    durations_str = ", ".join(str(d) for d in supported_durations)
    if default_duration is not None:
        return f"Duration: choose from [{durations_str}] seconds, default to {default_duration} seconds"
    return f"Duration: choose from [{durations_str}] seconds based on pacing"


def _format_aspect_ratio_desc(aspect_ratio: str) -> str:
    """Return the composition hint for an aspect ratio."""
    if aspect_ratio == "9:16":
        return "portrait composition"
    if aspect_ratio == "16:9":
        return "landscape composition"
    return f"{aspect_ratio} composition"


def build_narration_prompt(
    project_overview: dict,
    style: str,
    style_description: str,
    characters: dict,
    clues: dict,
    segments_md: str,
    supported_durations: list[int] | None = None,
    default_duration: int | None = None,
    aspect_ratio: str = "9:16",
) -> str:
    """Build the narration-mode script-generation prompt."""
    character_names = list(characters.keys())
    clue_names = list(clues.keys())

    return f"""Your task is to create a storyboard-ready script for a short-form video adaptation. Follow every instruction carefully.

Important:
- All generated content must be written in English.
- Keep JSON keys and enum values exactly as requested.
- Preserve any quoted original source text exactly where the instructions say to copy it verbatim.

You will receive a story overview, visual style, character list, clue list, and segmented source passages.

For each segment, generate:
- image_prompt: the first-frame image-generation prompt in English
- video_prompt: the motion-and-audio video-generation prompt in English

<overview>
{project_overview.get("synopsis", "")}

Genre: {project_overview.get("genre", "")}
Theme: {project_overview.get("theme", "")}
World setting: {project_overview.get("world_setting", "")}
</overview>

<style>
Style: {style}
Description: {style_description}
</style>

<characters>
{_format_character_names(characters)}
</characters>

<clues>
{_format_clue_names(clues)}
</clues>

<segments>
{segments_md}
</segments>

The segments table contains one segment per line, including:
- Segment ID: format E{{episode}}S{{index}}
- Original novel text: must be copied verbatim into novel_text
- {_format_duration_constraint(supported_durations or [4, 6, 8], default_duration)}
- Whether dialogue is present: decide whether video_prompt.dialogue should be filled
- Whether this is a segment_break: if marked yes, set segment_break to true

For each segment, follow these rules:

a. novel_text: copy the source passage exactly as written. Do not paraphrase it.

b. characters_in_segment:
- List the character names that appear in the segment.
- Allowed values: [{", ".join(character_names)}]
- Include only characters that are explicitly mentioned or clearly implied.

c. clues_in_segment:
- List the clue names used in the segment.
- Allowed values: [{", ".join(clue_names)}]
- Include only clues that are explicitly mentioned or clearly implied.

d. image_prompt:
- scene: describe the visible frame in English with concrete on-screen detail only: character positions, poses, expressions, clothing, environment, and objects. Use {_format_aspect_ratio_desc(aspect_ratio)}. Keep it focused on a single renderable moment.
- composition.shot_type: choose one from (Extreme Close-up, Close-up, Medium Close-up, Medium Shot, Medium Long Shot, Long Shot, Extreme Long Shot, Over-the-shoulder, Point-of-view)
- composition.lighting: describe the exact light source, direction, and color temperature in English
- composition.ambiance: describe visible atmosphere or environmental effects in English, not abstract emotion words

e. video_prompt:
- action: describe one coherent, achievable action in English for the specified duration
- camera_motion: choose one from (Static, Pan Left, Pan Right, Tilt Up, Tilt Down, Zoom In, Zoom Out, Tracking Shot)
- ambiance_audio: describe only diegetic in-scene sound in English; no music, narration, or voice-over
- dialogue: use an array of {{speaker, line}} objects only when the source passage includes quoted speech. speaker must come from characters_in_segment.

f. segment_break: set to true if the segment table marks it as yes.

g. duration_seconds: use the segment duration from the table.

h. transition_to_next: always use "cut".

Goal: create vivid, specific, visually coherent prompts suitable for AI image and video generation while staying faithful to the source text."""


def build_drama_prompt(
    project_overview: dict,
    style: str,
    style_description: str,
    characters: dict,
    clues: dict,
    scenes_md: str,
    supported_durations: list[int] | None = None,
    default_duration: int | None = None,
    aspect_ratio: str = "16:9",
) -> str:
    """Build the drama-mode script-generation prompt."""
    character_names = list(characters.keys())
    clue_names = list(clues.keys())

    return f"""Your task is to create a storyboard-ready animated episode script. Follow every instruction carefully.

Important:
- All generated content must be written in English.
- Keep JSON keys and enum values exactly as requested.

You will receive a story overview, visual style, character list, clue list, and a scene breakdown.

For each scene, generate:
- image_prompt: the first-frame image-generation prompt in English
- video_prompt: the motion-and-audio video-generation prompt in English

<overview>
{project_overview.get("synopsis", "")}

Genre: {project_overview.get("genre", "")}
Theme: {project_overview.get("theme", "")}
World setting: {project_overview.get("world_setting", "")}
</overview>

<style>
Style: {style}
Description: {style_description}
</style>

<characters>
{_format_character_names(characters)}
</characters>

<clues>
{_format_clue_names(clues)}
</clues>

<scenes>
{scenes_md}
</scenes>

The scenes table contains one scene per line, including:
- Scene ID: format E{{episode}}S{{index}}
- Scene description: adapted dramatic scene content
- {_format_duration_constraint(supported_durations or [4, 6, 8], default_duration)}
- Scene type: story, action, dialogue, or similar narrative intent
- Whether this is a segment_break: if marked yes, set segment_break to true

For each scene, follow these rules:

a. characters_in_scene:
- List the character names that appear in the scene.
- Allowed values: [{", ".join(character_names)}]
- Include only characters that are explicitly mentioned or clearly implied.

b. clues_in_scene:
- List the clue names used in the scene.
- Allowed values: [{", ".join(clue_names)}]
- Include only clues that are explicitly mentioned or clearly implied.

c. image_prompt:
- scene: describe the visible frame in English with concrete on-screen detail only: character positions, poses, expressions, clothing, environment, and objects. Use {_format_aspect_ratio_desc(aspect_ratio)}.
- composition.shot_type: choose one from (Extreme Close-up, Close-up, Medium Close-up, Medium Shot, Medium Long Shot, Long Shot, Extreme Long Shot, Over-the-shoulder, Point-of-view)
- composition.lighting: describe the exact light source, direction, and color temperature in English
- composition.ambiance: describe visible atmosphere or environmental effects in English, not abstract emotion words

d. video_prompt:
- action: describe one coherent, achievable action in English for the specified duration
- camera_motion: choose one from (Static, Pan Left, Pan Right, Tilt Up, Tilt Down, Zoom In, Zoom Out, Tracking Shot)
- ambiance_audio: describe only diegetic in-scene sound in English; no music, narration, or voice-over
- dialogue: use an array of {{speaker, line}} objects for spoken lines. speaker must come from characters_in_scene.

e. segment_break: set to true if the scenes table marks it as yes.

f. duration_seconds: use the scene duration from the table.

g. scene_type: normalize to one of "story" or "establishing". Use "story" for dramatic, action, or dialogue scenes. Use "establishing" for empty or establishing shots.

h. transition_to_next: always use "cut".

Goal: create vivid, specific, visually coherent prompts suitable for AI image and video generation while matching the intended dramatic beat for {_format_aspect_ratio_desc(aspect_ratio)} presentation."""
