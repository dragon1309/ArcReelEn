"""Shared prompt builders for character, clue, and storyboard generation."""


def build_character_prompt(name: str, description: str, style: str = "", style_description: str = "") -> str:
    """Build a character-sheet image prompt."""
    style_part = f", {style}" if style else ""

    # 构建风格前缀
    style_prefix = ""
    if style_description:
        style_prefix = f"Visual style: {style_description}\n\n"

    return f"""{style_prefix}Professional character design reference{style_part}.

Full-body turnaround portrait of "{name}".

{description}

Composition requirements: a single full-body character, natural pose, facing the camera.
Background: clean light gray, no decorative elements.
Lighting: soft, even studio lighting with no harsh shadows.
Image quality: high definition, clear details, accurate colors."""


def build_clue_prompt(
    name: str, description: str, clue_type: str = "prop", style: str = "", style_description: str = ""
) -> str:
    """Build a clue reference prompt based on clue type."""
    if clue_type == "location":
        return build_location_prompt(name, description, style, style_description)
    else:
        return build_prop_prompt(name, description, style, style_description)


def build_prop_prompt(name: str, description: str, style: str = "", style_description: str = "") -> str:
    """Build a prop-style clue reference prompt."""
    style_suffix = f", {style}" if style else ""

    # 构建风格前缀
    style_prefix = ""
    if style_description:
        style_prefix = f"Visual style: {style_description}\n\n"

    return f"""{style_prefix}Professional prop design reference{style_suffix}.

Multi-angle presentation of the prop "{name}". {description}

Arrange three views horizontally on a clean light gray background: full front view on the left, a 45-degree side view in the middle to show volume, and a detail close-up on the right. Use soft, even studio lighting with high-definition detail and accurate color."""


def build_location_prompt(name: str, description: str, style: str = "", style_description: str = "") -> str:
    """Build a location-style clue reference prompt."""
    style_suffix = f", {style}" if style else ""

    # 构建风格前缀
    style_prefix = ""
    if style_description:
        style_prefix = f"Visual style: {style_description}\n\n"

    return f"""{style_prefix}Professional environment design reference{style_suffix}.

Visual reference for the signature location "{name}". {description}

Use a composition where the main frame occupies roughly three quarters of the image to show the overall environment and atmosphere, with a detail inset in the lower-right corner. Use soft natural lighting."""


def build_storyboard_suffix(content_mode: str = "narration", *, aspect_ratio: str | None = None) -> str:
    """Build the aspect-ratio suffix for storyboard prompts."""
    if aspect_ratio is None:
        ratio = "9:16" if content_mode == "narration" else "16:9"
    else:
        ratio = aspect_ratio
    if ratio == "9:16":
        return "Portrait composition."
    elif ratio == "16:9":
        return "Landscape composition."
    return ""


def build_style_prompt(project_data: dict) -> str:
    """Build the merged style prompt fragment from project metadata."""
    parts = []

    style = project_data.get("style", "")
    if style:
        parts.append(f"Style: {style}")

    style_description = project_data.get("style_description", "")
    if style_description:
        parts.append(f"Visual style: {style_description}")

    return "\n".join(parts)
