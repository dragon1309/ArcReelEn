"""Prompt utility functions.

Provide helpers for converting structured prompt objects into YAML.
"""

import yaml

# Preset option definitions.
STYLES = ["Photographic", "Anime", "3D Animation"]

SHOT_TYPES = [
    "Extreme Close-up",
    "Close-up",
    "Medium Close-up",
    "Medium Shot",
    "Medium Long Shot",
    "Long Shot",
    "Extreme Long Shot",
    "Over-the-shoulder",
    "Point-of-view",
]

CAMERA_MOTIONS = [
    "Static",
    "Pan Left",
    "Pan Right",
    "Tilt Up",
    "Tilt Down",
    "Zoom In",
    "Zoom Out",
    "Tracking Shot",
]


def image_prompt_to_yaml(image_prompt: dict, project_style: str) -> str:
    """
    Convert a structured imagePrompt object into a YAML string.

    Args:
        image_prompt: Structured ``image_prompt`` object from a segment, for example:
            {
                "scene": "Scene description",
                "composition": {
                    "shot_type": "Shot type",
                    "lighting": "Lighting description",
                    "ambiance": "Ambiance description"
                }
            }
        project_style: Project-level style setting read from project.json.

    Returns:
        YAML string for the Gemini API.
    """
    ordered = {
        "Style": project_style,
        "Scene": image_prompt["scene"],
        "Composition": {
            "shot_type": image_prompt["composition"]["shot_type"],
            "lighting": image_prompt["composition"]["lighting"],
            "ambiance": image_prompt["composition"]["ambiance"],
        },
    }
    return yaml.dump(ordered, allow_unicode=True, default_flow_style=False, sort_keys=False)


def video_prompt_to_yaml(video_prompt: dict) -> str:
    """
    Convert a structured videoPrompt object into a YAML string.

    Args:
        video_prompt: Structured ``video_prompt`` object from a segment, for example:
            {
                "action": "Action description",
                "camera_motion": "Camera motion",
                "ambiance_audio": "Ambient audio description",
                "dialogue": [{"speaker": "Character name", "line": "Dialogue line"}]
            }

    Returns:
        YAML string for the Veo API.
    """
    dialogue = [{"Speaker": d["speaker"], "Line": d["line"]} for d in video_prompt.get("dialogue", [])]

    ordered = {
        "Action": video_prompt["action"],
        "Camera_Motion": video_prompt["camera_motion"],
        "Ambiance_Audio": video_prompt.get("ambiance_audio", ""),
    }

    # Add the Dialogue field only when dialogue exists.
    if dialogue:
        ordered["Dialogue"] = dialogue

    return yaml.dump(ordered, allow_unicode=True, default_flow_style=False, sort_keys=False)


def is_structured_image_prompt(image_prompt) -> bool:
    """
    Check whether image_prompt uses the structured object format.

    Args:
        image_prompt: The image_prompt field value.

    Returns:
        True for the structured dict format, False for the legacy string format.
    """
    return isinstance(image_prompt, dict) and "scene" in image_prompt


def is_structured_video_prompt(video_prompt) -> bool:
    """
    Check whether video_prompt uses the structured object format.

    Args:
        video_prompt: The video_prompt field value.

    Returns:
        True for the structured dict format, False for the legacy string format.
    """
    return isinstance(video_prompt, dict) and "action" in video_prompt


def validate_style(style: str) -> bool:
    """Return whether the style matches a preset option."""
    return style in STYLES


def validate_shot_type(shot_type: str) -> bool:
    """Return whether the shot type matches a preset option."""
    return shot_type in SHOT_TYPES


def validate_camera_motion(camera_motion: str) -> bool:
    """Return whether the camera motion matches a preset option."""
    return camera_motion in CAMERA_MOTIONS
