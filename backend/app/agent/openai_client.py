"""OpenAI chat-completions client implementing :class:`app.agent.schemas.LLMClient`."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import openai

from app.agent.schemas import LLMError, LLMResponse, Message, ToolCall, Usage
from app.logging_utils import redact

log = logging.getLogger(__name__)
EMBEDDING_MODEL = "text-embedding-3-small"


class OpenAIChatClient:
    """Thin adapter: our message/tool format is already OpenAI's, so this maps the response."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        max_retries: int = 2,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.model = model
        self._client = openai.AsyncOpenAI(
            api_key=api_key, timeout=timeout, max_retries=max_retries, http_client=http_client
        )

    async def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        try:
            completion = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                tools=tools,  # type: ignore[arg-type]
                tool_choice="auto",
                temperature=0,
            )
        except openai.APIStatusError as exc:
            log.warning("OpenAI API status error %s", exc.status_code)
            raise LLMError(redact(_status_message(exc))) from None
        except openai.APIConnectionError:
            raise LLMError("Could not reach the OpenAI API (network error or timeout).") from None
        except openai.OpenAIError as exc:
            raise LLMError(redact(f"OpenAI client error: {type(exc).__name__}")) from None

        if not completion.choices:
            raise LLMError("OpenAI returned no choices.")
        message = completion.choices[0].message
        calls = [
            ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments or "")
            for c in (message.tool_calls or [])
            if getattr(c, "type", "function") == "function"
        ]
        usage = Usage(
            prompt_tokens=completion.usage.prompt_tokens if completion.usage else 0,
            completion_tokens=completion.usage.completion_tokens if completion.usage else 0,
        )
        return LLMResponse(content=message.content, tool_calls=calls, usage=usage)


def _status_message(exc: openai.APIStatusError) -> str:
    match exc.status_code:
        case 401:
            return "OpenAI rejected the API key (401). Check OPENAI_API_KEY."
        case 403:
            return "OpenAI denied access to the model (403)."
        case 404:
            return "OpenAI model not found (404). Check OPENAI_MODEL."
        case 429:
            return "OpenAI rate limit or quota exceeded (429). Try again later."
        case code if code >= 500:
            return f"OpenAI server error ({code}). Try again later."
        case code:
            return f"OpenAI API error ({code})."


def make_openai_embedder(api_key: str, model: str = EMBEDDING_MODEL):
    """Synchronous embedder for :class:`app.datasheets.search.DatasheetIndex` (feature flag)."""
    client = openai.OpenAI(api_key=api_key, timeout=30, max_retries=2)

    def embed(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 256):
            batch = [t[:8000] for t in texts[start : start + 256]]
            response = client.embeddings.create(model=model, input=batch)
            vectors.extend(item.embedding for item in response.data)
        return vectors

    return embed
