"""AI Gateway — provider-agnostic LLM abstraction with strategy pattern.

Never call Groq, Gemini, or any provider directly. Route all LLM
requests through this gateway. Providers are pluggable components
registered via a registry. The gateway handles:

  - Provider selection (by name or automatic chain)
  - Retry with exponential backoff
  - Automatic failover across providers
  - Streaming (for providers that support it)
  - Token accounting and cost estimation
  - Response caching with configurable TTL
  - Structured JSON extraction and validation
  - Latency tracking and logging

Usage::

    gateway = AIGateway.get_instance()
    response = await gateway.execute(
        messages=[{"role": "user", "content": "Hello"}],
        expect_json=True,
    )
    print(response.text)
"""

import asyncio
import hashlib
import json
import os

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.events import Event, EventBus, EventType
from app.core.exceptions import AIProviderError
from app.core.logger import get_logger

log = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_RETRIES = 3
DEFAULT_CACHE_TTL_SECONDS = 30
MAX_CACHE_SIZE = 200

# Rough cost per 1K tokens (USD) — used for cost tracking
_COST_PER_1K: dict[str, tuple[float, float]] = {
    'groq': (0.00015, 0.00060),       # Llama 70B pricing
    'gemini': (0.00010, 0.00040),      # Gemini Flash
    'openai': (0.00015, 0.00060),      # GPT-4o-mini
    'openrouter': (0.00015, 0.00060),
    'ollama': (0.0, 0.0),              # Local — free
}


class LLMProvider(str, Enum):
    """Supported LLM backends."""
    GROQ = 'groq'
    GEMINI = 'gemini'
    OPENROUTER = 'openrouter'
    OPENAI = 'openai'
    OLLAMA = 'ollama'


@dataclass
class LLMResponse:
    """Normalised response from any LLM provider."""
    text: str
    provider: LLMProvider
    model: str
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cached: bool = False
    raw: Optional[dict[str, Any]] = None


@dataclass
class ProviderConfig:
    """Runtime configuration for a single provider instance."""
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    priority: int = 0
    enabled: bool = True


class CacheEntry:
    def __init__(self, response: LLMResponse, expires_at: float) -> None:
        self.response = response
        self.expires_at = expires_at


# ── Base Provider (Strategy) ──────────────────────────────────────────


class BaseProvider(ABC):
    """Abstract base for all LLM providers."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost = 0.0
        self._call_count = 0
        self._fail_count = 0

    @property
    def name(self) -> LLMProvider:
        return self.config.provider

    @property
    def model(self) -> str:
        return self.config.model

    @abstractmethod
    async def execute(
        self,
        messages: list[dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        expect_json: bool = False,
    ) -> LLMResponse:
        """Send messages to the LLM and return a structured response."""
        ...

    async def stream(
        self,
        messages: list[dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from the LLM.

        Default implementation raises — override in subclasses that
        support streaming.
        """
        raise AIProviderError(
            provider=self.config.provider.value,
            message=f'{self.config.provider.value} does not support streaming via this gateway',
        )

    def record_call(self, input_tokens: int, output_tokens: int, cost: float) -> None:
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_cost += cost
        self._call_count += 1

    def record_failure(self) -> None:
        self._fail_count += 1

    def stats(self) -> dict[str, Any]:
        return {
            'provider': self.config.provider.value,
            'model': self.config.model,
            'calls': self._call_count,
            'failures': self._fail_count,
            'total_input_tokens': self._total_input_tokens,
            'total_output_tokens': self._total_output_tokens,
            'total_cost': round(self._total_cost, 6),
        }

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~4 chars per token for English."""
        return max(1, len(text) // 4)

    def _compute_cost(self, input_tokens: int, output_tokens: int) -> float:
        rates = _COST_PER_1K.get(self.config.provider.value, (0.0, 0.0))
        return (input_tokens / 1000) * rates[0] + (output_tokens / 1000) * rates[1]


# ── Concrete Providers ────────────────────────────────────────────────


class GroqProvider(BaseProvider):
    """Provider using the Groq SDK."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self._client is None:
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self.config.api_key)
        return self._client

    async def execute(
        self,
        messages: list[dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        expect_json: bool = False,
    ) -> LLMResponse:
        if not self.config.api_key:
            raise AIProviderError(provider='groq', message='API key not configured')

        client = self._get_client()
        start = time.monotonic()

        response = await client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature if temperature is not None else self.config.temperature,
        )

        latency = (time.monotonic() - start) * 1000
        content = response.choices[0].message.content or ''

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else self._estimate_tokens(str(messages))
        output_tokens = usage.completion_tokens if usage else self._estimate_tokens(content)
        cost = self._compute_cost(input_tokens, output_tokens)

        self.record_call(input_tokens, output_tokens, cost)

        return LLMResponse(
            text=content,
            provider=LLMProvider.GROQ,
            model=self.config.model,
            latency_ms=round(latency, 1),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost, 8),
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        if not self.config.api_key:
            raise AIProviderError(provider='groq', message='API key not configured')

        client = self._get_client()
        stream = await client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature if temperature is not None else self.config.temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ''
            if delta:
                yield delta


