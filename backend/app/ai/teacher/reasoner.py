"""DEPRECATED — Unified LLM reasoner for all agents.

WARNING: This module is deprecated. All agents should use
``app.ai.gateway.AIGateway`` instead. This file exists only for
backward compatibility with the old ``brain.py``.

Supports multiple providers (Groq, OpenRouter, Gemini) with automatic
fallback, retry logic, JSON extraction, and streaming. Every agent in
the pipeline uses this module — never calls an LLM directly.
"""

import asyncio
import json

from collections.abc import AsyncGenerator
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.exceptions import AIProviderError
from app.core.logger import get_logger

log = get_logger(__name__)


class LLMProvider:
    """Available LLM backends."""
    GROQ = 'groq'
    OPENROUTER = 'openrouter'
    GEMINI = 'gemini'


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    from app.utils.json_utils import extract_json as _shared_extract
    return _shared_extract(text)


async def _call_groq(
    messages: list[dict[str, Any]],
    model: str,
    max_tokens: int,
    temperature: float,
    stream: bool = False,
) -> str:
    """Call the Groq API."""
    if not settings.groq_api_key:
        raise AIProviderError(provider='groq', message='GROQ_API_KEY is not configured')

    from groq import AsyncGroq

    client = AsyncGroq(api_key=settings.groq_api_key)
    kwargs = dict(model=model, messages=messages, max_tokens=max_tokens, temperature=temperature)

    if stream:
        collected: list[str] = []
        stream_resp = await client.chat.completions.create(**kwargs, stream=True)
        async for chunk in stream_resp:
            delta = chunk.choices[0].delta.content or ''
            collected.append(delta)
        return ''.join(collected)

    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ''


async def _call_openrouter(
    messages: list[dict[str, Any]],
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Call the OpenRouter API (OpenAI-compatible)."""
    if not settings.openrouter_api_key:
        raise AIProviderError(provider='openrouter', message='OPENROUTER_API_KEY is not configured')

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f'{settings.openrouter_base_url}/chat/completions',
            headers={
                'Authorization': f'Bearer {settings.openrouter_api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': model,
                'messages': messages,
                'max_tokens': max_tokens,
                'temperature': temperature,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content'] or ''


async def _call_gemini(
    messages: list[dict[str, Any]],
    model: str,
) -> str:
    """Call the Gemini API."""
    if not settings.gemini_api_key:
        raise AIProviderError(provider='gemini', message='GEMINI_API_KEY is not configured')

    from google import genai
    from google.genai import types as gemini_types

    client = genai.Client(api_key=settings.gemini_api_key)

    # Convert OpenAI-style messages to Gemini format
    contents: list[gemini_types.Content] = []
    system_text = ''
    for msg in messages:
        if msg['role'] == 'system':
            system_text += msg['content'] + '\n'
        elif msg['role'] == 'user':
            contents.append(gemini_types.Content(role='user', parts=[gemini_types.Part(text=msg['content'])]))
        elif msg['role'] == 'assistant':
            contents.append(gemini_types.Content(role='model', parts=[gemini_types.Part(text=msg['content'])]))

    config = gemini_types.GenerateContentConfig(
        system_instruction=system_text.strip() if system_text else None,
    )

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    return response.text or ''


async def reason(
    messages: list[dict[str, Any]],
    provider: str = LLMProvider.GROQ,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    expect_json: bool = True,
) -> dict[str, Any]:
    """Send messages to an LLM and return a parsed JSON response.

    Args:
        messages: OpenAI-format message list (system, user, assistant).
        provider: One of LLMProvider constants.
        model: Model override (uses default for provider if None).
        max_tokens: Max tokens for response.
        temperature: Sampling temperature.
        expect_json: If True, extracts JSON from the response.

    Returns:
        Parsed JSON dictionary.

    Raises:
        AIProviderError: If all retries or fallbacks fail.
    """
    model = model or {
        LLMProvider.GROQ: settings.groq_reasoning_model,
        LLMProvider.OPENROUTER: settings.openrouter_model,
        LLMProvider.GEMINI: settings.gemini_model,
    }.get(provider, settings.groq_reasoning_model)

    max_tokens = max_tokens or settings.groq_max_tokens
    temperature = temperature if temperature is not None else settings.groq_temperature

    last_error: Optional[Exception] = None

    for attempt in range(1, 4):
        try:
            log.info('llm_call', provider=provider, model=model, attempt=attempt)

            if provider == LLMProvider.GROQ:
                raw = await _call_groq(messages, model, max_tokens, temperature)
            elif provider == LLMProvider.OPENROUTER:
                raw = await _call_openrouter(messages, model, max_tokens, temperature)
            elif provider == LLMProvider.GEMINI:
                raw = await _call_gemini(messages, model)
            else:
                raise AIProviderError(provider=provider, message=f'Unknown provider: {provider}')

            if expect_json:
                parsed = _extract_json(raw)
                if parsed is None:
                    log.warning('llm_json_extract_failed', raw_preview=raw[:200])
                    raise AIProviderError(provider=provider, message='Failed to extract JSON from LLM response')

                return parsed

            return {'raw_text': raw}

        except AIProviderError:
            raise
        except Exception as exc:
            last_error = exc
            log.warning('llm_retry', provider=provider, attempt=attempt, error=str(exc))
            if attempt < 3:
                await asyncio.sleep(1.0 * attempt)

    raise AIProviderError(
        provider=provider,
        message=f'All {3} attempts failed',
        details={'last_error': str(last_error)},
    )


async def reason_stream(
    messages: list[dict[str, Any]],
    provider: str = LLMProvider.GROQ,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> AsyncGenerator[str, None]:
    """Stream a response from an LLM token by token.

    Only supports Groq for streaming currently.
    """
    model = model or settings.groq_reasoning_model
    max_tokens = max_tokens or settings.groq_max_tokens
    temperature = temperature if temperature is not None else settings.groq_temperature

    if provider != LLMProvider.GROQ:
        raise AIProviderError(provider=provider, message='Streaming is only supported via Groq')

    if not settings.groq_api_key:
        raise AIProviderError(provider='groq', message='GROQ_API_KEY is not configured')

    from groq import AsyncGroq

    client = AsyncGroq(api_key=settings.groq_api_key)
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content or ''
        if delta:
            yield delta



