"""AI Gateway — provider-agnostic LLM abstraction layer.

Never call Groq, Gemini, or any provider directly. Route all LLM
requests through this gateway. It handles provider selection, retry
with exponential backoff, automatic failover, token accounting, and
structured JSON extraction.

Supports:
  - Groq (default, fastest)
  - Gemini (Google)
  - OpenRouter (unified API for 200+ models)
  - OpenAI (direct)
  - Ollama (local)

Configuration determines the active provider and fallback chain.
Providers are tried in order; if one fails the next is attempted.
"""

import asyncio
import json
import re
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.events import Event, EventBus, EventType
from app.core.exceptions import AIProviderError
from app.core.logger import get_logger

log = get_logger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM backends."""
    GROQ = 'groq'
    GEMINI = 'gemini'
    OPENROUTER = 'openrouter'
    OPENAI = 'openai'
    OLLAMA = 'ollama'


class LLMModel(str, Enum):
    """Curated model short-names mapped to provider-specific identifiers."""
    GROQ_LLAMA_70B = 'llama-3.3-70b-versatile'
    GROQ_LLAMA_SCOUT = 'meta-llama/llama-4-scout-17b-16e-instruct'
    GROQ_MIXTRAL = 'mixtral-8x7b-32768'
    GEMINI_FLASH = 'gemini-2.0-flash'
    GEMINI_PRO = 'gemini-2.0-pro-exp-02-05'
    OPENAI_GPT4O_MINI = 'gpt-4o-mini'
    OPENAI_GPT4O = 'gpt-4o'
    OPENROUTER_GPT4O_MINI = 'openai/gpt-4o-mini'
    OPENROUTER_CLAUDE_SONNET = 'anthropic/claude-3.5-sonnet'
    OLLAMA_LLAMA3 = 'llama3'


@dataclass
class LLMResponse:
    """Normalised response from any LLM provider."""
    text: str
    provider: LLMProvider
    model: str
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cached: bool = False
    raw: Optional[dict[str, Any]] = None


@dataclass
class ProviderConfig:
    """Runtime configuration for a single provider."""
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: int = 60
    priority: int = 0  # lower = tried first
    enabled: bool = True


class AIGateway:
    """Unified gateway for all LLM providers with automatic failover.

    Usage::

        gateway = AIGateway.get_instance()
        response = await gateway.reason(
            messages=[{'role': 'user', 'content': 'Hello'}],
            expect_json=True,
        )
        # response is an LLMResponse with parsed text
    """

    _instance: Optional['AIGateway'] = None

    def __new__(cls) -> 'AIGateway':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    @classmethod
    def get_instance(cls) -> 'AIGateway':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        if self._initialised:
            return
        self._initialised = True
        self._bus = EventBus.get_instance()
        self._providers: list[ProviderConfig] = []
        self._cache: dict[str, LLMResponse] = {}
        self._cache_max_size = 100
        self._failover_count: dict[str, int] = {}
        self._init_providers()

    def _init_providers(self) -> None:
        """Build the ordered provider list from settings."""
        chain: list[ProviderConfig] = []

        if settings.groq_api_key:
            chain.append(ProviderConfig(
                provider=LLMProvider.GROQ,
                model=settings.groq_reasoning_model,
                api_key=settings.groq_api_key,
                max_tokens=settings.groq_max_tokens,
                temperature=settings.groq_temperature,
                priority=0,
            ))

        if settings.gemini_api_key:
            chain.append(ProviderConfig(
                provider=LLMProvider.GEMINI,
                model=settings.gemini_model,
                api_key=settings.gemini_api_key,
                max_tokens=4096,
                temperature=0.7,
                priority=1,
            ))

        if settings.openrouter_api_key:
            chain.append(ProviderConfig(
                provider=LLMProvider.OPENROUTER,
                model=settings.openrouter_model,
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
                max_tokens=settings.openrouter_max_tokens,
                temperature=0.7,
                priority=2,
            ))

        # OpenAI — configured via optional env vars (not in settings yet)
        openai_key = settings.openai_api_key if hasattr(settings, 'openai_api_key') else None
        if openai_key:
            chain.append(ProviderConfig(
                provider=LLMProvider.OPENAI,
                model='gpt-4o-mini',
                api_key=openai_key,
                max_tokens=4096,
                temperature=0.7,
                priority=3,
            ))

        # Ollama — local, always enabled if URL is set
        ollama_url = getattr(settings, 'ollama_base_url', 'http://localhost:11434')
        chain.append(ProviderConfig(
            provider=LLMProvider.OLLAMA,
            model=getattr(settings, 'ollama_model', 'llama3'),
            base_url=ollama_url,
            max_tokens=4096,
            temperature=0.7,
            priority=4,
        ))

        self._providers = sorted(chain, key=lambda p: p.priority)

    # ── Public API ─────────────────────────────────────────────────────

    async def reason(
        self,
        messages: list[dict[str, Any]],
        provider: Optional[LLMProvider] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        expect_json: bool = True,
        allow_failover: bool = True,
    ) -> LLMResponse:
        """Send messages to an LLM and return a structured response.

        If *provider* is specified, only that provider is tried.
        Otherwise the full configured chain is attempted with failover.

        Args:
            messages: OpenAI-format message list.
            provider: Pin to a specific provider.
            model: Override the model name.
            max_tokens: Max output tokens.
            temperature: Sampling temperature.
            expect_json: If True, validates and extracts JSON from response.
            allow_failover: If True, try fallback providers on failure.

        Returns:
            Normalised LLMResponse with parsed text.

        Raises:
            AIProviderError: If all providers fail.
        """
        if provider:
            configs = [p for p in self._providers if p.provider == provider]
        else:
            configs = list(self._providers)

        if not configs:
            raise AIProviderError(provider='none', message='No AI providers are configured')

        last_error: Optional[Exception] = None

        for cfg in configs:
            if not cfg.enabled:
                continue

            effective_model = model or cfg.model
            effective_max_tokens = max_tokens or cfg.max_tokens
            effective_temp = temperature if temperature is not None else cfg.temperature

            for attempt in range(1, 4):
                try:
                    start = time.monotonic()
                    log.info('llm_call', provider=cfg.provider.value, model=effective_model, attempt=attempt)

                    raw_text = await self._call_provider(
                        provider=cfg.provider,
                        model=effective_model,
                        messages=messages,
                        max_tokens=effective_max_tokens,
                        temperature=effective_temp,
                        api_key=cfg.api_key,
                        base_url=cfg.base_url,
                    )

                    latency_ms = (time.monotonic() - start) * 1000

                    if expect_json:
                        parsed = _extract_json(raw_text)
                        if parsed is None:
                            log.warning('json_extract_failed', provider=cfg.provider.value, preview=raw_text[:150])
                            raise AIProviderError(
                                provider=cfg.provider.value,
                                message='Failed to extract JSON from response',
                            )
                        raw_text = json.dumps(parsed, ensure_ascii=False)

                    response = LLMResponse(
                        text=raw_text,
                        provider=cfg.provider,
                        model=effective_model,
                        latency_ms=round(latency_ms, 1),
                    )
                    log.info('llm_success', provider=cfg.provider.value, latency_ms=round(latency_ms, 1))
                    return response

                except AIProviderError:
                    raise
                except Exception as exc:
                    last_error = exc
                    self._failover_count[cfg.provider.value] = self._failover_count.get(cfg.provider.value, 0) + 1
                    log.warning('llm_retry', provider=cfg.provider.value, attempt=attempt, error=str(exc))
                    if attempt < 3:
                        await asyncio.sleep(1.5 ** attempt)

            if allow_failover:
                log.info('llm_failover', failed_provider=cfg.provider.value)
                await self._bus.publish_sync(
                    EventType.PROVIDER_FAILOVER,
                    data={
                        'failed_provider': cfg.provider.value,
                        'next_provider': configs[configs.index(cfg) + 1].provider.value
                        if configs.index(cfg) + 1 < len(configs) else 'none',
                    },
                    source='ai_gateway',
                )

        raise AIProviderError(
            provider='all',
            message=f'All {len(configs)} providers failed',
            details={'last_error': str(last_error)},
        )

    async def reason_stream(
        self,
        messages: list[dict[str, Any]],
        provider: LLMProvider = LLMProvider.GROQ,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a response from an LLM token by token.

        Only Groq and Ollama support streaming currently.
        """
        cfg = next((p for p in self._providers if p.provider == provider), None)
        if cfg is None:
            raise AIProviderError(provider=provider.value, message=f'Provider {provider.value} not configured')

        effective_model = model or cfg.model
        effective_max_tokens = max_tokens or cfg.max_tokens
        effective_temp = temperature if temperature is not None else cfg.temperature

        if provider == LLMProvider.GROQ:
            async for token in self._stream_groq(cfg.api_key, effective_model, messages, effective_max_tokens, effective_temp):
                yield token
        elif provider == LLMProvider.OLLAMA:
            async for token in self._stream_ollama(cfg.base_url, effective_model, messages):
                yield token
        else:
            raise AIProviderError(
                provider=provider.value,
                message=f'Streaming not supported for {provider.value}',
            )

    # ── Provider implementations ───────────────────────────────────────

    async def _call_provider(
        self,
        provider: LLMProvider,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
        api_key: Optional[str],
        base_url: Optional[str],
    ) -> str:
        if provider == LLMProvider.GROQ:
            return await self._call_groq(api_key, model, messages, max_tokens, temperature)
        elif provider == LLMProvider.GEMINI:
            return await self._call_gemini(api_key, model, messages)
        elif provider == LLMProvider.OPENROUTER:
            return await self._call_openai_compat(base_url, api_key, model, messages, max_tokens, temperature)
        elif provider == LLMProvider.OPENAI:
            return await self._call_openai_compat('https://api.openai.com/v1', api_key, model, messages, max_tokens, temperature)
        elif provider == LLMProvider.OLLAMA:
            return await self._call_ollama(base_url, model, messages)
        else:
            raise AIProviderError(provider=provider.value, message=f'Unknown provider: {provider.value}')

    async def _call_groq(
        self,
        api_key: Optional[str],
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
    ) -> str:
        if not api_key:
            raise AIProviderError(provider='groq', message='API key not configured')

        from groq import AsyncGroq
        client = AsyncGroq(api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ''

    async def _call_gemini(
        self,
        api_key: Optional[str],
        model: str,
        messages: list[dict[str, Any]],
    ) -> str:
        if not api_key:
            raise AIProviderError(provider='gemini', message='API key not configured')

        from google import genai
        from google.genai import types as gemini_types

        client = genai.Client(api_key=api_key)
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
        response = client.models.generate_content(model=model, contents=contents, config=config)
        return response.text or ''

    async def _call_openai_compat(
        self,
        base_url: Optional[str],
        api_key: Optional[str],
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
    ) -> str:
        if not api_key:
            raise AIProviderError(provider='openai_compat', message='API key not configured')

        url = f'{(base_url or "https://api.openai.com/v1").rstrip("/")}/chat/completions'
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json={'model': model, 'messages': messages, 'max_tokens': max_tokens, 'temperature': temperature},
            )
            resp.raise_for_status()
            data = resp.json()
            return data['choices'][0]['message']['content'] or ''

    async def _call_ollama(
        self,
        base_url: Optional[str],
        model: str,
        messages: list[dict[str, Any]],
    ) -> str:
        url = f'{(base_url or "http://localhost:11434").rstrip("/")}/api/chat'
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json={'model': model, 'messages': messages, 'stream': False})
            resp.raise_for_status()
            data = resp.json()
            return data['message']['content'] or ''

    # ── Streaming implementations ──────────────────────────────────────

    async def _stream_groq(
        self,
        api_key: Optional[str],
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
    ) -> AsyncGenerator[str, None]:
        if not api_key:
            raise AIProviderError(provider='groq', message='API key not configured')

        from groq import AsyncGroq
        client = AsyncGroq(api_key=api_key)
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

    async def _stream_ollama(
        self,
        base_url: Optional[str],
        model: str,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        url = f'{(base_url or "http://localhost:11434").rstrip("/")}/api/chat'
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream('POST', url, json={'model': model, 'messages': messages, 'stream': True}) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get('done'):
                            break
                        yield data.get('message', {}).get('content', '')
                    except json.JSONDecodeError:
                        continue

    # ── Cache management ───────────────────────────────────────────────

    def clear_cache(self) -> None:
        self._cache.clear()

    @property
    def failover_counts(self) -> dict[str, int]:
        return dict(self._failover_count)


# ── JSON extraction helper ─────────────────────────────────────────────


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """Extract the first JSON object from a string.

    Tries in order:
      1. Direct parse if text is a JSON object.
      2. Extract from ```json ... ``` fences.
      3. Find the first balanced { } block.
    """
    text = text.strip()
    if text.startswith('{') and text.endswith('}'):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    pass
    return None