class GeminiProvider(BaseProvider):
    """Provider using the Google Generative AI SDK."""

    async def execute(
        self,
        messages: list[dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        expect_json: bool = False,
    ) -> LLMResponse:
        if not self.config.api_key:
            raise AIProviderError(provider='gemini', message='API key not configured')

        from google import genai
        from google.genai import types as gemini_types

        client = genai.Client(api_key=self.config.api_key)
        start = time.monotonic()

        contents: list[gemini_types.Content] = []
        system_text = ''
        for msg in messages:
            if msg['role'] == 'system':
                system_text += msg['content'] + '\n'
            elif msg['role'] == 'user':
                contents.append(gemini_types.Content(
                    role='user',
                    parts=[gemini_types.Part(text=msg['content'])],
                ))
            elif msg['role'] == 'assistant':
                contents.append(gemini_types.Content(
                    role='model',
                    parts=[gemini_types.Part(text=msg['content'])],
                ))

        gemini_config = gemini_types.GenerateContentConfig(
            system_instruction=system_text.strip() if system_text else None,
            max_output_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature if temperature is not None else self.config.temperature,
        )
        # genai.Client is synchronous — offload to thread to avoid blocking event loop
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=self.config.model,
            contents=contents,
            config=gemini_config,
        )

        latency = (time.monotonic() - start) * 1000
        content = response.text or ''

        input_tokens = self._estimate_tokens(str(messages))
        output_tokens = self._estimate_tokens(content)
        cost = self._compute_cost(input_tokens, output_tokens)

        self.record_call(input_tokens, output_tokens, cost)

        return LLMResponse(
            text=content,
            provider=LLMProvider.GEMINI,
            model=self.config.model,
            latency_ms=round(latency, 1),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost, 8),
        )


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI-compatible APIs (OpenAI, OpenRouter, etc.)."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    async def execute(
        self,
        messages: list[dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        expect_json: bool = False,
    ) -> LLMResponse:
        if not self.config.api_key:
            raise AIProviderError(provider=self.config.provider.value, message='API key not configured')

        client = self._get_client()
        start = time.monotonic()

        response = await client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature if temperature is not None else self.config.temperature,
        )

        latency = (time.monotonic() - start) * 1000
        content = response.choices[0].message.content or ''

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else self._estimate_tokens(str(messages))
        output_tokens = usage.completion_tokens if usage else self._estimate_tokens(content)
        cost = self._compute_cost(input_tokens, output_tokens)

        self.record_call(input_tokens, output_tokens, cost)

        return LLMResponse(
            text=content,
            provider=self.config.provider,
            model=self.config.model,
            latency_ms=round(latency, 1),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost, 8),
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        if not self.config.api_key:
            raise AIProviderError(provider=self.config.provider.value, message='API key not configured')

        client = self._get_client()
        stream = await client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature if temperature is not None else self.config.temperature,
            stream=True,
        )
        async for chunk in stream:
            choice = chunk.choices[0]
            if choice and choice.delta and choice.delta.content:
                yield choice.delta.content


