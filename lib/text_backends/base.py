"""Core interfaces and request/response models for text generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class TextCapability(StrEnum):
    """Capabilities supported by a text backend."""

    TEXT_GENERATION = "text_generation"
    STRUCTURED_OUTPUT = "structured_output"
    VISION = "vision"


class TextTaskType(StrEnum):
    """Text-generation task types."""

    SCRIPT = "script"
    OVERVIEW = "overview"
    STYLE_ANALYSIS = "style"


@dataclass
class ImageInput:
    """Image input used for vision-capable models."""

    path: Path | None = None
    url: str | None = None


@dataclass
class TextGenerationRequest:
    """Generic text-generation request. Unsupported fields may be ignored."""

    prompt: str
    response_schema: dict | type | None = None
    images: list[ImageInput] | None = None
    system_prompt: str | None = None


@dataclass
class TextGenerationResult:
    """Generic text-generation result."""

    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


def resolve_schema(schema: dict | type) -> dict:
    """Resolve ``response_schema`` into a plain JSON Schema dict without ``$ref``."""
    if isinstance(schema, type):
        schema = schema.model_json_schema()

    defs = schema.get("$defs", {})
    if not defs:
        return schema

    def _inline(obj, visited_refs=frozenset()):
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_name = obj["$ref"].split("/")[-1]
                if ref_name in visited_refs:
                    raise ValueError(f"Detected a cyclic reference in the schema: {ref_name}")
                resolved = _inline(defs[ref_name], visited_refs | {ref_name})
                extra = {k: v for k, v in obj.items() if k != "$ref"}
                return {**resolved, **extra} if extra else resolved
            return {k: _inline(v, visited_refs) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_inline(item, visited_refs) for item in obj]
        return obj

    result = _inline(schema)
    result.pop("$defs", None)
    return result


class TextBackend(Protocol):
    """Protocol implemented by text backends."""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def capabilities(self) -> set[TextCapability]: ...

    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult: ...
