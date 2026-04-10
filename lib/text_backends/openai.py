"""OpenAI text-generation backend."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI, BadRequestError

from lib.openai_shared import OPENAI_RETRYABLE_ERRORS, create_openai_client
from lib.providers import PROVIDER_OPENAI
from lib.retry import with_retry_async
from lib.text_backends.base import (
    TextCapability,
    TextGenerationRequest,
    TextGenerationResult,
    resolve_schema,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.4-mini"


class OpenAITextBackend:
    """OpenAI text backend using the Chat Completions API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        # Disable SDK-native retries so this layer controls retry behavior.
        self._client = create_openai_client(api_key=api_key, base_url=base_url, max_retries=0)
        self._model = model or DEFAULT_MODEL
        self._capabilities: set[TextCapability] = {
            TextCapability.TEXT_GENERATION,
            TextCapability.STRUCTURED_OUTPUT,
            TextCapability.VISION,
        }

    @property
    def name(self) -> str:
        return PROVIDER_OPENAI

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[TextCapability]:
        return self._capabilities

    @with_retry_async(max_attempts=4, backoff_seconds=(2, 4, 8), retryable_errors=OPENAI_RETRYABLE_ERRORS)
    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        """Generate text with one retry loop around native and fallback paths.

        The flow is:
        1. Try native ``response_format``
        2. If the schema is incompatible, fall back to Instructor in the same attempt
        3. If a transient error occurs, retry the whole flow via the decorator
        """
        messages = _build_messages(request)
        kwargs: dict = {"model": self._model, "messages": messages}

        if request.response_schema:
            schema = resolve_schema(request.response_schema)
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": schema,
                },
            }

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            if request.response_schema and _is_schema_error(exc):
                logger.warning(
                    "Native response_format failed (%s); falling back to Instructor",
                    exc,
                )
                return await _instructor_fallback(self._client, self._model, request, messages)
            raise

        usage = response.usage
        return TextGenerationResult(
            text=response.choices[0].message.content or "",
            provider=PROVIDER_OPENAI,
            model=self._model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )


def _build_messages(request: TextGenerationRequest) -> list[dict]:
    """Convert ``TextGenerationRequest`` into OpenAI messages format."""
    messages: list[dict] = []

    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})

    # Build the user message.
    if request.images:
        from lib.image_backends.base import image_to_base64_data_uri

        content: list[dict] = []
        for img in request.images:
            if img.path:
                data_uri = image_to_base64_data_uri(img.path)
                content.append({"type": "image_url", "image_url": {"url": data_uri}})
            elif img.url:
                content.append({"type": "image_url", "image_url": {"url": img.url}})
        content.append({"type": "text", "text": request.prompt})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": request.prompt})

    return messages


_SCHEMA_ERROR_KEYWORDS = (
    "response_schema",
    "json_schema",
    "Unknown name",
    "Cannot find field",
    "Invalid JSON payload",
)


def _is_schema_error(exc: BaseException) -> bool:
    """Return whether an exception appears to be caused by schema incompatibility.

    Some OpenAI-compatible proxies wrap upstream schema failures in non-400
    errors, so we also inspect the error text for schema-related keywords.
    """
    if isinstance(exc, BadRequestError):
        return True
    # Proxies may wrap upstream schema errors in non-400 status codes.
    error_str = str(exc)
    return any(kw in error_str for kw in _SCHEMA_ERROR_KEYWORDS)


async def _instructor_fallback(
    client: AsyncOpenAI,
    model: str,
    request: TextGenerationRequest,
    messages: list[dict],
) -> TextGenerationResult:
    """Instructor fallback used when native ``response_format`` is unavailable."""
    from lib.text_backends.instructor_support import instructor_fallback_async

    return await instructor_fallback_async(
        client=client,
        model=model,
        messages=messages,
        response_schema=request.response_schema,
        provider=PROVIDER_OPENAI,
    )