class OpenRouterProvider(OpenAIProvider):
    """OpenRouter uses OpenAI-compatible API. Reuses OpenAI provider."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)

    async def execute(
        self,
        messages: list[dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        response = await super().execute(messages, max_tokens, temperature)
        response.provider = LLMProvider.OPENROUTER
        return response


class OllamaProvider(BaseProvider):
    """Provider for local Ollama instances."""

    async def execute(
        self,
        messages: list[dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        url = f'{(self.config.base_url or "http://localhost:11434").rstrip("/")}/api/chat'
        start = time.monotonic()

        async with httpx.AsyncClient(timeout=httpx.Timeout(self.config.timeout_seconds)) as client:
            response = await client.post(
                url,
                json={
                    'model': self.config.model,
                    'messages': messages,
                    'stream': False,
                    'options': {
                        'num_predict': max_tokens or self.config.max_tokens,
                        'temperature': temperature if temperature is not None else self.config.temperature,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

        latency = (time.monotonic() - start) * 1000
        content = data.get('message', {}).get('content', '') or ''

        input_tokens = self._estimate_tokens(str(messages))
        output_tokens = self._estimate_tokens(content)
        cost = 0.0  # local = free

        self.record_call(input_tokens, output_tokens, cost)

        return LLMResponse(
            text=content,
            provider=LLMProvider.OLLAMA,
            model=self.config.model,
            latency_ms=round(latency, 1),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        url = f'{(self.config.base_url or "http://localhost:11434").rstrip("/")}/api/chat'

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream(
                'POST',
                url,
                json={
                    'model': self.config.model,
                    'messages': messages,
                    'stream': True,
                    'options': {
                        'num_predict': max_tokens or self.config.max_tokens,
                        'temperature': temperature if temperature is not None else self.config.temperature,
                    },
                },
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get('done'):
                            break
                        content = data.get('message', {}).get('content', '')
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue


# ── Provider Registry ─────────────────────────────────────────────────

_ProviderT = type[BaseProvider]

_PROVIDER_REGISTRY: dict[LLMProvider, _ProviderT] = {
    LLMProvider.GROQ: GroqProvider,
    LLMProvider.GEMINI: GeminiProvider,
    LLMProvider.OPENAI: OpenAIProvider,
    LLMProvider.OPENROUTER: OpenRouterProvider,
    LLMProvider.OLLAMA: OllamaProvider,
}


def register_provider(provider_type: LLMProvider, provider_class: _ProviderT) -> None:
    """Register a custom provider implementation."""
    _PROVIDER_REGISTRY[provider_type] = provider_class


# ── AIGateway ─────────────────────────────────────────────────────────


class AIGateway:
    """Unified gateway for all LLM providers.

    Singleton (thread/async-safe via lock). Manages provider instances,
    failover chain, response caching, and cost tracking. All LLM calls
    in the system must go through this gateway.
    """

    _instance: Optional['AIGateway'] = None
    _init_lock = asyncio.Lock()

    def __new__(cls) -> 'AIGateway':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    @classmethod
    async def get_instance(cls) -> 'AIGateway':
        if cls._instance is None:
            async with cls._init_lock:
                if cls._instance is None:
                    instance = cls()
                    instance.__init__()
                    cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        if self._initialised:
            return
        self._initialised = True
        self._bus = EventBus.get_instance()
        self._providers: list[BaseProvider] = []
        self._named_providers: dict[LLMProvider, BaseProvider] = {}
        self._cache: dict[str, CacheEntry] = {}
        self._build_providers()

    def _build_providers(self) -> None:
        """Initialise providers from configuration."""
        configs = self._load_configs()
        for cfg in configs:
            provider_class = _PROVIDER_REGISTRY.get(cfg.provider)
            if provider_class is None:
                log.warning('unknown_provider_skipped', provider=cfg.provider.value)
                continue
            instance = provider_class(cfg)
            self._providers.append(instance)
            self._named_providers[cfg.provider] = instance

        log.info('gateway_initialised', providers=[p.name.value for p in self._providers])

    def _load_configs(self) -> list[ProviderConfig]:
        chain: list[ProviderConfig] = []

        log.info('gateway_load_configs', groq_key_set=bool(settings.groq_api_key), env_groq='GROQ_API_KEY' in os.environ)

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

        openai_key = getattr(settings, 'openai_api_key', None)
        if openai_key:
            chain.append(ProviderConfig(
                provider=LLMProvider.OPENAI,
                model=getattr(settings, 'openai_model', 'gpt-4o-mini'),
                api_key=openai_key,
                base_url='https://api.openai.com/v1',
                max_tokens=4096,
                temperature=0.7,
                priority=3,
            ))

        ollama_api_key = getattr(settings, 'ollama_api_key', None) or os.environ.get('OLLAMA_API_KEY')
        if ollama_api_key:
            chain.append(ProviderConfig(
                provider=LLMProvider.OLLAMA,
                model=getattr(settings, 'ollama_model', 'llama3'),
                api_key=ollama_api_key,
                base_url=getattr(settings, 'ollama_base_url', 'http://localhost:11434'),
                max_tokens=4096,
                temperature=0.7,
                priority=4,
            ))

        return sorted(chain, key=lambda p: p.priority)

    # ── Public API ─────────────────────────────────────────────────────

    async def execute(
        self,
        messages: list[dict[str, Any]],
        provider: Optional[LLMProvider] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        expect_json: bool = True,
        allow_failover: bool = True,
        use_cache: bool = True,
        cache_ttl: float = DEFAULT_CACHE_TTL_SECONDS,
    ) -> LLMResponse:
        """Execute an LLM call through the gateway.

        Args:
            messages: OpenAI-format message list.
            provider: Pin to a specific provider (uses chain if None).
            model: Override the model name.
            max_tokens: Max output tokens.
            temperature: Sampling temperature.
            expect_json: If True, validates and extracts JSON from response.
            allow_failover: Try fallback providers on failure.
            use_cache: Check cache before calling.
            cache_ttl: Cache TTL in seconds.

        Returns:
            Normalised LLMResponse.

        Raises:
            AIProviderError: If all providers fail.
        """
        cache_key = ''
        if use_cache:
            cache_key = self._make_cache_key(messages, provider, model, max_tokens, temperature)
            cached = self._cache.get(cache_key)
            if cached and cached.expires_at > time.time():
                log.debug('cache_hit', key=cache_key[:32])
                cached.response.cached = True
                return cached.response

        if provider is not None:
            instances = [self._named_providers.get(provider)]
        else:
            instances = list(self._providers)

        instances = [p for p in instances if p is not None]

        if not instances:
            raise AIProviderError(provider='none', message='No AI providers are configured')

        last_error: Optional[Exception] = None
        last_response: Optional[LLMResponse] = None

        for inst in instances:
            for attempt in range(1, DEFAULT_MAX_RETRIES + 1):
                try:
                    log.debug(
                        'gateway_call',
                        provider=inst.name.value,
                        model=model or inst.model,
                        attempt=attempt,
                    )

                    effective = model or inst.model
                    if effective != inst.model:
                        inst.config.model = effective

                    response = await inst.execute(
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        expect_json=expect_json,
                    )

                    if expect_json:
                        parsed = _extract_json(response.text)
                        if parsed is not None:
                            response.text = json.dumps(parsed, ensure_ascii=False)
                        elif response.text.strip():
                            log.warning(
                                'json_extract_failed',
                                provider=inst.name.value,
                                attempt=attempt,
                                preview=response.text[:200],
                            )
                            raise ValueError(
                                f'{inst.name.value} returned non-JSON response (attempt {attempt}): '
                                f'{response.text[:200]}'
                            )

                    log.info(
                        'gateway_success',
                        provider=inst.name.value,
                        model=response.model,
                        latency_ms=response.latency_ms,
                        tokens_in=response.input_tokens,
                        tokens_out=response.output_tokens,
                        cost=response.cost_usd,
                    )

                    if use_cache and cache_key:
                        self._cache[cache_key] = CacheEntry(response, time.time() + cache_ttl)
                        if len(self._cache) > MAX_CACHE_SIZE:
                            self._evict_cache()

                    return response

                except AIProviderError:
                    raise
                except Exception as exc:
                    last_error = exc
                    inst.record_failure()
                    log.warning(
                        'gateway_retry',
                        provider=inst.name.value,
                        attempt=attempt,
                        error=str(exc)[:120],
                    )
                    if attempt < DEFAULT_MAX_RETRIES:
                        await asyncio.sleep(1.5 ** attempt)

            if allow_failover and provider is None:
                log.info('gateway_failover', failed_provider=inst.name.value)
                await self._bus.publish_sync(
                    EventType.PROVIDER_FAILOVER,
                    data={
                        'failed_provider': inst.name.value,
                        'model': inst.model,
                    },
                    source='ai_gateway',
                )

        raise AIProviderError(
            provider='all',
            message=f'All providers failed. Last error: {last_error}',
            details={'total_providers': len(instances)},
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        provider: LLMProvider = LLMProvider.GROQ,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from an LLM provider.

        Supported: Groq, Ollama, OpenAI-compatible.
        """
        inst = self._named_providers.get(provider)
        if inst is None:
            raise AIProviderError(provider=provider.value, message=f'Provider {provider.value} not configured')

        if model and model != inst.model:
            inst.config.model = model

        async for token in inst.stream(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            yield token

    # ─── Cache ─────────────────────────────────────────────────────────

    def clear_cache(self) -> None:
        self._cache.clear()
        log.debug('gateway_cache_cleared')

    def _make_cache_key(
        self,
        messages: list[dict[str, Any]],
        provider: Optional[LLMProvider],
        model: Optional[str],
        max_tokens: Optional[int],
        temperature: Optional[float],
    ) -> str:
        raw = json.dumps({
            'messages': messages,
            'provider': provider.value if provider else 'auto',
            'model': model,
            'max_tokens': max_tokens,
            'temperature': temperature,
        }, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _evict_cache(self) -> None:
        now = time.time()
        # Build fresh dict: keep only non-expired entries, then oldest if over limit
        valid = {k: v for k, v in self._cache.items() if v.expires_at > now}
        if len(valid) > MAX_CACHE_SIZE:
            sorted_keys = sorted(valid.keys(), key=lambda k: valid[k].expires_at)
            for k in sorted_keys[:len(valid) - MAX_CACHE_SIZE]:
                del valid[k]
        self._cache = valid

    # ── Provider management ────────────────────────────────────────────

    def get_provider(self, provider: LLMProvider) -> Optional[BaseProvider]:
        return self._named_providers.get(provider)

    @property
    def available_providers(self) -> list[LLMProvider]:
        return list(self._named_providers.keys())

    def provider_stats(self) -> dict[str, Any]:
        return {p.name.value: p.stats() for p in self._providers}

    def overall_stats(self) -> dict[str, Any]:
        total_cost = sum(p.stats()['total_cost'] for p in self._providers)
        total_calls = sum(p.stats()['calls'] for p in self._providers)
        return {
            'total_calls': total_calls,
            'total_cost': round(total_cost, 6),
            'active_providers': len(self._providers),
            'cache_size': len(self._cache),
        }


# ── JSON Extraction ───────────────────────────────────────────────────


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    from app.utils.json_utils import extract_json as _shared_extract
    return _shared_extract(text)

