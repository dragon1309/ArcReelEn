"""Pydantic models for generated scripts and prompts."""

from typing import Literal

from pydantic import BaseModel, Field

# ============ Enumerations ============

ShotType = Literal[
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

CameraMotion = Literal[
    "Static",
    "Pan Left",
    "Pan Right",
    "Tilt Up",
    "Tilt Down",
    "Zoom In",
    "Zoom Out",
    "Tracking Shot",
]


class Dialogue(BaseModel):
    """Dialogue item."""

    speaker: str = Field(description="Speaker name")
    line: str = Field(description="Dialogue line")


class Composition(BaseModel):
    """Composition metadata."""

    shot_type: ShotType = Field(description="Shot type")
    lighting: str = Field(description="Lighting description including source, direction, and atmosphere")
    ambiance: str = Field(description="Visible atmospheric details")


class ImagePrompt(BaseModel):
    """Storyboard-image prompt."""

    scene: str = Field(description="Scene description: character placement, expression, action, and environment")
    composition: Composition = Field(description="Composition metadata")


class VideoPrompt(BaseModel):
    """Video-generation prompt."""

    action: str = Field(description="Concrete action performed during the shot")
    camera_motion: CameraMotion = Field(description="Camera motion")
    ambiance_audio: str = Field(description="Diegetic in-scene audio only")
    dialogue: list[Dialogue] = Field(default_factory=list, description="Dialogue lines when present in the source")


class GeneratedAssets(BaseModel):
    """Generated asset state."""

    storyboard_image: str | None = Field(default=None, description="Storyboard image path")
    video_clip: str | None = Field(default=None, description="Video clip path")
    video_uri: str | None = Field(default=None, description="Video URI")
    status: Literal["pending", "storyboard_ready", "completed"] = Field(default="pending", description="Generation state")


# ============ Narration ============


class NarrationSegment(BaseModel):
    """Narration-mode segment."""

    segment_id: str = Field(description="Segment ID in E{episode}S{index} format")
    episode: int = Field(description="Episode number")
    duration_seconds: int = Field(ge=1, le=60, description="Segment duration in seconds")
    segment_break: bool = Field(default=False, description="Whether this starts a new scene block")
    novel_text: str = Field(description="Original novel text copied verbatim")
    characters_in_segment: list[str] = Field(description="Character names appearing in the segment")
    clues_in_segment: list[str] = Field(default_factory=list, description="Clue names appearing in the segment")
    image_prompt: ImagePrompt = Field(description="Storyboard image prompt")
    video_prompt: VideoPrompt = Field(description="Video prompt")
    transition_to_next: Literal["cut", "fade", "dissolve"] = Field(default="cut", description="Transition type")
    note: str | None = Field(default=None, description="User note excluded from generation")
    generated_assets: GeneratedAssets = Field(default_factory=GeneratedAssets, description="Generated asset state")


class NovelInfo(BaseModel):
    """Novel source metadata."""

    title: str = Field(description="Novel title")
    chapter: str = Field(description="Chapter title")


class NarrationEpisodeScript(BaseModel):
    """Narration-mode episode script."""

    episode: int = Field(description="Episode number")
    title: str = Field(description="Episode title")
    content_mode: Literal["narration"] = Field(default="narration", description="Content mode")
    duration_seconds: int = Field(default=0, description="Total duration in seconds")
    summary: str = Field(description="Episode summary")
    novel: NovelInfo = Field(description="Novel source metadata")
    segments: list[NarrationSegment] = Field(description="Segment list")


# ============ Drama ============


class DramaScene(BaseModel):
    """Drama-mode scene."""

    scene_id: str = Field(description="Scene ID in E{episode}S{index} format")
    duration_seconds: int = Field(default=8, ge=1, le=60, description="Scene duration in seconds")
    segment_break: bool = Field(default=False, description="Whether this starts a new scene block")
    scene_type: Literal["story", "establishing"] = Field(default="story", description="Scene type")
    characters_in_scene: list[str] = Field(description="Character names appearing in the scene")
    clues_in_scene: list[str] = Field(default_factory=list, description="Clue names appearing in the scene")
    image_prompt: ImagePrompt = Field(description="Storyboard image prompt")
    video_prompt: VideoPrompt = Field(description="Video prompt")
    transition_to_next: Literal["cut", "fade", "dissolve"] = Field(default="cut", description="Transition type")
    note: str | None = Field(default=None, description="User note excluded from generation")
    generated_assets: GeneratedAssets = Field(default_factory=GeneratedAssets, description="Generated asset state")


class DramaEpisodeScript(BaseModel):
    """Drama-mode episode script."""

    episode: int = Field(description="Episode number")
    title: str = Field(description="Episode title")
    content_mode: Literal["drama"] = Field(default="drama", description="Content mode")
    duration_seconds: int = Field(default=0, description="Total duration in seconds")
    summary: str = Field(description="Episode summary")
    novel: NovelInfo = Field(description="Novel source metadata")
    scenes: list[DramaScene] = Field(description="Scene list")
