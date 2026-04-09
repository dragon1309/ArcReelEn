"""Text-generation prompt helpers."""

from __future__ import annotations

import json

STYLE_ANALYSIS_PROMPT = (
    "Analyze the visual style of this image. Describe the lighting, "
    "color palette, medium (e.g., oil painting, digital art, photography), "
    "texture, and overall mood. Do NOT describe the subject matter "
    "(e.g., people, objects) or specific content. Focus ONLY on the "
    "artistic style. Provide a concise comma-separated list of descriptors "
    "suitable for an image generation prompt."
)

PROJECT_TRANSLATION_SYSTEM_PROMPT = (
    "You are a careful software migration translator. Translate user-authored "
    "creative content into natural English while preserving structure, IDs, "
    "placeholders, Markdown syntax, file paths, JSON keys, code spans, and "
    "technical identifiers exactly as provided. Do not add commentary."
)


def build_project_translation_prompt(*, context: str, items: list[dict[str, str]], target_language: str = "English") -> str:
    """Build a structured translation prompt for batch content migration."""
    payload = json.dumps(items, ensure_ascii=False, indent=2)
    return (
        f"Translate each item to {target_language}.\n\n"
        "Rules:\n"
        "- Preserve the item id exactly.\n"
        "- Preserve Markdown structure, placeholders, inline code, URLs, and file paths.\n"
        "- Keep scene IDs, enum values, model IDs, provider IDs, and technical identifiers unchanged.\n"
        "- Return only JSON with shape {\"items\": [{\"id\": string, \"text\": string}]}.\n"
        f"- Context: {context}\n\n"
        f"Items:\n{payload}\n"
    )
